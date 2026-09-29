"""
seed.py
Creates the SQLite database, applies the schema, and populates it
with realistic synthetic e-commerce data.
"""

import sqlite3
import random
import os
from datetime import datetime, timedelta

random.seed(99)

DB_PATH = os.path.join(os.path.dirname(__file__), 'ecommerce.db')
SCHEMA  = os.path.join(os.path.dirname(__file__), 'schema.sql')

START = datetime(2023, 1, 1)
END   = datetime(2024, 12, 31)

SEGMENTS = ['B2C', 'B2B', 'Enterprise']
SEG_W    = [0.55, 0.30, 0.15]

REGIONS  = ['Dublin', 'Cork', 'Galway', 'Limerick', 'Waterford', 'Other']
REG_W    = [0.40, 0.20, 0.15, 0.10, 0.08, 0.07]

CHANNELS = ['Organic Search', 'Paid Social', 'Email Campaign', 'Referral', 'Direct']
CHAN_W   = [0.30, 0.25, 0.20, 0.15, 0.10]

FIRST_NAMES = ['James','Aoife','Conor','Niamh','Patrick','Siobhan','Cian','Ciara',
               'Eoin','Aisling','Liam','Orla','Rory','Sinead','Sean','Fiona']
LAST_NAMES  = ['Murphy','Kelly','O\'Brien','Walsh','Smith','Ryan','O\'Connor',
               'Byrne','O\'Neill','Doyle','McCarthy','Gallagher','Doherty','Kennedy']

PRODUCTS = [
    ('P001','Analytics Pro Licence',  'Software',    599.00),
    ('P002','Reporting Suite',         'Software',    349.00),
    ('P003','Data Connector Plugin',   'Software',    199.00),
    ('P004','Dashboard Builder',       'Software',    449.00),
    ('P005','CRM Integration Module',  'Software',    279.00),
    ('P006','Support Package — Basic', 'Service',     149.00),
    ('P007','Support Package — Pro',   'Service',     299.00),
    ('P008','Onboarding Workshop',     'Service',     799.00),
    ('P009','Data Audit Report',       'Consulting',  999.00),
    ('P010','Custom Integration',      'Consulting', 1499.00),
]

N_CUSTOMERS = 200
N_ORDERS    = 1200


def rand_date(start=START, end=END):
    return start + timedelta(days=random.randint(0, (end - start).days))


def build_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    with open(SCHEMA) as f:
        cur.executescript(f.read())

    # ── Products ──────────────────────────────────────────────────────────
    cur.executemany(
        'INSERT INTO products VALUES (?,?,?,?)', PRODUCTS
    )

    # ── Customers ─────────────────────────────────────────────────────────
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        cid  = f'C{i:04d}'
        fn   = random.choice(FIRST_NAMES)
        ln   = random.choice(LAST_NAMES)
        seg  = random.choices(SEGMENTS, SEG_W)[0]
        reg  = random.choices(REGIONS,  REG_W)[0]
        chan = random.choices(CHANNELS, CHAN_W)[0]
        acq  = rand_date(START, END - timedelta(days=60)).strftime('%Y-%m-%d')
        customers.append((cid, fn, ln, seg, reg, chan, acq))

    cur.executemany('INSERT INTO customers VALUES (?,?,?,?,?,?,?)', customers)

    # ── Orders & Items ────────────────────────────────────────────────────
    product_ids = [p[0] for p in PRODUCTS]
    customer_ids = [c[0] for c in customers]
    # Enterprise customers order more
    seg_map = {c[0]: c[3] for c in customers}

    order_rows = []
    item_rows  = []
    item_counter = 1

    for i in range(1, N_ORDERS + 1):
        oid  = f'O{i:05d}'
        cid  = random.choice(customer_ids)
        seg  = seg_map[cid]
        # Enterprise more likely to be completed, fewer refunds
        status = random.choices(
            ['Completed', 'Refunded', 'Pending'],
            [0.85, 0.10, 0.05] if seg == 'Enterprise' else [0.78, 0.15, 0.07]
        )[0]
        # Slight revenue growth trend across 2 years
        odate = rand_date()
        order_rows.append((oid, cid, odate.strftime('%Y-%m-%d'), status))

        # 1-4 line items per order; Enterprise buys more
        n_items = random.choices([1,2,3,4], [0.4,0.35,0.15,0.10])[0]
        if seg == 'Enterprise':
            n_items = min(n_items + 1, 4)

        chosen_products = random.sample(product_ids, min(n_items, len(product_ids)))
        for pid in chosen_products:
            price = next(p[3] for p in PRODUCTS if p[0] == pid)
            # Enterprise gets slight volume discount
            if seg == 'Enterprise':
                price = round(price * 0.90, 2)
            qty = random.choices([1,2,3], [0.75, 0.20, 0.05])[0]
            item_rows.append((f'I{item_counter:06d}', oid, pid, qty, price))
            item_counter += 1

    cur.executemany('INSERT INTO orders VALUES (?,?,?,?)', order_rows)
    cur.executemany('INSERT INTO order_items VALUES (?,?,?,?,?)', item_rows)

    conn.commit()
    conn.close()

    completed = sum(1 for o in order_rows if o[3] == 'Completed')
    print(f'Database created: {N_CUSTOMERS} customers, {N_ORDERS} orders '
          f'({completed} completed), {item_counter-1} line items.')
    print(f'Path: {DB_PATH}')


if __name__ == '__main__':
    build_db()
