"""Seed 7 categories with 3 items each."""
from database import add_category, add_item

SEED_DATA = [
    ("Breakfast", [
        ("Pancakes", 6.50, "Fluffy buttermilk pancakes with maple syrup"),
        ("Eggs Benedict", 9.00, "Poached eggs on English muffin with hollandaise"),
        ("Avocado Toast", 7.50, "Sourdough with smashed avocado and poached egg"),
    ]),
    ("Drinks", [
        ("Espresso", 2.50, "Single shot of Italian roast espresso"),
        ("Fresh Orange Juice", 4.00, "Cold pressed orange juice"),
        ("Iced Latte", 4.50, "Espresso with cold milk and ice"),
    ]),
    ("Lunch", [
        ("Caesar Salad", 8.50, "Romaine, parmesan, croutons, Caesar dressing"),
        ("Club Sandwich", 11.00, "Triple decker with chicken, bacon, lettuce"),
        ("Soup of the Day", 6.00, "Chef's daily homemade soup with bread"),
    ]),
    ("Desserts", [
        ("Chocolate Cake", 5.50, "Rich chocolate layer cake with ganache"),
        ("Tiramisu", 6.50, "Classic Italian coffee-flavoured dessert"),
        ("Ice Cream Sundae", 5.00, "Vanilla ice cream with toppings"),
    ]),
    ("Snacks", [
        ("French Fries", 4.00, "Crispy golden fries with dipping sauce"),
        ("Nachos", 6.50, "Tortilla chips with cheese and salsa"),
        ("Hummus & Pita", 5.50, "House-made hummus with warm pita bread"),
    ]),
    ("Burgers", [
        ("Classic Burger", 10.00, "Beef patty, lettuce, tomato, pickles"),
        ("Cheese Burger", 11.00, "Classic burger with melted cheddar"),
        ("Veggie Burger", 9.50, "Plant-based patty with avocado"),
    ]),
    ("Pizza", [
        ("Margherita", 9.00, "Tomato, mozzarella, fresh basil"),
        ("Pepperoni", 10.50, "Classic pepperoni with tomato sauce"),
        ("Hawaiian", 10.00, "Ham, pineapple, mozzarella"),
    ]),
]

if __name__ == "__main__":
    for category, items in SEED_DATA:
        add_category(category)
        for title, price, desc in items:
            add_item(title, category, price, description=desc)
    print("Seeded 7 categories with 3 items each.")
