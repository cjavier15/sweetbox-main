"""
Management command: clean_duplicates
-------------------------------------
Safely deduplicates IngredientStock, ProductStock, ProductCategory, and Ingredient
records in the Sweet Box database. This command MUST be run BEFORE applying
migrations that add UniqueConstraints on these tables.

It is idempotent — safe to run multiple times without side effects.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Min
from inventory.models import Ingredient, IngredientStock, ProductStock, BillOfMaterial, StockAdjustment, RestockRequest, ConstraintParameter
from pos.models import ProductCategory, Product
from analytics.models import PrescriptiveOutput
import logging

from accounts.models import Branch
from django.db.models import Q

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Deduplicates records and enforces strict Hub-and-Spoke inventory architecture.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting database deduplication & Hub-and-Spoke sweep...'))

        self._dedup_product_categories()
        self._dedup_ingredients()
        self._dedup_ingredient_stocks()
        self._dedup_product_stocks()
        self._enforce_hub_and_spoke_isolation()
        self._dedup_prescriptive_outputs()

        self.stdout.write(self.style.SUCCESS('Deduplication & Hub-and-Spoke sweep complete. Database is clean.'))

    # -----------------------------------------------------------------
    # 1. ProductCategory — deduplicate case-insensitively by category_name
    # -----------------------------------------------------------------
    def _dedup_product_categories(self):
        seen = {}
        deleted = 0
        for cat in ProductCategory.objects.all().order_by('category_ID'):
            key = cat.category_name.strip().lower()
            if key not in seen:
                seen[key] = cat
            else:
                canonical = seen[key]
                # Re-point all Product FKs from the duplicate to the canonical record
                Product.objects.filter(category=cat).update(category=canonical)
                # Re-point all Ingredient FKs
                Ingredient.objects.filter(category=cat).update(category=canonical)
                cat.delete()
                deleted += 1
        self.stdout.write(f'  ProductCategory: {deleted} duplicate(s) removed.')

    # -----------------------------------------------------------------
    # 2. Ingredient — deduplicate case-insensitively by ingredient_name
    # -----------------------------------------------------------------
    def _dedup_ingredients(self):
        seen = {}
        deleted = 0
        for ing in Ingredient.objects.all().order_by('ingredient_ID'):
            key = ing.ingredient_name.strip().lower()
            if key not in seen:
                seen[key] = ing
            else:
                canonical = seen[key]
                # Reassign all FK references
                BillOfMaterial.objects.filter(ingredient=ing).update(ingredient=canonical)
                IngredientStock.objects.filter(ingredient=ing).update(ingredient=canonical)
                StockAdjustment.objects.filter(ingredients_inventory__ingredient=ing).update()
                RestockRequest.objects.filter(ingredient=ing).update(ingredient=canonical)
                ConstraintParameter.objects.filter(ingredient=ing).update(ingredient=canonical)
                PrescriptiveOutput.objects.filter(ingredient=ing).update(ingredient=canonical)
                ing.delete()
                deleted += 1
        self.stdout.write(f'  Ingredient: {deleted} duplicate(s) removed.')

    # -----------------------------------------------------------------
    # 3. IngredientStock — deduplicate (branch, ingredient) pairs
    #    Merges stock quantities into the canonical (lowest-PK) record.
    # -----------------------------------------------------------------
    def _dedup_ingredient_stocks(self):
        from django.db.models import Sum
        seen = {}
        deleted = 0
        for stock in IngredientStock.objects.all().order_by('ingredient_inventory_ID'):
            key = (stock.branch_id, stock.ingredient_id)
            if key not in seen:
                seen[key] = stock
            else:
                canonical = seen[key]
                # Merge quantities and costs into canonical
                canonical.quantity_available = (
                    float(canonical.quantity_available) + float(stock.quantity_available)
                )
                canonical.total_cost = float(canonical.total_cost) + float(stock.total_cost)
                canonical.save(update_fields=['quantity_available', 'total_cost'])
                # Reassign FK references in StockAdjustment
                StockAdjustment.objects.filter(ingredients_inventory=stock).update(ingredients_inventory=canonical)
                stock.delete()
                deleted += 1
        self.stdout.write(f'  IngredientStock: {deleted} duplicate(s) merged and removed.')

    # -----------------------------------------------------------------
    # 4. ProductStock — deduplicate (branch, product) pairs
    # -----------------------------------------------------------------
    def _dedup_product_stocks(self):
        seen = {}
        deleted = 0
        for stock in ProductStock.objects.all().order_by('product_inventory_ID'):
            key = (stock.branch_id, stock.product_id)
            if key not in seen:
                seen[key] = stock
            else:
                canonical = seen[key]
                canonical.quantity_available = (
                    float(canonical.quantity_available) + float(stock.quantity_available)
                )
                canonical.total_cost = float(canonical.total_cost) + float(stock.total_cost)
                canonical.save(update_fields=['quantity_available', 'total_cost'])
                StockAdjustment.objects.filter(product_inventory=stock).update(product_inventory=canonical)
                stock.delete()
                deleted += 1
        self.stdout.write(f'  ProductStock: {deleted} duplicate(s) merged and removed.')

    # -----------------------------------------------------------------
    # 5. Hub-and-Spoke Isolation Sweep
    #    - Raw materials (IngredientStock, ConstraintParameter, RestockRequest)
    #      are strictly centralized at Ibaan (Main Hub).
    #    - Satellite branches only carry Cake and Pastry products in ProductStock.
    # -----------------------------------------------------------------
    def _enforce_hub_and_spoke_isolation(self):
        hub_branch = Branch.objects.filter(
            Q(main_hub=True) | Q(branch_ID=1) | Q(name__icontains='ibaan')
        ).first()

        if not hub_branch:
            self.stdout.write(self.style.WARNING('  Hub-and-spoke: Main Hub (Ibaan) branch not found, skipping isolation.'))
            return

        # 1. Delete non-hub raw material stock, constraints, and ingredient restock requests
        del_stocks, _ = IngredientStock.objects.exclude(branch=hub_branch).delete()
        del_constraints, _ = ConstraintParameter.objects.filter(ingredient__isnull=False).exclude(branch=hub_branch).delete()
        del_restocks, _ = RestockRequest.objects.filter(ingredient__isnull=False).exclude(destination_branch=hub_branch).delete()
        self.stdout.write(f'  Hub-and-Spoke: Removed non-hub raw materials ({del_stocks} IngredientStock, {del_constraints} ConstraintParameter, {del_restocks} RestockRequest).')

        # 2. Scope ProductStock strictly to Cake & Pastry products across ALL branches (including Main Hub)
        # Non-cake/pastry items (Meals & Drinks) are made-to-order from raw materials via BOM at Main Hub POS.
        non_cp_ids = []
        for ps in ProductStock.objects.all().select_related('product__category'):
            cat_name = (ps.product.category.category_name if ps.product.category else '').strip().lower()
            if not any(k in cat_name for k in ['cake', 'pastry', 'pastries']):
                non_cp_ids.append(ps.pk)

        if non_cp_ids:
            ProductStock.objects.filter(pk__in=non_cp_ids).delete()
            self.stdout.write(f'  Hub-and-Spoke: Removed {len(non_cp_ids)} non-cake/pastry ProductStock records across all branches (pre-made ProductStock is strictly for Cakes & Pastries).')

    # -----------------------------------------------------------------
    # 6. PrescriptiveOutput — remove exact duplicates from seed re-runs
    #    (same branch + ingredient + output_type + status)
    # -----------------------------------------------------------------
    def _dedup_prescriptive_outputs(self):
        from analytics.models import PrescriptiveOutput
        seen = set()
        deleted = 0
        for po in PrescriptiveOutput.objects.all().order_by('prescriptive_output_ID'):
            key = (po.branch_id, po.ingredient_id, po.output_type, po.recommendation[:80])
            if key in seen:
                po.delete()
                deleted += 1
            else:
                seen.add(key)
        self.stdout.write(f'  PrescriptiveOutput: {deleted} exact duplicate(s) removed.')


