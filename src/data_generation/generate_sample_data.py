"""
Generate realistic e-commerce CSVs for the medallion pipeline assessment.

Produces:
  data/customers.csv   (~10,010 rows: 10,000 unique IDs + 10 duplicate-key rows)
  data/products.csv    (~505 rows: 500 unique IDs + 5 duplicate-key rows)
  data/orders.csv      (~100,020 rows: 100,000 unique IDs + 20 duplicate-key rows)

Quality issues are injected deterministically (seed=42) so Silver tests can
assert exact counts. Empty CSV fields represent NULL.

Run from the repository root:
  python src/data_generation/generate_sample_data.py
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Volumes and reproducibility
# ---------------------------------------------------------------------------
SEED = 42
N_CUSTOMERS = 10_000
N_PRODUCTS = 500
N_ORDERS = 100_000
AS_OF_DATE = date(2026, 8, 14)
SIGNUP_START = date(2020, 1, 1)

# Customers 9700-10000 are left without orders so Gold can form an Inactive segment.
INACTIVE_CUSTOMER_ID_START = 9_700

MONEY = Decimal("0.01")

# ---------------------------------------------------------------------------
# Mandated quality issues (assessment brief)
# ---------------------------------------------------------------------------
# customers.csv
N_NULL_EMAIL = 50
N_DUP_CUSTOMER_ID = 10
# orders.csv
N_NULL_ORDER_CUSTOMER_ID = 100
N_NULL_ORDER_PRODUCT_ID = 200
N_ORPHAN_CUSTOMER_ID = 50
N_ORPHAN_PRODUCT_ID = 30
N_DUP_ORDER_ID = 20

# ---------------------------------------------------------------------------
# Additional issues so every Silver check has planted defects in all 3 files
# ---------------------------------------------------------------------------
# customers.csv — type / domain / business-logic
N_INVALID_SEGMENT = 10
N_MALFORMED_EMAIL = 10
N_FUTURE_SIGNUP = 10
# products.csv — completeness / uniqueness / business-logic / type
N_NULL_PRODUCT_NAME = 10
N_NULL_CATEGORY = 5
N_DUP_PRODUCT_ID = 5
N_COST_GT_PRICE = 8
N_NEGATIVE_STOCK = 5
# orders.csv — business-logic
N_WRONG_TOTAL_AMOUNT = 25
N_COMPLETED_WITHOUT_PAYMENT = 15
N_PENDING_WITH_PAYMENT = 10

# Deterministic ID ranges used when injecting issues (do not overlap).
NULL_EMAIL_IDS = range(1, 1 + N_NULL_EMAIL)  # 1-50
INVALID_SEGMENT_IDS = range(201, 201 + N_INVALID_SEGMENT)  # 201-210
MALFORMED_EMAIL_IDS = range(211, 211 + N_MALFORMED_EMAIL)  # 211-220
FUTURE_SIGNUP_IDS = range(221, 221 + N_FUTURE_SIGNUP)  # 221-230
DUP_CUSTOMER_SOURCE_IDS = range(991, 991 + N_DUP_CUSTOMER_ID)  # 991-1000

NULL_PRODUCT_NAME_IDS = range(1, 1 + N_NULL_PRODUCT_NAME)  # 1-10
NULL_CATEGORY_IDS = range(11, 11 + N_NULL_CATEGORY)  # 11-15
COST_GT_PRICE_IDS = range(16, 16 + N_COST_GT_PRICE)  # 16-23
NEGATIVE_STOCK_IDS = range(24, 24 + N_NEGATIVE_STOCK)  # 24-28
DUP_PRODUCT_SOURCE_IDS = range(491, 491 + N_DUP_PRODUCT_ID)  # 491-495

NULL_ORDER_CUSTOMER_IDS = range(1, 1 + N_NULL_ORDER_CUSTOMER_ID)  # 1-100
NULL_ORDER_PRODUCT_IDS = range(101, 101 + N_NULL_ORDER_PRODUCT_ID)  # 101-300
ORPHAN_CUSTOMER_ORDER_IDS = range(301, 301 + N_ORPHAN_CUSTOMER_ID)  # 301-350
ORPHAN_PRODUCT_ORDER_IDS = range(351, 351 + N_ORPHAN_PRODUCT_ID)  # 351-380
DUP_ORDER_SOURCE_IDS = range(1_001, 1_001 + N_DUP_ORDER_ID)  # 1001-1020
WRONG_TOTAL_ORDER_IDS = range(601, 601 + N_WRONG_TOTAL_AMOUNT)  # 601-625
COMPLETED_NO_PAY_IDS = range(626, 626 + N_COMPLETED_WITHOUT_PAYMENT)  # 626-640
PENDING_WITH_PAY_IDS = range(641, 641 + N_PENDING_WITH_PAYMENT)  # 641-650

ORPHAN_CUSTOMER_ID_START = 20_001  # not in customers.customer_id
ORPHAN_PRODUCT_ID_START = 9_001  # not in products.product_id

CUSTOMER_COLUMNS = [
    "customer_id",
    "customer_name",
    "email",
    "country",
    "signup_date",
    "customer_segment",
    "lifetime_value",
]
PRODUCT_COLUMNS = [
    "product_id",
    "product_name",
    "category",
    "price",
    "cost",
    "stock_quantity",
    "reorder_level",
]
ORDER_COLUMNS = [
    "order_id",
    "customer_id",
    "order_date",
    "product_id",
    "quantity",
    "unit_price",
    "total_amount",
    "order_status",
    "payment_date",
]

FIRST_NAMES = [
    "James", "Olivia", "Liam", "Emma", "Noah", "Ava", "Oliver", "Sophia",
    "Elijah", "Isabella", "Lucas", "Mia", "Mason", "Amelia", "Ethan", "Harper",
    "Aarav", "Zara", "Wei", "Yuki", "Priya", "Chen", "Sofia", "Mateo",
    "Charlotte", "Jack", "Grace", "Leo", "Chloe", "Henry", "Ruby", "Oscar",
    "Isla", "Kai", "Maya", "Arjun", "Nina", "Hugo", "Eva", "Samuel",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Martin",
    "Lee", "Harris", "Clark", "Lewis", "Young", "Walker", "Hall", "Allen",
    "Patel", "Nguyen", "Kim", "Chen", "Singh", "Kowalski", "Silva", "Rossi",
    "Murphy", "Cohen", "Khan", "Nakamura", "Andersen", "Dubois", "Costa",
]
COUNTRIES = [
    "Australia", "Australia", "Australia", "Australia",
    "New Zealand", "United Kingdom", "United Kingdom",
    "United States", "United States", "India", "Singapore", "Canada", "Ireland",
]
SEGMENTS = (
    ["Premium"] * 15 + ["Standard"] * 55 + ["Basic"] * 30
)
ORDER_STATUSES = (
    ["Completed"] * 80 + ["Pending"] * 12 + ["Cancelled"] * 8
)
CATEGORIES: dict[str, list[str]] = {
    "Electronics": [
        "Wireless Headphones", "USB-C Charger", "Bluetooth Speaker",
        "4K Monitor", "Laptop Stand", "Mechanical Keyboard", "Webcam",
        "Power Bank", "Smart Watch", "Tablet Case",
    ],
    "Clothing": [
        "Cotton T-Shirt", "Denim Jeans", "Running Jacket", "Wool Sweater",
        "Linen Shirt", "Trail Shorts", "Hoodie", "Crew Socks", "Belt", "Cap",
    ],
    "Home": [
        "Ceramic Mug", "Throw Pillow", "Desk Lamp", "Storage Basket",
        "Cutlery Set", "Non-stick Pan", "Duvet Cover", "Wall Clock",
        "Plant Pot", "Cutting Board",
    ],
    "Sports": [
        "Yoga Mat", "Resistance Bands", "Water Bottle", "Dumbbell Pair",
        "Tennis Racket", "Soccer Ball", "Cycling Gloves", "Jump Rope",
        "Gym Bag", "Foam Roller",
    ],
    "Beauty": [
        "Face Moisturiser", "Sunscreen SPF50", "Hair Serum", "Lip Balm",
        "Body Wash", "Perfume Mini", "Nail Kit", "Face Mask Pack",
        "Shampoo", "Body Lotion",
    ],
    "Books": [
        "Paperback Novel", "Cookbook", "Travel Guide", "Colouring Book",
        "Business Hardcover", "Kids Picture Book", "Poetry Collection",
        "Science Magazine", "Puzzle Book", "Notebook Set",
    ],
    "Toys": [
        "Building Blocks", "Plush Bear", "Board Game", "Puzzle 1000pc",
        "RC Car", "Art Set", "Action Figure", "Doll House Kit",
        "STEM Robot Kit", "Card Game",
    ],
    "Grocery": [
        "Organic Coffee", "Green Tea Box", "Granola Pack", "Olive Oil",
        "Pasta Pack", "Dark Chocolate", "Spice Mix", "Honey Jar",
        "Rice 1kg", "Nut Mix",
    ],
}
BRANDS = [
    "Northpeak", "Blueharbor", "Sunfield", "Ironleaf", "Coral Bay",
    "Maple & Co", "Redstone", "Quietline", "AeroNest", "Lumen",
]


def money(value: float | Decimal) -> str:
    return str(Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP))


def iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def csv_value(value: Any) -> str:
    """Empty string is the CSV stand-in for NULL."""
    if value is None:
        return ""
    return str(value)


def random_date(rng: random.Random, start: date, end: date) -> date:
    span = (end - start).days
    if span <= 0:
        return start
    return start + timedelta(days=rng.randint(0, span))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_value(row[column]) for column in columns})


def generate_customers(rng: random.Random) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for customer_id in range(1, N_CUSTOMERS + 1):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        if customer_id <= 1_500:
            segment = "Premium"
        elif customer_id <= 7_000:
            segment = "Standard"
        else:
            segment = "Basic"
        rows.append(
            {
                "customer_id": customer_id,
                "customer_name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}{customer_id}@shopmail.com",
                "country": rng.choice(COUNTRIES),
                "signup_date": random_date(rng, SIGNUP_START, AS_OF_DATE),
                "customer_segment": segment,
                "lifetime_value": money(rng.uniform(0, 4_800)),
            }
        )
    return rows


def inject_customer_issues(
    rows: list[dict[str, Any]], rng: random.Random
) -> list[dict[str, Any]]:
    """Plant customer defects. Original 10,000 rows stay; duplicates are appended."""
    by_id = {row["customer_id"]: row for row in rows}

    for customer_id in NULL_EMAIL_IDS:
        by_id[customer_id]["email"] = None

    for customer_id in INVALID_SEGMENT_IDS:
        by_id[customer_id]["customer_segment"] = rng.choice(["VIP", "Gold", "Enterprise"])

    for customer_id in MALFORMED_EMAIL_IDS:
        by_id[customer_id]["email"] = f"customer{customer_id} at shopmail"

    for customer_id in FUTURE_SIGNUP_IDS:
        by_id[customer_id]["signup_date"] = date(2027, 3, 1)

    duplicates = [dict(by_id[customer_id]) for customer_id in DUP_CUSTOMER_SOURCE_IDS]
    return list(by_id.values()) + duplicates


def generate_products(rng: random.Random) -> list[dict[str, Any]]:
    category_names = list(CATEGORIES.keys())
    rows: list[dict[str, Any]] = []
    for product_id in range(1, N_PRODUCTS + 1):
        category = category_names[(product_id - 1) % len(category_names)]
        item = CATEGORIES[category][(product_id - 1) % len(CATEGORIES[category])]
        brand = BRANDS[(product_id - 1) % len(BRANDS)]
        price = Decimal(str(round(rng.uniform(6.5, 420.0), 2)))
        cost = (price * Decimal(str(round(rng.uniform(0.42, 0.72), 2)))).quantize(MONEY)
        stock = rng.randint(8, 480)
        reorder = min(stock, rng.randint(5, 60))
        rows.append(
            {
                "product_id": product_id,
                "product_name": f"{brand} {item}",
                "category": category,
                "price": money(price),
                "cost": money(cost),
                "stock_quantity": stock,
                "reorder_level": reorder,
            }
        )
    return rows


def inject_product_issues(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Plant product defects so completeness, uniqueness, type, and business checks fire."""
    by_id = {row["product_id"]: row for row in rows}

    for product_id in NULL_PRODUCT_NAME_IDS:
        by_id[product_id]["product_name"] = None

    for product_id in NULL_CATEGORY_IDS:
        by_id[product_id]["category"] = None

    for product_id in COST_GT_PRICE_IDS:
        price = Decimal(by_id[product_id]["price"])
        by_id[product_id]["cost"] = money(price * Decimal("1.25"))

    for product_id in NEGATIVE_STOCK_IDS:
        by_id[product_id]["stock_quantity"] = -rng_stock_for_id(product_id)

    duplicates = [dict(by_id[product_id]) for product_id in DUP_PRODUCT_SOURCE_IDS]
    return list(by_id.values()) + duplicates


def rng_stock_for_id(product_id: int) -> int:
    """Stable negative stock so regeneration does not depend on RNG position."""
    return 3 + (product_id % 7)


def generate_orders(
    rng: random.Random,
    customers: list[dict[str, Any]],
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    customer_by_id = {row["customer_id"]: row for row in customers}
    product_by_id = {row["product_id"]: row for row in products}
    active_customer_ids = [
        customer_id
        for customer_id in range(1, INACTIVE_CUSTOMER_ID_START)
        if customer_id in customer_by_id
    ]
    valid_product_ids = list(range(1, N_PRODUCTS + 1))

    rows: list[dict[str, Any]] = []
    for order_id in range(1, N_ORDERS + 1):
        customer_id = rng.choice(active_customer_ids)
        product_id = rng.choice(valid_product_ids)
        customer = customer_by_id[customer_id]
        product = product_by_id[product_id]
        signup = customer["signup_date"]
        order_start = signup if isinstance(signup, date) and signup <= AS_OF_DATE else SIGNUP_START
        order_date = random_date(rng, order_start, AS_OF_DATE)
        quantity = rng.randint(1, 6)
        if customer["customer_segment"] == "Premium":
            quantity = rng.randint(1, 8)
        unit_price = Decimal(product["price"])
        total_amount = (unit_price * quantity).quantize(MONEY)
        status = rng.choice(ORDER_STATUSES)
        payment_date: date | None
        if status == "Completed":
            payment_date = min(AS_OF_DATE, order_date + timedelta(days=rng.randint(0, 4)))
        else:
            payment_date = None
        rows.append(
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "order_date": order_date,
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": money(unit_price),
                "total_amount": money(total_amount),
                "order_status": status,
                "payment_date": payment_date,
            }
        )
    return rows


def inject_order_issues(
    rows: list[dict[str, Any]], rng: random.Random
) -> list[dict[str, Any]]:
    by_id = {row["order_id"]: row for row in rows}

    for order_id in NULL_ORDER_CUSTOMER_IDS:
        by_id[order_id]["customer_id"] = None

    for order_id in NULL_ORDER_PRODUCT_IDS:
        by_id[order_id]["product_id"] = None

    for offset, order_id in enumerate(ORPHAN_CUSTOMER_ORDER_IDS):
        by_id[order_id]["customer_id"] = ORPHAN_CUSTOMER_ID_START + offset

    for offset, order_id in enumerate(ORPHAN_PRODUCT_ORDER_IDS):
        by_id[order_id]["product_id"] = ORPHAN_PRODUCT_ID_START + offset

    for order_id in WRONG_TOTAL_ORDER_IDS:
        unit_price = Decimal(by_id[order_id]["unit_price"])
        quantity = int(by_id[order_id]["quantity"])
        by_id[order_id]["total_amount"] = money(unit_price * quantity + Decimal("17.50"))

    for order_id in COMPLETED_NO_PAY_IDS:
        by_id[order_id]["order_status"] = "Completed"
        by_id[order_id]["payment_date"] = None

    for order_id in PENDING_WITH_PAY_IDS:
        order_date = by_id[order_id]["order_date"]
        by_id[order_id]["order_status"] = "Pending"
        by_id[order_id]["payment_date"] = order_date

    duplicates = [dict(by_id[order_id]) for order_id in DUP_ORDER_SOURCE_IDS]
    return list(by_id.values()) + duplicates


def verify(
    customers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> dict[str, int]:
    """Recount planted issues so a failed generation is obvious on stdout."""
    customer_ids = [row["customer_id"] for row in customers]
    product_ids = [row["product_id"] for row in products]
    order_ids = [row["order_id"] for row in orders]
    unique_customers = set(customer_ids)
    unique_products = set(product_ids)

    stats = {
        "customer_rows": len(customers),
        "product_rows": len(products),
        "order_rows": len(orders),
        "null_email": sum(1 for row in customers if not row["email"]),
        "duplicate_customer_id_extra_rows": len(customers) - len(unique_customers),
        "invalid_segment": sum(
            1
            for row in customers
            if row["customer_segment"] not in {"Premium", "Standard", "Basic"}
        ),
        "malformed_email": sum(
            1
            for row in customers
            if row["email"] and "@" not in str(row["email"])
        ),
        "future_signup": sum(
            1
            for row in customers
            if isinstance(row["signup_date"], date) and row["signup_date"] > AS_OF_DATE
        ),
        "null_product_name": sum(1 for row in products if not row["product_name"]),
        "null_category": sum(1 for row in products if not row["category"]),
        "duplicate_product_id_extra_rows": len(products) - len(unique_products),
        "cost_gt_price": sum(
            1
            for row in products
            if Decimal(str(row["cost"])) > Decimal(str(row["price"]))
        ),
        "negative_stock": sum(1 for row in products if int(row["stock_quantity"]) < 0),
        "null_order_customer_id": sum(1 for row in orders if row["customer_id"] in (None, "")),
        "null_order_product_id": sum(1 for row in orders if row["product_id"] in (None, "")),
        "orphan_customer_id": sum(
            1
            for row in orders
            if row["customer_id"] not in (None, "") and row["customer_id"] not in unique_customers
        ),
        "orphan_product_id": sum(
            1
            for row in orders
            if row["product_id"] not in (None, "") and row["product_id"] not in unique_products
        ),
        "duplicate_order_id_extra_rows": len(orders) - len(set(order_ids)),
        "wrong_total_amount": sum(
            1
            for row in orders
            if Decimal(str(row["total_amount"]))
            != (Decimal(str(row["unit_price"])) * int(row["quantity"])).quantize(MONEY)
        ),
        "completed_without_payment": sum(
            1
            for row in orders
            if row["order_status"] == "Completed" and not row["payment_date"]
        ),
        "pending_with_payment": sum(
            1
            for row in orders
            if row["order_status"] == "Pending" and row["payment_date"]
        ),
    }

    expected = {
        "customer_rows": N_CUSTOMERS + N_DUP_CUSTOMER_ID,
        "product_rows": N_PRODUCTS + N_DUP_PRODUCT_ID,
        "order_rows": N_ORDERS + N_DUP_ORDER_ID,
        "null_email": N_NULL_EMAIL,
        "duplicate_customer_id_extra_rows": N_DUP_CUSTOMER_ID,
        "invalid_segment": N_INVALID_SEGMENT,
        "malformed_email": N_MALFORMED_EMAIL,
        "future_signup": N_FUTURE_SIGNUP,
        "null_product_name": N_NULL_PRODUCT_NAME,
        "null_category": N_NULL_CATEGORY,
        "duplicate_product_id_extra_rows": N_DUP_PRODUCT_ID,
        "cost_gt_price": N_COST_GT_PRICE,
        "negative_stock": N_NEGATIVE_STOCK,
        "null_order_customer_id": N_NULL_ORDER_CUSTOMER_ID,
        "null_order_product_id": N_NULL_ORDER_PRODUCT_ID,
        "orphan_customer_id": N_ORPHAN_CUSTOMER_ID,
        "orphan_product_id": N_ORPHAN_PRODUCT_ID,
        "duplicate_order_id_extra_rows": N_DUP_ORDER_ID,
        "wrong_total_amount": N_WRONG_TOTAL_AMOUNT,
        "completed_without_payment": N_COMPLETED_WITHOUT_PAYMENT,
        "pending_with_payment": N_PENDING_WITH_PAYMENT,
    }
    mismatches = {
        key: (stats[key], expected[key])
        for key in expected
        if stats[key] != expected[key]
    }
    if mismatches:
        raise RuntimeError(f"Generation counts did not match the contract: {mismatches}")
    return stats


def print_summary(stats: dict[str, int], data_dir: Path) -> None:
    print(f"Wrote CSVs to {data_dir}")
    print(
        f"  customers.csv  {stats['customer_rows']:>7} rows "
        f"({N_CUSTOMERS} unique IDs + {N_DUP_CUSTOMER_ID} duplicate-key rows)"
    )
    print(
        f"  products.csv   {stats['product_rows']:>7} rows "
        f"({N_PRODUCTS} unique IDs + {N_DUP_PRODUCT_ID} duplicate-key rows)"
    )
    print(
        f"  orders.csv     {stats['order_rows']:>7} rows "
        f"({N_ORDERS} unique IDs + {N_DUP_ORDER_ID} duplicate-key rows)"
    )
    print("Planted quality issues (verified):")
    skip_keys = {"customer_rows", "product_rows", "order_rows"}
    for key, value in stats.items():
        if key in skip_keys:
            continue
        print(f"  {key:32} {value}")


def repo_root() -> Path:
    file_value = globals().get("__file__")
    if file_value:
        src = Path(file_value).resolve().parent.parent
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
    else:
        cwd = Path.cwd().resolve()
        for root in [cwd, cwd / "src", cwd.parent, cwd.parent / "src"]:
            if (root / "runtime_paths.py").is_file():
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                break
    from runtime_paths import repo_root as _repo_root

    return _repo_root(file_value)


def generate_all(output_dir: Path, seed: int) -> dict[str, int]:
    rng = random.Random(seed)
    customers = inject_customer_issues(generate_customers(rng), rng)
    products = inject_product_issues(generate_products(rng))
    # Duplicates are appended, so the first N_* rows are the unique populations.
    # Orders use those IDs; orphans are planted later with IDs outside these sets.
    customer_population = customers[:N_CUSTOMERS]
    product_population = products[:N_PRODUCTS]
    orders = inject_order_issues(
        generate_orders(rng, customer_population, product_population), rng
    )
    stats = verify(customers, products, orders)
    write_csv(output_dir / "customers.csv", CUSTOMER_COLUMNS, customers)
    write_csv(output_dir / "products.csv", PRODUCT_COLUMNS, products)
    write_csv(output_dir / "orders.csv", ORDER_COLUMNS, orders)
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate medallion pipeline sample CSVs.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for CSV output (default: <repo>/data)",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="RNG seed (default: 42)")
    # parse_known_args: Databricks "Run file" injects `-f connection.json` via IPython.
    return parser.parse_known_args()[0]


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or (repo_root() / "data")
    stats = generate_all(output_dir, args.seed)
    print_summary(stats, output_dir)


if __name__ == "__main__":
    main()
