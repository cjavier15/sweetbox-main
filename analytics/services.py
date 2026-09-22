import json
import google.generativeai as genai
import pandas as pd
from django.conf import settings
from django.db.models import F
from inventory.models import IngredientStock, ConstraintParameter, Ingredient
from analytics.models import PrescriptiveOutput, ExternalVariable, ChatbotLog
from django.utils import timezone
from datetime import timedelta
from pos.models import Transaction

# Initialize the Gemini API client
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')

def generate_restock_directive(branch):
    low_stocks = IngredientStock.objects.filter(branch=branch, quantity_available__lte=F('reorder_threshold'))
    if not low_stocks.exists():
        return {"status": "optimal", "message": "All inventory levels are sufficient."}
    
    data_pipeline = []
    for stock in low_stocks:
        ingredient = stock.ingredient
        constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).first()
        data_pipeline.append({
            'Ingredient': ingredient.ingredient_name,
            'Current_Stock': float(stock.quantity_available),
            'Min_Order': float(constraint.min_order_quantity) if constraint else 0,
            'Max_Order': float(constraint.max_order_quantity) if constraint else 9999,
            'Cost_Per_Unit': float(ingredient.cost_per_unit)
        })
    
    df = pd.DataFrame(data_pipeline)
    
    prompt = f"""
    You are an expert supply chain AI for Sweet Box ({branch.name}).
    Analyze these low-stock ingredients and output a recommended feasible action:
    {df.to_string(index=False)}
    
    Return ONLY a valid JSON array of objects with exact keys: "ingredient", "recommended_qty", "estimated_cost", "justification".
    Do not use markdown formatting like ```json.
    """
    
    response = model.generate_content(prompt)
    
    try:
        ai_data = json.loads(response.text.strip())
        output_ids = []
        
        for item in ai_data:
            ingredient = Ingredient.objects.get(ingredient_name=item['ingredient'])
            constraint = ConstraintParameter.objects.filter(branch=branch, ingredient=ingredient).first()
            stock_record = IngredientStock.objects.filter(branch=branch, ingredient=ingredient).first()
            
            raw_qty = float(item['recommended_qty'])
            current_stock = float(stock_record.quantity_available) if stock_record else 0.0
            
            # HARD BOUNDING: Enforce physical capacity mathematically
            min_qty = float(constraint.min_order_quantity) if constraint else 0.0
            max_supplier_qty = float(constraint.max_order_quantity) if constraint else 9999.0
            capacity_limit = float(constraint.capacity_limit) if constraint else 9999.0
            
            room_available = max(0.0, capacity_limit - current_stock)
            absolute_max = min(max_supplier_qty, room_available)
            
            # Mathematically cap the output before saving
            bounded_qty = min(max(raw_qty, min_qty), absolute_max)
            
            justification = item['justification']
            if raw_qty != bounded_qty:
                justification = f"(System Auto-Bounded from {raw_qty} to {bounded_qty} to obey physical capacity constraints) " + justification
            
            record = PrescriptiveOutput.objects.create(
                branch=branch, ingredient=ingredient, constraint=constraint,
                output_type='Restock Prescription',
                recommendation=f"Order {bounded_qty} {ingredient.measurement_unit} of {ingredient.ingredient_name}",
                justification=justification, recommended_quantity=bounded_qty,
                estimated_cost=item['estimated_cost'], status="Pending Review"
            )
            output_ids.append(record.prescriptive_output_ID)
            
        return {"status": "generated", "outputs": output_ids}
    except json.JSONDecodeError:
        return {"status": "error", "message": "AI failed to return structured data."}

def generate_sales_report(branch, user, user_query):
    recent_date = timezone.now() - timedelta(days=180)
    transactions = Transaction.objects.filter(
        branch=branch, 
        transaction_status='Completed',
        transaction_date__gte=recent_date
    )
    
    data_pipeline = []
    for txn in transactions:
        for item in txn.items.all():
            data_pipeline.append({
                'Product': item.product.product_name,
                'Quantity_Sold': item.quantity,
                'Revenue': float(item.subtotal)
            })
            
    df = pd.DataFrame(data_pipeline)
    
    if df.empty:
        summary_data = "No sales data available for the past 180 days."
    else:
        summary_df = df.groupby('Product').agg({'Quantity_Sold': 'sum', 'Revenue': 'sum'}).reset_index()
        summary_data = summary_df.to_string(index=False)

    active_vars = ExternalVariable.objects.filter(is_active=True)
    var_pipeline = []
    for v in active_vars:
        var_pipeline.append({
            'Event': v.name, 
            'Type': v.variable_type, 
            'Impact': v.impact_level, 
            'Ends': v.end_date
        })
        
    var_df = pd.DataFrame(var_pipeline)
    var_context = var_df.to_string(index=False) if not var_df.empty else "No active external events."

    prompt = f"""
    You are a sharp financial analyst AI for the {branch.name} branch of Sweet Box.
    
    Current External Variables (Holidays/Paydays):
    {var_context}
    
    User Query: "{user_query}"
    
    Recent 180-Day Sales Data:
    {summary_data}
    
    Answer the user's query directly based on the provided data. Factor in the External Variables if the user asks about forecasting or demand. Be concise, professional, and actionable. Calculate the totals accurately and do not hallucinate metrics.
    """
    
    response = model.generate_content(prompt)
    
    ChatbotLog.objects.create(
        branch=branch, 
        user=user, 
        query_text=user_query, 
        response_text=response.text
    )
    
    return response.text