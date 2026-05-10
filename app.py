import json
import os
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, g
)
from dotenv import load_dotenv

from odoo_client import OdooClient, OdooAuthError, OdooConnectionError
from exporters import export_pdf, export_excel

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

PAGE_SIZE = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'odoo_uid' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_client() -> OdooClient:
    if not hasattr(g, 'odoo_client'):
        g.odoo_client = OdooClient(
            url=session['odoo_url'],
            db=session['odoo_db'],
            uid=session['odoo_uid'],
            password=session['odoo_api_key'],
        )
    return g.odoo_client


def fmt_currency(value, symbol=''):
    try:
        return f"{symbol}{value:,.2f}"
    except (TypeError, ValueError):
        return str(value)


def today_str():
    return date.today().isoformat()


def month_start_str():
    d = date.today().replace(day=1)
    return d.isoformat()


def three_months_ago_str():
    d = date.today() - timedelta(days=90)
    return d.isoformat()


def safe_int_param(name: str, default: int = 1) -> int:
    try:
        return int(request.args.get(name, default))
    except (ValueError, TypeError):
        return default


app.jinja_env.filters['fmt_currency'] = fmt_currency


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'odoo_uid' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        db = request.form.get('database', '').strip()
        username = request.form.get('username', '').strip()
        api_key = request.form.get('api_key', '').strip()

        if not all([url, db, username, api_key]):
            flash('All fields are required.', 'danger')
            return render_template('login.html', url=url, database=db, username=username)

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            client = OdooClient.authenticate(url, db, username, api_key)
        except OdooAuthError as e:
            flash(str(e), 'danger')
            return render_template('login.html', url=url, database=db, username=username)
        except OdooConnectionError as e:
            flash(str(e), 'danger')
            return render_template('login.html', url=url, database=db, username=username)

        session.permanent = True
        session['odoo_url'] = url
        session['odoo_db'] = db
        session['odoo_username'] = username
        session['odoo_uid'] = client.uid
        session['odoo_api_key'] = api_key
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    c = get_client()
    kpis = {}
    charts = {}

    # --- Financial KPIs ---
    try:
        kpis['unpaid_invoices'] = c.safe_count('account.move', [
            ['move_type', '=', 'out_invoice'],
            ['state', '=', 'posted'],
            ['payment_state', 'in', ['not_paid', 'partial']],
        ])
        grp = c.safe_read_group('account.move', [
            ['move_type', '=', 'out_invoice'],
            ['state', '=', 'posted'],
            ['payment_state', 'in', ['not_paid', 'partial']],
        ], ['amount_residual:sum'], [])
        kpis['unpaid_amount'] = grp[0].get('amount_residual', 0) if grp else 0
    except Exception:
        kpis['unpaid_invoices'] = 0
        kpis['unpaid_amount'] = 0

    # --- Sales KPIs ---
    try:
        kpis['open_orders'] = c.safe_count('sale.order', [['state', 'in', ['sale', 'done']]])
        grp = c.safe_read_group('sale.order', [
            ['state', 'in', ['sale', 'done']],
            ['date_order', '>=', month_start_str()],
        ], ['amount_total:sum'], [])
        kpis['monthly_sales'] = grp[0].get('amount_total', 0) if grp else 0
    except Exception:
        kpis['open_orders'] = 0
        kpis['monthly_sales'] = 0

    try:
        kpis['active_leads'] = c.safe_count('crm.lead', [
            ['type', '=', 'opportunity'],
            ['active', '=', True],
        ])
    except Exception:
        kpis['active_leads'] = 0

    # --- Inventory KPIs ---
    try:
        grp = c.safe_read_group('stock.quant', [
            ['location_id.usage', '=', 'internal'],
        ], ['value:sum'], [])
        kpis['stock_value'] = grp[0].get('value', 0) if grp else 0
        kpis['stock_products'] = c.safe_count('product.product', [['active', '=', True]])
    except Exception:
        kpis['stock_value'] = 0
        kpis['stock_products'] = 0

    # --- HR KPIs ---
    try:
        kpis['pending_leaves'] = c.safe_count('hr.leave', [
            ['state', '=', 'confirm'],
        ])
        kpis['employees'] = c.safe_count('hr.employee', [['active', '=', True]])
    except Exception:
        kpis['pending_leaves'] = 0
        kpis['employees'] = 0

    # --- Manufacturing KPIs ---
    try:
        kpis['in_progress_mo'] = c.safe_count('mrp.production', [
            ['state', 'in', ['confirmed', 'progress']],
        ])
    except Exception:
        kpis['in_progress_mo'] = 0

    # --- Expense KPIs ---
    try:
        kpis['pending_expenses'] = c.safe_count('hr.expense', [
            ['state', 'in', ['draft', 'reported']],
        ])
    except Exception:
        kpis['pending_expenses'] = 0

    # --- Invoice chart (monthly revenue last 6 months) ---
    try:
        inv_grp = c.safe_read_group(
            'account.move',
            [['move_type', '=', 'out_invoice'], ['state', '=', 'posted'],
             ['invoice_date', '>=', (date.today() - timedelta(days=180)).isoformat()]],
            ['amount_untaxed:sum', 'invoice_date:month'],
            ['invoice_date:month'],
        )
        # Use Odoo's own labels directly — avoids locale/format mismatches
        charts['revenue'] = json.dumps({
            'labels': [g.get('invoice_date:month', '') for g in inv_grp],
            'values': [g.get('amount_untaxed', 0) for g in inv_grp],
        })
    except Exception:
        charts['revenue'] = json.dumps({'labels': [], 'values': []})

    # --- Invoice status chart ---
    try:
        status_grp = c.safe_read_group(
            'account.move',
            [['move_type', '=', 'out_invoice'], ['state', '=', 'posted']],
            ['payment_state'],
            ['payment_state'],
        )
        labels_map = {
            'not_paid': 'Unpaid', 'in_payment': 'In Payment',
            'paid': 'Paid', 'partial': 'Partial', 'reversed': 'Reversed',
        }
        charts['inv_status'] = json.dumps({
            'labels': [labels_map.get(g['payment_state'], g['payment_state']) for g in status_grp],
            'values': [g.get('__count', 0) for g in status_grp],
        })
    except Exception:
        charts['inv_status'] = json.dumps({'labels': [], 'values': []})

    return render_template('dashboard.html', kpis=kpis, charts=charts,
                           username=session.get('odoo_username'),
                           odoo_url=session.get('odoo_url'))


# ---------------------------------------------------------------------------
# Financial
# ---------------------------------------------------------------------------

@app.route('/financial')
@login_required
def financial():
    c = get_client()
    tab = request.args.get('tab', 'invoices')
    page = safe_int_param('page')
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', three_months_ago_str())
    date_to = request.args.get('date_to', today_str())

    ctx = dict(tab=tab, page=page, search=search, date_from=date_from,
               date_to=date_to, total_pages=1, records=[], stats={}, charts={})

    if tab in ('invoices', 'bills'):
        move_type = 'out_invoice' if tab == 'invoices' else 'in_invoice'
        domain = [['move_type', '=', move_type], ['state', '!=', 'cancel']]
        if date_from:
            domain.append(['invoice_date', '>=', date_from])
        if date_to:
            domain.append(['invoice_date', '<=', date_to])
        if search:
            domain += ['|', ['name', 'ilike', search], ['partner_id.name', 'ilike', search]]

        total = c.safe_count('account.move', domain)
        records = c.safe_search_read('account.move', domain,
            ['name', 'partner_id', 'invoice_date', 'invoice_date_due',
             'amount_total', 'amount_residual', 'currency_id', 'state', 'payment_state'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='invoice_date desc')

        grps = c.safe_read_group('account.move', domain,
            ['amount_total:sum', 'amount_residual:sum'], [])
        totals = grps[0] if grps else {}

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {
            'total': totals.get('amount_total', 0),
            'unpaid': totals.get('amount_residual', 0),
            'paid': totals.get('amount_total', 0) - totals.get('amount_residual', 0),
            'count': total,
        }

        status_grp = c.safe_read_group('account.move', domain,
            ['payment_state'], ['payment_state'])
        labels_map = {'not_paid': 'Unpaid', 'in_payment': 'In Payment',
                      'paid': 'Paid', 'partial': 'Partial', 'reversed': 'Reversed'}
        ctx['charts']['status'] = json.dumps({
            'labels': [labels_map.get(g['payment_state'], g['payment_state']) for g in status_grp],
            'values': [g.get('__count', 0) for g in status_grp],
        })

    elif tab == 'banks':
        journals = c.safe_search_read('account.journal',
            [['type', 'in', ['bank', 'cash']]],
            ['name', 'type', 'currency_id', 'code'],
            order='type asc, name asc')
        ctx['records'] = journals
        ctx['stats'] = {'count': len(journals)}

        # Recent bank statement lines
        stmt_domain = [['journal_id.type', 'in', ['bank', 'cash']]]
        if date_from:
            stmt_domain.append(['date', '>=', date_from])
        if date_to:
            stmt_domain.append(['date', '<=', date_to])
        if search:
            stmt_domain.append(['payment_ref', 'ilike', search])

        stmt_total = c.safe_count('account.bank.statement.line', stmt_domain)
        stmts = c.safe_search_read('account.bank.statement.line', stmt_domain,
            ['date', 'payment_ref', 'partner_id', 'amount', 'journal_id', 'currency_id'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='date desc')
        ctx['statements'] = stmts
        ctx['stmt_total'] = stmt_total
        ctx['total_pages'] = max(1, (stmt_total + PAGE_SIZE - 1) // PAGE_SIZE)

    elif tab == 'assets':
        domain = []
        if search:
            domain.append(['name', 'ilike', search])
        try:
            total = c.safe_count('account.asset', domain)
            records = c.safe_search_read('account.asset', domain,
                ['name', 'category_id', 'acquisition_date', 'original_value',
                 'value_residual', 'state'],
                limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='acquisition_date desc')
            grps = c.safe_read_group('account.asset', domain,
                ['original_value:sum', 'value_residual:sum'], [])
            totals = grps[0] if grps else {}
            ctx['records'] = records
            ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            ctx['total_count'] = total
            ctx['stats'] = {
                'count': total,
                'original_value': totals.get('original_value', 0),
                'residual_value': totals.get('value_residual', 0),
                'depreciated': totals.get('original_value', 0) - totals.get('value_residual', 0),
            }
        except Exception:
            ctx['error'] = 'Assets module may not be installed on this Odoo instance.'

    elif tab == 'expenses':
        domain = []
        if date_from:
            domain.append(['date', '>=', date_from])
        if date_to:
            domain.append(['date', '<=', date_to])
        if search:
            domain += ['|', ['name', 'ilike', search], ['employee_id.name', 'ilike', search]]

        total = c.safe_count('hr.expense', domain)
        records = c.safe_search_read('hr.expense', domain,
            ['name', 'employee_id', 'date', 'total_amount', 'currency_id', 'state',
             'product_id', 'category_id'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='date desc')
        grps = c.safe_read_group('hr.expense', domain,
            ['total_amount:sum', 'state'], ['state'])
        state_totals = {g['state']: g.get('total_amount', 0) for g in grps}
        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {
            'count': total,
            'draft': state_totals.get('draft', 0),
            'reported': state_totals.get('reported', 0),
            'approved': state_totals.get('approved', 0),
            'done': state_totals.get('done', 0),
        }

    return render_template('financial.html', **ctx)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@app.route('/inventory')
@login_required
def inventory():
    c = get_client()
    tab = request.args.get('tab', 'stock')
    page = safe_int_param('page')
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', month_start_str())
    date_to = request.args.get('date_to', today_str())

    ctx = dict(tab=tab, page=page, search=search, date_from=date_from,
               date_to=date_to, total_pages=1, records=[], stats={}, charts={})

    if tab == 'stock':
        domain = [['location_id.usage', '=', 'internal']]
        if search:
            domain.append(['product_id.name', 'ilike', search])

        total = c.safe_count('stock.quant', domain)
        records = c.safe_search_read('stock.quant', domain,
            ['product_id', 'location_id', 'quantity', 'reserved_quantity',
             'product_uom_id'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE,
            order='product_id asc')

        grps = c.safe_read_group('stock.quant', domain, ['value:sum', 'quantity:sum'], [])
        totals = grps[0] if grps else {}
        zero_stock = c.safe_count('stock.quant', domain + [['quantity', '<=', 0]])

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {
            'count': total,
            'total_value': totals.get('value', 0),
            'total_qty': totals.get('quantity', 0),
            'zero_stock': zero_stock,
        }

        top_grp = c.safe_read_group('stock.quant',
            [['location_id.usage', '=', 'internal']],
            ['product_id', 'value:sum'], ['product_id'],
            limit=10, orderby='value desc')
        ctx['charts']['top_products'] = json.dumps({
            'labels': [g['product_id'][1] if g.get('product_id') else 'Unknown' for g in top_grp],
            'values': [g.get('value', 0) for g in top_grp],
        })

    elif tab == 'movements':
        domain = [['state', '=', 'done']]
        if date_from:
            domain.append(['date', '>=', date_from])
        if date_to:
            domain.append(['date', '<=', date_to])
        if search:
            domain.append(['product_id.name', 'ilike', search])

        total = c.safe_count('stock.move', domain)
        records = c.safe_search_read('stock.move', domain,
            ['date', 'product_id', 'location_id', 'location_dest_id',
             'product_uom_qty', 'product_uom', 'picking_id', 'origin'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='date desc')

        type_grp = c.safe_read_group('stock.move', domain,
            ['picking_type_id', 'product_uom_qty:sum'], ['picking_type_id'])
        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {'count': total}
        ctx['move_types'] = type_grp[:5]

    elif tab == 'valuation':
        domain = [['quantity', '!=', 0]]
        if search:
            domain.append(['product_id.name', 'ilike', search])

        total = c.safe_count('stock.valuation.layer', domain)
        records = c.safe_search_read('stock.valuation.layer', domain,
            ['product_id', 'quantity', 'value', 'unit_cost',
             'company_id', 'stock_move_id'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='create_date desc')

        grps = c.safe_read_group('stock.valuation.layer', domain,
            ['value:sum', 'quantity:sum'], [])
        totals = grps[0] if grps else {}
        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {
            'count': total,
            'total_value': totals.get('value', 0),
            'total_qty': totals.get('quantity', 0),
        }

    return render_template('inventory.html', **ctx)


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

@app.route('/sales')
@login_required
def sales():
    c = get_client()
    tab = request.args.get('tab', 'orders')
    page = safe_int_param('page')
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', month_start_str())
    date_to = request.args.get('date_to', today_str())

    ctx = dict(tab=tab, page=page, search=search, date_from=date_from,
               date_to=date_to, total_pages=1, records=[], stats={}, charts={})

    if tab == 'orders':
        domain = [['state', 'not in', ['cancel', 'draft']]]
        if date_from:
            domain.append(['date_order', '>=', date_from])
        if date_to:
            domain.append(['date_order', '<=', date_to])
        if search:
            domain += ['|', ['name', 'ilike', search], ['partner_id.name', 'ilike', search]]

        total = c.safe_count('sale.order', domain)
        records = c.safe_search_read('sale.order', domain,
            ['name', 'partner_id', 'date_order', 'amount_total',
             'currency_id', 'state', 'user_id', 'invoice_status'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='date_order desc')

        grps = c.safe_read_group('sale.order', domain, ['amount_total:sum', 'state'], ['state'])
        state_totals = {g['state']: g.get('amount_total', 0) for g in grps}
        all_grp = c.safe_read_group('sale.order', domain, ['amount_total:sum'], [])
        grand_total = all_grp[0].get('amount_total', 0) if all_grp else 0

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {
            'count': total,
            'total': grand_total,
            'confirmed': state_totals.get('sale', 0),
            'done': state_totals.get('done', 0),
        }

        monthly = c.safe_read_group('sale.order',
            [['state', 'not in', ['cancel', 'draft']],
             ['date_order', '>=', (date.today() - timedelta(days=180)).isoformat()]],
            ['amount_total:sum', 'date_order:month'], ['date_order:month'])
        ctx['charts']['monthly'] = json.dumps({
            'labels': [g.get('date_order:month', '') for g in monthly],
            'values': [g.get('amount_total', 0) for g in monthly],
        })

    elif tab == 'pipeline':
        domain = [['type', '=', 'opportunity'], ['active', '=', True]]
        if search:
            domain += ['|', ['name', 'ilike', search], ['partner_id.name', 'ilike', search]]

        total = c.safe_count('crm.lead', domain)
        records = c.safe_search_read('crm.lead', domain,
            ['name', 'partner_id', 'expected_revenue', 'probability',
             'stage_id', 'date_deadline', 'user_id', 'priority'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE,
            order='expected_revenue desc')

        stage_grp = c.safe_read_group('crm.lead', domain,
            ['stage_id', 'expected_revenue:sum'], ['stage_id'])
        all_grp = c.safe_read_group('crm.lead', domain, ['expected_revenue:sum'], [])
        grand = all_grp[0].get('expected_revenue', 0) if all_grp else 0

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {'count': total, 'total_revenue': grand}
        ctx['stages'] = stage_grp
        ctx['charts']['stages'] = json.dumps({
            'labels': [g['stage_id'][1] if g.get('stage_id') else 'No Stage' for g in stage_grp],
            'values': [g.get('expected_revenue', 0) for g in stage_grp],
        })

    return render_template('sales.html', **ctx)


# ---------------------------------------------------------------------------
# HR
# ---------------------------------------------------------------------------

@app.route('/hr')
@login_required
def hr():
    c = get_client()
    tab = request.args.get('tab', 'attendance')
    page = safe_int_param('page')
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', month_start_str())
    date_to = request.args.get('date_to', today_str())

    ctx = dict(tab=tab, page=page, search=search, date_from=date_from,
               date_to=date_to, total_pages=1, records=[], stats={}, charts={})

    if tab == 'attendance':
        domain = []
        if date_from:
            domain.append(['check_in', '>=', date_from])
        if date_to:
            domain.append(['check_in', '<=', date_to + ' 23:59:59'])
        if search:
            domain.append(['employee_id.name', 'ilike', search])

        total = c.safe_count('hr.attendance', domain)
        records = c.safe_search_read('hr.attendance', domain,
            ['employee_id', 'check_in', 'check_out', 'worked_hours'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='check_in desc')

        grps = c.safe_read_group('hr.attendance', domain, ['worked_hours:sum'], [])
        totals = grps[0] if grps else {}
        today_count = c.safe_count('hr.attendance', [
            ['check_in', '>=', today_str()]
        ])

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {
            'count': total,
            'total_hours': totals.get('worked_hours', 0),
            'today_count': today_count,
            'avg_hours': (totals.get('worked_hours', 0) / total) if total else 0,
        }

    elif tab == 'leave':
        domain = []
        if date_from:
            domain.append(['date_from', '>=', date_from])
        if date_to:
            domain.append(['date_from', '<=', date_to])
        if search:
            domain += ['|', ['employee_id.name', 'ilike', search],
                       ['holiday_status_id.name', 'ilike', search]]

        total = c.safe_count('hr.leave', domain)
        records = c.safe_search_read('hr.leave', domain,
            ['employee_id', 'holiday_status_id', 'date_from', 'date_to',
             'number_of_days', 'state', 'name'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='date_from desc')

        state_grp = c.safe_read_group('hr.leave', domain,
            ['state', 'number_of_days:sum'], ['state'])
        state_counts = {g['state']: g.get('__count', 0) for g in state_grp}
        state_days = {g['state']: g.get('number_of_days', 0) for g in state_grp}

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['stats'] = {
            'count': total,
            'pending': state_counts.get('confirm', 0) + state_counts.get('validate1', 0),
            'approved': state_counts.get('validate', 0),
            'refused': state_counts.get('refuse', 0),
            'approved_days': state_days.get('validate', 0),
        }
        ctx['charts']['status'] = json.dumps({
            'labels': [g['state'] for g in state_grp],
            'values': [g.get('__count', 0) for g in state_grp],
        })

    return render_template('hr.html', **ctx)


# ---------------------------------------------------------------------------
# Manufacturing
# ---------------------------------------------------------------------------

@app.route('/manufacturing')
@login_required
def manufacturing():
    c = get_client()
    tab = request.args.get('tab', 'production')
    page = safe_int_param('page')
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', month_start_str())
    date_to = request.args.get('date_to', today_str())

    ctx = dict(tab=tab, page=page, search=search, date_from=date_from,
               date_to=date_to, total_pages=1, records=[], stats={}, charts={})

    domain = []
    if date_from:
        domain.append(['date_planned_start', '>=', date_from])
    if date_to:
        domain.append(['date_planned_start', '<=', date_to])
    if search:
        domain += ['|', ['name', 'ilike', search], ['product_id.name', 'ilike', search]]

    total = c.safe_count('mrp.production', domain)
    records = c.safe_search_read('mrp.production', domain,
        ['name', 'product_id', 'product_qty', 'product_uom_id',
         'date_planned_start', 'date_planned_finished', 'state', 'user_id'],
        limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='date_planned_start desc')

    state_grp = c.safe_read_group('mrp.production', domain,
        ['state', 'product_qty:sum'], ['state'])
    state_counts = {g['state']: g.get('__count', 0) for g in state_grp}
    state_qty = {g['state']: g.get('product_qty', 0) for g in state_grp}

    ctx['records'] = records
    ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    ctx['total_count'] = total
    ctx['stats'] = {
        'count': total,
        'draft': state_counts.get('draft', 0),
        'confirmed': state_counts.get('confirmed', 0),
        'in_progress': state_counts.get('progress', 0),
        'done': state_counts.get('done', 0),
        'done_qty': state_qty.get('done', 0),
    }
    ctx['charts']['status'] = json.dumps({
        'labels': [g['state'] for g in state_grp],
        'values': [g.get('__count', 0) for g in state_grp],
    })

    return render_template('manufacturing.html', **ctx)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

EXPORT_CONFIG = {
    'financial_invoices': {
        'title': 'Customer Invoices Report',
        'model': 'account.move',
        'domain': [['move_type', '=', 'out_invoice'], ['state', '!=', 'cancel']],
        'fields': ['name', 'partner_id', 'invoice_date', 'invoice_date_due',
                   'amount_total', 'currency_id', 'state', 'payment_state'],
        'headers': ['Number', 'Customer', 'Invoice Date', 'Due Date',
                    'Amount', 'Currency', 'Status', 'Payment Status'],
    },
    'financial_bills': {
        'title': 'Vendor Bills Report',
        'model': 'account.move',
        'domain': [['move_type', '=', 'in_invoice'], ['state', '!=', 'cancel']],
        'fields': ['name', 'partner_id', 'invoice_date', 'invoice_date_due',
                   'amount_total', 'currency_id', 'state', 'payment_state'],
        'headers': ['Number', 'Vendor', 'Bill Date', 'Due Date',
                    'Amount', 'Currency', 'Status', 'Payment Status'],
    },
    'financial_expenses': {
        'title': 'Expense Report',
        'model': 'hr.expense',
        'fields': ['name', 'employee_id', 'date', 'total_amount', 'currency_id', 'state'],
        'headers': ['Description', 'Employee', 'Date', 'Amount', 'Currency', 'Status'],
    },
    'inventory_stock': {
        'title': 'Stock Report',
        'model': 'stock.quant',
        'domain': [['location_id.usage', '=', 'internal']],
        'fields': ['product_id', 'location_id', 'quantity', 'reserved_quantity', 'value'],
        'headers': ['Product', 'Location', 'Quantity', 'Reserved', 'Value'],
    },
    'inventory_movements': {
        'title': 'Stock Movements Report',
        'model': 'stock.move',
        'domain': [['state', '=', 'done']],
        'fields': ['date', 'product_id', 'location_id', 'location_dest_id', 'product_uom_qty'],
        'headers': ['Date', 'Product', 'From', 'To', 'Quantity'],
    },
    'inventory_valuation': {
        'title': 'Inventory Valuation Report',
        'model': 'stock.valuation.layer',
        'domain': [['quantity', '!=', 0]],
        'fields': ['product_id', 'quantity', 'value', 'unit_cost'],
        'headers': ['Product', 'Quantity', 'Value', 'Unit Cost'],
    },
    'sales_orders': {
        'title': 'Sales Orders Report',
        'model': 'sale.order',
        'domain': [['state', 'not in', ['cancel', 'draft']]],
        'fields': ['name', 'partner_id', 'date_order', 'amount_total', 'currency_id', 'state'],
        'headers': ['Order', 'Customer', 'Date', 'Amount', 'Currency', 'Status'],
    },
    'sales_pipeline': {
        'title': 'Sales Pipeline Report',
        'model': 'crm.lead',
        'domain': [['type', '=', 'opportunity'], ['active', '=', True]],
        'fields': ['name', 'partner_id', 'expected_revenue', 'probability', 'stage_id', 'date_deadline'],
        'headers': ['Opportunity', 'Customer', 'Expected Revenue', 'Probability %', 'Stage', 'Deadline'],
    },
    'hr_attendance': {
        'title': 'Attendance Report',
        'model': 'hr.attendance',
        'fields': ['employee_id', 'check_in', 'check_out', 'worked_hours'],
        'headers': ['Employee', 'Check In', 'Check Out', 'Hours Worked'],
    },
    'hr_leave': {
        'title': 'Leave Report',
        'model': 'hr.leave',
        'fields': ['employee_id', 'holiday_status_id', 'date_from', 'date_to', 'number_of_days', 'state'],
        'headers': ['Employee', 'Leave Type', 'From', 'To', 'Days', 'Status'],
    },
    'manufacturing_production': {
        'title': 'Production Orders Report',
        'model': 'mrp.production',
        'fields': ['name', 'product_id', 'product_qty', 'product_uom_id',
                   'date_planned_start', 'date_planned_finished', 'state'],
        'headers': ['Reference', 'Product', 'Qty', 'UoM', 'Planned Start', 'Planned End', 'Status'],
    },
}


@app.route('/export/<key>/<fmt>')
@login_required
def export(key: str, fmt: str):
    if key not in EXPORT_CONFIG or fmt not in ('pdf', 'excel'):
        flash('Invalid export request.', 'danger')
        return redirect(url_for('dashboard'))

    cfg = EXPORT_CONFIG[key]
    c = get_client()
    domain = cfg.get('domain', [])

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '')

    date_field_map = {
        'financial_invoices': 'invoice_date',
        'financial_expenses': 'date',
        'inventory_movements': 'date',
        'sales_orders': 'date_order',
        'hr_attendance': 'check_in',
        'hr_leave': 'date_from',
        'manufacturing_production': 'date_planned_start',
    }
    df = date_field_map.get(key)
    if df and date_from:
        domain = domain + [[df, '>=', date_from]]
    if df and date_to:
        domain = domain + [[df, '<=', date_to]]

    records = c.safe_search_read(cfg['model'], domain, cfg['fields'],
                                  limit=5000, order=None)

    def cell_val(rec, field):
        v = rec.get(field)
        if isinstance(v, list):
            return v[1] if len(v) > 1 else str(v[0])
        if isinstance(v, bool):
            return 'Yes' if v else 'No'
        if v is None:
            return ''
        return v

    rows = [[cell_val(r, f) for f in cfg['fields']] for r in records]
    title = cfg['title']

    if fmt == 'pdf':
        buf = export_pdf(title, cfg['headers'], rows)
        return send_file(buf, mimetype='application/pdf',
                         download_name=f'{key}.pdf', as_attachment=True)
    else:
        buf = export_excel(title, cfg['headers'], rows)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=f'{key}.xlsx', as_attachment=True,
        )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_ENV') != 'production', host='0.0.0.0', port=5000)
