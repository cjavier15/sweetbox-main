from django.contrib import admin
from .models import Ingredient, IngredientStock, ProductStock, BillOfMaterial, StockAdjustment, RestockRequest, ConstraintParameter

admin.site.register(Ingredient)
admin.site.register(IngredientStock)
admin.site.register(ProductStock)
admin.site.register(BillOfMaterial)
admin.site.register(StockAdjustment)
admin.site.register(RestockRequest)
admin.site.register(ConstraintParameter)