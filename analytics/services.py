import json
import re
from google import genai
from django.conf import settings
from django.db.models import F, Sum
from inventory.models import IngredientStock, ConstraintParameter, Ingredient, BillOfMaterial
from analytics.models import PrescriptiveOutput, ExternalVariable, ChatbotLog
from django.utils import timezone
from datetime import timedelta
from pos.models import Transaction, TransactionItem
from accounts.models import Branch

# Cascade through stable supported models
AVAILABLE_GEMINI_MODELS = ['gemini-flash-lite-latest', 'gemini-flash-latest']

def _get_genai_client():
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key or api_key == 'placeholder_key':
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

def _call_gemini_api(prompt, preferred_models=AVAILABLE_GEMINI_MODELS):
    client = _get_genai_client()
    if not client:
        return None
    for model_name in preferred_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
        except Exception:
            continue
    return None

def _clean_json_text(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text

def _calculate_historical_ingredient_consumption(branch, days=30):
    """
    Reads actual historical transaction data over the given timeframe and
    computes average daily burn rate per ingredient based on Bill of Materials.
    """
    cutoff = timezone.now() - timedelta(days=days)
    txns = Transaction.objects.filter(
        branch=branch,
        transaction_status='Completed',
        transaction_date__gte=cutoff
    )
    if not txns.exists():
        # Fallback to all completed transactions if the 30-day window has limited seeded transactions
        txns = Transaction.objects.filter(branch=branch, transaction_status='Completed')
        days = 30

    consumption = {}
    boms = BillOfMaterial.objects.select_related('ingredient', 'product').all()
    prod_bom_map = {}
    for b in boms:
        prod_bom_map.setdefault(b.product_id, []).append(b)

    items = TransactionItem.objects.filter(transaction__in=txns).values('product_id').annotate(total_sold=Sum('quantity'))
    for item in items:
        p_id = item['product_id']
        qty_sold = item['total_sold'] or 0
        for bom in prod_bom_map.get(p_id, []):
            ing_id = bom.ingredient_id
            used = float(bom.quantity_required) * float(qty_sold)
            if ing_id not in consumption:
                consumption[ing_id] = {
                    'total_used': 0.0,
                    'daily_burn': 0.0,
                    'products': set()
                }
            consumption[ing_id]['total_used'] += used
            consumption[ing_id]['products'].add(bom.product.product_name)

    for ing_id, data in consumption.items():
        data['daily_burn'] = round(data['total_used'] / float(max(days, 1)), 2)
        data['products'] = list(data['products'])

    return consumption

def _get_active_events_context(branch=None):
    """
    Retrieves active or upcoming Local Events & Variables for operational context.
    """
    today = timezone.now().date()
    upcoming_limit = today + timedelta(days=21)
    
    events = ExternalVariable.objects.filter(
        is_active=True,
        end_date__gte=today - timedelta(days=7),
        start_date__lte=upcoming_limit
    ).order_by('start_date')
    
    if not events.exists():
        events = ExternalVariable.objects.filter(is_active=True).order_by('-start_date')[:5]

    event_list = []
    multiplier = 1.0
    impact_events = []
    for ev in events:
        status_label = "Ongoing" if ev.start_date <= today <= ev.end_date else ("Upcoming" if ev.start_date > today else "Recent")
        event_list.append({
            'Event': ev.name,
            'Type': ev.variable_type,
            'Impact': ev.impact_level,
            'Timeline': f"{ev.start_date} to {ev.end_date} ({status_label})",
            'Description': ev.description
        })
        if ev.impact_level == 'High':
            multiplier = max(multiplier, 1.25)
            impact_events.append(ev.name)
        elif ev.impact_level == 'Medium':
            multiplier = max(multiplier, 1.15)
            impact_events.append(ev.name)

    return event_list, multiplier, impact_events

def _clean_db_text(text):
    if not text:
        return ""
    # Strip characters outside BMP (Basic Multilingual Plane, i.e., > 0xFFFF) for MySQL utf8mb3 compatibility
    return re.sub(r'[^\u0000-\uFFFF]', '', str(text)).strip()

def _generate_rule_based_prescriptions(branch, low_stocks, hist_consumption=None, event_multiplier=1.0, impact_events=None):
    """
    Deterministic rule-based mathematical prescription based exclusively on
    historical daily burn rate, constraint bounds, and local event impact.
    """
    if hist_consumption is None:
        hist_consumption = _calculate_historical_ingredient_consumption(branch, days=30)
    if impact_events is None:
        _, event_multiplier, impact_events = _get_active_events_context(branch)

    output_ids = []
    for stock in low_stocks:
        ingredient = stock.ingredient
        constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).first()
        min_qty = float(constraint.min_order_quantity) if constraint else 0.0
        max_supplier_qty = float(constraint.max_order_quantity) if constraint else 9999.0
        capacity_limit = float(constraint.capacity_limit) if constraint else 9999.0
        lead_time = float(constraint.lead_time_days) if constraint and constraint.lead_time_days else 3.0
        
        current_stock = float(stock.quantity_available)
        threshold = float(stock.reorder_threshold)
        
        # Historical burn rate calculation
        ing_hist = hist_consumption.get(ingredient.ingredient_ID, {})
        daily_burn = ing_hist.get('daily_burn', 0.0)
        if daily_burn <= 0.0:
            daily_burn = max(round(threshold / 7.0, 2), 0.50) # Fallback baseline: threshold covers ~7 days
            
        days_remaining = round(current_stock / daily_burn, 1) if daily_burn > 0 else 0.0
        
        # Target: Lead time buffer + 12 days operational stock, adjusted for local events
        target_coverage_days = 12.0
        needed_operational = round((lead_time + target_coverage_days) * daily_burn * event_multiplier, 2)
        net_reorder = max(needed_operational - current_stock, min_qty)
        
        # Physical constraints
        room_available = max(0.0, capacity_limit - current_stock)
        bounded_qty = min(max(net_reorder, min_qty), max_supplier_qty, room_available)
        if bounded_qty <= 0:
            bounded_qty = max(min_qty, 1.0)
            
        cost_per_unit = float(ingredient.cost_per_unit)
        estimated_cost = round(bounded_qty * cost_per_unit, 2)
        coverage_days = round(bounded_qty / daily_burn, 1) if daily_burn > 0 else target_coverage_days
        
        event_clause = f" including a {int((event_multiplier - 1.0) * 100)}% demand surge for {', '.join(impact_events)}" if impact_events and event_multiplier > 1.0 else ""
        justification = (
            f"Historical daily burn rate is {daily_burn:.2f} {ingredient.measurement_unit}/day. "
            f"Current stock of {current_stock:.2f} {ingredient.measurement_unit} provides only {days_remaining:.1f} days of operational runway "
            f"(threshold: {threshold:.2f} {ingredient.measurement_unit}). "
            f"Prescribed order of {bounded_qty:.2f} {ingredient.measurement_unit} provides {coverage_days:.1f} days buffer{event_clause}, "
            f"strictly bounded within branch storage capacity ({capacity_limit:.2f} {ingredient.measurement_unit}). Estimated cost: ₱{estimated_cost:,.2f}."
        )
        
        record = PrescriptiveOutput.objects.create(
            branch=branch, ingredient=ingredient, constraint=constraint,
            output_type='Restock Prescription',
            recommendation=f"Procure {bounded_qty:.2f} {ingredient.measurement_unit} of {ingredient.ingredient_name} ({coverage_days:.1f} days operational buffer)",
            justification=_clean_db_text(justification), recommended_quantity=bounded_qty,
            estimated_cost=estimated_cost, status="Pending Review"
        )
        output_ids.append(record.prescriptive_output_ID)
        
    return {"status": "generated", "outputs": output_ids, "fallback": True}

def generate_restock_directive(branch):
    """
    Generates realistic, measurable prescriptive recommendations grounded strictly in
    historical consumption data, stock parameters, and active local events.
    """
    low_stocks = IngredientStock.objects.filter(branch=branch, quantity_available__lte=F('reorder_threshold'))
    if not low_stocks.exists():
        return {"status": "optimal", "message": "All inventory levels are sufficient."}
    
    # 1. Historical Consumption Telemetry
    hist_consumption = _calculate_historical_ingredient_consumption(branch, days=30)
    
    # 2. Local Events & Variables Context
    event_list, event_multiplier, impact_events = _get_active_events_context(branch)
    events_summary = json.dumps(event_list, indent=2) if event_list else "No active external events."
    
    data_pipeline = []
    for stock in low_stocks:
        ingredient = stock.ingredient
        constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).first()
        ing_hist = hist_consumption.get(ingredient.ingredient_ID, {})
        daily_burn = ing_hist.get('daily_burn', 0.0)
        if daily_burn <= 0.0:
            daily_burn = max(round(float(stock.reorder_threshold) / 7.0, 2), 0.50)
            
        days_left = round(float(stock.quantity_available) / daily_burn, 1)
        
        data_pipeline.append({
            'Ingredient': ingredient.ingredient_name,
            'Unit': ingredient.measurement_unit,
            'Current_Stock': float(stock.quantity_available),
            'Reorder_Threshold': float(stock.reorder_threshold),
            'Historical_Daily_Burn': daily_burn,
            'Days_Runway_Remaining': days_left,
            'Min_Supplier_Order': float(constraint.min_order_quantity) if constraint else 0.0,
            'Max_Supplier_Order': float(constraint.max_order_quantity) if constraint else 9999.0,
            'Storage_Capacity_Limit': float(constraint.capacity_limit) if constraint else 9999.0,
            'Lead_Time_Days': float(constraint.lead_time_days) if constraint and constraint.lead_time_days else 3.0,
            'Cost_Per_Unit': float(ingredient.cost_per_unit)
        })
    
    telemetry_lines = []
    for item in data_pipeline:
        telemetry_lines.append(
            f"- {item['Ingredient']}: Current Stock: {item['Current_Stock']:.2f} {item['Unit']}, "
            f"Reorder Threshold: {item['Reorder_Threshold']:.2f} {item['Unit']}, "
            f"Historical Daily Burn: {item['Historical_Daily_Burn']:.2f} {item['Unit']}/day, "
            f"Runway Remaining: {item['Days_Runway_Remaining']:.1f} days, "
            f"Supplier Limits: [Min: {item['Min_Supplier_Order']:.2f}, Max: {item['Max_Supplier_Order']:.2f}], "
            f"Storage Limit: {item['Storage_Capacity_Limit']:.2f} {item['Unit']}, "
            f"Cost/Unit: ₱{item['Cost_Per_Unit']:.2f}"
        )
    telemetry_summary = "\n".join(telemetry_lines) if telemetry_lines else "No low stock records."
    
    prompt = f"""
    You are the dedicated Sweet Box Supply Chain AI for the {branch.name} branch.
    Generate realistic, measurable restock prescriptions for the following low-stock ingredients.
    
    CRITICAL GROUNDING RULES:
    1. Base all calculations EXCLUSIVELY on the provided historical burn rates, current stock levels, and active local events.
    2. Do NOT invent ingredients, metrics, or arbitrary values.
    3. Ensure recommendations are concrete and measurable (quantified units, coverage days, estimated cost in PHP).
    4. Account for active local events (surge multiplier: {event_multiplier}x due to {', '.join(impact_events) if impact_events else 'standard seasonality'}).
    
    Active Local Events & Variables:
    {events_summary}
    
    Low-Stock Ingredients & Historical Telemetry:
    {telemetry_summary}
    
    Return ONLY a valid JSON array of objects with exact keys:
    - "ingredient": string
    - "recommended_qty": float
    - "estimated_cost": float
    - "coverage_days": float
    - "justification": string (must reference historical daily burn rate, days runway, and local event impact)
    Do not use markdown formatting like ```json.
    """
    
    try:
        raw_ai_text = _call_gemini_api(prompt)
        if not raw_ai_text:
            return _generate_rule_based_prescriptions(branch, low_stocks, hist_consumption, event_multiplier, impact_events)
        
        clean_text = _clean_json_text(raw_ai_text)
        ai_data = json.loads(clean_text)
        output_ids = []
        
        for item in ai_data:
            ingredient = Ingredient.objects.get(ingredient_name=item['ingredient'])
            constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).first()
            stock_record = IngredientStock.objects.filter(branch=branch, ingredient=ingredient).first()
            
            raw_qty = float(item['recommended_qty'])
            current_stock = float(stock_record.quantity_available) if stock_record else 0.0
            
            # HARD BOUNDING: Enforce physical capacity and supplier limits mathematically
            min_qty = float(constraint.min_order_quantity) if constraint else 0.0
            max_supplier_qty = float(constraint.max_order_quantity) if constraint else 9999.0
            capacity_limit = float(constraint.capacity_limit) if constraint else 9999.0
            
            room_available = max(0.0, capacity_limit - current_stock)
            absolute_max = min(max_supplier_qty, room_available)
            bounded_qty = min(max(raw_qty, min_qty), absolute_max)
            if bounded_qty <= 0:
                bounded_qty = max(min_qty, 1.0)
            
            cost_per_unit = float(ingredient.cost_per_unit)
            estimated_cost = round(bounded_qty * cost_per_unit, 2)
            
            justification = item.get('justification', '')
            if raw_qty != bounded_qty:
                justification = f"(System Auto-Bounded from {raw_qty} to {bounded_qty} to obey physical capacity constraints) " + justification
            
            coverage_days = item.get('coverage_days')
            cov_text = f" ({coverage_days:.1f} days operational buffer)" if coverage_days else ""
            
            rec_text = _clean_db_text(f"Procure {bounded_qty:.2f} {ingredient.measurement_unit} of {ingredient.ingredient_name}{cov_text}")
            just_text = _clean_db_text(justification)
            
            record = PrescriptiveOutput.objects.create(
                branch=branch, ingredient=ingredient, constraint=constraint,
                output_type='Restock Prescription',
                recommendation=rec_text,
                justification=just_text, recommended_quantity=bounded_qty,
                estimated_cost=estimated_cost, status="Pending Review"
            )
            output_ids.append(record.prescriptive_output_ID)
            
        return {"status": "generated", "outputs": output_ids}
    except Exception:
        # Graceful fallback to deterministic rule-based replenishment on AI quota/network failure
        return _generate_rule_based_prescriptions(branch, low_stocks, hist_consumption, event_multiplier, impact_events)

def is_sweetbox_related_query(query_text):
    """
    Checks if query is related to Sweet Box business domains:
    sales, revenue, inventory, ingredients, transactions, branches, staff, products, events.
    """
    q = query_text.lower().strip()
    
    # Common greetings are handled directly
    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings"}
    if q in greetings or q.rstrip("!?.") in greetings:
        return True
        
    sweetbox_keywords = [
        "sweet box", "sweetbox", "sale", "sales", "revenue", "profit", "turnover", "gmroi",
        "product", "products", "cake", "cakes", "pastry", "pastries", "coffee", "drink", "drinks",
        "inventory", "stock", "stocks", "ingredient", "ingredients", "bom", "bill of material",
        "branch", "branches", "ibaan", "padre garcia", "san jose", "sampaguita", "lipa",
        "san antonio", "cuenca", "transaction", "transactions", "pos", "order", "orders",
        "payment", "cash", "e-wallet", "gcash", "maya", "discount", "pwd", "senior",
        "kpi", "restock", "produce", "production", "transfer", "spoilage", "cost", "price",
        "event", "events", "holiday", "payday", "fiesta", "weather", "season", "trend",
        "performance", "target", "forecast", "demand", "summary", "report", "loss", "threshold",
        "sell", "selling", "seller", "sellers", "best", "top", "item", "items", "runway", "burn",
        "supply", "supplies", "store", "shop", "bakery", "kitchen", "margin", "customer", "customers",
        "volume", "business", "operations", "status", "lead time", "capacity"
    ]
    
    return any(kw in q for kw in sweetbox_keywords)

def _build_dynamic_sales_response(
    branch, user, user_query, total_rev, total_txns, avg_txn,
    sorted_prods, low_stocks, event_list, event_multiplier, impact_events,
    payment_methods, all_branches_data
):
    """
    Intelligent intent-based dynamic generator that formulates targeted, structured,
    and measurable operational answers for specific Sweet Box queries.
    """
    q = user_query.lower()
    
    # Intent 1: Best Sellers / Top Products / Cakes / Pastries / Beverage Sales
    prod_keywords = ['product', 'products', 'top', 'best', 'popular', 'cake', 'cakes', 'pastry', 'pastries', 'coffee', 'drink', 'sold', 'item', 'items', 'selling', 'seller']
    if any(k in q for k in prod_keywords) and not any(k in q for k in ['stock', 'ingredient', 'restock', 'raw']):
        if not sorted_prods:
            return f"📊 **Sweet Box Product Sales Analysis ({branch.name})**\n\nNo finished product sales are recorded for this branch in the current window."
        
        top_name, top_stats = sorted_prods[0]
        event_note = f" Note that demand is currently bolstered by {', '.join(impact_events)} ({int((event_multiplier - 1.0)*100)}% surge multiplier)." if impact_events else ""
        
        lines = [
            f"🏆 **Top-Performing Products — {branch.name}**\n",
            f"Our #1 best-selling product is **{top_name}** with **{top_stats['Quantity_Sold']} units sold**, generating **₱{top_stats['Revenue']:,.2f}** in revenue.{event_note}\n",
            "**Sales Rankings:**"
        ]
        for rank, (name, stats) in enumerate(sorted_prods[:7], start=1):
            share = round((stats['Revenue'] / max(total_rev, 1.0)) * 100, 1)
            lines.append(f"{rank}. **{name}**: {stats['Quantity_Sold']} units sold | ₱{stats['Revenue']:,.2f} ({share}% of branch revenue)")
            
        lines.append(f"\n💡 **Recommendation:** Prioritize kitchen batch production and maintain safety stock for top pastry and cake lines to prevent stockouts during peak afternoon demand.")
        return "\n".join(lines)

    # Intent 2: Inventory / Stock Levels / Low Stock / Restocks / Ingredients / Runway
    stock_keywords = ['stock', 'stocks', 'inventory', 'low', 'restock', 'ingredient', 'ingredients', 'supply', 'supplies', 'runway', 'burn', 'reorder', 'capacity', 'procure']
    if any(k in q for k in stock_keywords):
        if not low_stocks.exists():
            return (
                f"📦 **Sweet Box Inventory Status ({branch.name})**\n\n"
                f"✅ **All ingredient stock levels are optimal.** No ingredients are currently below their reorder threshold. "
                f"Continuous production is well-buffered."
            )
        
        lines = [
            f"⚠️ **Low-Stock & Supply Chain Watch — {branch.name}**\n",
            f"We have identified **{low_stocks.count()} ingredient(s)** currently operating below reorder thresholds:\n"
        ]
        for s in low_stocks[:6]:
            ing = s.ingredient
            qty = float(s.quantity_available)
            thresh = float(s.reorder_threshold)
            unit = ing.measurement_unit
            lines.append(f"- **{ing.ingredient_name}**: {qty:.2f} {unit} remaining (Reorder Threshold: {thresh:.2f} {unit}, Unit Cost: ₱{float(ing.cost_per_unit):,.2f})")
        
        event_clause = f" with active {', '.join(impact_events)} multiplying consumption" if impact_events else ""
        lines.append(f"\n💡 **Prescriptive Action:** Submit a restock directive through the Supply Chain module to replenish these lines{event_clause} and prevent production downtime.")
        return "\n".join(lines)

    # Intent 3: Branch Performance & Comparison
    branch_keywords = ['branch', 'branches', 'compare', 'comparison', 'ibaan', 'padre garcia', 'san jose', 'sampaguita', 'lipa', 'san antonio', 'cuenca', 'hub', 'network', 'all branches']
    if any(k in q for k in branch_keywords):
        total_network_rev = sum(b['revenue'] for b in all_branches_data)
        top_branch = all_branches_data[0] if all_branches_data else None
        
        lines = [
            f"🏢 **Sweet Box Multi-Branch Performance Comparison**\n",
            f"Total Network Revenue across all operational branches is **₱{total_network_rev:,.2f}**.\n"
        ]
        if top_branch:
            lines.append(f"🌟 **Leading Branch:** **{top_branch['name']}** with **₱{top_branch['revenue']:,.2f}** ({top_branch['transactions']} transactions).\n")
            
        lines.append("**Branch Rankings:**")
        for idx, b in enumerate(all_branches_data, start=1):
            hub_tag = " (Main Production Hub)" if b['is_hub'] else ""
            lines.append(f"{idx}. **{b['name']}{hub_tag}**: ₱{b['revenue']:,.2f} across {b['transactions']} transactions")
            
        lines.append(f"\n💡 **Operational Insight:** Ensure finished cake and pastry transfers from the Ibaan Main Hub are synchronized with satellite branches experiencing elevated foot traffic.")
        return "\n".join(lines)

    # Intent 4: Local Events & Variables / Demand Surge
    event_keywords = ['event', 'events', 'holiday', 'holidays', 'fiesta', 'weather', 'variable', 'variables', 'surge', 'traffic', 'multiplier', 'season']
    if any(k in q for k in event_keywords):
        if not event_list:
            return (
                f"📅 **Sweet Box Local Events Context ({branch.name})**\n\n"
                f"There are currently no active high-impact local events or weather disruptions registered in the system. "
                f"Operations and demand forecasting are proceeding under baseline seasonality."
            )
        
        lines = [
            f"📅 **Active Local Events & External Variables**\n",
            f"The system has identified **{len(event_list)} external factor(s)** influencing customer demand (Current Demand Multiplier: **{event_multiplier}x**):\n"
        ]
        for ev in event_list:
            lines.append(f"- **{ev['Event']}** ({ev['Type']}): {ev['Timeline']} — **Impact: {ev['Impact']}**. {ev['Description']}")
            
        lines.append(f"\n💡 **Preparation Strategy:** Increase bakery display quantities and ensure high inventory availability on peak festival/payday dates.")
        return "\n".join(lines)

    # Intent 5: Payment Methods (Cash vs E-Wallets)
    payment_keywords = ['payment', 'payments', 'cash', 'e-wallet', 'ewallet', 'gcash', 'maya', 'tender', 'online payment']
    if any(k in q for k in payment_keywords):
        lines = [
            f"💳 **Sweet Box Payment Methods Breakdown ({branch.name})**\n",
            f"Total branch transaction volume: **{total_txns} orders** (₱{total_rev:,.2f}):\n"
        ]
        if payment_methods:
            for method, amount in payment_methods.items():
                pct = round((amount / max(total_rev, 1.0)) * 100, 1)
                lines.append(f"- **{method}**: ₱{amount:,.2f} ({pct}% of revenue)")
        else:
            lines.append("- No payment method breakdowns recorded.")
            
        lines.append("\n💡 **Insight:** Digital payments (GCash/Maya) streamline checkout times during peak rush hours.")
        return "\n".join(lines)

    # Default Intent: Executive Sales & Operations Overview
    top_str = f"**Top Product:** {sorted_prods[0][0]} ({sorted_prods[0][1]['Quantity_Sold']} sold)" if sorted_prods else "No top product recorded"
    low_count = low_stocks.count()
    low_str = f"⚠️ {low_count} ingredient(s) low" if low_count > 0 else "✅ Inventory levels optimal"
    ev_str = f"Active local events ({', '.join(impact_events)}) applying {event_multiplier}x multiplier." if impact_events else "Baseline operations."

    return (
        f"📊 **Sweet Box Executive Operational Summary — {branch.name}**\n\n"
        f"- **Total Revenue:** ₱{total_rev:,.2f}\n"
        f"- **Completed Transactions:** {total_txns}\n"
        f"- **Average Order Value (AOV):** ₱{avg_txn:,.2f}\n"
        f"- {top_str}\n"
        f"- **Stock Health:** {low_str}\n"
        f"- **Context:** {ev_str}\n\n"
        f"How would you like to drill down further? You can ask about **top-selling products**, **branch comparisons**, **low stock ingredients**, or **event impacts**."
    )

def generate_sales_report(branch, user, user_query):
    """
    Answers sales and operational queries using only real historical telemetry and local events.
    Enforces scope limitation, hallucination prevention, and records all interactions in ChatbotLog.
    """
    q_strip = user_query.strip()
    q_lower = q_strip.lower()
    
    # 1. Handle Greetings
    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings"}
    if q_lower in greetings or q_lower.rstrip("!?.") in greetings:
        active_vars = ExternalVariable.objects.filter(is_active=True)
        event_note = f" We currently have {active_vars.count()} active local event(s) influencing customer traffic." if active_vars.exists() else ""
        reply = (
            f"Hello, {user.name}! Welcome to your Sweet Box AI Sales Analyst.{event_note} "
            f"I have synchronized multi-branch sales records, inventory stock levels, and event telemetry. "
            f"How can I assist you with your business decisions today?"
        )
        ChatbotLog.objects.create(
            branch=branch, 
            user=user, 
            query_text=_clean_db_text(user_query), 
            response_text=_clean_db_text(reply)
        )
        return reply

    # 2. Strict Scope Limitation
    if not is_sweetbox_related_query(user_query):
        reply = (
            "I am specifically calibrated to assist with Sweet Box enterprise operations, sales analytics, "
            "multi-branch performance, and inventory management. I cannot assist with topics outside Sweet Box. "
            "How can I help you with your Sweet Box business data today?"
        )
        ChatbotLog.objects.create(
            branch=branch, 
            user=user, 
            query_text=_clean_db_text(user_query), 
            response_text=_clean_db_text(reply)
        )
        return reply

    # 3. Gather Historical Sales Telemetry (Past 30 - 180 Days)
    recent_date = timezone.now() - timedelta(days=180)
    
    transactions = Transaction.objects.filter(
        branch=branch, 
        transaction_status='Completed',
        transaction_date__gte=recent_date
    )
    
    if not transactions.exists():
        transactions = Transaction.objects.filter(branch=branch, transaction_status='Completed')

    total_rev = transactions.aggregate(Sum('total_amount'))['total_amount__sum'] or 0.0
    total_txns = transactions.count()
    avg_txn = round(float(total_rev) / max(total_txns, 1), 2)
    
    data_pipeline = []
    payment_methods = {}
    for txn in transactions:
        pm = txn.payments.first()
        method_name = pm.payment_method if pm else 'Cash'
        payment_methods[method_name] = payment_methods.get(method_name, 0) + float(txn.total_amount)
        
        for item in txn.items.all():
            data_pipeline.append({
                'Product': item.product.product_name,
                'Category': item.product.category.category_name if item.product.category else 'General',
                'Quantity_Sold': item.quantity,
                'Revenue': float(item.subtotal)
            })
            
    product_stats = {}
    for item in data_pipeline:
        p_name = item['Product']
        if p_name not in product_stats:
            product_stats[p_name] = {'Quantity_Sold': 0, 'Revenue': 0.0}
        product_stats[p_name]['Quantity_Sold'] += item['Quantity_Sold']
        product_stats[p_name]['Revenue'] += item['Revenue']

    sorted_prods = []
    if not product_stats:
        summary_data = "No sales transaction records available in the selected window."
        top_products_data = "No product sales recorded."
    else:
        sorted_prods = sorted(product_stats.items(), key=lambda x: x[1]['Revenue'], reverse=True)[:10]
        top_products_lines = [f"- {name}: {stats['Quantity_Sold']} units sold, ₱{stats['Revenue']:,.2f} revenue" for name, stats in sorted_prods]
        top_products_data = "\n".join(top_products_lines)
        summary_data = f"Total Completed Transactions: {total_txns}\nTotal Revenue: ₱{float(total_rev):,.2f}\nAverage Order Value: ₱{avg_txn:,.2f}\nPayment Methods: {json.dumps(payment_methods)}"

    # 4. Multi-Branch Summary for Cross-Branch Context
    all_branches_data = []
    for b in Branch.objects.all():
        b_txns = Transaction.objects.filter(branch=b, transaction_status='Completed', transaction_date__gte=recent_date)
        if not b_txns.exists():
            b_txns = Transaction.objects.filter(branch=b, transaction_status='Completed')
        b_rev = b_txns.aggregate(Sum('total_amount'))['total_amount__sum'] or 0.0
        b_count = b_txns.count()
        all_branches_data.append({
            'name': b.name,
            'revenue': float(b_rev),
            'transactions': b_count,
            'is_hub': bool(b.main_hub or b.branch_ID == 1)
        })
    all_branches_data.sort(key=lambda x: x['revenue'], reverse=True)
    branch_comp_lines = [f"- {b['name']}{' (Main Hub)' if b['is_hub'] else ''}: ₱{b['revenue']:,.2f} ({b['transactions']} transactions)" for b in all_branches_data]
    multi_branch_summary = "\n".join(branch_comp_lines) if branch_comp_lines else "No multi-branch telemetry."

    # 5. Gather Inventory Telemetry
    low_stocks = IngredientStock.objects.filter(branch=branch, quantity_available__lte=F('reorder_threshold'))
    low_stock_summary = ", ".join([f"{s.ingredient.ingredient_name} ({s.quantity_available} {s.ingredient.measurement_unit} left, threshold: {s.reorder_threshold})" for s in low_stocks[:5]]) if low_stocks.exists() else "All ingredients are at optimal levels."

    # 6. Gather Local Events & Variables
    event_list, event_multiplier, impact_events = _get_active_events_context(branch)
    var_context = json.dumps(event_list, indent=2) if event_list else "No active external events or holidays."

    prompt = f"""
    You are the dedicated Sweet Box Enterprise AI Analyst for {user.name} at the {branch.name} branch.
    
    CRITICAL OPERATIONAL & HALLUCINATION PREVENTION RULES:
    1. Base your answer EXCLUSIVELY and STRICTLY on the historical data, inventory telemetry, branch comparisons, and local events provided below.
    2. DIRECT INTENT FOCUS: Directly and specifically address the user's question without defaulting to a broad generic summary.
       - If asking about top-selling products, cakes, or sales performance, detail the top products, quantities, and revenue share.
       - If asking about low stock, restocks, or ingredients, detail the low-stock items, burn rates, and supply runway.
       - If asking about branch comparisons or which branch sells most, detail the multi-branch performance metrics.
       - If asking about payment methods, break down cash vs digital wallets (GCash/Maya).
       - If asking about local events, explain how active holidays/festivals affect demand.
    3. Do NOT invent transactions, product names, or financial numbers not present in the records.
    4. If asked about information not in the telemetry, state clearly: "The requested data is not recorded in our current Sweet Box database records."
    5. CITE the Local Events & Variables whenever explaining customer demand trends, sales variations, or seasonal volume.
    6. Keep responses concise, professional, structured with markdown bolding and bullet points, and immediately actionable for enterprise leadership.
    
    ACTIVE LOCAL EVENTS & VARIABLES:
    {var_context}
    
    BRANCH FINANCIAL OVERVIEW ({branch.name}):
    {summary_data}
    
    ALL BRANCHES COMPARISON:
    {multi_branch_summary}
    
    TOP PRODUCTS SALES TELEMETRY:
    {top_products_data}
    
    INVENTORY STATUS ({branch.name}):
    Low-Stock Ingredients: {low_stock_summary}
    
    USER QUERY:
    "{user_query}"
    """
    
    reply = None
    try:
        reply = _call_gemini_api(prompt)
    except Exception:
        reply = None

    if not reply:
        # Intelligent intent-driven fallback
        reply = _build_dynamic_sales_response(
            branch=branch, user=user, user_query=user_query,
            total_rev=float(total_rev), total_txns=total_txns, avg_txn=avg_txn,
            sorted_prods=sorted_prods, low_stocks=low_stocks,
            event_list=event_list, event_multiplier=event_multiplier, impact_events=impact_events,
            payment_methods=payment_methods, all_branches_data=all_branches_data
        )

    # Always persist every query and response to ChatbotLog in the database
    ChatbotLog.objects.create(
        branch=branch, 
        user=user, 
        query_text=_clean_db_text(user_query), 
        response_text=_clean_db_text(reply)
    )
    
    return reply