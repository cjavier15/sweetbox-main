from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import Branch
from pos.models import Product, ProductCategory

class Ingredient(models.Model):
    ingredient_ID = models.AutoField(primary_key=True)
    ingredient_name = models.CharField(max_length=255)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='ingredients')
    measurement_unit = models.CharField(max_length=50) # e.g., 'kg', 'grams', 'liters'
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.ingredient_name} ({self.measurement_unit})"

    def get_category_name(self):
        if self.category:
            return self.category.category_name
        first_bom = self.billofmaterial_set.select_related('product__category').first()
        if first_bom and first_bom.product.category:
            return first_bom.product.category.category_name
        return "General"

    def is_cake_or_pastry(self):
        cat_name = (self.get_category_name() or "").strip().lower()
        if cat_name in ['cakes', 'cake', 'pastries', 'pastry', 'baking supplies']:
            return True
        boms = list(self.billofmaterial_set.select_related('product__category').all())
        if not boms:
            return False
        return all(
            b.product.category and b.product.category.category_name.strip().lower() in ['cakes', 'cake', 'pastries', 'pastry']
            for b in boms
        )

class IngredientStock(models.Model):
    ingredient_inventory_ID = models.AutoField(primary_key=True)
    branch = models.ForeignKey('accounts.Branch', related_name='ingredient_stocks', on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, related_name='stocks', on_delete=models.PROTECT)
    
    expiry_date = models.DateTimeField(blank=True, null=True)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    quantity_available = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    reorder_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)

    def __str__(self):
        return f"{self.branch.name} - {self.ingredient.ingredient_name}: {self.quantity_available}"

class ProductStock(models.Model):
    product_inventory_ID = models.AutoField(primary_key=True)
    branch = models.ForeignKey('accounts.Branch', related_name='product_stocks', on_delete=models.CASCADE)
    product = models.ForeignKey('pos.Product', related_name='stocks', on_delete=models.PROTECT)
    
    expiry_date = models.DateTimeField(blank=True, null=True)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    quantity_available = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    reorder_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=5.00)

    def __str__(self):
        return f"{self.branch.name} - {self.product.product_name}: {self.quantity_available}"

class BillOfMaterial(models.Model):
    bom_ID = models.AutoField(primary_key=True)
    # The related_name 'bom_ingredients' allows the POS logic to easily fetch all recipe requirements when a product is sold
    product = models.ForeignKey('pos.Product', related_name='bom_ingredients', on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    
    quantity_required = models.DecimalField(max_digits=10, decimal_places=2)
    measurement_unit = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.product.product_name} requires {self.quantity_required} {self.measurement_unit} of {self.ingredient.ingredient_name}"

class StockAdjustment(models.Model):
    adjustments_ID = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    product_inventory = models.ForeignKey(ProductStock, on_delete=models.CASCADE, blank=True, null=True)
    ingredients_inventory = models.ForeignKey(IngredientStock, on_delete=models.CASCADE, blank=True, null=True)
    
    adjustment_type = models.CharField(max_length=50) # e.g., 'Stock-in', 'Stock-out', 'Spoilage'
    quantity_change = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    latest_update = models.DateTimeField(auto_now=True)

class RestockRequest(models.Model):
    restock_ID = models.AutoField(primary_key=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, blank=True, null=True)
    product = models.ForeignKey('pos.Product', on_delete=models.CASCADE, blank=True, null=True)
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='submitted_restocks', on_delete=models.SET_NULL, null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='approved_restocks', on_delete=models.SET_NULL, null=True)
    
    source_branch = models.ForeignKey('accounts.Branch', related_name='outgoing_restocks', on_delete=models.CASCADE)
    destination_branch = models.ForeignKey('accounts.Branch', related_name='incoming_restocks', on_delete=models.CASCADE)
    
    approved_at = models.DateTimeField(blank=True, null=True)
    requested_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50) # 'Pending', 'Approved', 'Rejected'
    request_finished = models.DateTimeField(blank=True, null=True)

class ConstraintParameter(models.Model):
    constraint_ID = models.AutoField(primary_key=True)
    branch = models.ForeignKey('accounts.Branch', related_name='constraints', on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, blank=True, null=True)
    product = models.ForeignKey('pos.Product', on_delete=models.CASCADE, blank=True, null=True)
    
    lead_time_days = models.IntegerField(default=3)
    min_order_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_order_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=9999.00)
    production_limit = models.DecimalField(max_digits=10, decimal_places=2, default=9999.00)
    capacity_limit = models.DecimalField(max_digits=10, decimal_places=2, default=9999.00)
    latest_update = models.DateTimeField(auto_now=True)

    def __str__(self):
        item_name = self.ingredient.ingredient_name if self.ingredient else self.product.product_name if self.product else "General"
        return f"Constraints for {item_name} at {self.branch.name}"

class ProductTransfer(models.Model):
    transfer_ID = models.AutoField(primary_key=True)
    product = models.ForeignKey('pos.Product', related_name='transfers', on_delete=models.CASCADE)
    source_branch = models.ForeignKey('accounts.Branch', related_name='outgoing_transfers', on_delete=models.CASCADE)
    destination_branch = models.ForeignKey('accounts.Branch', related_name='incoming_transfers', on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    transferred_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers_made')
    transfer_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Transfer #{self.transfer_ID}: {self.quantity} x {self.product.product_name} ({self.source_branch.name} -> {self.destination_branch.name})"

@receiver(post_save, sender=IngredientStock)
def auto_calculate_unit_cost(sender, instance, **kwargs):
    """
    Automatically recalculates the master ingredient cost per unit 
    based on the latest stock total_cost / quantity_available.
    """
    if instance.quantity_available > 0 and instance.total_cost > 0:
        new_cost = instance.total_cost / instance.quantity_available
        # Updates the parent ingredient profile silently
        instance.ingredient.cost_per_unit = round(new_cost, 2)
        instance.ingredient.save()