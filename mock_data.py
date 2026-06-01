"""Demo fixtures for DEMO_MODE.

`build_dataset(version_major, edition)` returns a dict keyed by Odoo model name,
each value a list of records. Records use the same shape Odoo returns from
search_read — many2one fields are 2-tuples `[id, display_name]`.

Records carry a few denormalized scalars (prefixed with `_`) that the mock's
domain evaluator uses to resolve dotted paths like `location_id.usage` without
keeping a separate location table in scope.
"""

import random
from datetime import date, datetime, timedelta


DEMO_COMPANY_ID = 1
DEMO_COMPANY_NAME = "Olens Demo Trading Co."
DEMO_CURRENCY_ID = 86
DEMO_CURRENCY_NAME = "SAR"
DEMO_CURRENCY_SYMBOL = "SAR"

_CUR = [DEMO_CURRENCY_ID, DEMO_CURRENCY_NAME]
_COM = [DEMO_COMPANY_ID, DEMO_COMPANY_NAME]


PARTNERS = [
    "Al-Rajhi Steel Industries", "Saudi Telecom Co.", "ARAMCO Services",
    "Tahweelat Logistics", "Riyadh Cement Co.", "Jeddah Marine Supplies",
    "Al-Faisal Construction", "Najd Petrochemicals", "Hilal Foods Group",
    "Tabuk Pharmaceuticals", "Hejaz Power Systems", "SABIC Resins",
    "Olive Tree Trading", "Sand Dune Logistics", "Crescent Holdings",
    "Falcon Aviation Co.", "Gulf Marine Engineering", "Mawared Real Estate",
    "Saudi Catering Co.", "Mahdi Brothers Group", "Al-Nahda Furniture",
    "Saudi Fertilizers Co.", "Khaleej Steel Rolling", "Bedouin Adventures Ltd",
    "Suhail IT Services", "Madinah Hospitality", "Roads & Bridges Co.",
    "Tamimi Markets", "Othaim Investment", "Al-Faisaliah Tower Mgmt",
]


EMPLOYEES = [
    "Ahmed Al-Mansour", "Fatima Al-Saud", "Mohammed Bin Rashid", "Layla Hussein",
    "Khalid Al-Otaibi", "Noura Al-Qahtani", "Yousef Al-Harbi", "Sara Al-Dosari",
    "Abdullah Al-Ghamdi", "Aisha Al-Shehri", "Omar Al-Zahrani", "Mariam Al-Maliki",
    "Hassan Al-Anazi", "Reem Al-Sulaiman", "Faisal Al-Mutairi", "Hala Al-Asiri",
    "Bandar Al-Rashidi", "Lina Al-Najjar", "Sultan Al-Balawi", "Maha Al-Ahmadi",
    "Talal Al-Subaie", "Dina Al-Fahad", "Nasser Al-Saif", "Joud Al-Hazmi",
    "Rashid Al-Jaber", "Hessa Al-Kuwari", "Saleh Al-Najem", "Bushra Al-Rashed",
    "Ziyad Al-Bishi", "Lujain Al-Buraidi", "Tareq Al-Halaby", "Amani Al-Tarifi",
    "Ibrahim Al-Bakr", "Salma Al-Tamimi", "Munir Al-Habib", "Jana Al-Madani",
    "Mansour Al-Fayez", "Rana Al-Shamrani", "Hatem Al-Yami", "Manal Al-Khalidi",
]


PRODUCTS = [
    ("Industrial Drilling Machine", 12500.0),
    ("HVAC Compressor Unit", 8200.0),
    ("Solar Panel Module 450W", 950.0),
    ("Steel Pipe 6m Sch.40", 320.0),
    ("Cement Bag 50kg", 28.5),
    ("Electric Cable 35mm² (per m)", 12.0),
    ("Hydraulic Pump Assembly", 4200.0),
    ("Fiber Optic Cable (per km)", 1850.0),
    ("Aluminum Sheet 1mm", 145.0),
    ("Engine Oil 20L", 220.0),
    ("LED Floodlight 200W", 380.0),
    ("Conveyor Belt 10m", 1750.0),
    ("Generator 100KVA", 28500.0),
    ("Pressure Gauge", 95.0),
    ("Ball Valve 4 inch", 280.0),
    ("Welding Rod 5kg", 110.0),
    ("Safety Helmet", 65.0),
    ("Industrial Fan 36 inch", 1200.0),
    ("Water Pump 5HP", 2400.0),
    ("Forklift 3-ton", 95000.0),
    ("Office Desk Premium", 1450.0),
    ("Server Rack 42U", 6200.0),
    ("Network Switch 48-port", 4800.0),
    ("CCTV Camera 4MP", 580.0),
    ("Smart Thermostat", 320.0),
]


LOCATIONS = [
    (8, "WH/Stock", "internal"),
    (12, "WH/Stock/Shelf A", "internal"),
    (13, "WH/Stock/Shelf B", "internal"),
    (14, "Cold Storage", "internal"),
    (15, "Outbound Dock", "internal"),
    (5, "Vendors", "supplier"),
    (9, "Customers", "customer"),
]


JOURNALS = [
    (1, "Bank — NCB Operating", "bank"),
    (2, "Bank — Riyadh Bank USD", "bank"),
    (3, "Petty Cash", "cash"),
    (4, "Customer Invoices", "sale"),
    (5, "Vendor Bills", "purchase"),
]


CRM_STAGES = [
    (1, "New"),
    (2, "Qualified"),
    (3, "Proposition"),
    (4, "Negotiation"),
    (5, "Won"),
]


LEAVE_TYPES = [
    (1, "Annual Leave"),
    (2, "Sick Leave"),
    (3, "Unpaid Leave"),
    (4, "Compensatory Days"),
    (5, "Hajj Leave"),
]


ANALYTIC_PLANS = [
    (1, "Cost Centers"),
]


# Cost centers and their target revenue / cost totals (in SAR).
# Drives both the analytic page KPIs and the budget vs actual section.
ANALYTIC_ACCOUNTS = [
    # (id, name, code, plan, target_revenue, target_costs, budget_planned)
    (1, "Operations",          "OPS",   1,   850_000,  620_000,  700_000),
    (2, "Sales & Marketing",   "SMK",   1, 1_200_000,  480_000,  500_000),
    (3, "IT & Technology",     "ITT",   1,   320_000,  290_000,  250_000),
    (4, "HR & Admin",          "HRA",   1,   150_000,  380_000,  400_000),
    (5, "Logistics",           "LOG",   1,   670_000,  510_000,  480_000),
]


# GL accounts referenced by analytic lines. The P&L statement classifies
# lines by `account_type`; the Account View filter (default 'pnl') keeps
# only income / income_other / expense* lines.
DEMO_GL_ACCOUNTS = [
    # (id, code, name, account_type)
    (101, "4000", "Sales Revenue",               "income"),
    (102, "4100", "Service Revenue",             "income"),
    (103, "4900", "Other Operating Income",      "income_other"),
    (201, "5000", "Cost of Goods Sold",          "expense_direct_cost"),
    (202, "5100", "Salary Expense",              "expense"),
    (203, "5200", "Travel Expense",              "expense"),
    (204, "5300", "Office Rent",                 "expense"),
    (205, "5400", "Utilities",                   "expense"),
    (206, "5500", "Marketing & Advertising",     "expense"),
    (207, "5600", "IT Software & Licenses",      "expense"),
    # Balance-sheet accounts (kept for completeness but unused by P&L view)
    (301, "1200", "Accounts Receivable",         "asset_receivable"),
    (302, "1100", "Cash & Banks",                "asset_cash"),
    (401, "2100", "Accounts Payable",            "liability_payable"),
    (501, "3000", "Equity",                      "equity"),
]


# Per-cost-center signed amounts. Each entry is a list of
# (gl_account_id, signed_amount_in_SAR, label) that sums to the spec
# revenue / cost target for the cost center.
DEMO_ANALYTIC_LINE_SPECS = {
    # Operations: Rev 850K (+), Costs 620K (-)
    1: [
        (101,  600_000, "Operations — Product sales (Q1-Q2)"),
        (102,  200_000, "Operations — Service contracts"),
        (103,   50_000, "Operations — Scrap & recoveries"),
        (202, -380_000, "Operations — Payroll"),
        (203,  -45_000, "Operations — Site visits"),
        (204, -120_000, "Operations — Riyadh HQ rent"),
        (205,  -50_000, "Operations — Power & water"),
        (206,  -25_000, "Operations — Trade events"),
    ],
    # Sales & Marketing: Rev 1.2M (+), Costs 480K (-)
    2: [
        (101,  950_000, "Sales — New customer wins"),
        (102,  250_000, "Sales — Account upsell"),
        (202, -280_000, "Sales — Salesforce payroll"),
        (203,  -85_000, "Sales — Customer travel"),
        (206,  -90_000, "Sales — Digital campaigns"),
        (204,  -25_000, "Sales — Office allocation"),
    ],
    # IT & Technology: Rev 320K (+), Costs 290K (-)
    3: [
        (102,  250_000, "IT — Internal billings"),
        (103,   70_000, "IT — Project rebates"),
        (202, -150_000, "IT — Engineering payroll"),
        (207,  -95_000, "IT — SaaS subscriptions"),
        (205,  -30_000, "IT — Datacenter power"),
        (204,  -15_000, "IT — Server room rent"),
    ],
    # HR & Admin: Rev 150K (+), Costs 380K (-)
    4: [
        (103,  150_000, "HR — Training reimbursements"),
        (202, -270_000, "HR — Admin payroll"),
        (204,  -60_000, "HR — Office rent share"),
        (203,  -25_000, "HR — Recruitment travel"),
        (205,  -25_000, "HR — Office utilities"),
    ],
    # Logistics: Rev 670K (+), Costs 510K (-)
    5: [
        (101,  470_000, "Logistics — Freight pass-through"),
        (102,  200_000, "Logistics — Storage fees"),
        (202, -290_000, "Logistics — Warehouse payroll"),
        (203, -120_000, "Logistics — Last-mile travel"),
        (204,  -50_000, "Logistics — Warehouse rent"),
        (205,  -50_000, "Logistics — Warehouse utilities"),
    ],
}


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _seeded(version_major, edition):
    return random.Random(hash(("olens-demo", version_major, edition)) & 0xFFFFFFFF)


def _iso(d):
    return d.isoformat() if isinstance(d, (date, datetime)) else d


def _build_invoices(rng):
    """Customer invoices + vendor bills + refunds."""
    today = date.today()
    moves = []
    move_id = 1000

    states = ['posted', 'draft', 'cancel']
    payment_states = ['paid', 'not_paid', 'partial', 'in_payment', 'reversed']
    payment_weights = [0.55, 0.20, 0.10, 0.10, 0.05]

    specs = [
        ('out_invoice', 120, 'INV'),
        ('in_invoice',  95,  'BILL'),
        ('out_refund',  18,  'RINV'),
        ('in_refund',   12,  'RBILL'),
    ]

    for move_type, count, prefix in specs:
        for _ in range(count):
            move_id += 1
            days_ago = rng.randint(0, 360)
            inv_date = today - timedelta(days=days_ago)
            term_days = rng.choice([0, 15, 30, 45, 60, 90])
            due_date = inv_date + timedelta(days=term_days)

            untaxed = round(rng.uniform(800, 95000), 2)
            tax = round(untaxed * 0.15, 2)
            total = round(untaxed + tax, 2)

            state = rng.choices(states, weights=[0.85, 0.10, 0.05])[0]
            if state != 'posted':
                payment_state = 'not_paid'
                residual = total
            else:
                payment_state = rng.choices(payment_states, weights=payment_weights)[0]
                if payment_state == 'paid':
                    residual = 0.0
                elif payment_state == 'partial':
                    residual = round(total * rng.uniform(0.2, 0.7), 2)
                elif payment_state in ('not_paid', 'in_payment'):
                    residual = total
                else:
                    residual = 0.0

            partner_id = rng.randint(0, len(PARTNERS) - 1) + 100
            partner_name = PARTNERS[partner_id - 100]

            moves.append({
                'id': move_id,
                'name': f"{prefix}/{inv_date.year}/{move_id:05d}",
                'move_type': move_type,
                'type': move_type,
                'state': state,
                'payment_state': payment_state,
                'invoice_payment_state': payment_state,
                'partner_id': [partner_id, partner_name],
                'invoice_date': _iso(inv_date),
                'date_invoice': _iso(inv_date),
                'invoice_date_due': _iso(due_date),
                'date_due': _iso(due_date),
                'amount_untaxed': untaxed,
                'amount_tax': tax,
                'amount_total': total,
                'amount_residual': residual,
                'residual': residual,
                'currency_id': list(_CUR),
                'company_id': list(_COM),
                '_invoice_month': inv_date.strftime('%B %Y'),
                '_invoice_year': inv_date.year,
            })
    return moves


def _build_payments(rng, invoices):
    """Bank statement lines tied loosely to invoice payments."""
    lines = []
    line_id = 5000
    paid_moves = [m for m in invoices if m['payment_state'] in ('paid', 'partial', 'in_payment')]
    for m in paid_moves[:120]:
        line_id += 1
        inv_date = date.fromisoformat(m['invoice_date'])
        offset = rng.randint(1, 45)
        pay_date = inv_date + timedelta(days=offset)
        amount = round(m['amount_total'] - m['amount_residual'], 2) or m['amount_total']
        if m['move_type'].startswith('in_'):
            amount = -amount
        j = rng.choice([j for j in JOURNALS if j[2] in ('bank', 'cash')])
        lines.append({
            'id': line_id,
            'date': _iso(pay_date),
            'payment_ref': f"Payment {m['name']}",
            'partner_id': list(m['partner_id']),
            'amount': amount,
            'journal_id': [j[0], j[1]],
            '_journal_type': j[2],
            'currency_id': list(_CUR),
            'company_id': list(_COM),
        })
    return lines


def _build_sale_orders(rng):
    today = date.today()
    orders = []
    states = ['draft', 'sent', 'sale', 'done', 'cancel']
    state_weights = [0.08, 0.10, 0.55, 0.20, 0.07]
    invoice_statuses = ['no', 'to invoice', 'invoiced', 'upselling']
    for i in range(80):
        oid = 2000 + i
        days_ago = rng.randint(0, 220)
        d = today - timedelta(days=days_ago)
        amount = round(rng.uniform(4500, 380000), 2)
        partner_id = rng.randint(0, len(PARTNERS) - 1) + 100
        salesperson = rng.randint(2, 12)
        state = rng.choices(states, weights=state_weights)[0]
        orders.append({
            'id': oid,
            'name': f"SO/{d.year}/{oid:05d}",
            'partner_id': [partner_id, PARTNERS[partner_id - 100]],
            'date_order': f"{_iso(d)} 09:00:00",
            'amount_total': amount,
            'amount_untaxed': round(amount / 1.15, 2),
            'amount_tax': round(amount - amount / 1.15, 2),
            'currency_id': list(_CUR),
            'state': state,
            'user_id': [salesperson, EMPLOYEES[salesperson % len(EMPLOYEES)]],
            'invoice_status': rng.choice(invoice_statuses),
            'company_id': list(_COM),
            '_order_month': d.strftime('%B %Y'),
        })
    return orders


def _build_leads(rng):
    today = date.today()
    leads = []
    priorities = ['0', '1', '2', '3']
    stage_weights = [0.25, 0.25, 0.20, 0.20, 0.10]
    for i in range(55):
        lid = 3000 + i
        days_ago = rng.randint(0, 90)
        d = today - timedelta(days=days_ago)
        deadline = today + timedelta(days=rng.randint(-20, 90))
        partner_id = rng.randint(0, len(PARTNERS) - 1) + 100
        salesperson = rng.randint(2, 12)
        stage = rng.choices(CRM_STAGES, weights=stage_weights)[0]
        revenue = round(rng.uniform(8000, 250000), 2)
        leads.append({
            'id': lid,
            'name': f"Opportunity — {PARTNERS[partner_id - 100]}",
            'partner_id': [partner_id, PARTNERS[partner_id - 100]],
            'expected_revenue': revenue,
            'probability': float(stage[0] * 18 + rng.randint(0, 15)),
            'stage_id': [stage[0], stage[1]],
            'date_deadline': _iso(deadline),
            'create_date': f"{_iso(d)} 10:00:00",
            'user_id': [salesperson, EMPLOYEES[salesperson % len(EMPLOYEES)]],
            'priority': rng.choice(priorities),
            'type': 'opportunity',
            'active': True,
            'company_id': list(_COM),
        })
    return leads


def _build_employees(rng):
    departments = ['Finance', 'Sales', 'Operations', 'IT', 'HR', 'Manufacturing', 'Logistics']
    emps = []
    for i, name in enumerate(EMPLOYEES):
        eid = 500 + i
        emps.append({
            'id': eid,
            'name': name,
            'active': True,
            'department_id': [i % len(departments) + 1, departments[i % len(departments)]],
            'company_id': list(_COM),
        })
    return emps, departments


def _build_attendances(rng, employees, version_major):
    today = date.today()
    rows = []
    rid = 7000
    for d_off in range(28):
        day = today - timedelta(days=d_off)
        if day.weekday() == 4:  # Friday off in KSA
            continue
        sample = rng.sample(employees, k=min(len(employees), rng.randint(18, 32)))
        for emp in sample:
            rid += 1
            check_in = datetime.combine(day, datetime.min.time()).replace(hour=8, minute=rng.randint(0, 30))
            worked = round(rng.uniform(7.0, 9.5), 2)
            check_out = check_in + timedelta(hours=worked)
            row = {
                'id': rid,
                'employee_id': [emp['id'], emp['name']],
                'check_in': check_in.strftime('%Y-%m-%d %H:%M:%S'),
                'check_out': check_out.strftime('%Y-%m-%d %H:%M:%S'),
                'worked_hours': worked,
                'company_id': list(_COM),
            }
            if version_major >= 17:
                row['overtime_hours'] = max(0.0, round(worked - 8.0, 2))
            rows.append(row)
    return rows


def _build_leaves(rng, employees):
    today = date.today()
    rows = []
    states = ['draft', 'confirm', 'validate', 'refuse']
    state_weights = [0.20, 0.30, 0.45, 0.05]
    rid = 6000
    for _ in range(45):
        rid += 1
        emp = rng.choice(employees)
        ltype = rng.choice(LEAVE_TYPES)
        days_ago = rng.randint(-30, 120)
        d_from = today - timedelta(days=days_ago)
        days = rng.randint(1, 10)
        d_to = d_from + timedelta(days=days - 1)
        state = rng.choices(states, weights=state_weights)[0]
        rows.append({
            'id': rid,
            'name': f"{ltype[1]} — {emp['name']}",
            'employee_id': [emp['id'], emp['name']],
            'holiday_status_id': [ltype[0], ltype[1]],
            'date_from': f"{_iso(d_from)} 00:00:00",
            'date_to': f"{_iso(d_to)} 23:59:59",
            'number_of_days': float(days),
            'state': state,
            'company_id': list(_COM),
        })
    return rows


def _build_products():
    prods = []
    for i, (name, price) in enumerate(PRODUCTS):
        pid = 200 + i
        prods.append({
            'id': pid,
            'name': name,
            'default_code': f"P-{pid:05d}",
            'list_price': price,
            'standard_price': round(price * 0.65, 2),
            'active': True,
            'type': 'product',
            'uom_id': [1, 'Units'],
            'company_id': list(_COM),
        })
    return prods


def _build_stock_quants(rng, products, version_major):
    today = date.today()
    rows = []
    rid = 8000
    for p in products:
        for loc in [l for l in LOCATIONS if l[2] == 'internal']:
            if rng.random() < 0.55:
                continue
            rid += 1
            qty = round(rng.uniform(0, 500), 2)
            reserved = round(qty * rng.uniform(0, 0.25), 2)
            row = {
                'id': rid,
                'product_id': [p['id'], p['name']],
                'location_id': [loc[0], loc[1]],
                'quantity': qty,
                'reserved_quantity': reserved,
                'product_uom_id': [1, 'Units'],
                'value': round(qty * p['standard_price'], 2),
                'company_id': list(_COM),
                '_location_usage': loc[2],
            }
            if version_major >= 17:
                row['inventory_date'] = _iso(today - timedelta(days=rng.randint(0, 90)))
                row['cyclic_inventory_frequency'] = rng.choice([0, 7, 30, 90])
            rows.append(row)
    # Add a few zero/negative quants so "low stock" KPI is non-zero
    for p in rng.sample(products, k=8):
        rid += 1
        loc = LOCATIONS[0]
        rows.append({
            'id': rid,
            'product_id': [p['id'], p['name']],
            'location_id': [loc[0], loc[1]],
            'quantity': 0.0,
            'reserved_quantity': 0.0,
            'product_uom_id': [1, 'Units'],
            'value': 0.0,
            'company_id': list(_COM),
            '_location_usage': loc[2],
        })
    return rows


def _build_stock_moves(rng, products):
    today = date.today()
    picking_types = [(1, 'Receipts', 'incoming'), (2, 'Deliveries', 'outgoing'),
                     (3, 'Internal Transfers', 'internal')]
    rows = []
    rid = 9000
    for _ in range(180):
        rid += 1
        p = rng.choice(products)
        days_ago = rng.randint(0, 120)
        d = today - timedelta(days=days_ago)
        ptype = rng.choices(picking_types, weights=[0.40, 0.50, 0.10])[0]
        if ptype[2] == 'incoming':
            src, dst = LOCATIONS[5], LOCATIONS[0]
        elif ptype[2] == 'outgoing':
            src, dst = LOCATIONS[0], LOCATIONS[6]
        else:
            src, dst = LOCATIONS[0], LOCATIONS[1]
        qty = round(rng.uniform(1, 80), 2)
        rows.append({
            'id': rid,
            'date': f"{_iso(d)} 11:00:00",
            'product_id': [p['id'], p['name']],
            'location_id': [src[0], src[1]],
            'location_dest_id': [dst[0], dst[1]],
            'product_uom_qty': qty,
            'product_uom': [1, 'Units'],
            'picking_id': [rid + 50000, f"WH/{ptype[2].upper()[:3]}/{rid:05d}"],
            'origin': rng.choice(['SO/2024/00345', 'PO/2024/00120', 'MO/2024/00088', False, False]),
            'state': 'done',
            'picking_type_id': [ptype[0], ptype[1]],
            '_picking_code': ptype[2],
            'company_id': list(_COM),
        })
    return rows


def _build_stock_valuation_layers(rng, products):
    today = date.today()
    rows = []
    rid = 10000
    for _ in range(140):
        rid += 1
        p = rng.choice(products)
        days_ago = rng.randint(0, 200)
        d = today - timedelta(days=days_ago)
        sign = rng.choice([1, -1])
        qty = sign * round(rng.uniform(1, 50), 2)
        unit_cost = p['standard_price']
        value = round(qty * unit_cost, 2)
        rows.append({
            'id': rid,
            'product_id': [p['id'], p['name']],
            'quantity': qty,
            'value': value,
            'unit_cost': unit_cost,
            'company_id': list(_COM),
            'stock_move_id': [rid + 100000, f"MOVE/{rid:05d}"],
            'create_date': f"{_iso(d)} 12:00:00",
        })
    return rows


def _build_mrp_productions(rng, products):
    today = date.today()
    states = ['draft', 'confirmed', 'progress', 'to_close', 'done', 'cancel']
    state_weights = [0.10, 0.20, 0.25, 0.05, 0.35, 0.05]
    rows = []
    rid = 4000
    for _ in range(35):
        rid += 1
        p = rng.choice(products)
        days_ago = rng.randint(-15, 90)
        d_start = today - timedelta(days=days_ago)
        d_finish = d_start + timedelta(days=rng.randint(2, 14))
        worker = rng.randint(2, 12)
        rows.append({
            'id': rid,
            'name': f"MO/{d_start.year}/{rid:05d}",
            'product_id': [p['id'], p['name']],
            'product_qty': round(rng.uniform(5, 200), 0),
            'product_uom_id': [1, 'Units'],
            'date_planned_start': f"{_iso(d_start)} 08:00:00",
            'date_planned_finished': f"{_iso(d_finish)} 17:00:00",
            'date_start': f"{_iso(d_start)} 08:00:00",
            'state': rng.choices(states, weights=state_weights)[0],
            'user_id': [worker, EMPLOYEES[worker % len(EMPLOYEES)]],
            'company_id': list(_COM),
        })
    return rows


def _build_expenses(rng, employees):
    today = date.today()
    states = ['draft', 'reported', 'approved', 'done', 'refused']
    state_weights = [0.15, 0.20, 0.20, 0.40, 0.05]
    expense_kinds = [
        "Travel — Hotel Riyadh", "Travel — Flight DMM-RUH",
        "Client Lunch Meeting", "Office Supplies — Stationery",
        "Mobile Bill Reimbursement", "Software License — Annual",
        "Conference Registration", "Taxi & Ride Hailing",
        "Project Materials", "Internet Allowance",
    ]
    rows = []
    rid = 11000
    for _ in range(60):
        rid += 1
        emp = rng.choice(employees)
        d = today - timedelta(days=rng.randint(0, 120))
        amount = round(rng.uniform(85, 5800), 2)
        rows.append({
            'id': rid,
            'name': rng.choice(expense_kinds),
            'employee_id': [emp['id'], emp['name']],
            'date': _iso(d),
            'total_amount': amount,
            'untaxed_amount': round(amount / 1.15, 2),
            'currency_id': list(_CUR),
            'state': rng.choices(states, weights=state_weights)[0],
            'company_id': list(_COM),
        })
    return rows


def _build_assets(rng, version_major):
    """v15/v16 use account.asset.asset (`value`, `value_residual`, `category_id`).
    v17+ use account.asset (`original_value`, `book_value`, `account_asset_id`).
    """
    today = date.today()
    categories = [
        (1, "Computers & IT"),
        (2, "Vehicles"),
        (3, "Office Furniture"),
        (4, "Production Machinery"),
        (5, "Buildings"),
    ]
    states = ['draft', 'open', 'paused', 'close']
    state_weights = [0.08, 0.65, 0.05, 0.22]
    rows = []
    rid = 12000
    for _ in range(48):
        rid += 1
        cat = rng.choice(categories)
        d = today - timedelta(days=rng.randint(60, 1800))
        gross = round(rng.uniform(8500, 280000), 2)
        used_pct = rng.uniform(0.05, 0.95)
        residual = round(gross * (1 - used_pct), 2)
        state = rng.choices(states, weights=state_weights)[0]
        if state == 'close':
            residual = 0.0
        row = {
            'id': rid,
            'name': f"{cat[1]} — Asset #{rid - 12000}",
            'state': state,
            'active': True,
            'acquisition_date': _iso(d),
            'first_depreciation_date': _iso(d),
            'date': _iso(d),
            'salvage_value': round(gross * 0.05, 2),
            'currency_id': list(_CUR),
            'company_id': list(_COM),
        }
        if version_major >= 17:
            row['original_value'] = gross
            row['book_value'] = residual
            row['value_residual'] = residual
            row['account_asset_id'] = [cat[0], cat[1]]
            row['model_id'] = [cat[0] + 100, f"{cat[1]} Model"]
        else:
            row['value'] = gross
            row['gross_value'] = gross
            row['value_residual'] = residual
            row['category_id'] = [cat[0], cat[1]]
            row['parent_id'] = [cat[0] + 100, f"{cat[1]} Template"]
        rows.append(row)
    return rows


def _build_analytic_lines(rng, version_major):
    """Build 5 cost centers + analytic lines whose sums match
    DEMO_ANALYTIC_LINE_SPECS exactly, so the Analytic dashboard KPI
    cards and P&L statement reflect the demo spec deterministically."""
    today = date.today()
    plan_field = 'plan_id' if version_major >= 17 else 'group_id'

    # Lookup for GL accounts (name + type) — used to attach general_account_id
    # tuples to each analytic line.
    gl_by_id = {gid: (code, name, atype)
                for gid, code, name, atype in DEMO_GL_ACCOUNTS}

    accounts = []
    for aid, name, code, plan, *_ in ANALYTIC_ACCOUNTS:
        accounts.append({
            'id': aid,
            'name': name,
            'display_name': name,
            'code': code,
            plan_field: [plan, ANALYTIC_PLANS[plan - 1][1]],
            'company_id': list(_COM),
            'active': True,
        })

    # Spread postings across the YTD window so KPI cards with the default
    # YTD range pick up everything.
    year_start = date(today.year, 1, 1)
    ytd_days = max(1, (today - year_start).days)

    lines = []
    lid = 14000
    for aid, specs in DEMO_ANALYTIC_LINE_SPECS.items():
        acc_name = next(a['name'] for a in accounts if a['id'] == aid)
        for gl_id, amount, label in specs:
            lid += 1
            gl_code, gl_name, _gl_type = gl_by_id[gl_id]
            # Pick a date inside YTD (deterministic via rng → stable demo).
            d = year_start + timedelta(days=rng.randint(0, ytd_days))
            row = {
                'id': lid,
                'date': _iso(d),
                'name': label,
                'amount': float(amount),
                'unit_amount': 0.0,
                'company_id': list(_COM),
                'general_account_id': [gl_id, f"[{gl_code}] {gl_name}"],
            }
            if version_major >= 17:
                row['account_id'] = [aid, acc_name]
                row['auto_account_id'] = [aid, acc_name]
            else:
                row['account_id'] = [aid, acc_name]
            lines.append(row)
    return accounts, lines


def _build_budget_lines(rng, version_major):
    """Build crossovered.budget.lines for the demo cost centers.
    One line per cost center for the full current year, with
    planned_amount = budget target and practical_amount = realized costs."""
    today = date.today()
    yr = today.year
    df = _iso(date(yr, 1, 1))
    dt = _iso(date(yr, 12, 31))

    parent = {'id': 9001, 'name': f'Annual Budget {yr}'}

    posts = []
    lines = []
    bid = 16000
    pid = 17000
    for aid, name, code, plan, _rev, costs, budget in ANALYTIC_ACCOUNTS:
        pid += 1
        posts.append({
            'id': pid,
            'name': f'{name} — Operating Budget',
            'account_ids': [],
            'company_id': list(_COM),
        })
        bid += 1
        lines.append({
            'id': bid,
            'analytic_account_id': [aid, name],
            'planned_amount': float(budget),
            'practical_amount': float(costs),
            'general_budget_id': [pid, f'{name} — Operating Budget'],
            'crossovered_budget_id': [parent['id'], parent['name']],
            'date_from': df,
            'date_to': dt,
            'company_id': list(_COM),
        })
    return posts, lines, parent


# ---------------------------------------------------------------------------
# Module / edition matrix
# ---------------------------------------------------------------------------

# Base modules present on a standard Community install.
_BASE_MODULES = {
    'base', 'web', 'mail', 'contacts',
    'account',                # base accounting
    'account_budget',         # Budgets (community-friendly)
    'sale', 'sale_management', # Sales
    'purchase',
    'stock',                  # Inventory
    'hr', 'hr_holidays',      # HR + Time Off
    'hr_expense',             # Expenses
    'crm',                    # CRM/pipeline
    'mrp',                    # Manufacturing (community-friendly)
    'project',
    'analytic',
    'hr_attendance',
}

# Modules that only exist on Enterprise.
_ENTERPRISE_ONLY = {
    'web_enterprise',
    'account_asset',          # ships with Enterprise; community uses OCA
    'account_reports',
    'account_accountant',
    'hr_payroll',
    'documents',
    'sign',
    'helpdesk',
    'planning',
    'marketing_automation',
}


def installed_modules(version_major, edition):
    mods = set(_BASE_MODULES)
    if edition == 'enterprise':
        mods |= _ENTERPRISE_ONLY
    # V15 didn't ship account_asset in core even on Enterprise — it lived in
    # account_asset_management. Keep it on for simplicity but mark it.
    if version_major < 15:
        mods.discard('hr_attendance')  # only meaningful as a flag
    return mods


# Field availability per model — used by the mock's get_model_fields().
def model_fields(model, version_major):
    base = {
        'account.move': {
            'id', 'name', 'state',
            'partner_id', 'invoice_date', 'invoice_date_due', 'date_invoice', 'date_due',
            'amount_untaxed', 'amount_tax', 'amount_total', 'amount_residual', 'residual',
            'currency_id', 'company_id',
            'payment_state', 'invoice_payment_state',
        },
        'account.move.line': {
            'id', 'name', 'move_id', 'account_id', 'partner_id',
            'debit', 'credit', 'balance', 'date', 'company_id',
        },
        'account.journal': {'id', 'name', 'type', 'code', 'currency_id', 'company_id'},
        'account.bank.statement.line': {
            'id', 'date', 'payment_ref', 'partner_id', 'amount',
            'journal_id', 'currency_id', 'company_id',
        },
        'account.account': {
            'id', 'name', 'code', 'company_id', 'account_type',
        },
        'account.analytic.account': {
            'id', 'name', 'display_name', 'code', 'active', 'company_id',
        },
        'account.analytic.line': {
            'id', 'name', 'date', 'amount', 'unit_amount',
            'company_id', 'partner_id', 'general_account_id',
        },
        'crossovered.budget.lines': {
            'id', 'analytic_account_id', 'planned_amount', 'practical_amount',
            'general_budget_id', 'crossovered_budget_id',
            'date_from', 'date_to', 'company_id',
        },
        'crossovered.budget': {
            'id', 'name', 'company_id', 'state',
        },
        'account.budget.post': {
            'id', 'name', 'account_ids', 'company_id',
        },
        'res.users': {'id', 'name', 'login', 'company_id', 'company_ids'},
        'res.company': {'id', 'name', 'currency_id'},
        'res.currency': {'id', 'name', 'symbol'},
        'res.partner': {'id', 'name', 'is_company'},
        'product.product': {
            'id', 'name', 'default_code', 'list_price', 'standard_price',
            'active', 'type', 'uom_id', 'company_id',
        },
        'stock.quant': {
            'id', 'product_id', 'location_id', 'quantity', 'reserved_quantity',
            'product_uom_id', 'value', 'company_id',
        },
        'stock.move': {
            'id', 'date', 'product_id', 'location_id', 'location_dest_id',
            'product_uom_qty', 'product_uom', 'picking_id', 'origin', 'state',
            'picking_type_id', 'company_id',
        },
        'stock.valuation.layer': {
            'id', 'product_id', 'quantity', 'value', 'unit_cost',
            'company_id', 'stock_move_id', 'create_date',
        },
        'sale.order': {
            'id', 'name', 'partner_id', 'date_order', 'amount_total',
            'amount_untaxed', 'amount_tax', 'currency_id', 'state',
            'user_id', 'invoice_status', 'company_id',
        },
        'crm.lead': {
            'id', 'name', 'partner_id', 'expected_revenue', 'probability',
            'stage_id', 'date_deadline', 'create_date', 'user_id',
            'priority', 'type', 'active', 'company_id',
        },
        'hr.employee': {
            'id', 'name', 'active', 'department_id', 'company_id',
        },
        'hr.attendance': {
            'id', 'employee_id', 'check_in', 'check_out', 'worked_hours', 'company_id',
        },
        'hr.leave': {
            'id', 'name', 'employee_id', 'holiday_status_id', 'date_from', 'date_to',
            'number_of_days', 'state', 'company_id',
        },
        'hr.expense': {
            'id', 'name', 'employee_id', 'date', 'total_amount', 'untaxed_amount',
            'currency_id', 'state', 'company_id',
        },
        'mrp.production': {
            'id', 'name', 'product_id', 'product_qty', 'product_uom_id',
            'date_planned_start', 'date_planned_finished', 'date_start', 'state',
            'user_id', 'company_id',
        },
        'ir.module.module': {'id', 'name', 'state'},
        'ir.actions.act_window': {'id', 'name', 'res_model', 'res_id', 'type'},
    }
    # v17+ field additions
    if version_major >= 17:
        base['hr.attendance'] |= {'overtime_hours'}
        base['stock.quant'] |= {'inventory_date', 'cyclic_inventory_frequency'}
        base['account.analytic.line'] |= {'auto_account_id', 'account_id'}
        base['account.analytic.account'] |= {'plan_id'}
    else:
        base['account.analytic.line'] |= {'account_id'}
        base['account.analytic.account'] |= {'group_id'}

    # Asset model name differs by version.
    if version_major >= 17:
        base['account.asset'] = {
            'id', 'name', 'state', 'active', 'acquisition_date', 'first_depreciation_date',
            'date', 'original_value', 'book_value', 'value_residual', 'salvage_value',
            'account_asset_id', 'model_id', 'currency_id', 'company_id',
        }
    else:
        base['account.asset.asset'] = {
            'id', 'name', 'state', 'active', 'acquisition_date', 'first_depreciation_date',
            'date', 'value', 'gross_value', 'value_residual', 'salvage_value',
            'category_id', 'parent_id', 'currency_id', 'company_id',
        }
        base['account.asset.depreciation.line'] = {
            'id', 'asset_id', 'amount', 'depreciation_date', 'move_id', 'move_check',
        }
    return base.get(model, set())


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_dataset(version_major, edition):
    rng = _seeded(version_major, edition)
    invoices = _build_invoices(rng)
    employees, _depts = _build_employees(rng)
    attendances = _build_attendances(rng, employees, version_major)
    leaves = _build_leaves(rng, employees)
    products = _build_products()
    quants = _build_stock_quants(rng, products, version_major)
    moves = _build_stock_moves(rng, products)
    valuations = _build_stock_valuation_layers(rng, products)
    productions = _build_mrp_productions(rng, products)
    expenses = _build_expenses(rng, employees)
    assets = _build_assets(rng, version_major)
    analytic_accounts, analytic_lines = _build_analytic_lines(rng, version_major)
    budget_posts, budget_lines, budget_parent = _build_budget_lines(rng, version_major)
    payments = _build_payments(rng, invoices)

    dataset = {
        'account.move':                 invoices,
        'account.move.line':            [],
        'account.journal':              [
            {'id': j[0], 'name': j[1], 'type': j[2], 'code': f"J{j[0]:03d}",
             'currency_id': list(_CUR), 'company_id': list(_COM)} for j in JOURNALS
        ],
        'account.bank.statement.line':  payments,
        'account.account':              [
            {'id': gid, 'name': n, 'code': c, 'account_type': t,
             'company_id': list(_COM)}
            for gid, c, n, t in DEMO_GL_ACCOUNTS
        ],
        'account.analytic.account':     analytic_accounts,
        'account.analytic.line':        analytic_lines,
        'crossovered.budget':           [{
            'id': budget_parent['id'], 'name': budget_parent['name'],
            'company_id': list(_COM), 'state': 'validate',
        }],
        'crossovered.budget.lines':     budget_lines,
        'account.budget.post':          budget_posts,
        'res.users':                    [{'id': 2, 'name': 'Demo Admin',
                                         'login': 'demo@olens.io',
                                         'company_id': list(_COM),
                                         'company_ids': [DEMO_COMPANY_ID]}],
        'res.company':                  [{'id': DEMO_COMPANY_ID, 'name': DEMO_COMPANY_NAME,
                                         'currency_id': list(_CUR)}],
        'res.currency':                 [{'id': DEMO_CURRENCY_ID,
                                         'name': DEMO_CURRENCY_NAME,
                                         'symbol': DEMO_CURRENCY_SYMBOL}],
        'res.partner':                  [{'id': 100 + i, 'name': n, 'is_company': True}
                                         for i, n in enumerate(PARTNERS)],
        'product.product':              products,
        'stock.quant':                  quants,
        'stock.move':                   moves,
        'stock.valuation.layer':        valuations,
        'sale.order':                   _build_sale_orders(rng),
        'crm.lead':                     _build_leads(rng),
        'hr.employee':                  employees,
        'hr.attendance':                attendances,
        'hr.leave':                     leaves,
        'hr.expense':                   expenses,
        'mrp.production':               productions,
        'ir.module.module':             [
            {'id': i + 1, 'name': m, 'state': 'installed'}
            for i, m in enumerate(sorted(installed_modules(version_major, edition)))
        ],
        'ir.actions.act_window':        [],
    }

    # Asset model name depends on version.
    if version_major >= 17:
        dataset['account.asset'] = assets
    else:
        dataset['account.asset.asset'] = assets
        dataset['account.asset.depreciation.line'] = []

    return dataset


# Dotted-path resolution for the domain evaluator. When a domain like
# `[('location_id.usage', '=', 'internal')]` arrives, we look the model up
# here and translate the dotted field into the denormalized scalar stored on
# each record (e.g. `_location_usage`).
DOTTED_ALIASES = {
    'stock.quant': {
        'location_id.usage': '_location_usage',
    },
    'stock.move': {
        'picking_type_id.code': '_picking_code',
    },
    'account.bank.statement.line': {
        'journal_id.type': '_journal_type',
    },
}


def version_info(version_major, edition):
    """Mimics what xmlrpc /xmlrpc/2/common.version() returns."""
    serie = f"{version_major}.0"
    suffix = "+e" if edition == 'enterprise' else ""
    return {
        'server_version': f"{serie}{suffix}",
        'server_version_info': [version_major, 0, 0, 'final', 0, suffix.lstrip('+')],
        'server_serie': serie,
        'protocol_version': 1,
    }


# ---------------------------------------------------------------------------
# Financial statements — hand-tuned figures for a mid-size Saudi trading
# company so that:
#   * Balance Sheet balances (Assets == Liabilities + Equity)
#   * Trial Balance balances (Total Debits == Total Credits)
#   * Current-year P&L net profit feeds Retained Earnings → Equity
#   * Ratios are derivable from the underlying numbers
# Amounts are in SAR (full units, no scaling).
# ---------------------------------------------------------------------------

# Current period P&L line items (one row per account).
FS_PNL_LINES = {
    # Revenue (positive)
    'product_sales':         ('Product Sales',              'revenue', 12_400_000, 10_800_000),
    'service_revenue':       ('Service Revenue',            'revenue',  5_200_000,  4_500_000),
    'other_income':          ('Other Income',               'revenue',    900_000,    900_000),
    # Cost of Revenue (positive figures, treated as subtractions)
    'cogs':                  ('Cost of Goods Sold',         'cogs',     8_600_000,  7_600_000),
    'direct_labor':          ('Direct Labor',               'cogs',     1_200_000,  1_050_000),
    # Operating expenses (positive figures, treated as subtractions)
    'salaries':              ('Salaries & Wages',           'opex',     2_800_000,  2_550_000),
    'rent_utilities':        ('Rent & Utilities',           'opex',       720_000,    680_000),
    'marketing':             ('Marketing & Advertising',    'opex',       580_000,    500_000),
    'depreciation':          ('Depreciation',               'opex',       450_000,    430_000),
    'other_opex':            ('Other Operating Expenses',   'opex',       600_000,    540_000),
    # Other income / expenses (signed — positive = income, negative = cost)
    'finance_income':        ('Finance Income',             'other_inc',   180_000,    120_000),
    'finance_costs':         ('Finance Costs',              'other_exp',   420_000,    380_000),
    # Tax (subtraction)
    'tax_expense':           ('Tax Expense',                'tax',         800_000,    580_000),
}


# Balance sheet items keyed by section. Tuples: (label, current, previous_year).
FS_BALANCE_SHEET = {
    'current_assets': [
        ('Cash & Bank',                   2_800_000, 2_100_000),
        ('Accounts Receivable',           4_200_000, 3_700_000),
        ('Inventory',                     5_600_000, 5_100_000),
        ('Other Current Assets',            350_000,   320_000),
    ],
    'non_current_assets': [
        ('Property & Equipment',          8_500_000, 8_500_000),
        ('Accumulated Depreciation',     -1_800_000, -1_350_000),
        ('Other Non-Current Assets',        950_000,   910_000),
    ],
    'current_liabilities': [
        ('Accounts Payable',              3_100_000, 2_950_000),
        ('Short-term Loans',              1_800_000, 2_000_000),
        ('Other Current Liabilities',       720_000,   680_000),
    ],
    'non_current_liabilities': [
        ('Long-term Loans',               4_200_000, 4_800_000),
        ('Other Non-Current Liabilities',   380_000,   350_000),
    ],
    'equity': [
        ('Share Capital',                 5_000_000, 5_000_000),
        ('Retained Earnings',             2_890_000, 1_490_000),
        # Current year profit is computed from FS_PNL_LINES and injected at runtime.
    ],
    # Hand-tuned current-year profit (matches prior-year P&L net profit so
    # BS comparison columns balance: 19.28M assets == 10.78M liab + 8.5M eq).
    'current_year_profit_previous': 2_010_000,
}


# Trial Balance — one row per GL account. Tuples:
#   (code, name, type, opening_debit, opening_credit, movement_debit, movement_credit)
# Closing = opening + movement (per side); we derive both closing columns.
# The figures are chosen so that:
#   * Total opening debits == total opening credits
#   * Total period debits == total period credits
#   * Total closing debits == total closing credits
#   * P&L closing balances match FS_PNL_LINES amounts
#   * BS closing balances match FS_BALANCE_SHEET (current period)
# Granular chart of accounts (id, code, name, account_type, balance in SAR).
# Drives the Account Mapping Settings picker. The per-type subtotals here
# reconcile with the FS_BALANCE_SHEET aggregated lines so the picker shows
# the same underlying numbers seen on the Balance Sheet tab.
FS_CHART_OF_ACCOUNTS = [
    # asset_cash — split between physical cash and bank accounts. The
    # default mapping classifies the first three as "Cash Only" and the
    # bank accounts as Bank (excluded from the strict cash ratio).
    (1010, '1010', 'Petty Cash',                    'asset_cash',           200_000),
    (1015, '1015', 'Cash on Hand - Riyadh Office',  'asset_cash',           350_000),
    (1016, '1016', 'Cash on Hand - Jeddah Office',  'asset_cash',           250_000),
    (1020, '1020', 'Cash - Main Vault',             'asset_cash',           700_000),
    (1030, '1030', 'Bank - NCB Operating SAR',      'asset_cash',           800_000),
    (1031, '1031', 'Bank - Riyadh Bank USD',        'asset_cash',           300_000),
    (1032, '1032', 'Bank - SABB Reserve',           'asset_cash',           200_000),

    # asset_current — inventory + prepayments + other.
    (1101, '1101', 'Raw Materials Inventory',       'asset_current',      1_900_000),
    (1102, '1102', 'Work in Progress',              'asset_current',        820_000),
    (1103, '1103', 'Finished Goods Inventory',      'asset_current',      2_650_000),
    (1104, '1104', 'Goods in Transit',              'asset_current',        230_000),
    (1110, '1110', 'Prepaid Insurance',             'asset_current',        120_000),
    (1115, '1115', 'Prepaid Rent',                  'asset_current',         80_000),
    (1120, '1120', 'Other Current Assets',          'asset_current',        150_000),

    # asset_receivable
    (1200, '1200', 'Accounts Receivable - Trade',   'asset_receivable',   4_200_000),

    # asset_fixed / asset_non_current
    (1500, '1500', 'Property & Equipment',          'asset_fixed',        8_500_000),
    (1510, '1510', 'Accumulated Depreciation',     'asset_fixed',       -1_800_000),
    (1600, '1600', 'Other Non-Current Assets',      'asset_non_current',    950_000),

    # liability_payable
    (2100, '2100', 'Accounts Payable - Trade',      'liability_payable',  2_700_000),
    (2110, '2110', 'Accounts Payable - VAT',        'liability_payable',    400_000),

    # liability_current
    (2200, '2200', 'Short-term Loans',              'liability_current',  1_800_000),
    (2210, '2210', 'Accrued Salaries',              'liability_current',    320_000),
    (2220, '2220', 'Accrued Expenses',              'liability_current',    180_000),
    (2230, '2230', 'Tax Payable',                   'liability_current',    220_000),

    # liability_non_current
    (2500, '2500', 'Long-term Loans',               'liability_non_current', 4_200_000),
    (2510, '2510', 'Deferred Tax Liability',        'liability_non_current',   280_000),
    (2520, '2520', 'Other Non-Current Liabilities', 'liability_non_current',   100_000),

    # equity
    (3000, '3000', 'Share Capital',                 'equity',             5_000_000),
    (3100, '3100', 'Retained Earnings',             'equity',             2_890_000),
    (3200, '3200', 'Current Year Profit',           'equity',             2_510_000),
]


# Default selections shown in demo mode before any user customization.
FS_DEMO_INVENTORY_DEFAULTS = [1101, 1102, 1103, 1104]
FS_DEMO_CASH_DEFAULTS = [1010, 1015, 1016, 1020]


# Seed Custom Ratios shown the first time a demo user opens the Ratios
# tab — wired so the feature is immediately visible without forcing the
# user to fill in the builder before seeing anything.
FS_DEMO_CUSTOM_RATIOS = [
    {
        'id': 'demo_operating_efficiency',
        'name_en': 'Operating Efficiency',
        'name_ar': 'كفاءة التشغيل',
        'description': 'Operating profit as a percentage of revenue.',
        'section': 'profitability',
        'numerator':   [{'op': '+', 'var': 'operating_profit'}],
        'denominator': [{'op': '+', 'var': 'revenue'}],
        'chart_type': 'bar',
        'result_format': 'percentage',
        'benchmarks': [
            {'label': 'Strong',  'min': 20, 'max': 100, 'color': 'green'},
            {'label': 'Average', 'min': 10, 'max': 20,  'color': 'yellow'},
            {'label': 'Weak',    'min': 0,  'max': 10,  'color': 'red'},
        ],
        'interpretation':    'Operating profit keeps {value} of every SAR of revenue.',
        'interpretation_ar': 'يحتفظ الربح التشغيلي بـ {value} من كل ريال إيرادات.',
    },
    {
        'id': 'demo_asset_coverage',
        'name_en': 'Asset Coverage',
        'name_ar': 'تغطية الأصول',
        'description': 'How many times total assets cover total liabilities.',
        'section': 'leverage',
        'numerator':   [{'op': '+', 'var': 'total_assets'}],
        'denominator': [{'op': '+', 'var': 'total_liabilities'}],
        'chart_type': 'gauge',
        'result_format': 'multiplier',
        'benchmarks': [
            {'label': 'Strong',   'min': 2.0, 'max': 999, 'color': 'green'},
            {'label': 'Adequate', 'min': 1.5, 'max': 2.0, 'color': 'yellow'},
            {'label': 'Risk',     'min': 0,   'max': 1.5, 'color': 'red'},
        ],
        'interpretation':    'Total assets cover total liabilities {value} over.',
        'interpretation_ar': 'إجمالي الأصول يغطي إجمالي الالتزامات {value}.',
    },
]


FS_TRIAL_BALANCE = [
    # ASSETS — normally debit balance
    ('1100', 'Cash & Bank',                 'Asset',      2_100_000,        0, 18_400_000, 17_700_000),
    ('1200', 'Accounts Receivable',         'Asset',      3_700_000,        0,  9_100_000,  8_600_000),
    ('1300', 'Inventory',                   'Asset',      5_100_000,        0,  3_200_000,  2_700_000),
    ('1400', 'Other Current Assets',        'Asset',        320_000,        0,    180_000,    150_000),
    ('1500', 'Property & Equipment',        'Asset',      8_500_000,        0,          0,          0),
    ('1510', 'Accumulated Depreciation',    'Asset',              0, 1_350_000,          0,    450_000),
    ('1600', 'Other Non-Current Assets',    'Asset',        910_000,        0,     90_000,     50_000),
    # LIABILITIES — normally credit balance
    ('2100', 'Accounts Payable',            'Liability',          0, 2_950_000,  6_400_000,  6_550_000),
    ('2200', 'Short-term Loans',            'Liability',          0, 2_000_000,    400_000,    200_000),
    ('2300', 'Other Current Liabilities',   'Liability',          0,   680_000,    480_000,    520_000),
    ('2500', 'Long-term Loans',             'Liability',          0, 4_800_000,    700_000,    100_000),
    ('2600', 'Other Non-Current Liabilities','Liability',         0,   350_000,     20_000,     50_000),
    # EQUITY — normally credit balance
    # RE opening = prior RE 1,490K + prior CY profit 2,010K rolled in at close = 3,500K.
    # Period movement = 610K distribution (debit) bringing closing RE to 2,890K.
    ('3000', 'Share Capital',               'Equity',             0, 5_000_000,          0,          0),
    ('3100', 'Retained Earnings',           'Equity',             0, 3_500_000,    610_000,         0),
    # REVENUE — credit balance during the year
    ('4000', 'Product Sales',               'Revenue',            0,         0,          0, 12_400_000),
    ('4100', 'Service Revenue',             'Revenue',            0,         0,          0,  5_200_000),
    ('4900', 'Other Income',                'Revenue',            0,         0,          0,    900_000),
    ('4950', 'Finance Income',              'Revenue',            0,         0,          0,    180_000),
    # EXPENSES — debit balance during the year
    ('5000', 'Cost of Goods Sold',          'Expense',            0,         0,  8_600_000,          0),
    ('5050', 'Direct Labor',                'Expense',            0,         0,  1_200_000,          0),
    ('5100', 'Salaries & Wages',            'Expense',            0,         0,  2_800_000,          0),
    ('5200', 'Rent & Utilities',            'Expense',            0,         0,    720_000,          0),
    ('5300', 'Marketing & Advertising',     'Expense',            0,         0,    580_000,          0),
    ('5400', 'Depreciation',                'Expense',            0,         0,    450_000,          0),
    ('5500', 'Other Operating Expenses',    'Expense',            0,         0,    600_000,          0),
    ('5600', 'Finance Costs',               'Expense',            0,         0,    420_000,          0),
    ('5900', 'Tax Expense',                 'Expense',            0,         0,    800_000,          0),
]


def _pnl_compute(period='current'):
    """Compute aggregated P&L figures from FS_PNL_LINES."""
    idx = 2 if period == 'current' else 3
    by_cat = {}
    for label, cat, cur, prev in FS_PNL_LINES.values():
        v = cur if period == 'current' else prev
        by_cat.setdefault(cat, 0)
        by_cat[cat] += v

    revenue = by_cat.get('revenue', 0)
    cogs = by_cat.get('cogs', 0)
    opex = by_cat.get('opex', 0)
    other_inc = by_cat.get('other_inc', 0)
    other_exp = by_cat.get('other_exp', 0)
    tax = by_cat.get('tax', 0)

    gross_profit = revenue - cogs
    operating_profit = gross_profit - opex
    net_profit_before_tax = operating_profit + other_inc - other_exp
    net_profit = net_profit_before_tax - tax
    return {
        'revenue': revenue, 'cogs': cogs, 'opex': opex,
        'other_inc': other_inc, 'other_exp': other_exp, 'tax': tax,
        'gross_profit': gross_profit,
        'operating_profit': operating_profit,
        'net_profit_before_tax': net_profit_before_tax,
        'net_profit': net_profit,
        'gross_margin_pct':       (gross_profit / revenue * 100) if revenue else 0,
        'operating_margin_pct':   (operating_profit / revenue * 100) if revenue else 0,
        'net_margin_pct':         (net_profit / revenue * 100) if revenue else 0,
    }


def financial_statements_snapshot(mapping=None):
    """Return a fully-populated, internally-consistent snapshot of all four
    statements (P&L, Balance Sheet, Trial Balance, Ratios).

    `mapping` is an optional `{'inventory_ids': [...], 'cash_ids': [...]}` dict.
    When provided, the Quick Ratio's inventory deduction and the Cash Ratio's
    numerator are computed from the *selected* chart-of-accounts rows rather
    than from the BS aggregated lines. Liability classification always
    follows Odoo's `account_type` (auto-detected — never user-mapped)."""
    pnl_cur = _pnl_compute('current')
    pnl_prev = _pnl_compute('previous')

    def _row(key):
        label, _cat, cur, prev = FS_PNL_LINES[key]
        return {'label': label, 'current': cur, 'previous': prev}

    pnl_sections = [
        {
            'key': 'revenue',
            'label': 'Revenue',
            'label_ar': 'الإيرادات',
            'lines': [_row('product_sales'), _row('service_revenue'), _row('other_income')],
            'subtotal_label': 'TOTAL REVENUE',
            'subtotal_label_ar': 'إجمالي الإيرادات',
            'subtotal_current': pnl_cur['revenue'],
            'subtotal_previous': pnl_prev['revenue'],
            'sign': 1,
        },
        {
            'key': 'cogs',
            'label': 'Cost of Revenue',
            'label_ar': 'تكلفة الإيرادات',
            'lines': [_row('cogs'), _row('direct_labor')],
            'subtotal_label': 'GROSS PROFIT',
            'subtotal_label_ar': 'مجمل الربح',
            'subtotal_current': pnl_cur['gross_profit'],
            'subtotal_previous': pnl_prev['gross_profit'],
            'subtotal_pct_current': pnl_cur['gross_margin_pct'],
            'subtotal_pct_previous': pnl_prev['gross_margin_pct'],
            'subtotal_pct_label': 'Gross Margin %',
            'subtotal_pct_label_ar': 'هامش الربح الإجمالي %',
            'sign': -1,
        },
        {
            'key': 'opex',
            'label': 'Operating Expenses',
            'label_ar': 'المصروفات التشغيلية',
            'lines': [_row('salaries'), _row('rent_utilities'), _row('marketing'),
                      _row('depreciation'), _row('other_opex')],
            'subtotal_label': 'OPERATING PROFIT',
            'subtotal_label_ar': 'الربح التشغيلي',
            'subtotal_current': pnl_cur['operating_profit'],
            'subtotal_previous': pnl_prev['operating_profit'],
            'subtotal_pct_current': pnl_cur['operating_margin_pct'],
            'subtotal_pct_previous': pnl_prev['operating_margin_pct'],
            'subtotal_pct_label': 'Operating Margin %',
            'subtotal_pct_label_ar': 'هامش الربح التشغيلي %',
            'sign': -1,
        },
        {
            'key': 'other',
            'label': 'Other Income / Expenses',
            'label_ar': 'إيرادات/مصروفات أخرى',
            'lines': [_row('finance_income'), _row('finance_costs')],
            'subtotal_label': 'NET PROFIT BEFORE TAX',
            'subtotal_label_ar': 'صافي الربح قبل الضريبة',
            'subtotal_current': pnl_cur['net_profit_before_tax'],
            'subtotal_previous': pnl_prev['net_profit_before_tax'],
            'sign': 0,  # mixed
        },
        {
            'key': 'tax',
            'label': 'Tax Expense',
            'label_ar': 'مصروف الضريبة',
            'lines': [_row('tax_expense')],
            'subtotal_label': 'NET PROFIT',
            'subtotal_label_ar': 'صافي الربح',
            'subtotal_current': pnl_cur['net_profit'],
            'subtotal_previous': pnl_prev['net_profit'],
            'subtotal_pct_current': pnl_cur['net_margin_pct'],
            'subtotal_pct_previous': pnl_prev['net_margin_pct'],
            'subtotal_pct_label': 'Net Margin %',
            'subtotal_pct_label_ar': 'هامش الربح الصافي %',
            'sign': -1,
        },
    ]

    # ---- Balance Sheet ----
    def _bs_block(rows):
        out = []
        total_cur = 0
        total_prev = 0
        for label, cur, prev in rows:
            out.append({'label': label, 'current': cur, 'previous': prev})
            total_cur += cur
            total_prev += prev
        return out, total_cur, total_prev

    ca_lines, ca_cur, ca_prev = _bs_block(FS_BALANCE_SHEET['current_assets'])
    nca_lines, nca_cur, nca_prev = _bs_block(FS_BALANCE_SHEET['non_current_assets'])
    cl_lines, cl_cur, cl_prev = _bs_block(FS_BALANCE_SHEET['current_liabilities'])
    ncl_lines, ncl_cur, ncl_prev = _bs_block(FS_BALANCE_SHEET['non_current_liabilities'])

    equity_lines, eq_cur, eq_prev = _bs_block(FS_BALANCE_SHEET['equity'])
    # Append current-year profit row sourced from the P&L
    equity_lines.append({
        'label': 'Current Year Profit',
        'current': pnl_cur['net_profit'],
        'previous': FS_BALANCE_SHEET['current_year_profit_previous'],
    })
    eq_cur += pnl_cur['net_profit']
    eq_prev += FS_BALANCE_SHEET['current_year_profit_previous']

    total_assets_cur = ca_cur + nca_cur
    total_assets_prev = ca_prev + nca_prev
    total_liab_cur = cl_cur + ncl_cur
    total_liab_prev = cl_prev + ncl_prev
    total_le_cur = total_liab_cur + eq_cur
    total_le_prev = total_liab_prev + eq_prev

    working_capital_cur = ca_cur - cl_cur
    current_ratio_cur = (ca_cur / cl_cur) if cl_cur else 0
    debt_to_equity_cur = (total_liab_cur / eq_cur) if eq_cur else 0
    debt_ratio_cur = (total_liab_cur / total_assets_cur) if total_assets_cur else 0

    # Cash and ST/LT debt extracted from BS for ratio formulas.
    cash_cur = next((r['current'] for r in ca_lines if r['label'] == 'Cash & Bank'), 0)
    inventory_cur = next((r['current'] for r in ca_lines if r['label'] == 'Inventory'), 0)

    # User-supplied account mapping overrides the BS-line defaults so the
    # ratio panel reflects what the user considers "true cash" and
    # "true inventory" — bank balances and prepayments are typically
    # excluded from a strict Cash Ratio / Quick Ratio.
    mapping_used = False
    if mapping:
        coa_by_id = {row[0]: row for row in FS_CHART_OF_ACCOUNTS}
        inv_ids = [int(i) for i in (mapping.get('inventory_ids') or [])]
        cash_ids = [int(i) for i in (mapping.get('cash_ids') or [])]
        if inv_ids:
            inventory_cur = sum(coa_by_id[i][4] for i in inv_ids if i in coa_by_id)
            mapping_used = True
        if cash_ids:
            cash_cur = sum(coa_by_id[i][4] for i in cash_ids if i in coa_by_id)
            mapping_used = True
    ar_cur = next((r['current'] for r in ca_lines if r['label'] == 'Accounts Receivable'), 0)
    ap_cur = next((r['current'] for r in cl_lines if r['label'] == 'Accounts Payable'), 0)
    st_debt_cur = next((r['current'] for r in cl_lines if r['label'] == 'Short-term Loans'), 0)
    lt_debt_cur = next((r['current'] for r in ncl_lines if r['label'] == 'Long-term Loans'), 0)

    bs = {
        'assets': {
            'current': ca_lines, 'total_current': ca_cur, 'total_current_prev': ca_prev,
            'non_current': nca_lines, 'total_non_current': nca_cur, 'total_non_current_prev': nca_prev,
            'total': total_assets_cur, 'total_prev': total_assets_prev,
        },
        'liabilities': {
            'current': cl_lines, 'total_current': cl_cur, 'total_current_prev': cl_prev,
            'non_current': ncl_lines, 'total_non_current': ncl_cur, 'total_non_current_prev': ncl_prev,
            'total': total_liab_cur, 'total_prev': total_liab_prev,
        },
        'equity': {
            'lines': equity_lines, 'total': eq_cur, 'total_prev': eq_prev,
        },
        'total_liab_equity': total_le_cur,
        'total_liab_equity_prev': total_le_prev,
        'balanced': total_assets_cur == total_le_cur,
        'difference': total_assets_cur - total_le_cur,
        'kpis': {
            'total_assets': total_assets_cur,
            'total_liabilities': total_liab_cur,
            'total_equity': eq_cur,
            'current_ratio': current_ratio_cur,
            'debt_to_equity': debt_to_equity_cur,
            'working_capital': working_capital_cur,
        },
    }

    # ---- Trial Balance ----
    tb_lines = []
    grand = {'od': 0, 'oc': 0, 'md': 0, 'mc': 0, 'cd': 0, 'cc': 0}
    for code, name, atype, od, oc, md, mc in FS_TRIAL_BALANCE:
        net_open = od - oc
        net_move = md - mc
        net_close = net_open + net_move
        cd = net_close if net_close > 0 else 0
        cc = -net_close if net_close < 0 else 0
        tb_lines.append({
            'code': code, 'name': name, 'type': atype,
            'opening_debit': od, 'opening_credit': oc,
            'movement_debit': md, 'movement_credit': mc,
            'closing_debit': cd, 'closing_credit': cc,
        })
        grand['od'] += od; grand['oc'] += oc
        grand['md'] += md; grand['mc'] += mc
        grand['cd'] += cd; grand['cc'] += cc

    tb = {
        'lines': tb_lines,
        'totals': grand,
        'kpis': {
            'total_debits': grand['cd'],
            'total_credits': grand['cc'],
            'difference': grand['cd'] - grand['cc'],
            'total_accounts': len(tb_lines),
        },
        'balanced': grand['cd'] == grand['cc'],
    }

    # ---- Ratios ----
    revenue = pnl_cur['revenue']
    net_profit = pnl_cur['net_profit']
    gross_profit = pnl_cur['gross_profit']
    quick_ratio = (ca_cur - inventory_cur) / cl_cur if cl_cur else 0
    cash_ratio = cash_cur / cl_cur if cl_cur else 0
    roa = (net_profit / total_assets_cur * 100) if total_assets_cur else 0
    roe = (net_profit / eq_cur * 100) if eq_cur else 0
    equity_multiplier = total_assets_cur / eq_cur if eq_cur else 0
    asset_turnover = revenue / total_assets_cur if total_assets_cur else 0
    receivables_turnover = revenue / ar_cur if ar_cur else 0
    payables_turnover = (pnl_cur['cogs']) / ap_cur if ap_cur else 0
    st_lt_ratio = st_debt_cur / lt_debt_cur if lt_debt_cur else 0

    # Days proxies for the turnover interpretations
    dso_days = int(365 / receivables_turnover) if receivables_turnover else 0
    dpo_days = int(365 / payables_turnover) if payables_turnover else 0

    ratios = {
        'liquidity': [
            {'key': 'current_ratio', 'name': 'Current Ratio',
             'name_ar': 'نسبة السيولة الجارية',
             'value': current_ratio_cur, 'value_str': f'{current_ratio_cur:.2f}',
             'formula': 'Current Assets ÷ Current Liabilities',
             'formula_ar': 'الأصول المتداولة ÷ الالتزامات المتداولة',
             'numerator': ca_cur, 'denominator': cl_cur,
             'unit': 'x', 'viz': 'gauge',
             'min': 0, 'max': 3,
             'benchmarks': [
                {'op': '>=', 'value': 1.5, 'color': 'green',  'label': 'Healthy (≥ 1.5)',     'label_ar': 'ممتاز (≥ 1.5)'},
                {'op': '>=', 'value': 1.0, 'color': 'yellow', 'label': 'Adequate (1.0 – 1.5)','label_ar': 'مقبول (1.0 – 1.5)'},
                {'op': '<',  'value': 1.0, 'color': 'red',    'label': 'Tight (< 1.0)',      'label_ar': 'ضعيف (< 1.0)'},
             ],
             'interpretation':    f'The company can cover short-term debts {current_ratio_cur:.2f}× over.',
             'interpretation_ar': f'الشركة قادرة على سداد التزاماتها المتداولة {current_ratio_cur:.2f}×'},
            {'key': 'quick_ratio', 'name': 'Quick Ratio',
             'name_ar': 'نسبة السيولة السريعة',
             'value': quick_ratio, 'value_str': f'{quick_ratio:.2f}',
             'formula': '(Current Assets − Inventory) ÷ Current Liabilities',
             'formula_ar': '(الأصول المتداولة − المخزون) ÷ الالتزامات المتداولة',
             'numerator': ca_cur - inventory_cur, 'denominator': cl_cur,
             'unit': 'x', 'viz': 'gauge',
             'min': 0, 'max': 2,
             'benchmarks': [
                {'op': '>=', 'value': 1.0, 'color': 'green',  'label': 'Healthy (≥ 1.0)',     'label_ar': 'ممتاز (≥ 1.0)'},
                {'op': '>=', 'value': 0.5, 'color': 'yellow', 'label': 'Adequate (0.5 – 1.0)','label_ar': 'مقبول (0.5 – 1.0)'},
                {'op': '<',  'value': 0.5, 'color': 'red',    'label': 'Tight (< 0.5)',      'label_ar': 'ضعيف (< 0.5)'},
             ],
             'interpretation':    f'Without selling inventory, the company covers {quick_ratio:.2f}× of short-term debt.',
             'interpretation_ar': f'بدون بيع المخزون، تغطي الشركة {quick_ratio:.2f}× من ديونها قصيرة الأجل'},
            {'key': 'cash_ratio', 'name': 'Cash Ratio',
             'name_ar': 'نسبة النقدية',
             'value': cash_ratio, 'value_str': f'{cash_ratio:.2f}',
             'formula': 'Cash ÷ Current Liabilities',
             'formula_ar': 'النقدية ÷ الالتزامات المتداولة',
             'numerator': cash_cur, 'denominator': cl_cur,
             'unit': 'x', 'viz': 'gauge',
             'min': 0, 'max': 1.2,
             'benchmarks': [
                {'op': '>=', 'value': 0.5, 'color': 'green',  'label': 'Healthy (≥ 0.5)',     'label_ar': 'ممتاز (≥ 0.5)'},
                {'op': '>=', 'value': 0.2, 'color': 'yellow', 'label': 'Adequate (0.2 – 0.5)','label_ar': 'مقبول (0.2 – 0.5)'},
                {'op': '<',  'value': 0.2, 'color': 'red',    'label': 'Tight (< 0.2)',      'label_ar': 'ضعيف (< 0.2)'},
             ],
             'interpretation':    f'Cash alone covers {cash_ratio:.2f}× of short-term obligations.',
             'interpretation_ar': f'تغطي النقدية المتاحة {cash_ratio:.2f}× من الالتزامات قصيرة الأجل'},
        ],
        'profitability': [
            {'key': 'gross_margin', 'name': 'Gross Margin %',
             'name_ar': 'هامش الربح الإجمالي',
             'value': pnl_cur['gross_margin_pct'], 'value_str': f"{pnl_cur['gross_margin_pct']:.1f}%",
             'formula': 'Gross Profit ÷ Revenue × 100',
             'formula_ar': 'الربح الإجمالي ÷ الإيرادات × 100',
             'numerator': gross_profit, 'denominator': revenue,
             'unit': '%', 'viz': 'bar',
             'min': 0, 'max': 100,
             'benchmarks': [
                {'op': '>=', 'value': 40, 'color': 'green',  'label': 'Strong (≥ 40%)',     'label_ar': 'قوي (≥ 40%)'},
                {'op': '>=', 'value': 20, 'color': 'yellow', 'label': 'Average (20 – 40%)', 'label_ar': 'متوسط (20 – 40%)'},
                {'op': '<',  'value': 20, 'color': 'red',    'label': 'Weak (< 20%)',       'label_ar': 'ضعيف (< 20%)'},
             ],
             'interpretation':    f'Each SAR of revenue keeps {pnl_cur["gross_margin_pct"]:.1f}% as gross profit.',
             'interpretation_ar': f'من كل ريال إيرادات، تحقق الشركة {pnl_cur["gross_margin_pct"]:.1f}% ربحاً إجمالياً'},
            {'key': 'net_margin', 'name': 'Net Margin %',
             'name_ar': 'هامش صافي الربح',
             'value': pnl_cur['net_margin_pct'], 'value_str': f"{pnl_cur['net_margin_pct']:.1f}%",
             'formula': 'Net Profit ÷ Revenue × 100',
             'formula_ar': 'صافي الربح ÷ الإيرادات × 100',
             'numerator': net_profit, 'denominator': revenue,
             'unit': '%', 'viz': 'bar',
             'min': 0, 'max': 50,
             'benchmarks': [
                {'op': '>=', 'value': 15, 'color': 'green',  'label': 'Strong (≥ 15%)',     'label_ar': 'قوي (≥ 15%)'},
                {'op': '>=', 'value': 5,  'color': 'yellow', 'label': 'Average (5 – 15%)',  'label_ar': 'متوسط (5 – 15%)'},
                {'op': '<',  'value': 5,  'color': 'red',    'label': 'Weak (< 5%)',        'label_ar': 'ضعيف (< 5%)'},
             ],
             'interpretation':    f'Bottom-line margin: {pnl_cur["net_margin_pct"]:.1f}% of revenue.',
             'interpretation_ar': f'من كل ريال إيرادات، يبقى {pnl_cur["net_margin_pct"]:.1f}% كصافي ربح بعد كل المصروفات'},
            {'key': 'roa', 'name': 'Return on Assets (ROA)',
             'name_ar': 'العائد على الأصول',
             'value': roa, 'value_str': f'{roa:.1f}%',
             'formula': 'Net Profit ÷ Total Assets × 100',
             'formula_ar': 'صافي الربح ÷ إجمالي الأصول × 100',
             'numerator': net_profit, 'denominator': total_assets_cur,
             'unit': '%', 'viz': 'gauge',
             'min': 0, 'max': 25,
             'benchmarks': [
                {'op': '>=', 'value': 10, 'color': 'green',  'label': 'Strong (≥ 10%)',     'label_ar': 'قوي (≥ 10%)'},
                {'op': '>=', 'value': 5,  'color': 'yellow', 'label': 'Average (5 – 10%)',  'label_ar': 'متوسط (5 – 10%)'},
                {'op': '<',  'value': 5,  'color': 'red',    'label': 'Weak (< 5%)',        'label_ar': 'ضعيف (< 5%)'},
             ],
             'interpretation':    f'Every SAR of assets yields {roa:.1f}% in net profit.',
             'interpretation_ar': f'الشركة تحقق {roa:.1f}% عائداً على كل ريال من أصولها'},
            {'key': 'roe', 'name': 'Return on Equity (ROE)',
             'name_ar': 'العائد على حقوق الملكية',
             'value': roe, 'value_str': f'{roe:.1f}%',
             'formula': 'Net Profit ÷ Total Equity × 100',
             'formula_ar': 'صافي الربح ÷ إجمالي حقوق الملكية × 100',
             'numerator': net_profit, 'denominator': eq_cur,
             'unit': '%', 'viz': 'gauge',
             'min': 0, 'max': 40,
             'benchmarks': [
                {'op': '>=', 'value': 15, 'color': 'green',  'label': 'Strong (≥ 15%)',     'label_ar': 'قوي (≥ 15%)'},
                {'op': '>=', 'value': 8,  'color': 'yellow', 'label': 'Average (8 – 15%)',  'label_ar': 'متوسط (8 – 15%)'},
                {'op': '<',  'value': 8,  'color': 'red',    'label': 'Weak (< 8%)',        'label_ar': 'ضعيف (< 8%)'},
             ],
             'interpretation':    f'Shareholders earn {roe:.1f}% on equity invested.',
             'interpretation_ar': f'المساهمون يحصلون على {roe:.1f}% عائداً على استثماراتهم'},
        ],
        'leverage': [
            {'key': 'debt_equity', 'name': 'Debt to Equity',
             'name_ar': 'نسبة الدين إلى حقوق الملكية',
             'value': debt_to_equity_cur, 'value_str': f'{debt_to_equity_cur:.2f}',
             'formula': 'Total Liabilities ÷ Total Equity',
             'formula_ar': 'إجمالي الالتزامات ÷ إجمالي حقوق الملكية',
             'numerator': total_liab_cur, 'denominator': eq_cur,
             'unit': 'x', 'viz': 'donut',
             'parts': [
                {'label': 'Liabilities', 'value': total_liab_cur, 'color': '#ef4444'},
                {'label': 'Equity',      'value': eq_cur,         'color': '#22c55e'},
             ],
             'benchmarks': [
                {'op': '<=', 'value': 1.0, 'color': 'green',  'label': 'Healthy (≤ 1.0)',       'label_ar': 'ممتاز (≤ 1.0)'},
                {'op': '<=', 'value': 2.0, 'color': 'yellow', 'label': 'Moderate (1.0 – 2.0)',  'label_ar': 'معتدل (1.0 – 2.0)'},
                {'op': '>',  'value': 2.0, 'color': 'red',    'label': 'High (> 2.0)',          'label_ar': 'مرتفع (> 2.0)'},
             ],
             'interpretation':    f'For every SAR of equity, the company carries {debt_to_equity_cur:.2f} SAR of debt.',
             'interpretation_ar': f'مقابل كل ريال من حقوق الملكية، تمتلك الشركة {debt_to_equity_cur:.2f} ريال ديون'},
            {'key': 'debt_ratio', 'name': 'Debt Ratio',
             'name_ar': 'نسبة الديون',
             'value': debt_ratio_cur * 100, 'value_str': f'{debt_ratio_cur*100:.1f}%',
             'formula': 'Total Liabilities ÷ Total Assets',
             'formula_ar': 'إجمالي الالتزامات ÷ إجمالي الأصول',
             'numerator': total_liab_cur, 'denominator': total_assets_cur,
             'unit': '%', 'viz': 'bar',
             'min': 0, 'max': 100,
             'benchmarks': [
                {'op': '<=', 'value': 40, 'color': 'green',  'label': 'Low (≤ 40%)',          'label_ar': 'منخفض (≤ 40%)'},
                {'op': '<=', 'value': 60, 'color': 'yellow', 'label': 'Moderate (40 – 60%)',  'label_ar': 'معتدل (40 – 60%)'},
                {'op': '>',  'value': 60, 'color': 'red',    'label': 'High (> 60%)',         'label_ar': 'مرتفع (> 60%)'},
             ],
             'interpretation':    f'{debt_ratio_cur*100:.1f}% of assets are financed by debt.',
             'interpretation_ar': f'{debt_ratio_cur*100:.1f}% من أصول الشركة ممولة بالديون'},
            {'key': 'st_lt_debt', 'name': 'ST / LT Debt',
             'name_ar': 'الديون قصيرة / طويلة الأجل',
             'value': st_lt_ratio, 'value_str': f'{st_lt_ratio:.2f}',
             'formula': 'Short-term Debt ÷ Long-term Debt',
             'formula_ar': 'الديون قصيرة الأجل ÷ الديون طويلة الأجل',
             'numerator': st_debt_cur, 'denominator': lt_debt_cur,
             'unit': 'x', 'viz': 'donut',
             'parts': [
                {'label': 'Short-term', 'value': st_debt_cur, 'color': '#f59e0b'},
                {'label': 'Long-term',  'value': lt_debt_cur, 'color': '#3b82f6'},
             ],
             'benchmarks': [
                {'op': '<=', 'value': 0.5, 'color': 'green',  'label': 'Mostly long-term (≤ 0.5)', 'label_ar': 'طويلة الأجل غالباً (≤ 0.5)'},
                {'op': '<=', 'value': 1.0, 'color': 'yellow', 'label': 'Balanced (0.5 – 1.0)',    'label_ar': 'متوازن (0.5 – 1.0)'},
                {'op': '>',  'value': 1.0, 'color': 'red',    'label': 'ST-heavy (> 1.0)',        'label_ar': 'قصيرة الأجل غالباً (> 1.0)'},
             ],
             'interpretation':    f'Short-term debt is {st_lt_ratio:.2f}× long-term debt.',
             'interpretation_ar': f'نسبة الديون قصيرة الأجل إلى طويلة الأجل هي {st_lt_ratio:.2f}'},
            {'key': 'equity_multiplier', 'name': 'Equity Multiplier',
             'name_ar': 'مضاعف حقوق الملكية',
             'value': equity_multiplier, 'value_str': f'{equity_multiplier:.2f}',
             'formula': 'Total Assets ÷ Total Equity',
             'formula_ar': 'إجمالي الأصول ÷ إجمالي حقوق الملكية',
             'numerator': total_assets_cur, 'denominator': eq_cur,
             'unit': 'x', 'viz': 'gauge',
             'min': 1, 'max': 4,
             'benchmarks': [
                {'op': '<=', 'value': 2.0, 'color': 'green',  'label': 'Low leverage (≤ 2.0)',   'label_ar': 'رافعة منخفضة (≤ 2.0)'},
                {'op': '<=', 'value': 3.0, 'color': 'yellow', 'label': 'Moderate (2.0 – 3.0)',   'label_ar': 'معتدل (2.0 – 3.0)'},
                {'op': '>',  'value': 3.0, 'color': 'red',    'label': 'High (> 3.0)',           'label_ar': 'مرتفع (> 3.0)'},
             ],
             'interpretation':    f'Assets are {equity_multiplier:.2f}× the equity base.',
             'interpretation_ar': f'الأصول تساوي {equity_multiplier:.2f}× من قاعدة حقوق الملكية'},
        ],
        'efficiency': [
            {'key': 'asset_turnover', 'name': 'Asset Turnover',
             'name_ar': 'معدل دوران الأصول',
             'value': asset_turnover, 'value_str': f'{asset_turnover:.2f}',
             'formula': 'Revenue ÷ Total Assets',
             'formula_ar': 'الإيرادات ÷ إجمالي الأصول',
             'numerator': revenue, 'denominator': total_assets_cur,
             'unit': 'x', 'viz': 'sparkline',
             'history': [0.78, 0.82, 0.85, 0.88, asset_turnover],
             'benchmarks': [
                {'op': '>=', 'value': 1.0, 'color': 'green',  'label': 'Efficient (≥ 1.0)',   'label_ar': 'كفؤ (≥ 1.0)'},
                {'op': '>=', 'value': 0.5, 'color': 'yellow', 'label': 'Average (0.5 – 1.0)', 'label_ar': 'متوسط (0.5 – 1.0)'},
                {'op': '<',  'value': 0.5, 'color': 'red',    'label': 'Low (< 0.5)',         'label_ar': 'منخفض (< 0.5)'},
             ],
             'interpretation':    f'Each SAR of assets generates {asset_turnover:.2f} SAR of revenue.',
             'interpretation_ar': f'الشركة تولد {asset_turnover:.2f} ريال إيرادات من كل ريال أصول'},
            {'key': 'receivables_turnover', 'name': 'Receivables Turnover',
             'name_ar': 'معدل دوران المدينين',
             'value': receivables_turnover, 'value_str': f'{receivables_turnover:.2f}',
             'formula': 'Revenue ÷ Accounts Receivable',
             'formula_ar': 'الإيرادات ÷ الذمم المدينة',
             'numerator': revenue, 'denominator': ar_cur,
             'unit': 'x', 'viz': 'sparkline',
             'history': [3.6, 3.9, 4.1, 4.3, receivables_turnover],
             'benchmarks': [
                {'op': '>=', 'value': 6.0, 'color': 'green',  'label': 'Fast (≥ 6×)',     'label_ar': 'سريع (≥ 6×)'},
                {'op': '>=', 'value': 3.0, 'color': 'yellow', 'label': 'Average (3 – 6×)','label_ar': 'متوسط (3 – 6×)'},
                {'op': '<',  'value': 3.0, 'color': 'red',    'label': 'Slow (< 3×)',     'label_ar': 'بطيء (< 3×)'},
             ],
             'interpretation':    f'Receivables collected {receivables_turnover:.2f}× per year (~{dso_days} days DSO).',
             'interpretation_ar': f'تُحصَّل الذمم المدينة {receivables_turnover:.2f}× سنوياً (~{dso_days} يوم متوسط فترة التحصيل)'},
            {'key': 'payables_turnover', 'name': 'Payables Turnover',
             'name_ar': 'معدل دوران الدائنين',
             'value': payables_turnover, 'value_str': f'{payables_turnover:.2f}',
             'formula': 'COGS ÷ Accounts Payable',
             'formula_ar': 'تكلفة المبيعات ÷ الذمم الدائنة',
             'numerator': pnl_cur['cogs'], 'denominator': ap_cur,
             'unit': 'x', 'viz': 'sparkline',
             'history': [2.4, 2.6, 2.8, 3.0, payables_turnover],
             'benchmarks': [
                {'op': '<=', 'value': 4.0, 'color': 'green',  'label': 'Slow payer — good cash mgmt (≤ 4×)', 'label_ar': 'سداد بطيء — إدارة نقد جيدة (≤ 4×)'},
                {'op': '<=', 'value': 8.0, 'color': 'yellow', 'label': 'Moderate (4 – 8×)',                  'label_ar': 'معتدل (4 – 8×)'},
                {'op': '>',  'value': 8.0, 'color': 'red',    'label': 'Fast payer — burns cash (> 8×)',    'label_ar': 'سداد سريع — يستهلك النقد (> 8×)'},
             ],
             'interpretation':    f'Payables cleared {payables_turnover:.2f}× per year (~{dpo_days} days DPO).',
             'interpretation_ar': f'تُسدَّد الذمم الدائنة {payables_turnover:.2f}× سنوياً (~{dpo_days} يوم متوسط فترة السداد)'},
        ],
    }

    return {
        'currency': DEMO_CURRENCY_NAME,
        'pnl': {
            'sections': pnl_sections,
            'kpis': {
                'total_revenue': pnl_cur['revenue'],
                'gross_profit': pnl_cur['gross_profit'],
                'operating_profit': pnl_cur['operating_profit'],
                'net_profit': pnl_cur['net_profit'],
                'gross_margin_pct': pnl_cur['gross_margin_pct'],
                'net_margin_pct': pnl_cur['net_margin_pct'],
            },
            'compare_kpis': {
                'total_revenue': pnl_prev['revenue'],
                'gross_profit': pnl_prev['gross_profit'],
                'operating_profit': pnl_prev['operating_profit'],
                'net_profit': pnl_prev['net_profit'],
                'gross_margin_pct': pnl_prev['gross_margin_pct'],
                'net_margin_pct': pnl_prev['net_margin_pct'],
            },
            'waterfall': {
                'labels': ['Revenue', 'Gross Profit', 'Operating Profit', 'Net Profit'],
                'values': [pnl_cur['revenue'], pnl_cur['gross_profit'],
                           pnl_cur['operating_profit'], pnl_cur['net_profit']],
            },
        },
        'balance_sheet': bs,
        'trial_balance': tb,
        'ratios': ratios,
        'mapping_used': mapping_used,
        'mapping_inputs': {
            'cash_total': cash_cur,
            'inventory_total': inventory_cur,
        },
    }
