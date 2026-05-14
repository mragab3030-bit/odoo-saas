import concurrent.futures
import json
import os
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, g, jsonify
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
            version_info=session.get('odoo_version_info') or {},
            installed_modules=session.get('installed_modules') or None,
        )
        cid = session.get('company_id')
        if cid:
            g.odoo_client.set_company(cid)

        # Lazy backfill for sessions that pre-date version detection — the
        # alternative is forcing every user to log out and back in.
        if not session.get('odoo_version_info'):
            try:
                g.odoo_client.version_info = OdooClient.fetch_version(
                    session['odoo_url'])
                session['odoo_version_info'] = g.odoo_client.version_info
                session['odoo_version_major'] = g.odoo_client.version_major
            except Exception:
                pass
        # Bump this constant whenever detect_edition's algorithm changes —
        # stale 'community' values from earlier runs will get re-probed.
        CURRENT_EDITION_ALGO = 3
        if session.get('odoo_edition_algo') != CURRENT_EDITION_ALGO:
            try:
                session['odoo_edition'] = g.odoo_client.detect_edition()
            except Exception:
                session['odoo_edition'] = 'community'
            session['odoo_edition_algo'] = CURRENT_EDITION_ALGO
        if session.get('installed_modules') is None:
            try:
                session['installed_modules'] = sorted(
                    g.odoo_client.fetch_installed_modules())
            except Exception:
                session['installed_modules'] = []
    return g.odoo_client


# Static metadata for each gated feature.
# `module` is the canonical Odoo technical name; if it's installed, the feature
# is on. `enterprise_only` flips the user-facing copy from "install module" to
# "Enterprise only" when the server is community.
FEATURE_INFO = {
    'manufacturing': {
        'label': 'Manufacturing',
        'icon': 'fa-industry',
        'module': 'mrp',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/manufacturing',
    },
    'expenses': {
        'label': 'Expenses',
        'icon': 'fa-receipt',
        'module': 'hr_expense',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/expenses',
    },
    'assets': {
        'label': 'Assets',
        'icon': 'fa-boxes-packing',
        'module': 'account_asset',
        # account_asset ships only with Enterprise (community users use OCA).
        'enterprise_only': True,
        'learn_more': 'https://www.odoo.com/app/accounting',
    },
    'analytic': {
        'label': 'Analytic Accounting',
        'icon': 'fa-diagram-project',
        'module': 'analytic',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/accounting',
    },
    'project': {
        'label': 'Project',
        'icon': 'fa-list-check',
        'module': 'project',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/project',
    },
    'hr_attendance': {
        'label': 'Attendance',
        'icon': 'fa-clock',
        'module': 'hr_attendance',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/attendances',
    },
    'hr_leave': {
        'label': 'Time Off',
        'icon': 'fa-calendar-xmark',
        'module': 'hr_holidays',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/employees',
    },
    'inventory': {
        'label': 'Inventory',
        'icon': 'fa-warehouse',
        'module': 'stock',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/inventory',
    },
    'sales': {
        'label': 'Sales',
        'icon': 'fa-cart-shopping',
        'module': 'sale_management',
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/app/sales',
    },
}


def _resolve_installed_features(installed: set) -> dict:
    """Map installed module names to feature flags. Inventory/Sales/HR keys
    use permissive defaults: when we can't read ir.module.module the tabs
    remain visible and the server-side fallback decides what to render."""
    inst = installed or set()
    return {
        'manufacturing': 'mrp' in inst,
        'expenses':      'hr_expense' in inst,
        # In v17+ `account_asset` was rolled into `account`. v15/v16 keep it
        # separate; if it's missing we treat the feature as locked and let
        # the friendly page explain.
        'assets':        ('account_asset' in inst),
        # `analytic` ships as a dependency of `account`, so falling back to
        # `account` keeps us permissive for installs where the module list
        # isn't readable.
        'analytic':      ('analytic' in inst) or ('account' in inst),
        'project':       'project' in inst,
        'hr_attendance': 'hr_attendance' in inst,
        'hr_leave':      'hr_holidays' in inst,
        'inventory':     'stock' in inst,
        'sales':         ('sale_management' in inst) or ('sale' in inst),
    }


def _feature_is_locked(feature: str) -> bool:
    """True iff the named feature isn't unlocked for the current session.
    Unknown feature names are treated as unlocked (no false positives)."""
    if feature not in FEATURE_INFO:
        return False
    inst = set(session.get('installed_modules') or [])
    # If we have no module list at all (ACL-blocked), keep tabs available.
    if not inst:
        return False
    return not _resolve_installed_features(inst).get(feature, True)


@app.after_request
def _no_store_for_authed_pages(response):
    """Prevent browser caching of authenticated data pages so Refresh always
    fetches a fresh response from Odoo. Static assets and the login page are
    left to default cache rules."""
    if session.get('odoo_uid') and response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.context_processor
def inject_company_context():
    """Expose company list, selected company, server version, edition, and
    feature flags to every template."""
    companies = session.get('companies') or []
    selected_id = session.get('company_id')
    selected = next((c for c in companies if c['id'] == selected_id), None)
    version_info = session.get('odoo_version_info') or {}
    installed = set(session.get('installed_modules') or [])
    edition = session.get('odoo_edition') or 'community'
    if installed:
        features = _resolve_installed_features(installed)
    else:
        # If we never got a module list (ACL-blocked or pre-login), default to
        # all features visible so the user sees real tabs instead of a wall of
        # locks. The handlers still guard each route individually.
        features = {k: True for k in FEATURE_INFO}

    # Prefer server_serie ("17.0") over server_version ("17.0+e"); strip
    # the +e / saas~ / -YYYYMMDD suffixes so the sidebar shows a clean "17.0".
    raw_ver = version_info.get('server_serie') or version_info.get('server_version') or ''
    clean_ver = str(raw_ver).split('+')[0].split('-')[0]
    if '~' in clean_ver:
        clean_ver = clean_ver.split('~')[-1]

    return {
        'companies': companies,
        'selected_company': selected,
        'has_multi_company': len(companies) > 1,
        'odoo_version_string': clean_ver,
        'odoo_version_major': session.get('odoo_version_major') or 0,
        'odoo_edition': edition,
        'installed_modules': installed,
        'features': features,
        'feature_info': FEATURE_INFO,
    }


def fmt_currency(value, symbol=''):
    try:
        return f"{symbol}{value:,.2f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_currency_int(value, symbol=''):
    try:
        return f"{symbol}{round(value or 0):,}"
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


DATE_RANGE_KEYS = (
    'today', 'yesterday', 'last_7', 'this_month', 'last_month',
    'last_30', 'this_quarter', 'last_quarter', 'last_90', 'ytd',
    'last_year', 'last_365', 'custom',
)


def _resolve_date_range(range_key: str, request_date_from: str,
                        request_date_to: str):
    today_d = date.today()
    today_iso = today_d.isoformat()

    if range_key == 'today':
        return today_iso, today_iso, 'today'
    if range_key == 'yesterday':
        y = (today_d - timedelta(days=1)).isoformat()
        return y, y, 'yesterday'
    if range_key == 'last_7':
        return (today_d - timedelta(days=6)).isoformat(), today_iso, 'last_7'
    if range_key == 'last_month':
        first_this = today_d.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.isoformat(), last_prev.isoformat(), 'last_month'
    if range_key == 'last_30':
        return (today_d - timedelta(days=29)).isoformat(), today_iso, 'last_30'
    if range_key == 'this_quarter':
        qm = ((today_d.month - 1) // 3) * 3 + 1
        return today_d.replace(month=qm, day=1).isoformat(), today_iso, 'this_quarter'
    if range_key == 'last_quarter':
        qm = ((today_d.month - 1) // 3) * 3 + 1
        first_this_q = today_d.replace(month=qm, day=1)
        last_prev_q = first_this_q - timedelta(days=1)
        prev_qm = ((last_prev_q.month - 1) // 3) * 3 + 1
        first_prev_q = last_prev_q.replace(month=prev_qm, day=1)
        return first_prev_q.isoformat(), last_prev_q.isoformat(), 'last_quarter'
    if range_key == 'last_90':
        return (today_d - timedelta(days=89)).isoformat(), today_iso, 'last_90'
    if range_key == 'ytd':
        return today_d.replace(month=1, day=1).isoformat(), today_iso, 'ytd'
    if range_key == 'last_year':
        ly = today_d.year - 1
        return date(ly, 1, 1).isoformat(), date(ly, 12, 31).isoformat(), 'last_year'
    if range_key == 'last_365':
        return (today_d - timedelta(days=364)).isoformat(), today_iso, 'last_365'
    if range_key == 'custom':
        return request_date_from or '', request_date_to or '', 'custom'
    if range_key == 'this_month':
        return today_d.replace(day=1).isoformat(), today_iso, 'this_month'
    # Default: Year to Date
    return today_d.replace(month=1, day=1).isoformat(), today_iso, 'ytd'


def _format_period_label(range_key, date_from, date_to):
    if range_key == 'all':
        return 'All Time'
    if not date_from or not date_to:
        return ''
    try:
        d_from = date.fromisoformat(date_from[:10])
        d_to = date.fromisoformat(date_to[:10])
    except (ValueError, TypeError):
        return f'{date_from} – {date_to}'
    fmt = '%b %Y'
    if d_from.year == d_to.year and d_from.month == d_to.month:
        return d_from.strftime(fmt)
    return f"{d_from.strftime(fmt)} – {d_to.strftime(fmt)}"


def _compute_collection_rate(client, move_type, date_from, date_to, today_iso):
    base_dom = [
        ['move_type', '=', move_type],
        ['state', '=', 'posted'],
    ]
    if date_from:
        base_dom.append(['invoice_date', '>=', date_from])
    if date_to:
        base_dom.append(['invoice_date', '<=', date_to])

    totals_grps = client.safe_read_group(
        'account.move', base_dom,
        ['amount_total:sum', 'amount_residual:sum'], [])
    totals = totals_grps[0] if totals_grps else {}
    total = totals.get('amount_total', 0) or 0
    outstanding = totals.get('amount_residual', 0) or 0
    paid = max(total - outstanding, 0)

    overdue_grps = client.safe_read_group(
        'account.move', base_dom + [
            ['payment_state', 'in', ['not_paid', 'partial']],
            ['invoice_date_due', '<', today_iso],
        ],
        ['amount_residual:sum'], [])
    overdue = ((overdue_grps[0].get('amount_residual', 0) or 0)
               if overdue_grps else 0)
    not_due = max(outstanding - overdue, 0)

    return {
        'total':   total,
        'paid':    paid,
        'overdue': overdue,
        'not_due': not_due,
    }


def _resolve_cr_range(range_key, raw_from, raw_to):
    """Return (range_key, date_from, date_to) for the chart's own selector.
    Supports the same keys as the main filter plus 'all' (no date bounds)."""
    if range_key == 'all':
        return 'all', '', ''
    valid_chart_keys = {
        'this_month', 'last_month', 'this_quarter', 'last_quarter',
        'ytd', 'last_year', 'custom',
    }
    if range_key not in valid_chart_keys:
        range_key = 'ytd'
    date_from, date_to, range_key = _resolve_date_range(
        range_key, raw_from, raw_to)
    return range_key, date_from, date_to


def _resolve_trend_range(range_key, raw_from, raw_to):
    """Return (range_key, date_from, date_to) for the trend / tax sections.
    Adds last_6, this_year, last_2_years on top of the standard keys."""
    today_d = date.today()
    today_iso = today_d.isoformat()
    if range_key == 'last_6':
        first_this = today_d.replace(day=1)
        m = first_this.month - 5
        y = first_this.year
        while m <= 0:
            m += 12
            y -= 1
        start = date(y, m, 1)
        return 'last_6', start.isoformat(), today_iso
    if range_key == 'this_year':
        return ('this_year',
                date(today_d.year, 1, 1).isoformat(),
                date(today_d.year, 12, 31).isoformat())
    if range_key == 'last_2_years':
        start_year = today_d.year - 2
        return ('last_2_years',
                date(start_year, today_d.month, 1).isoformat(),
                today_iso)
    if range_key in ('this_quarter', 'last_quarter', 'last_year',
                     'ytd', 'custom'):
        date_from, date_to, range_key = _resolve_date_range(
            range_key, raw_from, raw_to)
        return range_key, date_from, date_to
    # default last_6
    first_this = today_d.replace(day=1)
    m = first_this.month - 5
    y = first_this.year
    while m <= 0:
        m += 12
        y -= 1
    start = date(y, m, 1)
    return 'last_6', start.isoformat(), today_iso


def _compute_trend(client, move_type, date_from, date_to):
    """Return monthly series of {month, total, paid, outstanding} between
    date_from and date_to (inclusive) for the given move_type."""
    domain = [
        ['move_type', '=', move_type],
        ['state', '=', 'posted'],
    ]
    if date_from:
        domain.append(['invoice_date', '>=', date_from])
    if date_to:
        domain.append(['invoice_date', '<=', date_to])
    grps = client.safe_read_group(
        'account.move', domain,
        ['amount_total:sum', 'amount_residual:sum'],
        ['invoice_date:month'],
        orderby='invoice_date asc') or []

    # Build a continuous month series so empty months show 0.
    try:
        d_from = date.fromisoformat(date_from[:10]) if date_from else None
        d_to = date.fromisoformat(date_to[:10]) if date_to else None
    except (ValueError, TypeError):
        d_from = d_to = None

    bucket = {}
    for g in grps:
        raw = g.get('invoice_date:month') or ''
        total = g.get('amount_total') or 0
        residual = g.get('amount_residual') or 0
        bucket[raw] = {
            'label': raw,
            'total': total,
            'outstanding': residual,
            'paid': max(total - residual, 0),
        }

    months = []
    if d_from and d_to:
        y, m = d_from.year, d_from.month
        end_y, end_m = d_to.year, d_to.month
        while (y, m) <= (end_y, end_m):
            key = date(y, m, 1).strftime('%B %Y')
            entry = bucket.get(key) or {
                'label': key, 'total': 0, 'outstanding': 0, 'paid': 0,
            }
            months.append(entry)
            m += 1
            if m > 12:
                m = 1
                y += 1
    else:
        months = [bucket[k] for k in sorted(bucket.keys())]
    return months


def _compute_analytic(client, date_from, date_to):
    """Aggregate account.analytic.line into one row per analytic account.
    Returns a list of dicts with revenue / costs / net / margin / count / plan.
    Costs are stored as positive numbers (absolute value of negative amounts).

    Field-rename note: in Odoo 17+ the analytic line points at the canonical
    account via `auto_account_id` (multi-plan support); older versions used
    `account_id`. `pick_field` resolves whichever exists on the running server.
    """
    account_field = client.pick_field('account.analytic.line', 'account_id',
                                      default='account_id')

    base_dom = []
    if date_from:
        base_dom.append(['date', '>=', date_from])
    if date_to:
        base_dom.append(['date', '<=', date_to])

    rev_grps = client.safe_read_group(
        'account.analytic.line', base_dom + [['amount', '>', 0]],
        ['amount:sum'], [account_field]) or []
    cost_grps = client.safe_read_group(
        'account.analytic.line', base_dom + [['amount', '<', 0]],
        ['amount:sum'], [account_field]) or []
    count_grps = client.safe_read_group(
        'account.analytic.line', base_dom,
        [], [account_field]) or []

    def _aid(grp):
        pair = grp.get(account_field)
        if isinstance(pair, list) and pair:
            return pair[0], pair[1] if len(pair) > 1 else f'#{pair[0]}'
        if isinstance(pair, int):
            return pair, f'#{pair}'
        return None, ''

    accounts = {}

    def _ensure(aid, name):
        a = accounts.get(aid)
        if a is None:
            a = {'id': aid, 'name': name,
                 'revenue': 0, 'costs': 0, 'count': 0,
                 'plan_id': None, 'plan_name': ''}
            accounts[aid] = a
        return a

    for g in rev_grps:
        aid, name = _aid(g)
        if aid is None:
            continue
        _ensure(aid, name)['revenue'] = g.get('amount', 0) or 0
    for g in cost_grps:
        aid, name = _aid(g)
        if aid is None:
            continue
        _ensure(aid, name)['costs'] = abs(g.get('amount', 0) or 0)
    for g in count_grps:
        aid, name = _aid(g)
        if aid is None:
            continue
        _ensure(aid, name)['count'] = g.get('__count', 0)

    aids = list(accounts.keys())
    if aids:
        # `plan_id` was added with the v17 multi-plan rework; older versions
        # still expose `group_id`. Read whichever exists.
        plan_field = client.pick_field('account.analytic.account', 'plan_id')
        read_fields = ['id', 'code']
        if plan_field:
            read_fields.append(plan_field)
        recs = client.safe_search_read(
            'account.analytic.account',
            [['id', 'in', aids]],
            read_fields)
        for r in recs:
            a = accounts.get(r.get('id'))
            if not a:
                continue
            plan = r.get(plan_field) if plan_field else None
            if isinstance(plan, list) and len(plan) > 1:
                a['plan_id'] = plan[0]
                a['plan_name'] = plan[1]
            a['code'] = r.get('code') or ''

    rows = list(accounts.values())
    for a in rows:
        a['net'] = a['revenue'] - a['costs']
        a['margin_pct'], a['margin_display'] = _margin_pct_and_display(
            a['net'], a['revenue'], a['costs'])
    return rows


def _margin_pct_and_display(net, revenue, costs):
    """Return (pct, display_string) for an analytic row.

    - revenue > 0 → real percentage, formatted "%.1f%%"
    - revenue = 0 → 0.0 numeric (so sorts cleanly), "—" string (no
      percentage is meaningful without a denominator)
    """
    rev = revenue or 0
    if rev <= 0:
        return 0.0, '—'
    pct = (net / rev) * 100.0
    return pct, '%.1f%%' % pct


def _analytic_summary(rows):
    revenue = sum((a['revenue'] or 0) for a in rows)
    costs   = sum((a['costs']   or 0) for a in rows)
    return {
        'count':   len(rows),
        'revenue': revenue,
        'costs':   costs,
        'net':     revenue - costs,
    }


def _compute_tax_summary(client, move_type, date_from, date_to):
    """Return {'untaxed', 'tax', 'total'} for the given move_type/range."""
    domain = [
        ['move_type', '=', move_type],
        ['state', '=', 'posted'],
    ]
    if date_from:
        domain.append(['invoice_date', '>=', date_from])
    if date_to:
        domain.append(['invoice_date', '<=', date_to])
    grps = client.safe_read_group(
        'account.move', domain,
        ['amount_untaxed:sum', 'amount_tax:sum', 'amount_total:sum'], [])
    row = grps[0] if grps else {}
    untaxed = row.get('amount_untaxed', 0) or 0
    total = row.get('amount_total', 0) or 0
    tax_raw = row.get('amount_tax', None)
    tax = tax_raw if tax_raw not in (None, False) else (total - untaxed)
    return {
        'untaxed': untaxed,
        'tax': tax,
        'total': total,
    }


def _shift_year(d: date, years: int) -> date:
    """Shift a date back by N years, snapping Feb 29 to Feb 28 in non-leap years."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def _previous_date_range(range_key: str, date_from: str, date_to: str,
                         year_over_year: bool = False):
    """Return (prev_from_iso, prev_to_iso, human_label) for the comparison
    window that pairs with the current (range_key, date_from, date_to).

    When year_over_year is True, the same window is shifted back exactly one
    year; otherwise each preset maps to its contextual predecessor
    (this_month → last_month, this_quarter → last_quarter, YTD → previous YTD)."""
    if not date_from or not date_to:
        return '', '', 'Previous Period'
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except (ValueError, TypeError):
        return '', '', 'Previous Period'

    if year_over_year:
        pf, pt = _shift_year(df, 1), _shift_year(dt, 1)
        if pf.year == pt.year and pf.month == pt.month:
            label = pf.strftime('%b %Y')
        elif pf.year == pt.year:
            label = str(pf.year)
        else:
            label = f"{pf.year}–{pt.year}"
        return pf.isoformat(), pt.isoformat(), label

    if range_key == 'this_month':
        first_this = df.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.isoformat(), last_prev.isoformat(), 'Last Month'

    if range_key == 'last_month':
        first_this = df.replace(day=1)
        last_two_ago = first_this - timedelta(days=1)
        first_two_ago = last_two_ago.replace(day=1)
        return first_two_ago.isoformat(), last_two_ago.isoformat(), last_two_ago.strftime('%b %Y')

    if range_key == 'this_quarter':
        qm = ((df.month - 1) // 3) * 3 + 1
        first_this_q = df.replace(month=qm, day=1)
        last_prev_q = first_this_q - timedelta(days=1)
        prev_qm = ((last_prev_q.month - 1) // 3) * 3 + 1
        first_prev_q = last_prev_q.replace(month=prev_qm, day=1)
        return first_prev_q.isoformat(), last_prev_q.isoformat(), 'Last Quarter'

    if range_key == 'last_quarter':
        last_prev_q = df - timedelta(days=1)
        prev_qm = ((last_prev_q.month - 1) // 3) * 3 + 1
        first_prev_q = last_prev_q.replace(month=prev_qm, day=1)
        return first_prev_q.isoformat(), last_prev_q.isoformat(), 'Earlier Quarter'

    if range_key == 'ytd':
        prev_from = date(df.year - 1, 1, 1)
        prev_to = _shift_year(dt, 1)
        return prev_from.isoformat(), prev_to.isoformat(), f'YTD {df.year - 1}'

    if range_key == 'last_year':
        ly = df.year - 1
        return f'{ly}-01-01', f'{ly}-12-31', str(ly)

    # Generic fallback: shift back by the window length
    delta_days = (dt - df).days + 1
    prev_to = df - timedelta(days=1)
    prev_from = prev_to - timedelta(days=delta_days - 1)
    return prev_from.isoformat(), prev_to.isoformat(), 'Previous Period'


def _pct_change(current, previous):
    """Return percent change or None when there's no baseline to compare against."""
    try:
        cur = float(current or 0)
        prev = float(previous or 0)
    except (TypeError, ValueError):
        return None
    if prev == 0:
        return None
    return ((cur - prev) / prev) * 100


def _apply_aging_filter(domain, aging_indices, bucket_ranges, today_d):
    """Append multi-select aging clauses to `domain` in place.

    Multiple selected buckets are OR'd together using Odoo's polish-notation
    operators; the resulting OR expression is AND'd with the always-required
    `state = posted` and `payment_state in (not_paid, partial)` predicates."""
    if not aging_indices:
        return
    domain.append(['state', '=', 'posted'])
    domain.append(['payment_state', 'in', ['not_paid', 'partial']])

    # Each selected bucket becomes either a single leaf (open-ended last
    # bucket) or an AND group of two leaves (date_due <= upper AND >= lower).
    bucket_clauses = []
    for idx in aging_indices:
        lo, hi = bucket_ranges[idx]
        lo_clause = ['invoice_date_due', '<=',
                     (today_d - timedelta(days=lo)).isoformat()]
        if hi is not None:
            hi_clause = ['invoice_date_due', '>=',
                         (today_d - timedelta(days=hi)).isoformat()]
            bucket_clauses.append(['&', lo_clause, hi_clause])
        else:
            bucket_clauses.append([lo_clause])

    if len(bucket_clauses) == 1:
        # Single bucket — append its tokens directly; the implicit AND with
        # the preceding leaves keeps the semantics correct.
        for tok in bucket_clauses[0]:
            domain.append(tok)
        return

    # N buckets → prefix (N-1) '|' operators, then flatten the AND groups.
    polish = ['|'] * (len(bucket_clauses) - 1)
    for grp in bucket_clauses:
        if len(grp) == 1:
            polish.append(grp[0])
        else:
            polish.extend(grp)  # '&', lo, hi
    domain.extend(polish)


def _parse_status_filters(args):
    """Return validated, de-duplicated list of payment_state filters."""
    allowed = ('not_paid', 'paid', 'partial', 'reversed')
    out, seen = [], set()
    for s in args.getlist('status'):
        s = (s or '').strip()
        if s in allowed and s not in seen:
            out.append(s)
            seen.add(s)
    return out


def _parse_aging_filters(args):
    """Return validated, de-duplicated, sorted list of aging bucket indices (0..4)."""
    out = []
    for raw in args.getlist('aging'):
        try:
            i = int(raw)
        except (ValueError, TypeError):
            continue
        if 0 <= i <= 4 and i not in out:
            out.append(i)
    out.sort()
    return out


app.jinja_env.filters['fmt_currency'] = fmt_currency
app.jinja_env.filters['fmt_currency_int'] = fmt_currency_int


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
        # Version detection — captured during authenticate() via common.version()
        session['odoo_version_info'] = client.version_info or {}
        session['odoo_version_major'] = client.version_major or 0

        # Module detection — drives feature flags used to gate tabs.
        # Best-effort: if the user lacks access to ir.module.module, we fall
        # back to an empty set and `_resolve_installed_features` gives a
        # permissive default.
        try:
            session['installed_modules'] = sorted(client.fetch_installed_modules())
        except Exception:
            session['installed_modules'] = []

        # Edition detection — community vs enterprise. Drives the "Enterprise
        # only" copy on the feature-unavailable screen. Algorithm version is
        # captured so future detection changes auto-invalidate cached values
        # (see get_client()).
        try:
            session['odoo_edition'] = client.detect_edition()
        except Exception:
            session['odoo_edition'] = 'community'
        session['odoo_edition_algo'] = 3

        # Fetch companies the user has access to (multi-company support)
        try:
            user_data = client.execute_kw(
                'res.users', 'read', [[client.uid]],
                {'fields': ['company_id', 'company_ids']}
            )
            user_data = user_data[0] if user_data else {}
            default_cid = user_data.get('company_id')
            default_cid = default_cid[0] if isinstance(default_cid, list) else None
            allowed_ids = user_data.get('company_ids') or []
            if not isinstance(allowed_ids, list):
                allowed_ids = []
            if allowed_ids:
                companies = client.execute_kw(
                    'res.company', 'read', [allowed_ids],
                    {'fields': ['id', 'name', 'currency_id']}
                )
            else:
                companies = []
            # Resolve currency symbol/name for each company in one batch
            cur_ids = list({
                co['currency_id'][0]
                for co in (companies or [])
                if isinstance(co.get('currency_id'), list) and co['currency_id']
            })
            cur_map = {}
            if cur_ids:
                cur_rows = client.execute_kw(
                    'res.currency', 'read', [cur_ids],
                    {'fields': ['id', 'symbol', 'name']}
                )
                cur_map = {cu['id']: cu for cu in (cur_rows or [])}
        except Exception:
            companies = []
            default_cid = None
            cur_map = {}

        session['companies'] = [
            {
                'id': co['id'],
                'name': co.get('name', ''),
                'currency_id': (co.get('currency_id') or [None])[0]
                    if isinstance(co.get('currency_id'), list) else None,
                'currency_name': (
                    cur_map.get((co.get('currency_id') or [0])[0], {}).get('name', '')
                    if isinstance(co.get('currency_id'), list) else ''
                ),
                'currency_symbol': (
                    cur_map.get((co.get('currency_id') or [0])[0], {}).get('symbol', '')
                    if isinstance(co.get('currency_id'), list) else ''
                ),
            }
            for co in (companies or [])
        ]
        session['company_id'] = default_cid or (
            session['companies'][0]['id'] if session['companies'] else None
        )
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/select-company', methods=['POST'])
@login_required
def select_company():
    try:
        cid = int(request.form.get('company_id', '0'))
    except (TypeError, ValueError):
        cid = 0
    allowed_ids = {c['id'] for c in (session.get('companies') or [])}
    if cid in allowed_ids:
        session['company_id'] = cid
    return redirect(request.referrer or url_for('dashboard'))


# ---------------------------------------------------------------------------
# Session refresh — re-probes the Odoo server for version, installed modules,
# and edition. Fired by the global Refresh button so newly-installed modules
# light up their tabs without forcing a logout.
# ---------------------------------------------------------------------------

@app.route('/refresh-session', methods=['POST'])
@login_required
def refresh_session():
    c = get_client()
    # Force re-detection by clearing the in-memory module cache. The session
    # values are overwritten below.
    c._installed_modules = None
    c._field_cache = {}

    result = {'ok': True, 'version': '', 'edition': 'community', 'modules': 0}

    try:
        c.version_info = OdooClient.fetch_version(session['odoo_url'])
        session['odoo_version_info'] = c.version_info
        session['odoo_version_major'] = c.version_major
    except Exception:
        pass
    result['version'] = c.version_string or ''

    try:
        modules = sorted(c.fetch_installed_modules())
        session['installed_modules'] = modules
        result['modules'] = len(modules)
    except Exception:
        # Keep whatever was already in session — wiping it would visibly
        # collapse the sidebar on a transient network blip.
        result['modules'] = len(session.get('installed_modules') or [])

    try:
        session['odoo_edition'] = c.detect_edition()
    except Exception:
        session['odoo_edition'] = 'community'
    session['odoo_edition_algo'] = 3
    result['edition'] = session['odoo_edition']

    return jsonify(result)


# ---------------------------------------------------------------------------
# Feature unavailable (locked tab landing page)
# ---------------------------------------------------------------------------

@app.route('/feature-unavailable/<feature>')
@login_required
def feature_unavailable(feature):
    """Friendly landing page reached when a user clicks a locked tab in the
    sidebar (or hits a locked tab's URL directly). Never raises — unknown
    feature keys fall back to a generic message."""
    info = FEATURE_INFO.get(feature, {
        'label': feature.replace('_', ' ').title(),
        'icon': 'fa-lock',
        'module': feature,
        'enterprise_only': False,
        'learn_more': 'https://www.odoo.com/page/apps',
    })
    edition = session.get('odoo_edition') or 'community'
    # Enterprise copy only fires when the module is enterprise-only AND we
    # detected community. Otherwise it's a plain "module not installed".
    show_enterprise_copy = info.get('enterprise_only') and edition != 'enterprise'
    return render_template(
        'feature_unavailable.html',
        feature=feature,
        info=info,
        show_enterprise_copy=show_enterprise_copy,
    )


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
    tab = request.args.get('tab', 'invoices')
    # Tab-level lock check: direct URLs to a locked tab land on the friendly
    # unavailable page instead of running the handler with broken data.
    tab_feature = {'analytic': 'analytic',
                   'assets':   'assets',
                   'expenses': 'expenses'}.get(tab)
    if tab_feature and _feature_is_locked(tab_feature):
        return redirect(url_for('feature_unavailable', feature=tab_feature))
    c = get_client()
    page = safe_int_param('page')
    search = request.args.get('search', '').strip()
    raw_date_from = request.args.get('date_from', '')
    raw_date_to = request.args.get('date_to', '')
    range_key = request.args.get('range', '').strip()

    if tab in ('invoices', 'bills', 'analytic'):
        if range_key not in DATE_RANGE_KEYS:
            range_key = 'ytd'
        date_from, date_to, range_key = _resolve_date_range(
            range_key, raw_date_from, raw_date_to)
    else:
        date_from = raw_date_from or three_months_ago_str()
        date_to = raw_date_to or today_str()
        range_key = ''

    ctx = dict(tab=tab, page=page, search=search, date_from=date_from,
               date_to=date_to, range_key=range_key,
               total_pages=1, records=[], stats={}, charts={},
               status_filter='', aging_filter=None, period_days=30)

    if tab in ('invoices', 'bills'):
        move_type = 'out_invoice' if tab == 'invoices' else 'in_invoice'
        period_days = max(1, safe_int_param('period', 30))

        status_filter = _parse_status_filters(request.args)
        aging_filter = _parse_aging_filters(request.args)
        cashflow_filter = request.args.get('cashflow', '').strip()
        if cashflow_filter not in ('overdue', 'b1', 'b2', 'b3'):
            cashflow_filter = ''

        domain = [['move_type', '=', move_type], ['state', '!=', 'cancel']]
        if date_from:
            domain.append(['invoice_date', '>=', date_from])
        if date_to:
            domain.append(['invoice_date', '<=', date_to])
        if search:
            domain += ['|', ['name', 'ilike', search], ['partner_id.name', 'ilike', search]]

        n = period_days
        bucket_ranges = [
            (0,       n),
            (n + 1,   2 * n),
            (2 * n + 1, 3 * n),
            (3 * n + 1, 4 * n),
            (4 * n + 1, None),
        ]

        today_d = date.today()
        table_domain = list(domain)
        if len(status_filter) == 1:
            table_domain.append(['payment_state', '=', status_filter[0]])
        elif status_filter:
            table_domain.append(['payment_state', 'in', status_filter])
        _apply_aging_filter(table_domain, aging_filter, bucket_ranges, today_d)

        # Cash-flow forecast filter — anchored to TODAY, independent of the
        # period date filter. Bucket bounds scale with the aging period_days
        # so the cashflow window matches the aging cards above.
        if cashflow_filter and tab in ('invoices', 'bills'):
            today_iso_now = today_d.isoformat()
            table_domain.append(['state', '=', 'posted'])
            table_domain.append(['payment_state', 'in', ['not_paid', 'partial']])
            if cashflow_filter == 'overdue':
                table_domain.append(['invoice_date_due', '<', today_iso_now])
            else:
                bounds = {
                    'b1': (0,             period_days),
                    'b2': (period_days + 1, 2 * period_days),
                    'b3': (2 * period_days + 1, 3 * period_days),
                }[cashflow_filter]
                lower = (today_d + timedelta(days=bounds[0])).isoformat()
                upper = (today_d + timedelta(days=bounds[1])).isoformat()
                table_domain.append(['invoice_date_due', '>=', lower])
                table_domain.append(['invoice_date_due', '<=', upper])

        # ---- Previous-period comparison (fired in background while current
        # period queries run on the main thread) ----
        compare_yoy = request.args.get('compare_yoy') == '1'
        prev_from, prev_to, prev_label = _previous_date_range(
            range_key, date_from, date_to, year_over_year=compare_yoy)

        prev_domain = [['move_type', '=', move_type], ['state', '!=', 'cancel']]
        if prev_from:
            prev_domain.append(['invoice_date', '>=', prev_from])
        if prev_to:
            prev_domain.append(['invoice_date', '<=', prev_to])
        if search:
            prev_domain += ['|', ['name', 'ilike', search],
                             ['partner_id.name', 'ilike', search]]
        prev_table_domain = list(prev_domain)
        if len(status_filter) == 1:
            prev_table_domain.append(['payment_state', '=', status_filter[0]])
        elif status_filter:
            prev_table_domain.append(['payment_state', 'in', status_filter])
        _apply_aging_filter(prev_table_domain, aging_filter, bucket_ranges, today_d)

        def _fresh_client():
            # xmlrpc.client.ServerProxy is not thread-safe; give each background
            # call its own client bound to the same session credentials.
            return OdooClient(c.url, c.db, c.uid, c.password,
                              context=dict(c.context))

        def _prev_count_job():
            return _fresh_client().safe_count('account.move', prev_table_domain)

        def _prev_totals_job():
            return _fresh_client().safe_read_group(
                'account.move', prev_domain,
                ['amount_total:sum', 'amount_residual:sum'], [])

        _prev_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        prev_count_fut = _prev_pool.submit(_prev_count_job)
        prev_totals_fut = _prev_pool.submit(_prev_totals_job)

        total = c.safe_count('account.move', table_domain)
        records = c.safe_search_read('account.move', table_domain,
            ['id', 'name', 'partner_id', 'invoice_date', 'invoice_date_due',
             'amount_untaxed', 'amount_tax',
             'amount_total', 'amount_residual', 'currency_id', 'state', 'payment_state'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='invoice_date desc')

        grps = c.safe_read_group('account.move', domain,
            ['amount_total:sum', 'amount_residual:sum'], [])
        totals = grps[0] if grps else {}

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['status_filter'] = status_filter
        ctx['aging_filter'] = aging_filter
        ctx['today_iso'] = today_str()
        ctx['stats'] = {
            'total': totals.get('amount_total', 0),
            'unpaid': totals.get('amount_residual', 0),
            'paid': totals.get('amount_total', 0) - totals.get('amount_residual', 0),
            'count': total,
        }

        status_keys = ['not_paid', 'paid', 'partial', 'reversed']
        status_labels = {'not_paid': 'Unpaid', 'paid': 'Paid',
                         'partial': 'Partial', 'reversed': 'Reversed'}
        status_data = {k: {'key': k, 'label': status_labels[k],
                           'count': 0, 'amount': 0, 'overdue': 0}
                       for k in status_keys}
        status_grp = c.safe_read_group('account.move', domain,
            ['amount_total:sum'], ['payment_state'])
        for grp in status_grp:
            ps = grp.get('payment_state')
            if ps in status_data:
                status_data[ps]['count'] = grp.get('__count', 0)
                status_data[ps]['amount'] = grp.get('amount_total', 0) or 0

        today_iso = today_str()
        for ps in ('not_paid', 'partial'):
            overdue_dom = list(domain) + [
                ['payment_state', '=', ps],
                ['invoice_date_due', '<', today_iso],
            ]
            status_data[ps]['overdue'] = c.safe_count('account.move', overdue_dom)
        ctx['payment_status'] = [status_data[k] for k in status_keys]

        aging_dom = list(domain) + [
            ['state', '=', 'posted'],
            ['payment_state', 'in', ['not_paid', 'partial']],
        ]
        aging_records = c.paginated_search_read('account.move', aging_dom,
            fields=['invoice_date_due', 'invoice_date', 'amount_residual'],
            order='invoice_date_due asc')

        n = period_days
        buckets = [
            {'label': f'0-{n}',           'lo': 0,       'hi': n,    'count': 0, 'amount': 0},
            {'label': f'{n+1}-{2*n}',     'lo': n+1,     'hi': 2*n,  'count': 0, 'amount': 0},
            {'label': f'{2*n+1}-{3*n}',   'lo': 2*n+1,   'hi': 3*n,  'count': 0, 'amount': 0},
            {'label': f'{3*n+1}-{4*n}',   'lo': 3*n+1,   'hi': 4*n,  'count': 0, 'amount': 0},
            {'label': f'{4*n}+',          'lo': 4*n+1,   'hi': None, 'count': 0, 'amount': 0},
        ]
        today_d = date.today()
        for r in aging_records:
            due = r.get('invoice_date_due') or r.get('invoice_date')
            if not due:
                continue
            try:
                due_d = date.fromisoformat(str(due)[:10])
            except (ValueError, TypeError):
                continue
            days_overdue = (today_d - due_d).days
            if days_overdue < 0:
                continue
            amt = r.get('amount_residual') or 0
            for b in buckets:
                if b['hi'] is None:
                    if days_overdue >= b['lo']:
                        b['count'] += 1
                        b['amount'] += amt
                        break
                elif b['lo'] <= days_overdue <= b['hi']:
                    b['count'] += 1
                    b['amount'] += amt
                    break
        ctx['aging_buckets'] = buckets
        ctx['period_days'] = period_days

        # ---- Cash flow forecast (Invoices + Bills) ----
        # Always anchored to today, independent of the period date filter.
        # Only Unpaid / Partial posted records count toward the forecast.
        # Bucket widths follow the active aging period (period_days).
        cashflow_dom = [
            ['move_type', '=', move_type],
            ['state', '=', 'posted'],
            ['payment_state', 'in', ['not_paid', 'partial']],
        ]
        cashflow_records = c.paginated_search_read(
            'account.move', cashflow_dom,
            fields=['invoice_date_due', 'amount_residual'],
            order='invoice_date_due asc')

        n = period_days
        cf = {
            'overdue': {'count': 0, 'amount': 0, 'days_sum': 0, 'avg_days': 0,
                        'label': 'Overdue'},
            'b1': {'count': 0, 'amount': 0, 'label': f'0-{n} Days'},
            'b2': {'count': 0, 'amount': 0, 'label': f'{n + 1}-{2 * n} Days'},
            'b3': {'count': 0, 'amount': 0, 'label': f'{2 * n + 1}-{3 * n} Days'},
        }
        for r in cashflow_records:
            due_raw = r.get('invoice_date_due')
            if not due_raw:
                continue
            try:
                due_d = date.fromisoformat(str(due_raw)[:10])
            except (ValueError, TypeError):
                continue
            amt = r.get('amount_residual') or 0
            delta = (due_d - today_d).days
            if delta < 0:
                cf['overdue']['count'] += 1
                cf['overdue']['amount'] += amt
                cf['overdue']['days_sum'] += -delta
            elif delta <= n:
                cf['b1']['count'] += 1
                cf['b1']['amount'] += amt
            elif delta <= 2 * n:
                cf['b2']['count'] += 1
                cf['b2']['amount'] += amt
            elif delta <= 3 * n:
                cf['b3']['count'] += 1
                cf['b3']['amount'] += amt

        if cf['overdue']['count']:
            cf['overdue']['avg_days'] = (
                cf['overdue']['days_sum'] / cf['overdue']['count']
            )
        cf['total_expected'] = {
            'amount': cf['b1']['amount'] + cf['b2']['amount'] + cf['b3']['amount'],
            'count':  cf['b1']['count']  + cf['b2']['count']  + cf['b3']['count'],
        }
        ctx['cashflow'] = cf
        ctx['cashflow_filter'] = cashflow_filter

        # ---- Top 5 Overdue Customers / Vendors ----
        # Always shows the overall top 5; ignores period, search, status,
        # aging, and cashflow filters. Company filter is applied by the
        # OdooClient context automatically.
        top_overdue_dom = [
            ['move_type', '=', move_type],
            ['state', '=', 'posted'],
            ['payment_state', 'in', ['not_paid', 'partial']],
            ['invoice_date_due', '<', today_d.isoformat()],
        ]
        top_overdue_records = c.paginated_search_read(
            'account.move', top_overdue_dom,
            fields=['partner_id', 'invoice_date_due', 'amount_residual'],
            order='invoice_date_due asc')

        partners_agg = {}
        for r in top_overdue_records:
            pid_pair = r.get('partner_id')
            if not pid_pair:
                continue
            pid = pid_pair[0]
            pname = pid_pair[1] if len(pid_pair) > 1 else f'#{pid}'
            due_raw = r.get('invoice_date_due')
            if not due_raw:
                continue
            try:
                due_d = date.fromisoformat(str(due_raw)[:10])
            except (ValueError, TypeError):
                continue
            days_overdue = (today_d - due_d).days
            if days_overdue <= 0:
                continue
            amt = r.get('amount_residual') or 0
            agg = partners_agg.get(pid)
            if agg is None:
                agg = {
                    'partner_id': pid,
                    'name': pname,
                    'count': 0,
                    'total': 0,
                    'oldest_days': 0,
                    'days_sum': 0,
                }
                partners_agg[pid] = agg
            agg['count'] += 1
            agg['total'] += amt
            agg['days_sum'] += days_overdue
            if days_overdue > agg['oldest_days']:
                agg['oldest_days'] = days_overdue

        top_overdue = sorted(partners_agg.values(),
                             key=lambda a: a['total'], reverse=True)[:5]
        for a in top_overdue:
            a['avg_days'] = a['days_sum'] / a['count'] if a['count'] else 0
        ctx['top_overdue'] = top_overdue

        # ---- Collection rate (independent of main filters) ----
        # The chart has its own period selector; on first load it defaults
        # to YTD. The selector is independent from the main period filter
        # above and from search / status / aging / cashflow filters. Company
        # filter is applied automatically at the OdooClient level.
        cr_today_iso = today_d.isoformat()
        cr_range_default, cr_from_default, cr_to_default = _resolve_cr_range(
            'ytd', '', '')
        collection_rate = _compute_collection_rate(
            c, move_type, cr_from_default, cr_to_default, cr_today_iso)
        collection_rate['range_key']    = cr_range_default
        collection_rate['date_from']    = cr_from_default
        collection_rate['date_to']      = cr_to_default
        collection_rate['period_label'] = _format_period_label(
            cr_range_default, cr_from_default, cr_to_default)
        ctx['collection_rate'] = collection_rate

        # ---- Monthly trend chart (independent, default Last 6 Months) ----
        trend_range, trend_from, trend_to = _resolve_trend_range(
            'last_6', '', '')
        ctx['trend'] = {
            'months':       _compute_trend(c, move_type, trend_from, trend_to),
            'range_key':    trend_range,
            'date_from':    trend_from,
            'date_to':      trend_to,
            'period_label': _format_period_label(
                trend_range, trend_from, trend_to),
        }

        # ---- Tax summary (independent, default YTD) ----
        tax_range, tax_from, tax_to = _resolve_trend_range('ytd', '', '')
        tax_summary = _compute_tax_summary(c, move_type, tax_from, tax_to)
        tax_summary['range_key']    = tax_range
        tax_summary['date_from']    = tax_from
        tax_summary['date_to']      = tax_to
        tax_summary['period_label'] = _format_period_label(
            tax_range, tax_from, tax_to)
        ctx['tax_summary'] = tax_summary

        status_colors = {
            'not_paid': '#ef4444',
            'paid': '#22c55e',
            'partial': '#f59e0b',
            'reversed': '#94a3b8',
        }
        selected_status_indices = [
            i for i, s in enumerate(ctx['payment_status'])
            if s['key'] in status_filter
        ]
        ctx['payment_chart'] = {
            'labels': [s['label'] for s in ctx['payment_status']],
            'counts': [s['count'] for s in ctx['payment_status']],
            'amounts': [s['amount'] for s in ctx['payment_status']],
            'colors': [status_colors[s['key']] for s in ctx['payment_status']],
            'selected': selected_status_indices,
        }
        aging_palette = ['#22c55e', '#eab308', '#f97316', '#ef4444', '#991b1b']
        ctx['aging_chart'] = {
            'labels': [f"{b['label']} days" for b in buckets],
            'counts': [b['count'] for b in buckets],
            'amounts': [b['amount'] for b in buckets],
            'colors': aging_palette,
            'selected': list(aging_filter),
        }

        # ---- Collect previous-period results and compute comparison stats ----
        try:
            prev_count = prev_count_fut.result(timeout=30)
        except Exception:
            prev_count = 0
        try:
            prev_grps = prev_totals_fut.result(timeout=30) or []
        except Exception:
            prev_grps = []
        finally:
            _prev_pool.shutdown(wait=False)
        prev_totals = prev_grps[0] if prev_grps else {}
        prev_stats = {
            'count': prev_count,
            'total': prev_totals.get('amount_total', 0),
            'unpaid': prev_totals.get('amount_residual', 0),
            'paid': (prev_totals.get('amount_total', 0)
                     - prev_totals.get('amount_residual', 0)),
        }
        ctx['compare_stats'] = prev_stats
        ctx['compare_label'] = f'vs {prev_label}'
        ctx['compare_yoy'] = compare_yoy
        ctx['compare_pct'] = {
            'count':   _pct_change(ctx['stats']['count'],   prev_stats['count']),
            'total':   _pct_change(ctx['stats']['total'],   prev_stats['total']),
            'paid':    _pct_change(ctx['stats']['paid'],    prev_stats['paid']),
            'unpaid':  _pct_change(ctx['stats']['unpaid'],  prev_stats['unpaid']),
        }

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

    elif tab == 'analytic':
        # Probe the underlying model once — if it's missing or ACL-blocked we
        # render a clean "Not available in this version" notice instead of
        # crashing.
        analytic_fields = c.get_model_fields('account.analytic.line')
        if not analytic_fields:
            rows = []
            ctx['error'] = (
                'Analytic Accounting is not available on this Odoo instance '
                '(model account.analytic.line is missing or inaccessible).'
            )
        else:
            try:
                rows = _compute_analytic(c, date_from, date_to)
            except Exception as e:
                rows = []
                ctx['error'] = (
                    f'Analytic data is not available in this Odoo version: {e}'
                )
        if search:
            s = search.lower()
            rows = [r for r in rows if s in (r.get('name') or '').lower()
                    or s in (r.get('plan_name') or '').lower()
                    or s in (r.get('code') or '').lower()]
        summary = _analytic_summary(rows)

        # Previous-period comparison
        prev_from, prev_to, prev_label = _previous_date_range(
            range_key, date_from, date_to)
        try:
            prev_rows = _compute_analytic(c, prev_from, prev_to) if prev_from else []
        except Exception:
            prev_rows = []
        prev_summary = _analytic_summary(prev_rows)

        # Two Top-5 lists:
        #   profitable: net > 0 (revenue must exist for net to be positive)
        #   loss:       net < 0 — includes pure cost centres (revenue=0,
        #               costs>0); their Loss % column renders as "—".
        top_profitable = sorted(
            [r for r in rows if r['net'] > 0],
            key=lambda r: r['net'], reverse=True)[:5]
        top_loss = sorted(
            [r for r in rows if r['net'] < 0],
            key=lambda r: r['net'])[:5]

        ctx['records']       = rows
        ctx['total_count']   = len(rows)
        ctx['total_pages']   = 1
        ctx['stats']         = summary
        ctx['compare_stats'] = prev_summary
        ctx['compare_label'] = f'vs {prev_label}'
        ctx['compare_pct']   = {
            'count':   _pct_change(summary['count'],   prev_summary['count']),
            'revenue': _pct_change(summary['revenue'], prev_summary['revenue']),
            'costs':   _pct_change(summary['costs'],   prev_summary['costs']),
            'net':     _pct_change(summary['net'],     prev_summary['net']),
        }
        ctx['top_profitable'] = top_profitable
        ctx['top_loss']       = top_loss
        ctx['period_label']   = _format_period_label(
            range_key, date_from, date_to)

    return render_template('financial.html', **ctx)


@app.route('/financial/collection-rate')
@login_required
def financial_collection_rate():
    """JSON endpoint for the Collection Rate / Vendor Payment chart's own
    period selector. Independent of the main filter set on /financial."""
    tab = request.args.get('tab', 'invoices')
    if tab not in ('invoices', 'bills'):
        return jsonify({'error': 'invalid tab'}), 400
    move_type = 'out_invoice' if tab == 'invoices' else 'in_invoice'

    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    raw_from = request.args.get('date_from', '')
    raw_to = request.args.get('date_to', '')
    range_key, date_from, date_to = _resolve_cr_range(
        range_key, raw_from, raw_to)

    c = get_client()
    today_iso = today_str()
    data = _compute_collection_rate(
        c, move_type, date_from, date_to, today_iso)
    data['range_key']    = range_key
    data['date_from']    = date_from
    data['date_to']      = date_to
    data['period_label'] = _format_period_label(
        range_key, date_from, date_to)
    return jsonify(data)


@app.route('/financial/trend')
@login_required
def financial_trend():
    """JSON endpoint for the monthly trend line chart."""
    tab = request.args.get('tab', 'invoices')
    if tab not in ('invoices', 'bills'):
        return jsonify({'error': 'invalid tab'}), 400
    move_type = 'out_invoice' if tab == 'invoices' else 'in_invoice'

    range_key = (request.args.get('range', 'last_6') or 'last_6').strip()
    raw_from = request.args.get('date_from', '')
    raw_to = request.args.get('date_to', '')
    range_key, date_from, date_to = _resolve_trend_range(
        range_key, raw_from, raw_to)

    c = get_client()
    months = _compute_trend(c, move_type, date_from, date_to)
    return jsonify({
        'range_key':    range_key,
        'date_from':    date_from,
        'date_to':      date_to,
        'period_label': _format_period_label(range_key, date_from, date_to),
        'months':       months,
    })


@app.route('/financial/analytic-aggregate')
@login_required
def financial_analytic_aggregate():
    """JSON endpoint feeding the Analytic tab's per-chart period selectors.
    Returns per-account rows plus summary totals for the requested range."""
    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    raw_from = request.args.get('date_from', '')
    raw_to   = request.args.get('date_to', '')
    if range_key not in DATE_RANGE_KEYS:
        range_key = 'ytd'
    date_from, date_to, range_key = _resolve_date_range(
        range_key, raw_from, raw_to)

    c = get_client()
    try:
        rows = _compute_analytic(c, date_from, date_to)
    except Exception:
        rows = []
    summary = _analytic_summary(rows)
    return jsonify({
        'range_key':    range_key,
        'date_from':    date_from,
        'date_to':      date_to,
        'period_label': _format_period_label(range_key, date_from, date_to),
        'rows':         rows,
        'summary':      summary,
    })


@app.route('/financial/tax-summary')
@login_required
def financial_tax_summary():
    """JSON endpoint for the untaxed / tax / total summary cards."""
    tab = request.args.get('tab', 'invoices')
    if tab not in ('invoices', 'bills'):
        return jsonify({'error': 'invalid tab'}), 400
    move_type = 'out_invoice' if tab == 'invoices' else 'in_invoice'

    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    raw_from = request.args.get('date_from', '')
    raw_to = request.args.get('date_to', '')
    range_key, date_from, date_to = _resolve_trend_range(
        range_key, raw_from, raw_to)

    c = get_client()
    data = _compute_tax_summary(c, move_type, date_from, date_to)
    data['range_key']    = range_key
    data['date_from']    = date_from
    data['date_to']      = date_to
    data['period_label'] = _format_period_label(
        range_key, date_from, date_to)
    return jsonify(data)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@app.route('/inventory')
@login_required
def inventory():
    if _feature_is_locked('inventory'):
        return redirect(url_for('feature_unavailable', feature='inventory'))
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
    if _feature_is_locked('sales'):
        return redirect(url_for('feature_unavailable', feature='sales'))
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
    tab = request.args.get('tab', 'attendance')
    tab_feature = {'attendance': 'hr_attendance',
                   'leave':      'hr_leave'}.get(tab)
    if tab_feature and _feature_is_locked(tab_feature):
        return redirect(url_for('feature_unavailable', feature=tab_feature))
    c = get_client()
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
    if _feature_is_locked('manufacturing'):
        return redirect(url_for('feature_unavailable', feature='manufacturing'))
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
        'fields': ['id', 'name', 'partner_id', 'invoice_date', 'invoice_date_due',
                   'amount_untaxed', 'amount_tax', 'amount_total',
                   'state', 'payment_state'],
        'headers': ['Number', 'Customer', 'Invoice Date', 'Due Date',
                    'Untaxed', 'Tax', 'Amount', 'Status', 'Payment', 'Overdue'],
        'col_widths': [1.0, 2.4, 1.1, 1.1, 1.2, 1.0, 1.2, 0.9, 1.0, 1.0],
    },
    'financial_bills': {
        'title': 'Vendor Bills Report',
        'model': 'account.move',
        'domain': [['move_type', '=', 'in_invoice'], ['state', '!=', 'cancel']],
        'fields': ['id', 'name', 'partner_id', 'invoice_date', 'invoice_date_due',
                   'amount_untaxed', 'amount_tax', 'amount_total',
                   'state', 'payment_state'],
        'headers': ['Number', 'Vendor', 'Bill Date', 'Due Date',
                    'Untaxed', 'Tax', 'Amount', 'Status', 'Payment', 'Overdue'],
        'col_widths': [1.0, 2.4, 1.1, 1.1, 1.2, 1.0, 1.2, 0.9, 1.0, 1.0],
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
    'financial_analytic': {
        'title': 'Analytic Accounts Report',
        'model': 'account.analytic.account',  # aggregation handled in export()
        'fields': [],
        'headers': ['Cost Center', 'Plan / Group', 'Revenue', 'Costs',
                    'Net', 'Margin %', '# Transactions'],
        'col_widths': [2.4, 1.6, 1.3, 1.3, 1.3, 1.0, 1.0],
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
    domain = list(cfg.get('domain', []))

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '').strip()

    date_field_map = {
        'financial_invoices': 'invoice_date',
        'financial_bills': 'invoice_date',
        'financial_expenses': 'date',
        'inventory_movements': 'date',
        'sales_orders': 'date_order',
        'hr_attendance': 'check_in',
        'hr_leave': 'date_from',
        'manufacturing_production': 'date_planned_start',
    }
    df = date_field_map.get(key)
    if df and date_from:
        domain += [[df, '>=', date_from]]
    if df and date_to:
        domain += [[df, '<=', date_to]]

    title = cfg['title']
    title_extras = []

    if key in ('financial_invoices', 'financial_bills'):
        if search:
            domain += ['|', ['name', 'ilike', search],
                       ['partner_id.name', 'ilike', search]]

        statuses = _parse_status_filters(request.args)
        agings = _parse_aging_filters(request.args)
        period_days = max(1, safe_int_param('period', 30))

        if len(statuses) == 1:
            domain.append(['payment_state', '=', statuses[0]])
        elif statuses:
            domain.append(['payment_state', 'in', statuses])
        if statuses:
            title_extras.append(', '.join(
                PAYMENT_STATE_LABELS.get(s, s) for s in statuses))

        n = period_days
        bucket_ranges = [
            (0,       n),
            (n + 1,   2 * n),
            (2 * n + 1, 3 * n),
            (3 * n + 1, 4 * n),
            (4 * n + 1, None),
        ]
        bucket_labels = [
            f'0-{n} Days',
            f'{n + 1}-{2 * n} Days',
            f'{2 * n + 1}-{3 * n} Days',
            f'{3 * n + 1}-{4 * n} Days',
            f'{4 * n}+ Days',
        ]
        if agings:
            _apply_aging_filter(domain, agings, bucket_ranges, date.today())
            title_extras.append(', '.join(bucket_labels[i] for i in agings))

        if search:
            title_extras.append(f'Search: "{search}"')

    if key == 'financial_analytic':
        range_key = (request.args.get('range', '') or '').strip()
        if range_key in DATE_RANGE_KEYS:
            date_from_a, date_to_a, _ = _resolve_date_range(
                range_key, date_from, date_to)
        else:
            date_from_a = date_from or date.today().replace(month=1, day=1).isoformat()
            date_to_a = date_to or today_str()
        try:
            rows_a = _compute_analytic(c, date_from_a, date_to_a)
        except Exception:
            rows_a = []
        if search:
            s = search.lower()
            rows_a = [r for r in rows_a if s in (r.get('name') or '').lower()
                      or s in (r.get('plan_name') or '').lower()
                      or s in (r.get('code') or '').lower()]
        rows_a.sort(key=lambda r: r['net'], reverse=True)
        rows = [
            [
                (r.get('name') or '') +
                (f" [{r.get('code')}]" if r.get('code') else ''),
                r.get('plan_name') or '',
                fmt_currency(r.get('revenue', 0)),
                fmt_currency(r.get('costs', 0)),
                fmt_currency(r.get('net', 0)),
                f"{r.get('margin_pct', 0):.1f}%",
                r.get('count', 0),
            ]
            for r in rows_a
        ]
        period_lbl = _format_period_label(range_key or 'custom',
                                          date_from_a, date_to_a)
        if period_lbl:
            title = f'{title} - {period_lbl}'
        if fmt == 'pdf':
            buf = export_pdf(title, cfg['headers'], rows,
                             col_widths=cfg.get('col_widths'))
            return send_file(buf, mimetype='application/pdf',
                             download_name=f'{key}.pdf', as_attachment=True)
        else:
            buf = export_excel(title, cfg['headers'], rows)
            return send_file(
                buf,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                download_name=f'{key}.xlsx', as_attachment=True,
            )

    records = c.paginated_search_read(cfg['model'], domain,
                                      fields=cfg['fields'], order=None)

    def cell_val(rec, field):
        v = rec.get(field)
        if isinstance(v, list):
            return v[1] if len(v) > 1 else str(v[0])
        if isinstance(v, bool):
            return 'Yes' if v else 'No'
        if v is None:
            return ''
        return v

    if key in ('financial_invoices', 'financial_bills'):
        rows = _build_invoice_export_rows(records)
    else:
        rows = [[cell_val(r, f) for f in cfg['fields']] for r in records]

    if title_extras:
        title = f'{title} - {", ".join(title_extras)}'

    if fmt == 'pdf':
        buf = export_pdf(title, cfg['headers'], rows,
                         col_widths=cfg.get('col_widths'))
        return send_file(buf, mimetype='application/pdf',
                         download_name=f'{key}.pdf', as_attachment=True)
    else:
        buf = export_excel(title, cfg['headers'], rows)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=f'{key}.xlsx', as_attachment=True,
        )


PAYMENT_STATE_LABELS = {
    'paid': 'Paid',
    'not_paid': 'Unpaid',
    'partial': 'Partial',
    'reversed': 'Reversed',
    'in_payment': 'In Payment',
}

MOVE_STATE_LABELS = {
    'posted': 'Posted',
    'draft': 'Draft',
    'cancel': 'Cancelled',
}


def _build_invoice_export_rows(records: list) -> list:
    today_iso = today_str()
    out = []
    for r in records:
        partner = r.get('partner_id')
        partner_name = partner[1] if isinstance(partner, list) and len(partner) > 1 else ''
        ps = r.get('payment_state') or ''
        st = r.get('state') or ''
        due = r.get('invoice_date_due') or ''

        if not due:
            overdue = '—'
        elif ps == 'paid':
            overdue = 'Paid'
        elif ps == 'reversed':
            overdue = 'Reversed'
        elif ps in ('not_paid', 'partial') and str(due) < today_iso:
            overdue = 'Overdue'
        else:
            overdue = 'On Time'

        untaxed = r.get('amount_untaxed') or 0
        total = r.get('amount_total') or 0
        tax = r.get('amount_tax')
        if tax in (None, False):
            tax = total - untaxed
        out.append([
            r.get('name') or '',
            partner_name,
            r.get('invoice_date') or '',
            due,
            untaxed,
            tax,
            total,
            MOVE_STATE_LABELS.get(st, st),
            PAYMENT_STATE_LABELS.get(ps, ps or '—'),
            overdue,
        ])
    return out


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_ENV') != 'production', host='0.0.0.0', port=5000)
