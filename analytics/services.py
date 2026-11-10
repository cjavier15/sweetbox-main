import json
import re
from decimal import Decimal
from google import genai
from django.conf import settings
from django.db.models import F, Sum
from inventory.models import IngredientStock, ConstraintParameter, Ingredient, BillOfMaterial, ProductStock
from analytics.models import PrescriptiveOutput, ExternalVariable, ChatbotLog, ProductClassification
from django.utils import timezone
from datetime import timedelta
from pos.models import Transaction, TransactionItem, Product
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
        constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).order_by('-constraint_ID').first()
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

def _generate_satellite_prescriptions(branch):
    """
    Generates finished Cake & Pastry dispatch transfer recommendations from Ibaan Main Hub
    to the satellite branch based on low ProductStock and historical sales velocity.
    """
    low_prod_stocks = list(ProductStock.objects.filter(
        branch=branch,
        quantity_available__lte=F('reorder_threshold')
    ).select_related('product', 'product__category'))

    # If no items are strictly at or below threshold, check items with low quantity <= 5.0
    if not low_prod_stocks:
        low_prod_stocks = list(ProductStock.objects.filter(
            branch=branch,
            quantity_available__lte=5.0
        ).select_related('product', 'product__category'))

    if not low_prod_stocks:
        return {"status": "optimal", "message": f"All finished product display stock levels at {branch.name} are sufficient."}

    # 1. Historical Sales Velocity Telemetry (last 30 days)
    cutoff = timezone.now() - timedelta(days=30)
    txns = Transaction.objects.filter(
        branch=branch,
        transaction_status='Completed',
        transaction_date__gte=cutoff
    )
    if not txns.exists():
        txns = Transaction.objects.filter(branch=branch, transaction_status='Completed')

    items = TransactionItem.objects.filter(transaction__in=txns).values('product_id').annotate(total_sold=Sum('quantity'))
    velocity_map = {i['product_id']: round(float(i['total_sold']) / 30.0, 2) for i in items}

    # 2. Local Events & Variables Context
    event_list, event_multiplier, impact_events = _get_active_events_context(branch)

    # 3. Product Recipe Costs for estimated commissary cost
    boms = BillOfMaterial.objects.select_related('ingredient').all()
    recipe_costs = {}
    for b in boms:
        recipe_costs[b.product_id] = recipe_costs.get(b.product_id, 0.0) + (
            float(b.quantity_required) * float(b.ingredient.cost_per_unit)
        )

    output_ids = []
    data_pipeline = []
    target_coverage_days = 7.0

    for stock in low_prod_stocks:
        prod = stock.product
        constraint = ConstraintParameter.objects.filter(branch=branch, product=prod).order_by('-constraint_ID').first()
        current_stock = float(stock.quantity_available)
        threshold = float(stock.reorder_threshold)
        daily_vel = velocity_map.get(prod.product_ID, 0.0)
        if daily_vel <= 0.0:
            daily_vel = max(round(threshold / 5.0, 2), 0.50)

        days_runway = round(current_stock / daily_vel, 1) if daily_vel > 0 else 0.0
        if constraint:
            lead_time = float(constraint.lead_time_days or 2)
            cov_days = max(target_coverage_days, lead_time + 5.0)
            needed = round((cov_days * daily_vel * event_multiplier) - current_stock)
            min_qty = float(constraint.min_order_quantity)
            max_order = float(constraint.max_order_quantity)
            prod_limit = float(constraint.production_limit)
            cap_limit = float(constraint.capacity_limit)
            room_available = max(0.0, cap_limit - current_stock)
            upper_bound = min(max_order, prod_limit, room_available)
            recommended_qty = float(min(max(float(needed), min_qty), upper_bound))
            if recommended_qty <= 0:
                recommended_qty = max(min_qty, 1.0)
        else:
            cov_days = target_coverage_days
            needed = round((target_coverage_days * daily_vel * event_multiplier) - current_stock)
            recommended_qty = float(max(needed, 5.0))
            if recommended_qty > 50.0:
                recommended_qty = 50.0

        unit_cost = recipe_costs.get(prod.product_ID, float(prod.price) * 0.35)
        estimated_cost = round(recommended_qty * unit_cost, 2)

        data_pipeline.append({
            'product': prod,
            'constraint': constraint,
            'cov_days': cov_days,
            'current_stock': current_stock,
            'threshold': threshold,
            'daily_vel': daily_vel,
            'days_runway': days_runway,
            'recommended_qty': recommended_qty,
            'estimated_cost': estimated_cost,
            'unit_cost': unit_cost
        })

    # Try Gemini AI for satellite branch
    prompt = f"""
    You are the dedicated Sweet Box Supply Chain AI for the {branch.name} satellite branch.
    The business operates on a Hub-and-Spoke model where all raw materials and baking are centralized at Ibaan (Main Hub).
    Satellite branches carry finished Cakes & Pastries and receive dispatch transfers from Ibaan Commissary.
    
    Generate realistic, measurable dispatch transfer prescriptions from Ibaan Main Hub to {branch.name} for the following low finished product stocks:
    
    Active Local Events:
    {json.dumps(event_list, indent=2) if event_list else "No active external events."}
    
    Low-Stock Products & Sales Telemetry:
    """ + "\n".join([
        (
            f"- {d['product'].product_name}: Current Stock: {d['current_stock']:.0f} units, "
            f"Reorder Threshold: {d['threshold']:.0f} units, Daily Sales Velocity: {d['daily_vel']:.1f} units/day, "
            f"Runway: {d['days_runway']:.1f} days, Recommended Batch: {d['recommended_qty']:.0f} units, Unit Cost: ₱{d['unit_cost']:.2f}"
            + (
                f", Constraints: [MOQ: {float(d['constraint'].min_order_quantity):.2f}, "
                f"Max Order: {float(d['constraint'].max_order_quantity):.2f}, "
                f"Prod Limit: {float(d['constraint'].production_limit):.2f}, "
                f"Capacity: {float(d['constraint'].capacity_limit):.2f}, "
                f"Lead Time: {d['constraint'].lead_time_days}d]"
                if d.get('constraint') else ""
            )
        )
        for d in data_pipeline
    ]) + """
    
    Return ONLY a valid JSON array of objects with exact keys:
    - "product": string
    - "recommended_qty": float
    - "estimated_cost": float
    - "coverage_days": float
    - "justification": string (must reference sales velocity, remaining runway, Ibaan commissary dispatch, and event context)
    Do not use markdown formatting like ```json.
    """

    try:
        raw_ai_text = _call_gemini_api(prompt)
        if raw_ai_text:
            clean_text = _clean_json_text(raw_ai_text)
            ai_data = json.loads(clean_text)
            pipeline_by_prod_id = {d['product'].product_ID: d for d in data_pipeline}
            for item in ai_data:
                prod_obj = Product.objects.filter(product_name=item['product']).first()
                if not prod_obj:
                    continue
                d_info = pipeline_by_prod_id.get(prod_obj.product_ID)
                constraint = d_info['constraint'] if d_info else ConstraintParameter.objects.filter(branch=branch, product=prod_obj).order_by('-constraint_ID').first()
                qty = float(item['recommended_qty'])
                if constraint:
                    curr_s = d_info['current_stock'] if d_info else 0.0
                    min_q = float(constraint.min_order_quantity)
                    max_q = float(constraint.max_order_quantity)
                    prod_lim = float(constraint.production_limit)
                    cap_lim = float(constraint.capacity_limit)
                    room_avail = max(0.0, cap_lim - curr_s)
                    qty = float(min(max(qty, min_q), max_q, prod_lim, room_avail))
                    if qty <= 0:
                        qty = max(min_q, 1.0)
                elif qty <= 0:
                    qty = 5.0
                cost = float(item.get('estimated_cost', qty * recipe_costs.get(prod_obj.product_ID, float(prod_obj.price) * 0.35)))
                rec_text = _clean_db_text(f"Dispatch transfer {int(qty)} units of {prod_obj.product_name} from Ibaan (Main Hub) to {branch.name}")
                just_text = _clean_db_text(item.get('justification', ''))

                record = PrescriptiveOutput.objects.create(
                    branch=branch,
                    product=prod_obj,
                    constraint=constraint,
                    output_type='Dispatch Transfer Prescription',
                    recommendation=rec_text,
                    justification=just_text,
                    recommended_quantity=Decimal(str(qty)),
                    estimated_cost=Decimal(str(round(cost, 2))),
                    status="Pending Review"
                )
                output_ids.append(record.prescriptive_output_ID)
            if output_ids:
                return {"status": "generated", "outputs": output_ids}
    except Exception:
        pass # Fallback to deterministic rule-based below

    # Deterministic rule-based satellite dispatch prescription
    event_clause = f" accounting for {', '.join(impact_events)} ({int((event_multiplier - 1.0) * 100)}% demand surge)" if impact_events and event_multiplier > 1.0 else ""
    for d in data_pipeline:
        prod = d['product']
        constraint = d.get('constraint')
        qty = d['recommended_qty']
        cost = d['estimated_cost']
        cov_d = d.get('cov_days', target_coverage_days)
        cap_clause = f", bounded within storage capacity ({float(constraint.capacity_limit):.2f} units)" if constraint else ""
        justification = (
            f"Historical sales velocity is {d['daily_vel']:.1f} units/day at {branch.name}. "
            f"Current display stock of {d['current_stock']:.0f} units provides only {d['days_runway']:.1f} days runway "
            f"(threshold: {d['threshold']:.0f} units). "
            f"Recommended dispatch transfer of {int(qty)} units from Ibaan Commissary secures a {cov_d:.0f}-day sales buffer{event_clause}{cap_clause}. "
            f"Estimated commissary transfer cost: ₱{cost:,.2f}."
        )
        record = PrescriptiveOutput.objects.create(
            branch=branch,
            product=prod,
            constraint=constraint,
            output_type='Dispatch Transfer Prescription',
            recommendation=f"Dispatch transfer {int(qty)} units of {prod.product_name} from Ibaan (Main Hub) to {branch.name}",
            justification=_clean_db_text(justification),
            recommended_quantity=Decimal(str(qty)),
            estimated_cost=Decimal(str(cost)),
            status="Pending Review"
        )
        output_ids.append(record.prescriptive_output_ID)

    return {"status": "generated", "outputs": output_ids, "fallback": True}

def generate_restock_directive(branch):
    """
    Generates realistic, measurable prescriptive recommendations grounded strictly in
    historical consumption data, stock parameters, and active local events.
    Enforces Hub-and-Spoke architecture:
    - Satellite branches: Cake & Pastry dispatch transfer recommendations from Ibaan Main Hub
    - Ibaan (Main Hub): Raw ingredient replenishment and commissary kitchen production batch targets
    """
    is_satellite = not bool(branch.main_hub or branch.branch_ID == 1 or 'ibaan' in branch.name.lower())
    if is_satellite:
        return _generate_satellite_prescriptions(branch)

    low_stocks = IngredientStock.objects.filter(branch=branch, quantity_available__lte=F('reorder_threshold'))
    
    # Also check low finished goods at Ibaan Commissary
    low_prod_stocks = ProductStock.objects.filter(
        branch=branch,
        quantity_available__lte=F('reorder_threshold')
    ).select_related('product')

    if not low_stocks.exists() and not low_prod_stocks.exists():
        return {"status": "optimal", "message": "All inventory levels are sufficient."}
    
    # 1. Historical Consumption Telemetry
    hist_consumption = _calculate_historical_ingredient_consumption(branch, days=30)
    
    # 2. Local Events & Variables Context
    event_list, event_multiplier, impact_events = _get_active_events_context(branch)
    events_summary = json.dumps(event_list, indent=2) if event_list else "No active external events."
    
    data_pipeline = []
    for stock in low_stocks:
        ingredient = stock.ingredient
        constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).order_by('-constraint_ID').first()
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
            f"Runway Remaining: {item['Days_Runway_Remaining']:.1f} days, Lead Time: {item['Lead_Time_Days']:.0f} days, "
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
    
    output_ids = []
    try:
        raw_ai_text = _call_gemini_api(prompt)
        if not raw_ai_text:
            res = _generate_rule_based_prescriptions(branch, low_stocks, hist_consumption, event_multiplier, impact_events)
            output_ids.extend(res.get('outputs', []))
        else:
            clean_text = _clean_json_text(raw_ai_text)
            ai_data = json.loads(clean_text)
            
            for item in ai_data:
                ingredient = Ingredient.objects.get(ingredient_name=item['ingredient'])
                constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).order_by('-constraint_ID').first()
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
    except Exception:
        res = _generate_rule_based_prescriptions(branch, low_stocks, hist_consumption, event_multiplier, impact_events)
        output_ids.extend(res.get('outputs', []))

    # Add commissary batch production targets for Ibaan Hub
    if low_prod_stocks.exists():
        for ps in low_prod_stocks[:5]:
            p = ps.product
            boms = list(p.bom_ingredients.select_related('ingredient').all())
            if not boms:
                continue
            prod_cp = ConstraintParameter.objects.filter(branch=branch, product=p).order_by('-constraint_ID').first()
            p_threshold = float(ps.reorder_threshold)
            p_qty = float(ps.quantity_available)
            batch_qty = max(round(p_threshold * 2 - p_qty), 10.0)
            if prod_cp:
                min_q = float(prod_cp.min_order_quantity)
                max_batch = min(float(prod_cp.production_limit), float(prod_cp.max_order_quantity))
                room_avail = max(0.0, float(prod_cp.capacity_limit) - p_qty)
                batch_qty = min(max(batch_qty, min_q), max_batch, room_avail)
                if batch_qty <= 0:
                    batch_qty = max(min_q, 1.0)
            recipe_cost = sum(float(b.quantity_required) * float(b.ingredient.cost_per_unit) for b in boms)
            est_cost = round(batch_qty * recipe_cost, 2)
            cap_note = f", constrained within daily production limit ({float(prod_cp.production_limit):.0f}) and storage capacity ({float(prod_cp.capacity_limit):.0f})" if prod_cp else ""
            
            prod_rec = PrescriptiveOutput.objects.create(
                branch=branch,
                product=p,
                constraint=prod_cp,
                output_type='Production Target',
                recommendation=f"Commissary batch production of {int(batch_qty)} units of {p.product_name}",
                justification=_clean_db_text(
                    f"Commissary display stock is low ({p_qty:.0f} units remaining, threshold: {p_threshold:.0f} units). "
                    f"Batch production of {int(batch_qty)} units satisfies network demand across Ibaan and satellite branches{cap_note}. "
                    f"Estimated BOM ingredient production cost: ₱{est_cost:,.2f}."
                ),
                recommended_quantity=Decimal(str(batch_qty)),
                estimated_cost=Decimal(str(est_cost)),
                status="Pending Review"
            )
            output_ids.append(prod_rec.prescriptive_output_ID)

    return {"status": "generated", "outputs": output_ids}

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
        "performance", "target", "targets", "forecast", "demand", "summary", "report", "loss", "threshold",
        "sell", "selling", "seller", "sellers", "best", "top", "item", "items", "runway", "burn",
        "supply", "supplies", "store", "shop", "bakery", "kitchen", "margin", "customer", "customers",
        "volume", "business", "operations", "status", "lead time", "capacity", "directive", "dispatch",
        "allocation", "allocate", "batch", "yield", "bake", "baking", "recipe", "recommendation", "recommend",
        # Ingredients & Baking terms
        "flour", "all purpose flour", "all-purpose flour", "sugar", "butter", "egg", "eggs", "milk",
        "cream", "cheese", "cream cheese", "cocoa", "chocolate", "vanilla", "yeast", "salt", "ube",
        "matcha", "syrup", "tea", "boba", "pearls", "bento", "ganache", "almond", "carrots", "bread"
    ]
    
    return any(kw in q for kw in sweetbox_keywords)

def _build_dynamic_sales_response(
    branch, user, user_query, total_rev, total_txns, avg_txn,
    sorted_prods, low_stocks, event_list, event_multiplier, impact_events,
    payment_methods, all_branches_data,
    bom_production_plans=None, matched_ingredients=None,
    satellite_needs_text=None, top_products_telemetry_text=None
):
    """
    Intelligent intent-based dynamic generator that formulates targeted, structured,
    and measurable operational answers for specific Sweet Box queries.
    """
    q = user_query.lower()
    
    # Intent 0: Ingredient-Based Production Recommendation & BOM Allocation
    prod_rec_keywords = ['recommendation', 'recommend', 'produce', 'production', 'batch', 'bake', 'baking', 'allocate', 'allocation', 'recipe', 'bom', 'yield', 'make']
    ing_keywords = ['flour', 'sugar', 'butter', 'egg', 'eggs', 'milk', 'cream', 'cheese', 'cocoa', 'chocolate', 'ube', 'yeast', 'vanilla', 'boba', 'tea', 'ingredient', 'ingredients']

    is_production_query = any(k in q for k in prod_rec_keywords) or ('based on' in q and any(k in q for k in ing_keywords))
    is_ingredient_query = any(k in q for k in ing_keywords) or bool(matched_ingredients)

    if (is_production_query and is_ingredient_query) or (bool(bom_production_plans) and ('flour' in q or 'production' in q or 'recommendation' in q)):
        # Select best matching ingredient plan
        selected_plan = None
        if bom_production_plans:
            for ing_key, plan in bom_production_plans.items():
                if any(word in q for word in ing_key.lower().split()):
                    selected_plan = plan
                    break
            if not selected_plan:
                selected_plan = list(bom_production_plans.values())[0]

        if selected_plan:
            ing_name = selected_plan['ingredient_name']
            unit = selected_plan['unit']
            q_avail = selected_plan['quantity_available']
            reorder_th = selected_plan['reorder_threshold']
            q_safe = selected_plan['safe_usable_stock']
            batches = selected_plan['batches']
            total_cons = selected_plan['total_consumed']
            rem_bal = selected_plan['remaining_balance']
            products = selected_plan['products']

            lines = [
                f"🏭 **Sweet Box Executive Production Recommendation — {ing_name}**",
                f"**Production Hub:** {branch.name} Commissary | **Active Context:** Daily Production & BOM Allocation\n",
                f"📦 **1. Current Ingredient Inventory & Safety Runway**",
                f"- **Stock on Hand:** **{q_avail:.2f} {unit}**",
                f"- **Reorder Threshold:** {reorder_th:.2f} {unit}",
                f"- **Safe Usable Buffer:** **{q_safe:.2f} {unit}** ({'Optimal buffer available' if q_safe > 0 else 'Operating near/below threshold; prioritize high-velocity items'})",
                f"- **Supply Status:** {'⚠️ Low Stock / Strict Prioritization' if q_avail <= reorder_th else '✅ Healthy Operating Buffer'}\n",
                f"📋 **2. Key BOM Product Utilization & 30-Day Sales Velocity**"
            ]

            for p in products[:5]:
                lines.append(
                    f"- **{p['product_name']}**: Requires **{p['qty_required']:.2f} {unit}**/unit | "
                    f"30d Sales: **{p['units_30d']} units** | Retail: ₱{p['price']:.2f} | Unit Margin: ₱{p['margin']:.2f}"
                )

            lines.append("\n💡 **3. Recommended Daily Production Batch Plan**")
            if batches:
                tot_rev = sum(b['est_revenue'] for b in batches)
                tot_margin = sum(b['est_margin'] for b in batches)
                for b in batches:
                    lines.append(
                        f"- **{b['batch_units']}x {b['product_name']}**: Consumes **{b['ing_consumed']:.2f} {unit}** "
                        f"(Est. Revenue: ₱{b['est_revenue']:,.2f} | Est. Margin: ₱{b['est_margin']:,.2f})"
                    )
                lines.append(
                    f"\n* **Total Ingredient Consumption:** **{total_cons:.2f} {unit}**\n"
                    f"* **Projected Batch Revenue:** **₱{tot_rev:,.2f}** (Gross Margin: **₱{tot_margin:,.2f}**)"
                )
            else:
                lines.append("- Allocate stock toward core flagship cakes (Bento & Minimalist series) in small 5–10 unit test batches.")

            lines.append(f"\n⚖️ **4. Post-Production Balance & Supply Chain Directives**")
            lines.append(f"- **Remaining Ingredient Balance:** **{rem_bal:.2f} {unit}**.")
            if rem_bal <= reorder_th:
                lines.append(f"- **Procurement Alert:** Submit a restock order for **30.00–50.00 {unit}** through SCM to prevent line downtime (Lead time: ~3 days).")
            else:
                lines.append(f"- **Procurement Status:** Stock balance remains safely buffered above reorder threshold.")

            if satellite_needs_text and "All satellite" not in satellite_needs_text:
                lines.append(f"\n🚚 **Satellite Dispatch Strategy:**\nSynchronize baking output with counter display deficits:\n{satellite_needs_text}")

            return "\n".join(lines)

    # Intent 1: Best Sellers / Top Products / Cakes / Pastries / Beverage Sales
    prod_keywords = ['product', 'products', 'top', 'best', 'popular', 'cake', 'cakes', 'pastry', 'pastries', 'coffee', 'drink', 'sold', 'item', 'items', 'selling', 'seller']
    if any(k in q for k in prod_keywords) and not any(k in q for k in ['stock', 'ingredient', 'restock', 'raw']):
        if not sorted_prods:
            return f"📊 **Sweet Box Product Sales Analysis ({branch.name})**\n\nNo finished product sales are recorded for this branch in the current window."
        
        top_name, top_stats = sorted_prods[0]
        event_note = f" Note that demand is currently bolstered by {', '.join(impact_events)} ({int((event_multiplier - 1.0)*100)}% surge multiplier)." if impact_events else ""
        
        lines = [
            f"🏆 **Top-Performing Products — {branch.name}**\n",
            f"Our #1 best-selling product is **{top_name}** with **{top_stats['units_30d'] if 'units_30d' in top_stats else top_stats.get('Quantity_Sold', 0)} units sold**, generating **₱{top_stats.get('revenue_30d', top_stats.get('Revenue', 0.0)):,.2f}** in revenue.{event_note}\n",
            "**Sales Rankings:**"
        ]
        for rank, (name, stats) in enumerate(sorted_prods[:7], start=1):
            sold = stats['units_30d'] if 'units_30d' in stats else stats.get('Quantity_Sold', 0)
            rev = stats.get('revenue_30d', stats.get('Revenue', 0.0))
            share = round((rev / max(total_rev, 1.0)) * 100, 1)
            lines.append(f"{rank}. **{name}**: {sold} units sold | ₱{rev:,.2f} ({share}% of branch revenue)")
            
        lines.append(f"\n💡 **Recommendation:** Prioritize kitchen batch production and maintain safety stock for top pastry and cake lines to prevent stockouts during peak afternoon demand.")
        return "\n".join(lines)

    # Intent 2: Inventory / Stock Levels / Low Stock / Restocks / Ingredients / Runway
    stock_keywords = ['stock', 'stocks', 'inventory', 'low', 'restock', 'ingredient', 'ingredients', 'supply', 'supplies', 'runway', 'burn', 'reorder', 'capacity', 'procure']
    if any(k in q for k in stock_keywords):
        is_satellite = not bool(branch.main_hub or branch.branch_ID == 1 or 'ibaan' in branch.name.lower())
        if is_satellite:
            low_prods = ProductStock.objects.filter(branch=branch, quantity_available__lte=F('reorder_threshold')).select_related('product')
            if not low_prods.exists():
                return (
                    f"📦 **Sweet Box Finished Product Inventory Status ({branch.name})**\n\n"
                    f"✅ **All finished cake and pastry display stock levels are optimal at {branch.name}.** "
                    f"Display chillers and counters are fully stocked."
                )
            lines = [
                f"⚠️ **Low Finished Goods Watch — {branch.name}**\n",
                f"We have identified **{low_prods.count()} finished product line(s)** currently operating below display reorder thresholds:\n"
            ]
            for ps in low_prods[:6]:
                prod = ps.product
                qty = float(ps.quantity_available)
                thresh = float(ps.reorder_threshold)
                lines.append(f"- **{prod.product_name}**: {qty:.0f} units remaining (Reorder Threshold: {thresh:.0f} units, Selling Price: ₱{float(prod.price):,.2f})")
            lines.append(f"\n💡 **Prescriptive Action:** Submit a dispatch transfer request from Ibaan Main Hub Commissary to replenish these lines and prevent counter stockouts.")
            return "\n".join(lines)

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
    top_prod_name = sorted_prods[0][0] if sorted_prods else "No top product recorded"
    top_units = sorted_prods[0][1].get('units_30d', sorted_prods[0][1].get('Quantity_Sold', 0)) if sorted_prods else 0
    top_str = f"**Top Product:** {top_prod_name} ({top_units} sold)"
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
        f"How would you like to drill down further? You can ask about **top-selling products**, **production recommendations based on ingredients**, **branch comparisons**, **low stock ingredients**, or **event impacts**."
    )

def generate_sales_report(branch, user=None, user_query=None, **kwargs):
    """
    Answers sales, operational, BOM production, restocking, and strategic queries using real historical telemetry,
    ingredient stocks, BOM allocations, constraints, and local events.
    Enforces scope limitation, prevents hallucinations, and records all interactions in ChatbotLog.
    """
    # Robust parameter resolution
    if isinstance(user, str) and user_query is None:
        user_query = user
        user = kwargs.get('user')
    elif user_query is None:
        user_query = kwargs.get('user_query', '') or kwargs.get('query', '')

    if isinstance(branch, (int, str)):
        branch_obj = Branch.objects.filter(branch_ID=branch).first()
        if not branch_obj:
            branch_obj = Branch.objects.filter(name__icontains=str(branch)).first() or Branch.objects.first()
        branch = branch_obj
    elif not branch:
        branch = Branch.objects.filter(main_hub=True).first() or Branch.objects.first()

    if user is None:
        user = kwargs.get('user') or getattr(branch, 'manager', None) or Branch.objects.first()

    user_name = getattr(user, 'name', 'Executive')

    q_strip = str(user_query).strip()
    q_lower = q_strip.lower()
    
    # 1. Handle Greetings
    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings"}
    if q_lower in greetings or q_lower.rstrip("!?.") in greetings:
        active_vars = ExternalVariable.objects.filter(is_active=True)
        event_note = f" We currently have {active_vars.count()} active local event(s) influencing customer traffic." if active_vars.exists() else ""
        reply = (
            f"Hello, {user_name}! Welcome to your Sweet Box AI Sales Analyst.{event_note} "
            f"I have synchronized multi-branch sales records, inventory stock levels, and event telemetry. "
            f"How can I assist you with your business decisions today?"
        )
        ChatbotLog.objects.create(
            branch=branch, 
            user=user if hasattr(user, 'user_ID') else None, 
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
            user=user if hasattr(user, 'user_ID') else None, 
            query_text=_clean_db_text(user_query), 
            response_text=_clean_db_text(reply)
        )
        return reply

    # 3. Multi-Module Telemetry Gathering
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    recent_date = now - timedelta(days=180)

    # A. Pre-compute BOM costs in memory
    bom_cost_map = {}
    boms_by_ingredient = {}
    for bom in BillOfMaterial.objects.select_related('ingredient', 'product', 'product__category').all():
        cost = Decimal(str(bom.quantity_required)) * bom.ingredient.cost_per_unit
        bom_cost_map[bom.product_id] = bom_cost_map.get(bom.product_id, Decimal('0.00')) + cost
        
        if bom.ingredient_id not in boms_by_ingredient:
            boms_by_ingredient[bom.ingredient_id] = []
        boms_by_ingredient[bom.ingredient_id].append(bom)

    # B. Product Classifications
    classification_map = {
        pc.product_id: pc.classification 
        for pc in ProductClassification.objects.all()
    }

    # C. Target branch completed transactions (180-day window)
    transactions = Transaction.objects.filter(
        branch=branch, 
        transaction_status='Completed',
        transaction_date__gte=recent_date
    ).prefetch_related('items__product__category', 'payments')
    
    if not transactions.exists():
        transactions = Transaction.objects.filter(
            branch=branch, transaction_status='Completed'
        ).prefetch_related('items__product__category', 'payments')

    total_rev = transactions.aggregate(Sum('total_amount'))['total_amount__sum'] or 0.0
    total_txns = transactions.count()
    avg_txn = round(float(total_rev) / max(total_txns, 1), 2)
    
    product_stats = {}
    payment_methods = {}
    for txn in transactions:
        for pm in txn.payments.all():
            m_name = pm.payment_method or 'Cash'
            payment_methods[m_name] = payment_methods.get(m_name, 0) + float(pm.amount_paid)

        is_recent_30d = txn.transaction_date >= thirty_days_ago if txn.transaction_date else False

        for item in txn.items.all():
            prod = item.product
            pid = prod.product_ID
            pname = prod.product_name
            cat_name = prod.category.category_name if prod.category else 'General'
            price = float(prod.price)
            unit_c = float(bom_cost_map.get(pid, prod.price * Decimal('0.35')))
            margin = price - unit_c

            if pname not in product_stats:
                product_stats[pname] = {
                    'product_id': pid,
                    'category': cat_name,
                    'price': price,
                    'unit_cost': unit_c,
                    'margin': margin,
                    'units_180d': 0,
                    'revenue_180d': 0.0,
                    'units_30d': 0,
                    'revenue_30d': 0.0,
                    'classification': classification_map.get(pid, 'Standard')
                }

            product_stats[pname]['units_180d'] += item.quantity
            product_stats[pname]['revenue_180d'] += float(item.subtotal)

            if is_recent_30d:
                product_stats[pname]['units_30d'] += item.quantity
                product_stats[pname]['revenue_30d'] += float(item.subtotal)

    sorted_prods = sorted(
        product_stats.items(),
        key=lambda x: (x[1]['units_30d'], x[1]['revenue_180d']),
        reverse=True
    )

    top_products_telemetry_lines = []
    for name, s in sorted_prods[:15]:
        top_products_telemetry_lines.append(
            f"- {name} ({s['category']}) | 30d Units: {s['units_30d']} | Price: ₱{s['price']:.2f} | "
            f"BOM Cost: ₱{s['unit_cost']:.2f} | Margin: ₱{s['margin']:.2f} | Class: {s['classification']}"
        )
    top_products_telemetry_text = "\n".join(top_products_telemetry_lines) if top_products_telemetry_lines else "No product sales records."

    # D. Raw Ingredient Stock & Constraints (Ibaan Central Commissary)
    ibaan_hub = Branch.objects.filter(main_hub=True).first() or Branch.objects.filter(branch_ID=1).first() or branch
    hub_ingredient_stocks = IngredientStock.objects.filter(branch=ibaan_hub).select_related('ingredient')
    hub_stock_map = {s.ingredient_id: s for s in hub_ingredient_stocks}
    constraint_map = {cp.ingredient_id: cp for cp in ConstraintParameter.objects.filter(branch=ibaan_hub, ingredient__isnull=False)}

    all_ingredients = Ingredient.objects.all().order_by('ingredient_name')
    ingredient_telemetry_lines = []
    matched_ingredients = []

    for ing in all_ingredients:
        stk = hub_stock_map.get(ing.ingredient_ID)
        q_avail = float(stk.quantity_available) if stk else 0.0
        reorder_th = float(stk.reorder_threshold) if stk else 0.0
        cost_unit = float(ing.cost_per_unit)
        safe_buffer = max(0.0, q_avail - reorder_th)

        status_str = "Critical" if q_avail <= (0.5 * reorder_th) else "Low Stock" if q_avail <= reorder_th else "In Stock"

        cp = constraint_map.get(ing.ingredient_ID)
        min_ord = float(cp.min_order_quantity) if cp else 5.0
        max_ord = float(cp.max_order_quantity) if cp else 50.0
        lead_days = cp.lead_time_days if cp else 3

        ing_info = {
            'ingredient_obj': ing,
            'name': ing.ingredient_name,
            'unit': ing.measurement_unit,
            'cost_per_unit': cost_unit,
            'quantity_available': q_avail,
            'reorder_threshold': reorder_th,
            'safe_usable_stock': safe_buffer,
            'status': status_str,
            'min_order_quantity': min_ord,
            'max_order_quantity': max_ord,
            'lead_time_days': lead_days
        }

        ing_clean_name = ing.ingredient_name.lower()
        is_matched = (
            ing_clean_name in q_lower 
            or (ing_clean_name.replace('-', ' ') in q_lower)
            or ('flour' in ing_clean_name and 'flour' in q_lower)
            or ('sugar' in ing_clean_name and 'sugar' in q_lower and 'brown' not in ing_clean_name and 'syrup' not in ing_clean_name)
            or ('butter' in ing_clean_name and 'butter' in q_lower)
            or ('egg' in ing_clean_name and ('egg' in q_lower or 'eggs' in q_lower))
            or ('milk' in ing_clean_name and 'milk' in q_lower and 'tea' not in q_lower)
            or ('cream cheese' in ing_clean_name and 'cream cheese' in q_lower)
            or ('whipping cream' in ing_clean_name and 'cream' in q_lower and 'cream cheese' not in q_lower)
            or ('cocoa' in ing_clean_name and ('cocoa' in q_lower or 'chocolate' in q_lower))
            or ('ube' in ing_clean_name and 'ube' in q_lower)
            or ('boba' in ing_clean_name and ('boba' in q_lower or 'pearl' in q_lower))
        )
        if is_matched:
            matched_ingredients.append(ing_info)

        ingredient_telemetry_lines.append(
            f"- {ing.ingredient_name}: {q_avail:.2f} {ing.measurement_unit} available (Reorder Thresh: {reorder_th:.2f} {ing.measurement_unit}, "
            f"Safe Buffer: {safe_buffer:.2f} {ing.measurement_unit}, Status: {status_str}, Cost: ₱{cost_unit:.2f}/{ing.measurement_unit})"
        )

    # E. Bill of Materials (BOM) Production Matrix
    bom_analysis_lines = []
    bom_production_plans = {}

    target_ings_to_analyze = matched_ingredients if matched_ingredients else [
        {
            'ingredient_obj': ing,
            'name': ing.ingredient_name,
            'unit': ing.measurement_unit,
            'cost_per_unit': float(ing.cost_per_unit),
            'quantity_available': float(hub_stock_map[ing.ingredient_ID].quantity_available) if ing.ingredient_ID in hub_stock_map else 0.0,
            'reorder_threshold': float(hub_stock_map[ing.ingredient_ID].reorder_threshold) if ing.ingredient_ID in hub_stock_map else 0.0,
            'safe_usable_stock': max(0.0, float(hub_stock_map[ing.ingredient_ID].quantity_available) - float(hub_stock_map[ing.ingredient_ID].reorder_threshold)) if ing.ingredient_ID in hub_stock_map else 0.0,
            'status': 'In Stock',
            'min_order_quantity': 5.0,
            'max_order_quantity': 50.0,
            'lead_time_days': 3
        }
        for ing in all_ingredients[:8]
    ]

    for ing_info in target_ings_to_analyze:
        ing_obj = ing_info['ingredient_obj']
        ing_name = ing_info['name']
        q_avail = ing_info['quantity_available']
        q_safe = ing_info['safe_usable_stock']
        unit = ing_info['unit']

        boms_for_ing = boms_by_ingredient.get(ing_obj.ingredient_ID, [])
        if not boms_for_ing:
            continue

        prods_using_ing = []
        for b in boms_for_ing:
            p = b.product
            req = float(b.quantity_required)
            stats = product_stats.get(p.product_name, {
                'units_30d': 0, 'price': float(p.price), 'unit_cost': float(bom_cost_map.get(p.product_ID, p.price * Decimal('0.35'))),
                'margin': float(p.price) - float(bom_cost_map.get(p.product_ID, p.price * Decimal('0.35'))),
                'classification': classification_map.get(p.product_ID, 'Standard')
            })

            max_yield_avail = int(q_avail // req) if req > 0 else 0
            max_yield_safe = int(q_safe // req) if req > 0 else 0

            prods_using_ing.append({
                'product_name': p.product_name,
                'category': p.category.category_name if p.category else 'General',
                'qty_required': req,
                'units_30d': stats['units_30d'],
                'price': stats['price'],
                'margin': stats['margin'],
                'classification': stats['classification'],
                'max_yield_avail': max_yield_avail,
                'max_yield_safe': max_yield_safe
            })

        prods_using_ing.sort(key=lambda x: (x['units_30d'], x['margin']), reverse=True)

        active_candidates = [p for p in prods_using_ing if p['units_30d'] > 0][:4]
        if not active_candidates:
            active_candidates = prods_using_ing[:4]

        usable_budget = q_safe if q_safe > 0 else (q_avail * 0.8)
        tot_vel = sum(c['units_30d'] for c in active_candidates) or len(active_candidates)

        allocated_batches = []
        consumed_ing = 0.0
        for cand in active_candidates:
            weight = (cand['units_30d'] / tot_vel) if tot_vel > 0 else (1.0 / len(active_candidates))
            ing_portion = usable_budget * weight
            batch_units = max(1, int(ing_portion // cand['qty_required']))
            actual_ing_needed = batch_units * cand['qty_required']

            if (consumed_ing + actual_ing_needed) > q_avail:
                batch_units = max(0, int((q_avail - consumed_ing) // cand['qty_required']))
                actual_ing_needed = batch_units * cand['qty_required']

            if batch_units > 0:
                consumed_ing += actual_ing_needed
                allocated_batches.append({
                    'product_name': cand['product_name'],
                    'batch_units': batch_units,
                    'qty_required': cand['qty_required'],
                    'ing_consumed': round(actual_ing_needed, 2),
                    'est_revenue': round(batch_units * cand['price'], 2),
                    'est_margin': round(batch_units * cand['margin'], 2)
                })

        rem_balance = max(0.0, q_avail - consumed_ing)
        bom_production_plans[ing_name] = {
            'ingredient_name': ing_name,
            'unit': unit,
            'quantity_available': q_avail,
            'reorder_threshold': ing_info['reorder_threshold'],
            'safe_usable_stock': q_safe,
            'products': prods_using_ing[:8],
            'batches': allocated_batches,
            'total_consumed': round(consumed_ing, 2),
            'remaining_balance': round(rem_balance, 2)
        }

        bom_analysis_lines.append(f"Ingredient: {ing_name} ({q_avail:.2f} {unit} available, Safe Buffer: {q_safe:.2f} {unit}):")
        for p in prods_using_ing[:5]:
            bom_analysis_lines.append(f"  * {p['product_name']}: {p['qty_required']:.2f} {unit}/unit | 30d Sales: {p['units_30d']} units | Retail: ₱{p['price']:.2f} | Margin: ₱{p['margin']:.2f} | Max Yield: {p['max_yield_avail']} units")
        if allocated_batches:
            batch_summary = ", ".join([f"{b['batch_units']}x {b['product_name']} ({b['ing_consumed']:.2f} {unit})" for b in allocated_batches])
            bom_analysis_lines.append(f"  * Recommended Production Batch: {batch_summary} (Consumes: {consumed_ing:.2f} {unit}, Post-Batch Remainder: {rem_balance:.2f} {unit})")

    bom_telemetry_text = "\n".join(bom_analysis_lines) if bom_analysis_lines else "No specific BOM ingredient query."

    # F. Satellite Branches Finished Goods Deficit
    sat_stocks = ProductStock.objects.filter(
        quantity_available__lte=F('reorder_threshold')
    ).select_related('product', 'branch')

    sat_needs_by_branch = {}
    for ps in sat_stocks:
        b_name = ps.branch.name
        if b_name not in sat_needs_by_branch:
            sat_needs_by_branch[b_name] = []
        sat_needs_by_branch[b_name].append(f"{ps.product.product_name} ({int(ps.quantity_available)} left, threshold: {int(ps.reorder_threshold)})")

    sat_lines = [f"- {b}: {', '.join(prods[:4])}" for b, prods in sat_needs_by_branch.items()]
    satellite_needs_text = "\n".join(sat_lines[:4]) if sat_lines else "All satellite branch counter display stocks are optimal."

    # G. Multi-Branch Summary for Cross-Branch Context
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

    # H. Gather Local Events & Variables
    event_list, event_multiplier, impact_events = _get_active_events_context(branch)
    var_context = json.dumps(event_list, indent=2) if event_list else "No active external events or holidays."

    # Low stocks at target branch
    low_stocks = IngredientStock.objects.filter(branch=branch, quantity_available__lte=F('reorder_threshold'))
    pending_prescriptions = PrescriptiveOutput.objects.filter(status='Pending Review').select_related('ingredient', 'branch')
    presc_lines = [f"- {po.branch.name}: {po.recommendation}" for po in pending_prescriptions[:5]]
    pending_presc_text = "\n".join(presc_lines) if presc_lines else "No pending prescriptive directives."

    prompt = f"""
    You are the dedicated Sweet Box AI Executive Prescriptive & Decision-Support Analyst for {user_name} at the {branch.name} branch (Central Production Hub: {ibaan_hub.name}).
    
    CRITICAL DECISION-SUPPORT & HALLUCINATION PREVENTION GUIDELINES:
    1. Base your answer on the historical sales telemetry, Bill of Materials (BOM) allocations, ingredient inventory, branch comparisons, and local events provided below.
    2. NEVER refuse legitimate business, production, recipe, inventory, or operational questions with "The requested data is not recorded in our current Sweet Box database records". All telemetry below is authentic Sweet Box production data. Only decline queries if they are completely unrelated to business, retail, food service, baking, or Sweet Box operations.
    3. INGREDIENT & PRODUCTION RECOMMENDATION PROTOCOL:
       When the user asks for a production recommendation based on an ingredient (e.g., "give me a production recommendation based on all purpose flour" or any other ingredient):
       a. State the exact current stock of that ingredient at Ibaan (Main Hub Commissary), its measurement unit, unit cost, and reorder threshold, noting how much safe usable stock (quantity_available - reorder_threshold) is available before triggering a low-stock alert.
       b. List the top-selling products in the database that require that ingredient in their Bill of Materials (BOM), citing each product's exact BOM deduction per unit, retail price, and recent 30-day sales velocity.
       c. Provide a concrete, mathematically feasible production batch plan (exact unit numbers per cake/pastry to produce today) that stays within the safe usable stock and production limits, prioritizing high-velocity/high-margin items and satellite branch display needs.
       d. State the exact post-production remaining ingredient balance and whether a restock order should be queued immediately.
    4. CITE active Local Events & External Variables whenever explaining customer demand trends, sales variations, or seasonal volume.
    5. Format responses with clean Markdown headers, bullet points, bold product names, and tabular numbers for executive clarity.

    ACTIVE LOCAL EVENTS & EXTERNAL VARIABLES:
    {var_context}

    BRANCH FINANCIAL & SALES OVERVIEW ({branch.name}):
    Total Completed Transactions (180d): {total_txns}
    Total Revenue: ₱{float(total_rev):,.2f} | Average Order Value: ₱{avg_txn:,.2f}
    Payment Methods: {json.dumps(payment_methods)}

    MULTI-BRANCH NETWORK COMPARISON:
    {multi_branch_summary}

    TOP PRODUCTS VELOCITY & UNIT ECONOMICS (30-DAY / 180-DAY):
    {top_products_telemetry_text}

    RAW INGREDIENT INVENTORY & CONSTRAINTS (IBAAN MAIN HUB COMMISSARY):
    {chr(10).join(ingredient_telemetry_lines[:25])}

    BILL OF MATERIALS (BOM) RECIPE ALLOCATION & PRODUCTION CAPABILITY:
    {bom_telemetry_text}

    SATELLITE BRANCH COUNTER DISPLAY DEFICITS (FINISHED GOODS DISPATCH NEEDS):
    {satellite_needs_text}

    PENDING SYSTEM PRESCRIPTIONS:
    {pending_presc_text}

    USER QUERY:
    "{user_query}"
    """
    
    reply = None
    try:
        reply = _call_gemini_api(prompt)
    except Exception:
        reply = None

    if not reply or "not recorded in our current sweet box database records" in reply.lower():
        # Intelligent intent-driven fallback
        reply = _build_dynamic_sales_response(
            branch=branch, user=user, user_query=user_query,
            total_rev=float(total_rev), total_txns=total_txns, avg_txn=avg_txn,
            sorted_prods=sorted_prods, low_stocks=low_stocks,
            event_list=event_list, event_multiplier=event_multiplier, impact_events=impact_events,
            payment_methods=payment_methods, all_branches_data=all_branches_data,
            bom_production_plans=bom_production_plans, matched_ingredients=matched_ingredients,
            satellite_needs_text=satellite_needs_text, top_products_telemetry_text=top_products_telemetry_text
        )

    # Always persist every query and response to ChatbotLog in the database
    ChatbotLog.objects.create(
        branch=branch, 
        user=user if hasattr(user, 'user_ID') else None, 
        query_text=_clean_db_text(user_query), 
        response_text=_clean_db_text(reply)
    )
    
    return reply
