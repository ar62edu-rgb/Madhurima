"""First-run data: categories and tables always; a sample menu, raw materials and a biriyani recipe on request."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Category, DiningTable, Product, RecipeItem
from .services import move_stock

CATEGORIES = ["Food", "Beverages", "Tea and Coffee", "Snacks", "Main Course", "Desserts",
              "Raw Materials", "Packing Materials", "Other Items"]

# name, category, subcategory, price, unit
SAMPLE_MENU = [
    ("Chicken Biriyani", "Main Course", "Biriyani", 180, "PLATE"),
    ("Mutton Biriyani", "Main Course", "Biriyani", 260, "PLATE"),
    ("Veg Biriyani", "Main Course", "Biriyani", 140, "PLATE"),
    ("Kerala Meals", "Main Course", "Meals", 120, "PLATE"),
    ("Fish Curry Meals", "Main Course", "Meals", 170, "PLATE"),
    ("Chicken Curry", "Main Course", "Curries", 160, "PLATE"),
    ("Beef Fry", "Main Course", "Curries", 170, "PLATE"),
    ("Paneer Butter Masala", "Main Course", "Curries", 180, "PLATE"),
    ("Kerala Parotta", "Food", "Breads", 18, "NOS"),
    ("Chapathi", "Food", "Breads", 15, "NOS"),
    ("Appam", "Food", "Breakfast", 15, "NOS"),
    ("Puttu", "Food", "Breakfast", 40, "PLATE"),
    ("Masala Dosa", "Food", "Breakfast", 70, "PLATE"),
    ("Idli (2 nos)", "Food", "Breakfast", 40, "PLATE"),
    ("Chicken 65", "Snacks", "Starters", 190, "PLATE"),
    ("Pazhampori", "Snacks", "Evening", 15, "NOS"),
    ("Samosa", "Snacks", "Evening", 15, "NOS"),
    ("Tea", "Tea and Coffee", "", 15, "CUP"),
    ("Coffee", "Tea and Coffee", "", 20, "CUP"),
    ("Lime Juice", "Beverages", "Juices", 30, "GLASS"),
    ("Fresh Orange Juice", "Beverages", "Juices", 70, "GLASS"),
    ("Mineral Water 1L", "Beverages", "Packaged", 20, "BTL"),
    ("Payasam", "Desserts", "", 50, "CUP"),
    ("Ice Cream", "Desserts", "", 60, "CUP"),
]

# name, category, unit, purchase price, opening stock, min, gst
RAW = [
    ("Basmati Rice", "Raw Materials", "KG", 110, 50, 10, 5),
    ("Chicken", "Raw Materials", "KG", 220, 20, 5, 0),
    ("Biriyani Masala", "Raw Materials", "KG", 600, 3, 1, 5),
    ("Cooking Oil", "Raw Materials", "LTR", 140, 30, 5, 5),
    ("Onion", "Raw Materials", "KG", 40, 25, 5, 0),
    ("Parcel Container", "Packing Materials", "NOS", 6, 300, 50, 18),
]


def seed_base(db: Session):
    if not db.scalars(select(Category)).first():
        for i, n in enumerate(CATEGORIES):
            db.add(Category(name=n, sort_order=i, show_in_pos=n not in ("Raw Materials", "Packing Materials")))
    if not db.scalars(select(DiningTable)).first():
        for i in range(1, 11):
            db.add(DiningTable(name=f"T{i}", area="Main Hall" if i <= 6 else "Family Hall", seats=4))
        db.add(DiningTable(name="AC1", area="AC Hall", seats=6))
        db.add(DiningTable(name="AC2", area="AC Hall", seats=6))
    db.flush()


def seed_sample(db: Session, username: str):
    cats = {c.name: c.id for c in db.scalars(select(Category))}
    n = 1
    for name, cat, sub, price, unit in SAMPLE_MENU:
        db.add(Product(code=f"M{n:03d}", name=name, category_id=cats.get(cat), subcategory=sub,
                       product_type="MENU", hsn="996331", unit=unit, selling_price=price,
                       purchase_price=round(price * 0.45, 2), gst_rate=5, tax_category="TAXABLE"))
        n += 1
    raw = {}
    for i, (name, cat, unit, pp, stock, mn, gst) in enumerate(RAW, 1):
        p = Product(code=f"R{i:03d}", name=name, category_id=cats.get(cat),
                    product_type="PACKING" if cat == "Packing Materials" else "RAW",
                    hsn="", unit=unit, purchase_price=pp, selling_price=0, gst_rate=gst,
                    tax_category="TAXABLE" if gst else "EXEMPT", min_stock=mn, max_stock=stock * 3,
                    track_stock=True, opening_stock=stock, current_stock=0)
        db.add(p)
        db.flush()
        move_stock(db, p, stock, "OPENING", "OPENING", "Sample opening stock", username)
        raw[name] = p
    db.flush()
    biriyani = db.scalars(select(Product).where(Product.name == "Chicken Biriyani")).first()
    if biriyani:
        biriyani.use_recipe = True
        for ing, qty in (("Basmati Rice", 0.15), ("Chicken", 0.2), ("Biriyani Masala", 0.01),
                         ("Cooking Oil", 0.02), ("Onion", 0.05)):
            db.add(RecipeItem(product_id=biriyani.id, ingredient_id=raw[ing].id, quantity=qty))
