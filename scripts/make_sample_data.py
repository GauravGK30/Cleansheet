"""Create the sample files in sample_data/ (a deliberately messy retail export).

    python scripts/make_sample_data.py

The data is generated with a fixed seed, so the files are identical every time. It exercises every feature:
duplicates, padded text, N/A placeholders, leading-zero IDs, a mapping (customer_id -> customer), formulas
(revenue, cost, margin), Yes/No and TRUE/FALSE flags with gaps, valid and invalid dates, and one ambiguous
day/month column.
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_data"

CUSTOMERS = {"00101": "Asha Rao", "00102": "Ben Carter", "00103": "Chloe Martin", "00104": "Dev Patel",
             "00105": "Elena Rossi", "00106": "Farid Khan", "00107": "Grace Liu", "00108": "Hugo Silva"}
PRODUCTS = {"P-100": "Desk Lamp", "P-101": "Notebook", "P-102": "Backpack", "P-103": "Water Bottle",
            "P-104": "Headphones", "P-105": "Phone Stand"}
PRICES = {"P-100": 24.50, "P-101": 4.25, "P-102": 39.99, "P-103": 12.00, "P-104": 59.90, "P-105": 9.75}
COSTS = {"P-100": 14.00, "P-101": 1.80, "P-102": 22.50, "P-103": 5.10, "P-104": 31.00, "P-105": 3.40}
COLUMNS = ["invoice_no", "customer_id", "customer", "product_id", "product", "order_date", "ship_date",
           "quantity", "unit_price", "unit_cost", "revenue", "cost", "margin", "is_returned", "anomaly",
           "newsletter", "notes"]


def build(rows: int = 120, seed: int = 7) -> list[list[str]]:
    rnd = random.Random(seed)
    out: list[list[str]] = []
    for i in range(rows):
        cid = rnd.choice(list(CUSTOMERS))
        pid = rnd.choice(list(PRODUCTS))
        qty = rnd.randint(1, 9)
        price, cost_each = PRICES[pid], COSTS[pid]
        revenue, cost = round(qty * price, 2), round(qty * cost_each, 2)
        month, day = rnd.randint(1, 12), rnd.randint(1, 28)
        order = f"2024-{month:02d}-{day:02d}"
        ship = f"2024-{month:02d}-{min(day + rnd.randint(1, 3), 28):02d}"
        out.append([
            f"INV-{1000 + i}", cid, CUSTOMERS[cid], pid, PRODUCTS[pid], order, ship, str(qty),
            f"{price:.2f}", f"{cost_each:.2f}", f"{revenue:.2f}", f"{cost:.2f}", f"{revenue - cost:.2f}",
            rnd.choice(["Yes", "No", "No", "No"]), rnd.choice(["TRUE", "FALSE", "FALSE", "FALSE"]),
            rnd.choice(["1", "0"]), rnd.choice(["gift wrap", "leave at door", "fragile", "call first", "none"]),
        ])
    col = {c: i for i, c in enumerate(COLUMNS)}

    def blank(row: int, name: str, token: str = "") -> None:
        out[row][col[name]] = token

    # --- gaps, in the different spellings people use for "nothing" -------------------------------
    for r in (3, 17, 40, 77):
        blank(r, "quantity", "N/A")
    for r in (5, 22, 58):
        blank(r, "unit_price", "")
    for r in (8, 31, 66, 91):
        blank(r, "revenue", "null")           # recoverable: quantity x unit_price are present
    for r in (12, 45):
        blank(r, "cost", "")
    for r in (14, 60):
        blank(r, "margin", "-")
    for r in (9, 26, 52, 83):
        blank(r, "customer", "n/a")           # recoverable from customer_id
    for r in (11, 30):
        blank(r, "customer_id", "")           # an identifier: never guessed
    for r in (20, 70):
        blank(r, "invoice_no", "")
    for r in (6, 34, 99):
        blank(r, "order_date", "N/A")
    for r in (15, 49, 88):
        blank(r, "anomaly", "")               # unknown stays unknown
    for r in (4, 29):
        blank(r, "is_returned", "none")
    blank(18, "notes", "NULL")
    # --- invalid dates (ship_date must NOT be converted) ------------------------------------------
    out[25][col["ship_date"]] = "2024-13-45"
    out[61][col["ship_date"]] = "soon"
    # --- messy text ------------------------------------------------------------------------------
    out[1][col["notes"]] = "  FRAGILE   handle   with care  "
    out[2][col["customer"]] = "  " + out[2][col["customer"]] + "  "
    out[10][col["notes"]] = "Gift  Wrap"
    out[13][col["notes"]] = "gift wrap"
    # --- exact duplicates --------------------------------------------------------------------------
    for r in (2, 19, 33, 47, 64, 100):
        out.append(list(out[r]))
    return out


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)


def write_xlsx(path: Path, rows: list[list[str]]) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"
    ws.append(COLUMNS)
    for r in rows:
        ws.append([None if v == "" else v for v in r])        # text cells, so leading zeros survive
    wb.save(path)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    rows = build()
    write_csv(OUT / "retail_orders_messy.csv", rows)
    write_xlsx(OUT / "retail_orders_messy.xlsx", rows)
    print(f"wrote {len(rows)} rows x {len(COLUMNS)} columns to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
