"""
Seed data for initial database setup.
Contains Sean's full category taxonomy and account definitions,
imported from the Jupyter notebook analysis.
"""

import logging
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import Category, Account, AmountRule, MerchantMapping

logger = logging.getLogger(__name__)


def seed_categories_and_accounts():
    """Seed the database with categories, accounts, and initial merchant mappings."""
    db = SessionLocal()
    try:
        # Only seed if categories table is empty
        if db.query(Category).count() > 0:
            return

        logger.info("Seeding database with initial data...")

        # ── Parent Categories (Category_2) ──
        PARENT_CATEGORIES = {
            "Food": {"color": "#FF6B6B", "is_income": False},
            "Housing": {"color": "#4ECDC4", "is_income": False},
            "Transportation": {"color": "#45B7D1", "is_income": False},
            "Insurance": {"color": "#96CEB4", "is_income": False},
            "Utilities": {"color": "#FFEAA7", "is_income": False},
            "Medical": {"color": "#DDA0DD", "is_income": False},
            "Government": {"color": "#98D8C8", "is_income": False},
            "Savings": {"color": "#87CEEB", "is_income": False},
            "Personal_Spending": {"color": "#F7DC6F", "is_income": False},
            "Recreation_Entertainment": {"color": "#BB8FCE", "is_income": False},
            "Streaming_Services": {"color": "#E74C3C", "is_income": False},
            "Education": {"color": "#5DADE2", "is_income": False},
            "Travel": {"color": "#F1948A", "is_income": False},
            "Misc": {"color": "#AEB6BF", "is_income": False},
            "People": {"color": "#73C6B6", "is_income": False},
            "Payment_and_Interest": {"color": "#F0B27A", "is_income": False},
            "Income": {"color": "#58D68D", "is_income": True},
            "Balance": {"color": "#85C1E9", "is_income": False},
        }

        parent_map = {}
        for name, props in PARENT_CATEGORIES.items():
            cat = Category(
                short_desc=name.lower(),
                display_name=name.replace("_", " "),
                parent_id=None,
                color=props["color"],
                is_income=props["is_income"],
            )
            db.add(cat)
            db.flush()
            parent_map[name] = cat.id

        # ── Subcategories (Short_Desc) ──
        SUBCATEGORIES = {
            "Food": [
                ("groceries", "Groceries", False),
                ("fast_food", "Fast Food", False),
                ("restaurant", "Restaurant", False),
                ("coffee", "Coffee", False),
                ("work_lunch", "Work Lunch", False),
                ("food_delivery", "Food Delivery", False),
                ("boba", "Boba", False),
                ("bar", "Bar", False),
            ],
            "Housing": [
                ("rent", "Rent", True),
                ("furniture", "Furniture", False),
                ("home_supplies", "Home Supplies", False),
            ],
            "Transportation": [
                ("gas_station", "Gas Station", False),
                ("car_maintenance", "Car Maintenance", False),
                ("parking", "Parking", False),
                ("toll", "Toll", False),
                ("ride_share", "Ride Share", False),
                ("public_transit", "Public Transit", False),
            ],
            "Insurance": [
                ("health_insurance", "Health Insurance", True),
                ("renters_insurance", "Renters Insurance", True),
                ("car_insurance", "Car Insurance", True),
            ],
            "Utilities": [
                ("cell_phone", "Cell Phone", True),
                ("internet", "Internet", True),
                ("electric", "Electric", True),
                ("water", "Water", True),
            ],
            "Medical": [
                ("doctor", "Doctor", False),
                ("pharmacy", "Pharmacy", False),
                ("dental", "Dental", False),
                ("vision", "Vision", False),
                ("therapy", "Therapy", False),
            ],
            "Government": [
                ("taxes", "Taxes", False),
                ("government_fee", "Government Fee", False),
            ],
            "Savings": [
                ("savings_transfer", "Savings Transfer", False),
                ("investment", "Investment", False),
                ("student_loan", "Student Loan", True),
            ],
            "Personal_Spending": [
                ("clothing", "Clothing", False),
                ("haircut", "Haircut", True),
                ("amazon", "Amazon", False),
                ("walmart_target", "Walmart/Target", False),
                ("personal_care", "Personal Care", False),
                ("subscriptions", "Subscriptions", True),
                ("gym", "Gym", True),
            ],
            "Recreation_Entertainment": [
                ("concerts", "Concerts", False),
                ("live_nba", "Live NBA", False),
                ("movies", "Movies", False),
                ("tennis", "Tennis", False),
                ("gaming", "Gaming", False),
            ],
            "Streaming_Services": [
                ("spotify", "Spotify", True),
                ("netflix", "Netflix", True),
                ("hulu", "Hulu", True),
                ("hbo", "HBO", True),
                ("apple_tv", "Apple TV", True),
                ("youtube_premium", "YouTube Premium", True),
                ("disney_plus", "Disney+", True),
            ],
            "Education": [
                ("books", "Books", False),
                ("courses", "Courses", False),
                ("tuition", "Tuition", False),
            ],
            "Travel": [
                ("air_travel", "Air Travel", False),
                ("hotel", "Hotel", False),
                ("airport", "Airport", False),
                ("travel_food", "Travel Food", False),
                ("travel_transport", "Travel Transport", False),
            ],
            "Misc": [
                ("misc_other", "Miscellaneous", False),
                ("gift", "Gift", False),
                ("donation", "Donation", False),
                ("pet", "Pet", False),
            ],
            "People": [
                ("don", "Don", False),
                ("jayelin", "Jayelin", False),
                ("tahjei", "Tahjei", False),
                ("sharon", "Sharon", False),
                ("vincent", "Vincent", False),
                ("family", "Family", False),
                ("friends", "Friends", False),
            ],
            "Payment_and_Interest": [
                ("credit_card_payment", "Credit Card Payment", True),
                ("interest_charge", "Interest Charge", False),
                ("bank_fee", "Bank Fee", False),
            ],
            "Income": [
                ("payroll", "Payroll", True),
                ("side_income", "Side Income", False),
                ("refund", "Refund", False),
                ("cashback", "Cashback", False),
                ("venmo_income", "Venmo Income", False),
            ],
            "Balance": [
                ("transfer", "Transfer", False),
                ("atm", "ATM", False),
            ],
        }

        for parent_name, subs in SUBCATEGORIES.items():
            parent_id = parent_map[parent_name]
            for short_desc, display_name, is_recurring in subs:
                cat = Category(
                    short_desc=short_desc,
                    display_name=display_name,
                    parent_id=parent_id,
                    is_recurring=is_recurring,
                )
                db.add(cat)

        db.flush()

        # ── Accounts ──
        accounts = [
            Account(name="Discover Card", institution="discover", account_type="credit"),
            Account(name="SoFi Checking", institution="sofi", account_type="checking"),
            Account(name="SoFi Savings", institution="sofi", account_type="savings"),
            Account(name="Wells Fargo Checking", institution="wellsfargo", account_type="checking"),
        ]
        for acct in accounts:
            db.add(acct)

        db.flush()

        # ── Amount Rules (Tier 1 — Apple/Venmo disambiguation) ──
        # Build a lookup from short_desc to category_id
        cat_lookup = {}
        for cat in db.query(Category).all():
            cat_lookup[cat.short_desc] = cat.id

        AMOUNT_RULES = [
            # Apple billing disambiguation
            ("APPLE.COM/BILL", 15.89, 0.50, "hbo", "HBO via Apple billing"),
            ("APPLE.COM/BILL", 10.59, 0.50, "netflix", "Netflix via Apple billing"),
            ("APPLE.COM/BILL", 5.29, 0.50, "apple_tv", "Apple TV+"),
            ("APPLE.COM/BILL", 6.99, 0.50, "hulu", "Hulu via Apple billing"),
            ("APPLE.COM/BILL", 11.99, 0.50, "spotify", "Spotify via Apple billing"),
            ("APPLE.COM/BILL", 13.99, 0.50, "youtube_premium", "YouTube Premium via Apple"),
            ("APPLE.COM/BILL", 7.99, 0.50, "disney_plus", "Disney+ via Apple billing"),
            # Venmo disambiguation
            ("VENMO", 816.87, 1.00, "rent", "Rent via Venmo"),
            ("VENMO", 1803.40, 5.00, "vincent", "Vincent debt via Venmo"),
            ("VENMO", 3606.80, 5.00, "vincent", "Vincent debt via Venmo (double)"),
        ]

        for pattern, amount, tolerance, short_desc, notes in AMOUNT_RULES:
            cat_id = cat_lookup.get(short_desc)
            if cat_id:
                rule = AmountRule(
                    description_pattern=pattern,
                    amount=amount,
                    tolerance=tolerance,
                    short_desc=short_desc,
                    category_id=cat_id,
                    notes=notes,
                )
                db.add(rule)

        # ── Merchant Mappings (Tier 2 — seeded from notebook patterns) ──
        # These are the most common patterns from the Jupyter notebooks
        # All seeded with confidence=10 (well above auto-confirm threshold of 3)
        MERCHANT_SEEDS = [
            # Food
            ("SAFEWAY", "groceries"), ("TRADER JOE", "groceries"), ("WHOLEFDS", "groceries"),
            ("GROCERY OUTLET", "groceries"), ("COSTCO", "groceries"), ("SPROUTS", "groceries"),
            ("TARGET", "walmart_target"), ("WALMART", "walmart_target"),
            ("MCDONALD", "fast_food"), ("BURGER KING", "fast_food"), ("WENDY", "fast_food"),
            ("TACO BELL", "fast_food"), ("CHICK-FIL-A", "fast_food"), ("POPEYES", "fast_food"),
            ("JACK IN THE BOX", "fast_food"), ("FIVE GUYS", "fast_food"),
            ("CHIPOTLE", "restaurant"), ("OLIVE GARDEN", "restaurant"),
            ("STARBUCKS", "coffee"), ("PEET", "coffee"), ("PHILZ", "coffee"),
            ("DOORDASH", "food_delivery"), ("UBER EATS", "food_delivery"), ("GRUBHUB", "food_delivery"),
            ("BOBA", "boba"), ("KUNG FU TEA", "boba"), ("GONG CHA", "boba"),
            # Transportation
            ("CHEVRON", "gas_station"), ("SHELL", "gas_station"), ("ARCO", "gas_station"),
            ("76 ", "gas_station"), ("EXXON", "gas_station"), ("VALERO", "gas_station"),
            ("PARKING", "parking"), ("PARK MOBILE", "parking"), ("SP PLUS", "parking"),
            ("FASTRAK", "toll"), ("GOLDEN GATE", "toll"),
            ("UBER ", "ride_share"), ("LYFT", "ride_share"),
            ("BART", "public_transit"), ("CLIPPER", "public_transit"),
            # Utilities
            ("TMOBILE", "cell_phone"), ("T-MOBILE", "cell_phone"),
            ("COMCAST", "internet"), ("XFINITY", "internet"), ("ATT", "internet"),
            ("PG&E", "electric"), ("PGE", "electric"),
            # Subscriptions & Entertainment
            ("NETFLIX", "netflix"), ("SPOTIFY", "spotify"), ("HULU", "hulu"),
            ("DISNEY PLUS", "disney_plus"), ("YOUTUBE", "youtube_premium"),
            ("AMAZON PRIME", "subscriptions"), ("AMZN MKTP", "amazon"), ("AMAZON.COM", "amazon"),
            ("PLANET FITNESS", "gym"), ("24 HOUR", "gym"),
            # Housing
            ("IKEA", "furniture"),
            # Medical
            ("CVS", "pharmacy"), ("WALGREENS", "pharmacy"), ("RITE AID", "pharmacy"),
            ("KAISER", "doctor"),
            # Income
            ("PAYROLL", "payroll"), ("DIRECT DEP", "payroll"), ("GUSTO", "payroll"),
            # People
            ("LEWIS JR", "don"),
            # Payments
            ("DISCOVER", "credit_card_payment"), ("INTEREST CHARGE", "interest_charge"),
            # Insurance
            ("STATE FARM", "car_insurance"), ("PROGRESSIVE", "car_insurance"),
            # Savings
            ("STUDENT LOAN", "student_loan"), ("NAVIENT", "student_loan"),
            ("SOFI INVEST", "investment"),
        ]

        for pattern, short_desc in MERCHANT_SEEDS:
            cat_id = cat_lookup.get(short_desc)
            if cat_id:
                mapping = MerchantMapping(
                    merchant_pattern=pattern,
                    category_id=cat_id,
                    confidence=10,  # High confidence — imported from notebooks
                )
                db.add(mapping)

        db.commit()
        logger.info("Database seeded successfully.")

    except Exception as e:
        db.rollback()
        logger.error(f"Seed data error: {e}")
        raise
    finally:
        db.close()
