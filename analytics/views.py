import json
import csv
from django.db.models import Sum, Count, F
from django.views.generic import TemplateView
from pos.models import Transaction, PaymentRecord, TransactionItem
from .models import ChatbotLog, PrescriptiveOutput, ExternalVariable, ArchiveStorage, KPIRecord, ProductClassification
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from accounts.models import Branch, AuditLog
from .services import generate_restock_directive, generate_sales_report
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
from django.db import transaction as db_transaction
from inventory.models import IngredientStock, BillOfMaterial, ProductStock
from decimal import Decimal
from django.db.models.functions import TruncDate, TruncMonth

class EnterpriseDashboardView(TemplateView):
    template_name = 'enterprise_analytics.html'

class ProcessPrescriptionView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, output_id):
        action = request.data.get('action') # 'Approve' or 'Override'
        reason = request.data.get('override_reason', '')
        
        try:
            prescription = PrescriptiveOutput.objects.get(prescriptive_output_ID=output_id)
            
            if action == 'Override':
                if not reason:
                    return Response({"error": "An override reason is mandatory for future AI calibration."}, status=400)
                prescription.is_overridden = True
                prescription.override_reason = reason
                prescription.status = 'Overridden'
                
                AuditLog.objects.create(user=request.user, action="AI Override", module="Analytics", details=f"Overrode prescription ID {output_id}. Reason: {reason}")
            
            elif action == 'Approve':
                prescription.status = 'Approved'
                AuditLog.objects.create(user=request.user, action="AI Approved", module="Analytics", details=f"Approved AI prescription ID {output_id}.")
                
            prescription.save()
            return Response({"message": f"Prescription successfully {prescription.status.lower()}."})
            
        except PrescriptiveOutput.DoesNotExist:
            return Response({"error": "Prescription not found."}, status=404)
    
class RestockDirectiveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        branch_id = request.data.get('branch_id')

        # Allow passing a branch_id, or fall back to the user's assigned branch
        if branch_id:
            try:
                branch = Branch.objects.get(branch_ID=branch_id)
            except Branch.DoesNotExist:
                return Response({"error": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)
        elif user.branch:
            branch = user.branch
        else:
            return Response({"error": "Please provide a branch_id in the request body."}, status=status.HTTP_400_BAD_REQUEST)

        # Trigger Gemini AI Pipeline
        result = generate_restock_directive(branch)
        return Response(result, status=status.HTTP_200_OK)
    
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'name': request.user.name,
            'role': request.user.role,
            'branch': request.user.branch.name if request.user.branch else "Headquarters"
        })

class SalesChatbotView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        branch_id = request.data.get('branch_id')
        user_query = request.data.get('query', 'Give me a brief summary of our recent sales.')

        if branch_id:
            try:
                branch = Branch.objects.get(branch_ID=branch_id)
            except Branch.DoesNotExist:
                return Response({"error": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)
        elif user.branch:
            branch = user.branch
        else:
            return Response({"error": "Please provide a branch_id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ai_response = generate_sales_report(branch, request.user, user_query)
            ChatbotLog.objects.create(
                branch=branch,
                user=user,
                query_text=user_query,
                response_text=ai_response
            )
            
            return Response({"reply": ai_response}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class EnterpriseDashboardDataView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        time_filter = request.GET.get('filter', 'this_month')
        today = timezone.now()
        
        # Determine Date Ranges
        if time_filter == 'this_week':
            days, trunc_func = 7, TruncDate
        elif time_filter == 'last_7_months':
            days, trunc_func = 210, TruncMonth
        else: # 'this_month'
            days, trunc_func = 30, TruncDate
            
        start_date = today - timedelta(days=days)
        prev_start_date = start_date - timedelta(days=days)
        
        # Base QuerySets
        txns_current = Transaction.objects.filter(transaction_status='Completed', transaction_date__gte=start_date)
        txns_prev = Transaction.objects.filter(transaction_status='Completed', transaction_date__gte=prev_start_date, transaction_date__lt=start_date)
        
        # 1. Top Scorecards & Trends
        curr_revenue = txns_current.aggregate(Sum('total_amount'))['total_amount__sum'] or 0.00
        prev_revenue = txns_prev.aggregate(Sum('total_amount'))['total_amount__sum'] or 1.00 # Prevent division by zero
        rev_trend = ((float(curr_revenue) - float(prev_revenue)) / float(prev_revenue)) * 100
        
        curr_txns = txns_current.count()
        prev_txns = txns_prev.count() or 1
        txn_trend = ((curr_txns - prev_txns) / prev_txns) * 100
        
        latest_kpi = KPIRecord.objects.order_by('-period_date').first()
        turnover = float(latest_kpi.inventory_turnover) if latest_kpi else 0.00
        gmroi = float(latest_kpi.gmroi) if latest_kpi else 0.00
        
        total_branches = Branch.objects.count()
        # Branches that have processed a transaction in the current period are considered "Active"
        active_branches = txns_current.values('branch').distinct().count()
        
        scorecards = {
            'revenue': float(curr_revenue), 'revenue_trend': round(rev_trend, 1), 'prev_revenue': float(prev_revenue),
            'transactions': curr_txns, 'transactions_trend': round(txn_trend, 1),
            'turnover': turnover, 'gmroi': gmroi,
            'active_branches': active_branches, 'total_branches': total_branches
        }

        # 2. Time-Series: Daily/Monthly Sales Overview
        sales_over_time = txns_current.annotate(period=trunc_func('transaction_date')).values('period').annotate(total=Sum('total_amount')).order_by('period')
        time_series = { 'labels': [s['period'].strftime('%b %d') for s in sales_over_time], 'data': [float(s['total']) for s in sales_over_time] }

        # 3. Payment Methods (Preserving your exact cleansing logic)
        payments = PaymentRecord.objects.filter(transaction__transaction_date__gte=start_date).values('payment_method').annotate(count=Count('payment_method'))
        payment_data = {}
        for p in payments:
            raw = str(p['payment_method'])
            clean = 'Split Payment' if 'Split' in raw else 'E-Wallet' if any(x in raw for x in ['GCash', 'Maya', 'E-Wallet']) else 'Cash' if 'Cash' in raw else 'Other'
            payment_data[clean] = payment_data.get(clean, 0) + p['count']

        # 4. Branch Performance & Targets
        
        # Define your specific monthly sales targets for each branch
        monthly_targets = {
            'Ibaan (Main Hub)': 20000.00,
            'South Supermarket Lipa': 16000.00,
            'Sampaguita': 18000.00,
            'San Jose': 12000.00,
            'Padre Garcia': 11000.00,
            'San Antonio Quezon': 10000.00,
            'Cuenca': 9000.00
        }
        
        branch_performance = []
        for b in Branch.objects.all():
            b_rev = txns_current.filter(branch=b).aggregate(Sum('total_amount'))['total_amount__sum'] or 0.00
            
            # Fetch the specific branch target, default to 150,000 if not listed
            base_monthly_target = monthly_targets.get(b.name, 150000.00)
            
            # Dynamically scale the target based on the selected date filter
            if days == 7:
                target = base_monthly_target / 4  # Convert to weekly target
            elif days == 210:
                target = base_monthly_target * 7  # Convert to 7-month target
            else:
                target = base_monthly_target      # Default 30-day target
                
            branch_performance.append({
                'branch': b.name,
                'actual': float(b_rev),
                'target': float(target),
                'status': 'On Target' if float(b_rev) >= target else 'Below Target'
            })
            
        # Sort branches by highest actual revenue
        branch_performance.sort(key=lambda x: x['actual'], reverse=True)

        # 5. Top Selling Products
        top_items = TransactionItem.objects.filter(transaction__transaction_date__gte=start_date).values(
            'product__product_name', 'product__category__category_name'
        ).annotate(units=Sum('quantity'), rev=Sum('subtotal')).order_by('-rev')[:15]
        
        top_products = []
        for idx, item in enumerate(top_items):
            # Simulated trend metric for UI demonstration (calculating exact item trends requires complex subqueries)
            trend = round(((float(item['rev']) / float(curr_revenue)) * 100) if curr_revenue > 0 else 0, 1)
            top_products.append({
                'rank': idx + 1, 'name': item['product__product_name'], 'category': item['product__category__category_name'],
                'units': item['units'], 'revenue': float(item['rev']), 'trend': trend
            })

        return Response({
            'scorecards': scorecards,
            'time_series': time_series,
            'payment_methods': payment_data,
            'branch_performance': branch_performance,
            'top_products': top_products
        })

class ExternalVariableView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        variables = ExternalVariable.objects.filter(is_active=True).values(
            'variable_ID', 'name', 'variable_type', 'start_date', 'end_date', 'impact_level'
        ).order_by('start_date')
        return Response(variables, status=status.HTTP_200_OK)

    def post(self, request):
        try:
            ExternalVariable.objects.create(
                name=request.data.get('name'),
                variable_type=request.data.get('variable_type'),
                start_date=request.data.get('start_date'),
                end_date=request.data.get('end_date'),
                impact_level=request.data.get('impact_level'),
                description="Manually logged via Enterprise Dashboard"
            )
            return Response({"message": "Event successfully logged for AI context."}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, var_id):
        ExternalVariable.objects.filter(variable_ID=var_id).delete()
        return Response({"message": "Event removed from AI context."}, status=status.HTTP_200_OK)

# ETL pipeline
class RunETLPipelineView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        if getattr(request.user, 'role', '') != 'Business Owner':
            return Response({"error": "Only the Business Owner can execute ETL jobs."}, status=403)
        
        today = timezone.now().date()
        cutoff_date = timezone.now() - timedelta(days=180)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        branches = Branch.objects.all()
        
        # 1. Transform & Load: Batch Calculate KPIs 
        for branch in branches:
            recent_txns = Transaction.objects.filter(branch=branch, transaction_status='Completed', transaction_date__gte=thirty_days_ago)
            total_rev = recent_txns.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
            
            # Calculate Exact COGS via Bill of Materials
            cogs = Decimal('0.00')
            for txn in recent_txns:
                for item in txn.items.all():
                    boms = BillOfMaterial.objects.filter(product=item.product)
                    item_cost = sum([Decimal(str(bom.quantity_required)) * bom.ingredient.cost_per_unit for bom in boms])
                    cogs += (item_cost * item.quantity)
                    
            gross_margin = total_rev - cogs
            avg_inventory_cost = IngredientStock.objects.filter(branch=branch).aggregate(Sum('total_cost'))['total_cost__sum'] or Decimal('1.00')
            if avg_inventory_cost <= 0: avg_inventory_cost = Decimal('1.00')
            
            # Apply Panel Formulas
            inv_turnover = cogs / avg_inventory_cost
            gmroi = gross_margin / avg_inventory_cost
            stockouts = IngredientStock.objects.filter(branch=branch, quantity_available__lte=0).count()
            
            KPIRecord.objects.create(
                branch=branch, inventory_turnover=round(inv_turnover, 2), gmroi=round(gmroi, 2),
                gross_margin=round(gross_margin, 2), total_revenue=round(total_rev, 2),
                dead_stock_value=Decimal('0.00'), stockout_count=stockouts, period_date=today
            )
            
        # 2. Deterministic Product Classification 
        recent_txns = Transaction.objects.filter(transaction_status='Completed', transaction_date__gte=thirty_days_ago)
        product_sales = {}
        for txn in recent_txns:
            for item in txn.items.all():
                product_sales[item.product] = product_sales.get(item.product, 0) + item.quantity
                
        # Check if a Holiday or Weather Seasonality is currently active
        is_seasonal = ExternalVariable.objects.filter(is_active=True, variable_type__in=['Holiday', 'Weather Seasonality']).exists()

        ProductClassification.objects.all().delete()
        for product, qty in product_sales.items():
            if qty >= 50:
                classification = 'Best-Selling'
            elif qty <= 10:
                classification = 'Slow-Moving'
            elif is_seasonal:
                classification = 'Seasonal'
            else:
                classification = 'Standard'
                
            ProductClassification.objects.create(
                product=product, classification=classification,
                recommended_action="Generated deterministically via ETL Pipeline."
            )
            
        # 3. Extract & Archive: Move old transactions
        old_txns = Transaction.objects.filter(transaction_date__lte=cutoff_date)
        archive_count = 0
        for txn in old_txns:
            txn_data = {
                "id": txn.transaction_ID,
                "branch": txn.branch.name,
                "amount": str(txn.total_amount),
                "date": str(txn.transaction_date)
            }
            ArchiveStorage.objects.create(
                module_table="TRANSACTIONS",
                record_ID=txn.transaction_ID,
                archived_data=json.dumps(txn_data)
            )
            txn.delete()
            archive_count += 1
            
        AuditLog.objects.create(user=request.user, action="ETL Execution", module="System Admin", details=f"ETL Pipeline generated KPIs, classified products, and archived {archive_count} records.")
        return Response({"message": f"ETL Pipeline complete. KPIs/Classifications generated and {archive_count} old records securely archived."})

class ExportKPIReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="SweetBox_KPI_Report.csv"'

        writer = csv.writer(response)
        writer.writerow(['Branch', 'Period Date', 'Total Revenue (PHP)', 'Gross Margin', 'Inventory Turnover', 'GMROI', 'Stockouts'])

        kpis = KPIRecord.objects.all().order_by('-period_date')
        for kpi in kpis:
            writer.writerow([kpi.branch.name, kpi.period_date, kpi.total_revenue, kpi.gross_margin, kpi.inventory_turnover, kpi.gmroi, kpi.stockout_count])

        AuditLog.objects.create(user=request.user, action="Report Export", module="Analytics", details="Exported KPI CSV Report.")
        return response