from django.db import models
from django.conf import settings

class PrescriptiveOutput(models.Model):
    prescriptive_output_ID = models.AutoField(primary_key=True)
    branch = models.ForeignKey('accounts.Branch', related_name='prescriptive_outputs', on_delete=models.CASCADE)
    product = models.ForeignKey('pos.Product', on_delete=models.SET_NULL, null=True, blank=True)
    ingredient = models.ForeignKey('inventory.Ingredient', on_delete=models.SET_NULL, null=True, blank=True)
    constraint = models.ForeignKey('inventory.ConstraintParameter', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Categorizes the output: 'Production Target', 'Restock Prescription', 'Pricing Guidance'
    output_type = models.CharField(max_length=100) 
    recommendation = models.TextField()
    # Stores the constraint justification explaining the reasoning behind the recommendation
    justification = models.TextField() 
    
    recommended_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    recommended_date = models.DateField(null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Tracks managerial approval workflow: 'Pending Review', 'Approved', 'Overridden', 'Expired'
    status = models.CharField(max_length=50, default='Pending Review') 
    is_overridden = models.BooleanField(default=False)
    override_reason = models.TextField(null=True, blank=True)
    
    generated_at = models.DateTimeField(auto_now_add=True)
    expired_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"[{self.output_type}] {self.branch.name} - {self.status} ({self.generated_at.strftime('%Y-%m-%d')})"

class ChatbotLog(models.Model):
    chatbot_log_ID = models.AutoField(primary_key=True)
    branch = models.ForeignKey('accounts.Branch', related_name='chatbot_logs', on_delete=models.CASCADE)
    prescriptive_output = models.ForeignKey(PrescriptiveOutput, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    query_text = models.TextField()
    response_text = models.TextField()
    created_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Query by {self.user.name} on {self.created_time.strftime('%Y-%m-%d %H:%M')}"

class ProductClassification(models.Model):
    classification_ID = models.AutoField(primary_key=True)
    product = models.ForeignKey('pos.Product', related_name='classifications', on_delete=models.CASCADE)
    # Classifications: 'Best-Selling', 'Slow-Moving', 'Seasonal'
    classification = models.CharField(max_length=50) 
    recommended_action = models.TextField()
    classified_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.product_name} - {self.classification}"

class ExternalVariable(models.Model):
    variable_ID = models.AutoField(primary_key=True)
    branch = models.ForeignKey('accounts.Branch', related_name='external_variables', on_delete=models.CASCADE, null=True, blank=True)
    # Variable Types: 'Holiday', 'Payday Cycle', 'Academic Calendar', 'Weather Seasonality'
    variable_type = models.CharField(max_length=100) 
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    impact_level = models.CharField(max_length=50) # e.g., 'High', 'Medium', 'Low'
    description = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.variable_type}) - {self.impact_level} Impact"

class KPIRecord(models.Model):
    kpi_ID = models.AutoField(primary_key=True)
    branch = models.ForeignKey('accounts.Branch', related_name='kpi_records', on_delete=models.CASCADE)
    
    inventory_turnover = models.DecimalField(max_digits=10, decimal_places=2)
    gmroi = models.DecimalField(max_digits=10, decimal_places=2) # Gross Margin Return on Investment
    gross_margin = models.DecimalField(max_digits=12, decimal_places=2)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2)
    dead_stock_value = models.DecimalField(max_digits=12, decimal_places=2)
    stockout_count = models.IntegerField(default=0)
    
    period_date = models.DateField()
    computed_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"KPIs for {self.branch.name} ({self.period_date})"

class ArchiveStorage(models.Model):
    archive_ID = models.AutoField(primary_key=True)
    module_table = models.CharField(max_length=100) # e.g., 'TRANSACTIONS', 'INGREDIENT_STOCK'
    record_ID = models.IntegerField()
    archived_data = models.TextField() # Structured JSON string of the historical record
    archived_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Archived {self.module_table} ID:{self.record_ID} at {self.archived_time.strftime('%Y-%m-%d')}"