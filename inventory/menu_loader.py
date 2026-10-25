import os
import re
from decimal import Decimal
from django.conf import settings

# -------------------------------------------------------------------------
# Validated Commercial Master Ingredients (58+ Commercial Wholesale Costs)
# -------------------------------------------------------------------------
MASTER_INGREDIENTS = {
    # Baking & Cake Base (Category: Decorated Cakes / Pastries)
    "All-Purpose Flour": ("kg", 65.00, "Decorated Cakes"),
    "Refined Sugar": ("kg", 85.00, "Decorated Cakes"),
    "Unsalted Butter": ("kg", 360.00, "Decorated Cakes"),
    "Fresh Eggs": ("pcs", 8.00, "Decorated Cakes"),
    "Fresh Milk": ("L", 90.00, "Espresso Based"),
    "Whipping Cream": ("L", 240.00, "Decorated Cakes"),
    "Cream Cheese": ("kg", 450.00, "Premium Cakes"),
    "Baking Powder": ("kg", 180.00, "Decorated Cakes"),
    "Vanilla Extract": ("L", 550.00, "Decorated Cakes"),
    "Instant Dry Yeast": ("kg", 280.00, "Pastries"),
    "Graham Cracker Crumbs": ("kg", 180.00, "Premium Cakes"),
    "Mascarpone Cheese": ("kg", 620.00, "Best Seller Cakes"),
    "Ladyfinger Biscuits": ("kg", 320.00, "Best Seller Cakes"),
    "Kataifi Pastry Shreds": ("kg", 580.00, "Pastries"),
    "Food Gel Coloring": ("L", 400.00, "Decorated Cakes"),
    "Cake Box & Board Packaging": ("pcs", 22.00, "Decorated Cakes"),
    "Pastry Box / Tub Packaging": ("pcs", 6.00, "Pastries"),

    # Cake & Pastry Flavorings
    "Cocoa Powder": ("kg", 260.00, "Decorated Cakes"),
    "Belgian Dark Chocolate": ("kg", 520.00, "Premium Cakes"),
    "White Chocolate Shavings": ("kg", 460.00, "Premium Cakes"),
    "Ube Halaya": ("kg", 300.00, "Decorated Cakes"),
    "Fresh Mangoes": ("kg", 150.00, "Everyday Cakes"),
    "Strawberry Puree": ("L", 320.00, "Fruit Tea"),
    "Blueberry Compote": ("kg", 350.00, "Premium Cakes"),
    "Mixed Berries Puree": ("L", 340.00, "Fruit Tea"),
    "Peach Halves": ("kg", 220.00, "Decorated Cakes"),
    "Cherry Filling": ("kg", 360.00, "Everyday Cakes"),
    "Crushed Oreo": ("kg", 280.00, "Everyday Cakes"),
    "Nutella Spread": ("kg", 490.00, "Best Seller Cakes"),
    "Biscoff Spread": ("kg", 540.00, "Premium Cakes"),
    "Pistachio Paste": ("kg", 780.00, "Pastries"),
    "Sliced Almonds": ("kg", 580.00, "Best Seller Cakes"),
    "Condensed Milk / Yema": ("L", 130.00, "Everyday Cakes"),
    "Caramel Syrup": ("L", 230.00, "Everyday Cakes"),
    "Grated Carrots": ("kg", 85.00, "Everyday Cakes"),
    "Cheddar Cheese": ("kg", 390.00, "Burgers & Sandwiches"),
    "Cinnamon Powder": ("kg", 420.00, "Pastries"),

    # Beverage Base
    "Espresso Coffee Beans": ("kg", 600.00, "Espresso Based"),
    "Black Tea Leaves": ("kg", 380.00, "Milk Tea"),
    "Non-Dairy Creamer": ("kg", 180.00, "Milk Tea"),
    "Fructose Syrup": ("L", 120.00, "Milk Tea"),
    "Tapioca Pearls / Boba": ("kg", 130.00, "Milk Tea"),
    "Okinawa Brown Sugar Syrup": ("L", 240.00, "Milk Tea"),
    "Wintermelon Syrup": ("L", 230.00, "Milk Tea"),
    "Rock Salt Cheese Puff Powder": ("kg", 390.00, "Milk Tea"),
    "Coffee Jelly Cubes": ("kg", 160.00, "Espresso Based"),
    "Chocolate Java Chips": ("kg", 350.00, "Frappe Coffee Based"),
    "Matcha Powder": ("kg", 880.00, "Milk Tea"),
    "Taro Powder": ("kg", 350.00, "Milk Tea"),
    "White Chocolate Sauce": ("L", 320.00, "Espresso Based"),
    "Hazelnut Syrup": ("L", 290.00, "Espresso Based"),
    "Passion Fruit Syrup": ("L", 300.00, "Fruit Tea"),
    "Lemon Juice": ("L", 160.00, "Other Drinks"),
    "Ice Cubes": ("kg", 12.00, "Milk Tea"),
    "Cup & Lid Packaging": ("pcs", 4.50, "Milk Tea"),

    # Kitchen / Savory Base
    "Jasmine Rice": ("kg", 56.00, "Rice Meals"),
    "Cooking Oil": ("L", 90.00, "Rice Meals"),
    "Pork Tapa / Sisig Meat": ("kg", 320.00, "Rice Meals"),
    "Pork Tocino": ("kg", 300.00, "Rice Meals"),
    "Beef Tapa / Patty / Ground Beef": ("kg", 380.00, "Rice Meals"),
    "Corned Beef": ("kg", 270.00, "Rice Meals"),
    "Chicken Fillet": ("kg", 250.00, "Rice Meals"),
    "Tuna Flakes": ("kg", 260.00, "Pasta"),
    "Hotdog / Sausage / Spam": ("kg", 220.00, "Rice Meals"),
    "Sliced Sweet Ham": ("kg", 260.00, "Burgers & Sandwiches"),
    "Smoked Bacon": ("kg", 450.00, "Pasta"),
    "Pasta Noodles": ("kg", 105.00, "Pasta"),
    "All-Purpose Cream": ("L", 170.00, "Pasta"),
    "Marinara Tomato Sauce": ("L", 150.00, "Pasta"),
    "Basil Pesto Sauce": ("L", 390.00, "Pasta"),
    "Burger Buns / Loaf Bread": ("pcs", 6.50, "Burgers & Sandwiches"),
    "Fresh Lettuce & Tomatoes": ("kg", 110.00, "Burgers & Sandwiches"),
    "Mayonnaise & Dressing": ("L", 160.00, "Burgers & Sandwiches"),
    "Pineapple Slices": ("kg", 150.00, "Gourmet Burgers & Sandwiches"),
    "Nacho Tortilla Chips": ("kg", 200.00, "Finger Foods"),
    "Nacho Cheese Sauce": ("L", 200.00, "Finger Foods"),
    "French Fries Potatoes": ("kg", 130.00, "Finger Foods"),
    "Fries Seasoning Powder": ("kg", 260.00, "Finger Foods"),
    "Flour Tortilla Wrap": ("pcs", 10.00, "Finger Foods"),
    "Button Mushrooms": ("kg", 190.00, "Rice Meals"),
}

# -------------------------------------------------------------------------
# Commercial Size Multiplier Engine
# -------------------------------------------------------------------------
def get_size_multiplier(category_name, size_tag):
    cat = (category_name or '').strip().lower()
    s = (size_tag or '').strip().lower()

    if 'cake' in cat:
        if any(k in s for k in ['10"', '10x3', '10 in']):
            return Decimal('2.50')
        if any(k in s for k in ['9x4', '9"', '9 in']):
            return Decimal('2.20')
        if any(k in s for k in ['10x2', '8x3']):
            return Decimal('1.95')
        if any(k in s for k in ['7x4', '7"', '9x9', '7 in']):
            return Decimal('1.75')
        if any(k in s for k in ['8x2', '8"', '6x4', '8 in']):
            return Decimal('1.35')
        if any(k in s for k in ['6x2', '6"', '6 in']):
            return Decimal('1.00')
        return Decimal('1.00')

    if any(k in cat for k in ['tea', 'coffee', 'espresso', 'frappe', 'drink']):
        if '12oz' in s or ('hot' in s and '12' in s):
            return Decimal('0.80')
        if any(k in s for k in ['22oz', 'grande']):
            return Decimal('1.25')
        if any(k in s for k in ['16oz', 'medio', 'cold', 'iced']):
            return Decimal('1.00')
        return Decimal('1.00')

    if 'pastr' in cat:
        if 'box' in s:
            return Decimal('3.20')
        if any(k in s for k in ['tub', 'tab', 'bento']):
            return Decimal('2.20')
        if any(k in s for k in ['slice', 'cc', 'cookie']):
            return Decimal('1.40')
        return Decimal('1.00')

    return Decimal('1.00')

# -------------------------------------------------------------------------
# Commercial BOM Recipe Engine (Strict 31% - 37% Food Cost & >= 0.01 Qty)
# -------------------------------------------------------------------------
def make_recipe(name, category, size_tag):
    mult = get_size_multiplier(category, size_tag)
    recipe = []

    def add_ing(ing_name, base_qty, scale=True):
        if scale:
            qty = max(round(Decimal(str(base_qty)) * mult, 2), Decimal('0.01'))
        else:
            qty = max(round(Decimal(str(base_qty)), 2), Decimal('0.01'))
        unit = MASTER_INGREDIENTS[ing_name][0]
        recipe.append((ing_name, qty, unit))

    n_lower = name.lower()
    cat_lower = category.lower()

    if 'cake' in cat_lower:
        # Base (scaled by size)
        add_ing("All-Purpose Flour", 0.15, scale=True)
        add_ing("Refined Sugar", 0.10, scale=True)
        add_ing("Fresh Eggs", 3.0, scale=True)
        add_ing("Unsalted Butter", 0.06, scale=True)
        add_ing("Whipping Cream", 0.12, scale=True)
        # Unscaled packaging
        add_ing("Cake Box & Board Packaging", 1.0, scale=False)

        # Flavors
        if 'cheesecake' in n_lower:
            add_ing("Cream Cheese", 0.20, scale=True)
            add_ing("Graham Cracker Crumbs", 0.08, scale=True)
        if 'ube' in n_lower:
            add_ing("Ube Halaya", 0.10, scale=True)
        if 'mango' in n_lower:
            add_ing("Fresh Mangoes", 0.12, scale=True)
        if any(k in n_lower for k in ['belgian', 'ganache', 'decadent']):
            add_ing("Belgian Dark Chocolate", 0.08, scale=True)
        elif 'choco' in n_lower or 'black velvet' in n_lower:
            add_ing("Cocoa Powder", 0.06, scale=True)
        if 'mocha' in n_lower or 'coffee' in n_lower:
            add_ing("Espresso Coffee Beans", 0.02, scale=True)
        if 'oreo' in n_lower:
            add_ing("Crushed Oreo", 0.07, scale=True)
        if 'red velvet' in n_lower:
            add_ing("Cocoa Powder", 0.03, scale=True)
            add_ing("Cream Cheese", 0.07, scale=True)
            add_ing("Food Gel Coloring", 0.01, scale=False)
        if 'tiramisu' in n_lower:
            add_ing("Mascarpone Cheese", 0.12, scale=True)
            add_ing("Ladyfinger Biscuits", 0.08, scale=True)
            add_ing("Espresso Coffee Beans", 0.02, scale=True)
        if 'nutella' in n_lower:
            add_ing("Nutella Spread", 0.07, scale=True)
        if 'biscoff' in n_lower:
            add_ing("Biscoff Spread", 0.07, scale=True)
        if 'almond' in n_lower:
            add_ing("Sliced Almonds", 0.05, scale=True)
        if 'caramel' in n_lower:
            add_ing("Caramel Syrup", 0.06, scale=True)
        if 'yema' in n_lower:
            add_ing("Condensed Milk / Yema", 0.10, scale=True)
        if 'carrot' in n_lower:
            add_ing("Grated Carrots", 0.12, scale=True)
        if 'blueberry' in n_lower:
            add_ing("Blueberry Compote", 0.08, scale=True)
        if 'peach' in n_lower:
            add_ing("Peach Halves", 0.08, scale=True)
        if 'forrest' in n_lower or 'forest' in n_lower:
            add_ing("Cherry Filling", 0.08, scale=True)
            if 'white' in n_lower:
                add_ing("White Chocolate Shavings", 0.07, scale=True)
            else:
                add_ing("Belgian Dark Chocolate", 0.07, scale=True)
        if any(k in n_lower for k in ['vanilla', 'minimalist', 'rosette', 'wreath', 'kiss', 'pipe', 'sunflower', 'daisy', 'floral', 'buttercream', 'drip']):
            add_ing("Vanilla Extract", 0.01, scale=False)
        if any(k in n_lower for k in ['blue', 'pink', 'red', 'floral', 'rosette', 'wreath', 'sunflower', 'daisy']):
            add_ing("Food Gel Coloring", 0.01, scale=False)

    elif cat_lower == 'pastries':
        # Base (scaled by size)
        add_ing("All-Purpose Flour", 0.04, scale=True)
        add_ing("Refined Sugar", 0.02, scale=True)
        add_ing("Unsalted Butter", 0.02, scale=True)
        add_ing("Fresh Eggs", 0.50, scale=True)
        # Unscaled packaging
        add_ing("Pastry Box / Tub Packaging", 1.0, scale=False)

        # Flavors
        if any(k in n_lower for k in ['ensymada', 'bread', 'roll', 'croissant']):
            add_ing("Instant Dry Yeast", 0.01, scale=False)
        if 'dubai' in n_lower:
            add_ing("Kataifi Pastry Shreds", 0.02, scale=False)
            add_ing("Pistachio Paste", 0.02, scale=False)
            add_ing("Belgian Dark Chocolate", 0.02, scale=False)
        elif 'pistachio' in n_lower:
            add_ing("Pistachio Paste", 0.01, scale=True)
        if 'cc' in n_lower or 'cheese' in n_lower:
            if 'cc' in n_lower:
                add_ing("Cream Cheese", 0.02, scale=True)
            else:
                add_ing("Cheddar Cheese", 0.02, scale=True)
        if any(k in n_lower for k in ['choco', 'brownie', 'brigadero']):
            add_ing("Cocoa Powder", 0.02, scale=True)
        if 'rv' in n_lower:
            add_ing("Cocoa Powder", 0.01, scale=True)
            add_ing("Cream Cheese", 0.02, scale=True)
        if 'carrot' in n_lower:
            add_ing("Grated Carrots", 0.03, scale=True)
        if 'blueberry' in n_lower:
            add_ing("Blueberry Compote", 0.02, scale=True)
        if 'caramel' in n_lower:
            add_ing("Caramel Syrup", 0.02, scale=True)
        if 'ube' in n_lower:
            add_ing("Ube Halaya", 0.02, scale=True)
        if 'leche' in n_lower or 'custard' in n_lower:
            add_ing("Condensed Milk / Yema", 0.03, scale=True)
        if 'cinnamon' in n_lower:
            add_ing("Cinnamon Powder", 0.01, scale=False)
        if 'nutella' in n_lower:
            add_ing("Nutella Spread", 0.02, scale=True)
        if 'hotdog' in n_lower:
            add_ing("Hotdog / Sausage / Spam", 0.03, scale=False)
        if 'ham' in n_lower:
            add_ing("Sliced Sweet Ham", 0.03, scale=False)

    elif any(k in cat_lower for k in ['tea', 'espresso', 'frappe', 'other drinks']):
        # Packaging & Ice
        add_ing("Cup & Lid Packaging", 1.0, scale=False)
        if 'hot' not in n_lower:
            add_ing("Ice Cubes", 0.12, scale=True)

        # Base by category
        if cat_lower == 'milk tea':
            add_ing("Black Tea Leaves", 0.01, scale=False)
            add_ing("Non-Dairy Creamer", 0.02, scale=True)
            add_ing("Fructose Syrup", 0.02, scale=True)
            add_ing("Tapioca Pearls / Boba", 0.03, scale=True)
        elif cat_lower in ['espresso based', 'frappe coffee based']:
            beans_qty = 0.01 if mult <= Decimal('1.0') else 0.02
            add_ing("Espresso Coffee Beans", beans_qty, scale=False)
            if 'americano' not in n_lower:
                add_ing("Fresh Milk", 0.12, scale=True)
            if 'frappe' in cat_lower:
                add_ing("Whipping Cream", 0.02, scale=False)
        elif cat_lower in ['non-espresso based', 'frappe non-coffee based']:
            add_ing("Fresh Milk", 0.12, scale=True)
            add_ing("Fructose Syrup", 0.02, scale=True)
            if 'frappe' in cat_lower:
                add_ing("Whipping Cream", 0.02, scale=False)
        elif cat_lower == 'fruit tea':
            add_ing("Black Tea Leaves", 0.01, scale=False)
            add_ing("Fructose Syrup", 0.02, scale=True)
        elif cat_lower == 'other drinks':
            add_ing("Fructose Syrup", 0.01, scale=False)
            if 'lemonade' in n_lower:
                add_ing("Lemon Juice", 0.02, scale=True)
            else:
                add_ing("Black Tea Leaves", 0.01, scale=True)

        # Drink Flavorings
        if 'okinawa' in n_lower:
            add_ing("Okinawa Brown Sugar Syrup", 0.02, scale=True)
        if 'wintermelon' in n_lower:
            add_ing("Wintermelon Syrup", 0.02, scale=True)
        if 'matcha' in n_lower:
            add_ing("Matcha Powder", 0.01, scale=False)
        if 'oreo' in n_lower:
            add_ing("Crushed Oreo", 0.02, scale=True)
        if 'cheesepuff' in n_lower or 'cheesecake' in n_lower:
            add_ing("Rock Salt Cheese Puff Powder", 0.02, scale=False)
        if 'nutella' in n_lower:
            add_ing("Nutella Spread", 0.02, scale=False)
        if 'white' in n_lower and ('mocha' in n_lower or 'choco' in n_lower):
            add_ing("White Chocolate Sauce", 0.02, scale=True)
        elif 'dark' in n_lower and ('mocha' in n_lower or 'choco' in n_lower):
            add_ing("Belgian Dark Chocolate", 0.02, scale=False)
        elif any(k in n_lower for k in ['choco', 'mocha', 'red velvet']):
            add_ing("Cocoa Powder", 0.02, scale=False)
        if 'hazelnut' in n_lower:
            add_ing("Hazelnut Syrup", 0.02, scale=True)
        if 'blueberry' in n_lower or 'bluberry' in n_lower:
            add_ing("Blueberry Compote", 0.02, scale=True)
        if 'strawberry' in n_lower:
            add_ing("Strawberry Puree", 0.02, scale=True)
        if 'taro' in n_lower:
            add_ing("Taro Powder", 0.02, scale=True)
        if 'caramel' in n_lower:
            add_ing("Caramel Syrup", 0.02, scale=True)
        if 'spanish' in n_lower:
            add_ing("Condensed Milk / Yema", 0.03, scale=True)
        if 'vanilla' in n_lower:
            add_ing("Vanilla Extract", 0.01, scale=False)
        if 'coffee jelly' in n_lower:
            add_ing("Coffee Jelly Cubes", 0.04, scale=True)
        if 'peach' in n_lower or 'mango' in n_lower:
            add_ing("Fresh Mangoes", 0.03, scale=True)
        if 'berries' in n_lower:
            add_ing("Mixed Berries Puree", 0.02, scale=True)
        if 'passion' in n_lower:
            add_ing("Passion Fruit Syrup", 0.02, scale=True)
        if 'java chip' in n_lower:
            add_ing("Chocolate Java Chips", 0.02, scale=False)

    elif cat_lower == 'rice meals':
        add_ing("Jasmine Rice", 0.08, scale=True)
        add_ing("Cooking Oil", 0.01, scale=True)
        if 'silog' in n_lower or 'egg' in n_lower:
            add_ing("Fresh Eggs", 1.0, scale=False)
        if 'sisilog' in n_lower or ('sisig' in n_lower and 'tuna' not in n_lower) or 'tapsilog pork' in n_lower:
            add_ing("Pork Tapa / Sisig Meat", 0.09, scale=True)
        elif 'tapsilog beef' in n_lower or 'beef' in n_lower or 'burger steak' in n_lower:
            add_ing("Beef Tapa / Patty / Ground Beef", 0.08, scale=True)
        elif 'tosilog' in n_lower:
            add_ing("Pork Tocino", 0.09, scale=True)
        elif any(k in n_lower for k in ['hotsilog', 'sausage', 'spam']):
            add_ing("Hotdog / Sausage / Spam", 0.09, scale=True)
        elif 'cornsilog' in n_lower:
            add_ing("Corned Beef", 0.09, scale=True)
        elif 'chick' in n_lower:
            add_ing("Chicken Fillet", 0.10, scale=True)
        elif 'tuna' in n_lower:
            add_ing("Tuna Flakes", 0.09, scale=True)
        if 'bacon' in n_lower:
            add_ing("Smoked Bacon", 0.04, scale=True)
        if any(k in n_lower for k in ['mushroom', 'burger steak', 'ala king']):
            add_ing("Button Mushrooms", 0.03, scale=True)
            add_ing("All-Purpose Cream", 0.03, scale=True)
        if 'cheesy' in n_lower:
            add_ing("Cheddar Cheese", 0.02, scale=True)
        if 'marinara' in n_lower:
            add_ing("Marinara Tomato Sauce", 0.04, scale=True)

    elif cat_lower == 'pasta':
        if 'combo' in n_lower:
            add_ing("Black Tea Leaves", 0.01, scale=False)
            add_ing("Cup & Lid Packaging", 1.0, scale=False)
            if 'chicken' in n_lower:
                add_ing("Chicken Fillet", 0.08, scale=True)
                add_ing("Jasmine Rice", 0.08, scale=True)
            else:
                add_ing("Burger Buns / Loaf Bread", 1.0, scale=False)
                add_ing("Beef Tapa / Patty / Ground Beef", 0.04, scale=True)
                add_ing("French Fries Potatoes", 0.06, scale=True)
        else:
            add_ing("Pasta Noodles", 0.09, scale=True)
            if 'spaghetti' in n_lower:
                add_ing("Marinara Tomato Sauce", 0.06, scale=True)
                add_ing("Beef Tapa / Patty / Ground Beef", 0.03, scale=True)
            else:
                add_ing("All-Purpose Cream", 0.05, scale=True)
            if 'carbonara' in n_lower or 'bacon' in n_lower:
                add_ing("Smoked Bacon", 0.03, scale=True)
            if 'tuna' in n_lower:
                add_ing("Tuna Flakes", 0.05, scale=True)
            if 'pesto' in n_lower:
                add_ing("Basil Pesto Sauce", 0.02, scale=True)
            if 'sausage' in n_lower:
                add_ing("Hotdog / Sausage / Spam", 0.05, scale=True)
            if 'cheesy' in n_lower:
                add_ing("Cheddar Cheese", 0.02, scale=True)

    elif cat_lower == 'finger foods':
        add_ing("Cooking Oil", 0.01, scale=True)
        if 'fries' in n_lower and 'nachos' not in n_lower:
            add_ing("French Fries Potatoes", 0.15, scale=True)
            if 'seasoned' in n_lower:
                add_ing("Fries Seasoning Powder", 0.02, scale=True)
        if 'nachos' in n_lower:
            add_ing("Nacho Tortilla Chips", 0.07, scale=True)
            add_ing("Nacho Cheese Sauce", 0.03, scale=True)
            add_ing("Beef Tapa / Patty / Ground Beef", 0.03, scale=True)
            if 'fries' in n_lower:
                add_ing("French Fries Potatoes", 0.06, scale=True)
            if 'salad' in n_lower:
                add_ing("Fresh Lettuce & Tomatoes", 0.03, scale=True)
        if 'quesadilla' in n_lower:
            add_ing("Flour Tortilla Wrap", 1.0, scale=False)
            add_ing("Cheddar Cheese", 0.04, scale=True)
            if 'beefy' in n_lower:
                add_ing("Beef Tapa / Patty / Ground Beef", 0.04, scale=True)

    elif 'burger' in cat_lower or 'sandwich' in cat_lower:
        if 'combo' in n_lower:
            add_ing("Black Tea Leaves", 0.01, scale=False)
            add_ing("Cup & Lid Packaging", 1.0, scale=False)
            if 'chicken' in n_lower:
                add_ing("Chicken Fillet", 0.08, scale=True)
                add_ing("Jasmine Rice", 0.08, scale=True)
            else:
                add_ing("Burger Buns / Loaf Bread", 1.0, scale=False)
                add_ing("Beef Tapa / Patty / Ground Beef", 0.04, scale=True)
                add_ing("French Fries Potatoes", 0.06, scale=True)
        else:
            add_ing("Burger Buns / Loaf Bread", 1.0, scale=False)
            add_ing("Mayonnaise & Dressing", 0.01, scale=True)
            add_ing("Fresh Lettuce & Tomatoes", 0.02, scale=True)
            if 'double' in n_lower or 'upgrade' in n_lower:
                add_ing("Beef Tapa / Patty / Ground Beef", 0.06, scale=True)
            elif 'ham' in n_lower:
                add_ing("Sliced Sweet Ham", 0.04, scale=True)
                if 'grilled' in n_lower:
                    add_ing("Cheddar Cheese", 0.02, scale=True)
            elif 'tuna' in n_lower:
                add_ing("Tuna Flakes", 0.05, scale=True)
                if 'melt' in n_lower:
                    add_ing("Cheddar Cheese", 0.02, scale=True)
            elif 'chicken' in n_lower:
                add_ing("Chicken Fillet", 0.08, scale=True)
            elif 'grilled cheese' in n_lower:
                add_ing("Cheddar Cheese", 0.05, scale=True)
                add_ing("Unsalted Butter", 0.01, scale=True)
            else:
                beef_qty = 0.03 if cat_lower == 'burgers & sandwiches' else 0.06
                add_ing("Beef Tapa / Patty / Ground Beef", beef_qty, scale=True)
            if 'cheese' in n_lower and 'grilled cheese' not in n_lower:
                add_ing("Cheddar Cheese", 0.02, scale=True)
            if 'hawaiian' in n_lower:
                add_ing("Pineapple Slices", 0.03, scale=True)
                add_ing("Sliced Sweet Ham", 0.02, scale=True)
            if 'bacon' in n_lower:
                add_ing("Smoked Bacon", 0.02, scale=True)
            if 'mushroom' in n_lower:
                add_ing("Button Mushrooms", 0.02, scale=True)

    consolidated = {}
    for ing_name, qty, unit in recipe:
        if ing_name in consolidated:
            consolidated[ing_name] = (consolidated[ing_name][0] + qty, unit)
        else:
            consolidated[ing_name] = (qty, unit)
    return [(k, v[0], v[1]) for k, v in consolidated.items()]

# -------------------------------------------------------------------------
# Excel Menu Parser (products/Sweetboox_Menu.xlsx & SweetBox_Cakes_Pastries.xlsx)
# -------------------------------------------------------------------------
def _is_num(val):
    if val is None:
        return False
    s = str(val).strip()
    return s != '' and s.replace('.', '', 1).isdigit()

def _clean_str(val):
    return str(val).strip() if val is not None else ''

def _get_val(row, col_idx):
    if row is not None and col_idx < len(row):
        return row[col_idx]
    return None

def parse_excel_menu(base_dir=None):
    import openpyxl

    if not base_dir:
        try:
            base_dir = getattr(settings, 'BASE_DIR', os.getcwd())
        except Exception:
            base_dir = os.getcwd()
    
    f_menu = os.path.join(base_dir, 'products', 'Sweetboox_Menu.xlsx')
    f_cakes = os.path.join(base_dir, 'products', 'SweetBox_Cakes_Pastries.xlsx')

    if not os.path.exists(f_menu) or not os.path.exists(f_cakes):
        # Fallback to local products directory relative to file
        local_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        f_menu = os.path.join(local_dir, 'products', 'Sweetboox_Menu.xlsx')
        f_cakes = os.path.join(local_dir, 'products', 'SweetBox_Cakes_Pastries.xlsx')

    wb_menu = openpyxl.load_workbook(f_menu, data_only=True, read_only=True)
    wb_cakes = openpyxl.load_workbook(f_cakes, data_only=True, read_only=True)

    products = []

    # 1. Beverages Sheet
    rows_bev = list(wb_menu['Beverages'].iter_rows(values_only=True))[1:]

    # Milk Tea: Cols 0, 1, 2
    for row in rows_bev:
        name_val = _get_val(row, 0)
        if name_val is None or _clean_str(name_val) == '':
            continue
        name = _clean_str(name_val)
        p16 = _get_val(row, 1)
        p22 = _get_val(row, 2)
        if _is_num(p16):
            products.append({'name': f'{name} Milk Tea (16oz)', 'category': 'Milk Tea', 'price': float(p16), 'size_tag': '16oz'})
        if _is_num(p22):
            products.append({'name': f'{name} Milk Tea (22oz)', 'category': 'Milk Tea', 'price': float(p22), 'size_tag': '22oz'})

    # Espresso Based (Rows 0-10)
    for idx in range(0, 11):
        if idx >= len(rows_bev): break
        row = rows_bev[idx]
        name_val = _get_val(row, 4)
        if name_val is None or _clean_str(name_val) == '': continue
        name = _clean_str(name_val)
        p_hot = _get_val(row, 5)
        p_iced16 = _get_val(row, 6)
        p_iced22 = _get_val(row, 7)
        if _is_num(p_hot):
            products.append({'name': f'{name} (Hot 12oz)', 'category': 'Espresso Based', 'price': float(p_hot), 'size_tag': '12oz'})
        if _is_num(p_iced16):
            products.append({'name': f'{name} (Iced 16oz)', 'category': 'Espresso Based', 'price': float(p_iced16), 'size_tag': '16oz'})
        if _is_num(p_iced22):
            products.append({'name': f'{name} (Iced 22oz)', 'category': 'Espresso Based', 'price': float(p_iced22), 'size_tag': '22oz'})

    # Non-Espresso Based (Rows 14-end)
    for idx in range(14, len(rows_bev)):
        row = rows_bev[idx]
        name_val = _get_val(row, 4)
        if name_val is None or _clean_str(name_val) == '': continue
        name = _clean_str(name_val)
        p_hot = _get_val(row, 5)
        p_cold16 = _get_val(row, 6)
        p_cold22 = _get_val(row, 7)
        if _is_num(p_hot):
            products.append({'name': f'{name} (Hot 12oz)', 'category': 'Non-Espresso Based', 'price': float(p_hot), 'size_tag': '12oz'})
        if _is_num(p_cold16):
            products.append({'name': f'{name} (Cold 16oz)', 'category': 'Non-Espresso Based', 'price': float(p_cold16), 'size_tag': '16oz'})
        if _is_num(p_cold22):
            products.append({'name': f'{name} (Cold 22oz)', 'category': 'Non-Espresso Based', 'price': float(p_cold22), 'size_tag': '22oz'})

    # Fruit Tea & Frappes: Cols 9, 10, 11
    # Fruit Tea (Rows 0-3)
    for idx in range(0, 4):
        if idx >= len(rows_bev): break
        row = rows_bev[idx]
        name_val = _get_val(row, 9)
        if name_val is None or _clean_str(name_val) == '': continue
        name = _clean_str(name_val)
        if name.lower() == 'mised berries':
            name = 'Mixed Berries'
        p_medio = _get_val(row, 10)
        p_grande = _get_val(row, 11)
        if _is_num(p_medio):
            products.append({'name': f'{name} Fruit Tea (Medio)', 'category': 'Fruit Tea', 'price': float(p_medio), 'size_tag': 'Medio'})
        if _is_num(p_grande):
            products.append({'name': f'{name} Fruit Tea (Grande)', 'category': 'Fruit Tea', 'price': float(p_grande), 'size_tag': 'Grande'})

    # Frappe Coffee Based (Rows 7-10)
    for idx in range(7, 11):
        if idx >= len(rows_bev): break
        row = rows_bev[idx]
        name_val = _get_val(row, 9)
        if name_val is None or _clean_str(name_val) == '': continue
        price = _get_val(row, 10)
        if _is_num(price):
            products.append({'name': f'{_clean_str(name_val)} Frappe', 'category': 'Frappe Coffee Based', 'price': float(price), 'size_tag': '16oz'})

    # Frappe Non-Coffee Based (Rows 14-20)
    for idx in range(14, len(rows_bev)):
        row = rows_bev[idx]
        name_val = _get_val(row, 9)
        if name_val is None or _clean_str(name_val) == '': continue
        price = _get_val(row, 10)
        if _is_num(price):
            products.append({'name': f'{_clean_str(name_val)} Frappe', 'category': 'Frappe Non-Coffee Based', 'price': float(price), 'size_tag': '16oz'})

    # Other Drinks (Rows 0-1)
    for idx in range(0, 2):
        if idx >= len(rows_bev): break
        row = rows_bev[idx]
        name_val = _get_val(row, 13)
        if name_val is None or _clean_str(name_val) == '': continue
        price = _get_val(row, 14)
        if _is_num(price):
            products.append({'name': _clean_str(name_val), 'category': 'Other Drinks', 'price': float(price), 'size_tag': '16oz'})

    # 2. Foods & Snacks Sheet
    rows_food = list(wb_menu['Foods & Snacks'].iter_rows(values_only=True))[1:]

    # Rice Meals (Cols 0, 1)
    for row in rows_food:
        name_val = _get_val(row, 0)
        price = _get_val(row, 1)
        if name_val is None or _clean_str(name_val) == '': continue
        if _is_num(price):
            products.append({'name': _clean_str(name_val), 'category': 'Rice Meals', 'price': float(price), 'size_tag': 'solo'})

    # Pasta (Rows 0-7)
    for idx in range(0, 8):
        if idx >= len(rows_food): break
        row = rows_food[idx]
        name_val = _get_val(row, 3)
        price = _get_val(row, 4)
        if name_val is None or _clean_str(name_val) == '': continue
        if _is_num(price):
            n_str = _clean_str(name_val)
            if 'combo' in n_str.lower():
                n_str = f'{n_str} (Pasta)'
            products.append({'name': n_str, 'category': 'Pasta', 'price': float(price), 'size_tag': 'solo'})

    # Finger Foods (Rows 12-18)
    for idx in range(12, len(rows_food)):
        row = rows_food[idx]
        name_val = _get_val(row, 3)
        price = _get_val(row, 4)
        if name_val is None or _clean_str(name_val) == '': continue
        if _is_num(price):
            n_str = _clean_str(name_val)
            if 'combo' in n_str.lower():
                n_str = f'{n_str} (Finger Foods)'
            products.append({'name': n_str, 'category': 'Finger Foods', 'price': float(price), 'size_tag': 'solo'})

    # Burgers & Sandwiches (Rows 0-5)
    for idx in range(0, 6):
        if idx >= len(rows_food): break
        row = rows_food[idx]
        name_val = _get_val(row, 6)
        price = _get_val(row, 7)
        if name_val is None or _clean_str(name_val) == '': continue
        if _is_num(price):
            n_str = _clean_str(name_val)
            if 'combo' in n_str.lower():
                n_str = f'{n_str} (Burgers & Sandwiches)'
            products.append({'name': n_str, 'category': 'Burgers & Sandwiches', 'price': float(price), 'size_tag': 'solo'})

    # Gourmet Burgers & Sandwiches (Rows 8-17)
    for idx in range(8, len(rows_food)):
        row = rows_food[idx]
        name_val = _get_val(row, 6)
        price = _get_val(row, 7)
        if name_val is None or _clean_str(name_val) == '': continue
        if _is_num(price):
            n_str = _clean_str(name_val)
            if 'combo' in n_str.lower():
                n_str = f'{n_str} (Gourmet Burgers & Sandwiches)'
            products.append({'name': n_str, 'category': 'Gourmet Burgers & Sandwiches', 'price': float(price), 'size_tag': 'solo'})

    # 3. Cakes Sheet
    rows_cakes = list(wb_cakes['cakes'].iter_rows(values_only=True))[1:]
    triplets = [
        (0, 1, 2, 'Decorated Cakes'),
        (4, 5, 6, 'Everyday Cakes'),
        (8, 9, 10, 'Drip Cakes'),
        (12, 13, 14, 'Best Seller Cakes'),
        (16, 17, 18, 'Premium Cakes'),
        (20, 21, 22, 'Square Cakes')
    ]
    for c_name, c_size, c_price, cat in triplets:
        for row in rows_cakes:
            name_val = _get_val(row, c_name)
            size_val = _get_val(row, c_size)
            price_val = _get_val(row, c_price)
            if name_val is None or _clean_str(name_val) == '': continue
            if not _is_num(price_val): continue
            name_str = _clean_str(name_val).title()
            size_str = _clean_str(size_val)
            full_name = f'{name_str} ({size_str})' if size_str else name_str
            products.append({'name': full_name, 'category': cat, 'size_tag': size_str, 'price': float(price_val)})

    # 4. Pastries Sheet
    rows_past = list(wb_cakes['pastries'].iter_rows(values_only=True))[1:]
    ignore_set = {'pastries', 'cake slice', '?', ''}
    clean_map = {
        '(sept5)cinnamon flavored': 'Cinnamon Flavored Pastry',
        '(sep25)assorted': 'Assorted Pastries Box',
        '(sep28)classic cro': 'Classic Croissant',
        '*choco caramel': 'Choco Caramel Slice'
    }
    for col_idx in [1, 2, 3, 4]:
        for row in rows_past:
            val = _get_val(row, col_idx)
            if val is None: continue
            s_val = _clean_str(val)
            if s_val.lower() in ignore_set or s_val == '?': continue
            cleaned = clean_map.get(s_val.lower(), s_val)
            c_low = cleaned.lower()
            if any(k in c_low for k in ['box of 4', 'ensymada box', 'cheese roll box', 'assorted']):
                price, size_tag = 280.00, 'box'
            elif any(k in c_low for k in ['box of 2', 'tub', 'tab', 'bento']):
                price, size_tag = 180.00, 'tub'
            elif any(k in c_low for k in ['slice', ' cc', 'ccbomb', 'cookie']):
                price, size_tag = 120.00, 'slice'
            else:
                price, size_tag = 75.00, 'solo'
            products.append({'name': cleaned.title(), 'category': 'Pastries', 'price': price, 'size_tag': size_tag})

    wb_menu.close()
    wb_cakes.close()

    return products
