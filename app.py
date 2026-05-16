import concurrent.futures
import json
import logging
import os
from datetime import datetime, date, timedelta
from functools import wraps

logger = logging.getLogger(__name__)

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


def _analytic_line_company_dom(client, line_fields_set, company_id):
    """Build a domain fragment that restricts account.analytic.line to a
    single company. The way to do this differs across Odoo versions:

      • v15/v16:                line has direct company_id
      • v17+ multi-plan:        line.company_id often gone; reach via
                                move_line_id.company_id (a.k.a. general
                                ledger journal item) or move_id
      • Worst case:             no path → return [] and log a warning so
                                the operator can see why filtering was
                                skipped.

    We always allow company_id = False alongside the real id, so records
    shared across companies (the "global" pattern) aren't accidentally
    hidden in single-company mode.
    """
    if not company_id:
        return []
    cid = int(company_id)
    vals = [cid, False]
    if 'company_id' in line_fields_set:
        return [['company_id', 'in', vals]]
    if 'move_line_id' in line_fields_set:
        return [['move_line_id.company_id', 'in', vals]]
    if 'move_id' in line_fields_set:
        return [['move_id.company_id', 'in', vals]]
    logger.warning(
        "Analytic: no company_id path on account.analytic.line "
        "(checked company_id, move_line_id, move_id). Multi-company "
        "filter cannot be applied — falling back to context-based filtering.")
    return []


def _compute_analytic(client, date_from, date_to, account_view='all'):
    """Aggregate account.analytic.line into one row per analytic account.
    Returns a list of dicts with revenue / costs / net / margin / count / plan.
    Costs are stored as positive numbers (absolute value of negative amounts).

    `account_view` ('pnl' | 'balance' | 'all') restricts which general
    accounts the analytic lines must hit. The list of allowed GL ids is
    resolved once via _account_view_allowed_gl_ids and added to the
    analytic-line domain as `general_account_id in [...]`.

    Strategy (resilient to the v17+ field rename + multi-company):
      1. Load every analytic account *for the selected company* up-front
         into an id → {name, plan, code} dict. Source of truth for names.
      2. Read-group the lines (also company-scoped) to get
         revenue / cost / count per account.
      3. Match groups to accounts by id and copy the canonical name across.

    Field-rename note: v17 renamed the line's m2o from `account_id` to
    `auto_account_id`; we prefer auto_account_id whenever it exists.
    """
    # Field resolution: on Odoo 17+ multi-plan the canonical relation is
    # `auto_account_id`. The legacy `account_id` column may still exist on
    # the model but read as False for every row (it's only populated under
    # the single-plan compatibility path). So PREFER auto_account_id when
    # present, falling back to account_id for v15/v16.
    line_fields = client.get_model_fields('account.analytic.line')
    if 'auto_account_id' in line_fields:
        account_field = 'auto_account_id'
    elif 'account_id' in line_fields:
        account_field = 'account_id'
    else:
        account_field = 'account_id'
    plan_field = client.pick_field('account.analytic.account', 'plan_id')

    # Resolve the active company from the client context (set by
    # OdooClient.set_company at login). Passing it through every domain
    # is more reliable than depending on Odoo's record-rule context — in
    # some deployments analytic record rules don't honour the context
    # filter and we get an empty multi-company result.
    company_id = client.context.get('company_id') or 0
    line_company_dom = _analytic_line_company_dom(client, line_fields, company_id)

    # ---- Step 1: id → name map for every analytic account in scope.
    # account.analytic.account.company_id is optional (False = shared
    # across companies). Allow both the selected company and False.
    acc_fields_set = client.get_model_fields('account.analytic.account')
    acc_company_dom = []
    if company_id and 'company_id' in acc_fields_set:
        acc_company_dom = [['company_id', 'in', [int(company_id), False]]]

    acc_read_fields = ['id', 'name', 'display_name', 'code']
    if plan_field:
        acc_read_fields.append(plan_field)
    if 'company_id' in acc_fields_set:
        acc_read_fields.append('company_id')

    # Include archived accounts — lines often reference them, and Odoo's
    # default search filter hides active=False unless we ask explicitly.
    archived_dom = ([['active', 'in', [True, False]]]
                    if 'active' in acc_fields_set else [])
    all_accounts = client.safe_search_read(
        'account.analytic.account',
        archived_dom + acc_company_dom,
        acc_read_fields) or []
    # If that returned 0 rows, retry without the active-bypass (in case
    # `active` isn't on this version) and finally without any domain.
    if not all_accounts and acc_company_dom:
        all_accounts = client.safe_search_read(
            'account.analytic.account', acc_company_dom, acc_read_fields) or []
    if not all_accounts:
        all_accounts = client.safe_search_read(
            'account.analytic.account', [], acc_read_fields) or []

    def _str_or_none(v):
        # Odoo encodes "no value" as Python False, not '' or None.
        if v is False or v is None or v == '':
            return None
        return v

    account_index = {}
    for r in all_accounts:
        aid = r.get('id')
        if not aid:
            continue
        # Prefer display_name (parent-prefixed) then plain name.
        nm = _str_or_none(r.get('display_name')) or _str_or_none(r.get('name'))
        plan = r.get(plan_field) if plan_field else None
        plan_id = None
        plan_name = ''
        if isinstance(plan, list) and len(plan) > 1:
            plan_id = plan[0]
            plan_name = _str_or_none(plan[1]) or ''
        account_index[aid] = {
            'name':      nm or 'Unassigned',
            'code':      _str_or_none(r.get('code')) or '',
            'plan_id':   plan_id,
            'plan_name': plan_name,
        }

    # ---- Step 2: read-group lines (company-scoped + account-view filter).
    base_dom = list(line_company_dom)
    if date_from:
        base_dom.append(['date', '>=', date_from])
    if date_to:
        base_dom.append(['date', '<=', date_to])

    # Account View filter — restrict analytic lines to those posting to a
    # GL account of the chosen type (P&L, Balance Sheet, or All). When
    # the resolver returns None we skip the filter entirely; when it
    # returns [] (e.g. a v15 server with no matching accounts) we still
    # short-circuit so the rest of the function returns an empty result.
    allowed_gl_ids = _account_view_allowed_gl_ids(client, account_view)
    if allowed_gl_ids is not None:
        if not allowed_gl_ids:
            logger.info("Analytic: account_view=%s yielded 0 GL accounts — "
                        "returning empty result set", account_view)
            return []
        base_dom.append(['general_account_id', 'in', allowed_gl_ids])

    rev_grps = client.safe_read_group(
        'account.analytic.line', base_dom + [['amount', '>', 0]],
        ['amount:sum'], [account_field]) or []
    cost_grps = client.safe_read_group(
        'account.analytic.line', base_dom + [['amount', '<', 0]],
        ['amount:sum'], [account_field]) or []
    count_grps = client.safe_read_group(
        'account.analytic.line', base_dom,
        [], [account_field]) or []

    # Diagnostic: log the field name + first few raw rows so any future
    # field-shape surprise (new Odoo version, installed extension) is
    # visible in server logs without a debugger.
    logger.info(
        "Analytic _compute_analytic: company_id=%s line_field=%s plan_field=%s "
        "company_dom=%s indexed_accounts=%d rev_groups=%d cost_groups=%d sample_groups=%s",
        company_id, account_field, plan_field, line_company_dom,
        len(account_index), len(rev_grps), len(cost_grps),
        (rev_grps or cost_grps or count_grps)[:3])
    if not account_index:
        logger.warning(
            "Analytic: account_index is EMPTY — search_read on account.analytic.account "
            "returned no rows (access rights or company filter?). All rows will be 'Unassigned'.")

    def _aid(grp):
        # In v17 multi-plan setups read_group can return the bare integer
        # id (no display tuple) — handle both shapes. Critically: bool is a
        # subclass of int in Python, so we must reject False explicitly,
        # otherwise an "empty" group (account_id=False) collapses every
        # row into one fake account.
        pair = grp.get(account_field)
        if isinstance(pair, bool):
            return None
        if isinstance(pair, list) and pair:
            first = pair[0]
            return None if isinstance(first, bool) else first
        if isinstance(pair, int):
            return pair
        return None

    # ---- Step 3: stitch groups → account rows.
    accounts = {}

    def _row(aid):
        a = accounts.get(aid)
        if a is None:
            meta = account_index.get(aid) or {}
            a = {
                'id': aid,
                'name':      meta.get('name')      or 'Unassigned',
                'code':      meta.get('code')      or '',
                'plan_id':   meta.get('plan_id'),
                'plan_name': meta.get('plan_name') or '',
                'revenue':   0,
                'costs':     0,
                'count':     0,
            }
            accounts[aid] = a
        return a

    for g in rev_grps:
        aid = _aid(g)
        if aid is None:
            continue
        _row(aid)['revenue'] = g.get('amount', 0) or 0
    for g in cost_grps:
        aid = _aid(g)
        if aid is None:
            continue
        _row(aid)['costs'] = abs(g.get('amount', 0) or 0)
    for g in count_grps:
        aid = _aid(g)
        if aid is None:
            continue
        _row(aid)['count'] = g.get('__count', 0)

    # ---- Step 4: fallback for v18 + Analytic Plans -----------------
    # On servers using Odoo's Analytic Plans, BOTH account_id and
    # auto_account_id can be False on every line — the real link is in
    # the JSON `analytic_distribution` field ({"51": 100, "93": 50}),
    # with custom plan m2o fields (x_plan*_id, plan*_id) as a secondary
    # signal. read_group can't aggregate through a JSON column, so when
    # the primary path produces nothing usable we read the raw lines
    # and split amounts client-side by percentage.
    primary_groups_produced_rows = bool(accounts)
    has_distribution = 'analytic_distribution' in line_fields
    plan_account_fields = sorted(
        f for f in line_fields
        if (f.startswith('x_plan') or f.startswith('plan'))
           and f.endswith('_id')
           and f not in (account_field, 'auto_account_id', 'account_id')
    )
    if (not primary_groups_produced_rows) and (has_distribution or plan_account_fields):
        logger.info(
            "Analytic: primary group path produced no rows — falling back "
            "to analytic_distribution / plan-account-field walk "
            "(has_distribution=%s plan_fields=%s)",
            has_distribution, plan_account_fields)
        accounts = _compute_analytic_via_distribution(
            client, base_dom, account_index,
            has_distribution=has_distribution,
            plan_account_fields=plan_account_fields)

    rows = list(accounts.values())
    for a in rows:
        a['net'] = a['revenue'] - a['costs']
        a['margin_pct'], a['margin_display'] = _margin_pct_and_display(
            a['net'], a['revenue'], a['costs'])
    return rows


def _compute_analytic_via_distribution(client, base_dom, account_index,
                                       has_distribution, plan_account_fields):
    """Fallback aggregator for Odoo's Analytic Plans architecture.

    Each line carries a JSON `analytic_distribution` like {"51": 100} or
    {"51,93": 50} (multi-plan composite keys). The total amount is
    distributed across the referenced accounts by percentage. If the
    JSON is empty, a plan-specific m2o (x_plan4_id, plan2_id, …) holds
    the account — full amount attributes to it.
    """
    read_fields = ['id', 'amount', 'date']
    if has_distribution:
        read_fields.append('analytic_distribution')
    read_fields.extend(plan_account_fields)

    lines = client.safe_search_read(
        'account.analytic.line', base_dom, read_fields) or []
    logger.info(
        "Analytic fallback: scanned %d raw lines (fields=%s sample=%s)",
        len(lines), read_fields, lines[:1])

    accounts = {}

    def _row(aid):
        a = accounts.get(aid)
        if a is None:
            meta = account_index.get(aid) or {}
            a = {
                'id': aid,
                'name':      meta.get('name')      or 'Unassigned',
                'code':      meta.get('code')      or '',
                'plan_id':   meta.get('plan_id'),
                'plan_name': meta.get('plan_name') or '',
                'revenue':   0,
                'costs':     0,
                'count':     0,
            }
            accounts[aid] = a
        return a

    # Backfill the index for any account id we encounter that wasn't in
    # the original company-scoped account read (e.g. cross-company plan
    # accounts). One bulk read at the end, after we know the set of ids.
    missing_ids = set()

    def _shares(line):
        """Yield (account_id, amount_share) pairs for a single line."""
        amount = line.get('amount') or 0
        dist = line.get('analytic_distribution') if has_distribution else None
        emitted = False
        if isinstance(dist, dict) and dist:
            for key, pct in dist.items():
                try:
                    pct_f = float(pct or 0) / 100.0
                except (TypeError, ValueError):
                    continue
                # Composite multi-plan keys look like "51,93" — Odoo
                # records the SAME amount × pct under each id, not split.
                for tok in str(key).split(','):
                    tok = tok.strip()
                    if not tok:
                        continue
                    try:
                        aid = int(tok)
                    except ValueError:
                        continue
                    yield aid, amount * pct_f
                    emitted = True
        if emitted:
            return
        # No distribution data — try plan-specific m2o fields.
        for f in plan_account_fields:
            v = line.get(f)
            if isinstance(v, bool):
                continue
            if isinstance(v, list) and v and not isinstance(v[0], bool):
                yield v[0], amount
                return
            if isinstance(v, int):
                yield v, amount
                return

    for ln in lines:
        for aid, share in _shares(ln):
            if not aid:
                continue
            row = _row(aid)
            if aid not in account_index:
                missing_ids.add(aid)
            if share > 0:
                row['revenue'] += share
            elif share < 0:
                row['costs'] += abs(share)
            row['count'] += 1

    # Backfill names for any account id we touched but didn't see in the
    # initial scoped read (e.g. company-shared analytic accounts).
    if missing_ids:
        try:
            extras = client.execute_kw(
                'account.analytic.account', 'read',
                [list(missing_ids)],
                {'fields': ['id', 'name', 'display_name', 'code']}) or []
        except Exception as e:
            logger.warning("Analytic fallback: failed to read %d extra accounts: %s",
                           len(missing_ids), e)
            extras = []
        for r in extras:
            a = accounts.get(r.get('id'))
            if not a:
                continue
            dn = r.get('display_name')
            nm = r.get('name')
            if dn and dn is not False:
                a['name'] = dn
            elif nm and nm is not False:
                a['name'] = nm
            if r.get('code'):
                a['code'] = r['code']

    return accounts


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


# account_type values that mark P&L revenue / expense accounts in Odoo
# v16+. The legacy v15 schema uses user_type_id → account.account.type with
# a free-text 'name' and a 'type' enum; we classify v15 with a hybrid
# approach (see _classify_gl_accounts).
PNL_REVENUE_TYPES = {'income', 'income_other'}
PNL_EXPENSE_TYPES = {
    'expense', 'expense_depreciation', 'expense_direct_cost',
    'expenses',  # tolerated alias seen on some forks
}

# Balance-sheet account_type values (v16+ keys; v15 is mapped into the same
# vocabulary by _classify_gl_accounts).
BALANCE_SHEET_TYPES = {
    'asset_receivable', 'asset_cash', 'asset_current',
    'asset_non_current', 'asset_prepayments', 'asset_fixed',
    'liability_payable', 'liability_current', 'liability_non_current',
    'equity', 'equity_unaffected',
}

# What each Account View on the Analytic page lets through. Used by both
# the analytic aggregation and the cost-center P&L computation.
ACCOUNT_VIEW_TYPES = {
    'pnl':     PNL_REVENUE_TYPES | PNL_EXPENSE_TYPES,
    'balance': BALANCE_SHEET_TYPES,
    'all':     None,        # no filter
}
ACCOUNT_VIEW_LABELS = {
    'pnl':     'P&L Accounts',
    'balance': 'Balance Sheet Accounts',
    'all':     'All Accounts',
}
ACCOUNT_VIEW_DEFAULT = 'pnl'


def _normalise_account_view(value):
    v = (value or '').lower()
    return v if v in ACCOUNT_VIEW_TYPES else ACCOUNT_VIEW_DEFAULT


def _current_account_view():
    """Resolve the Analytic page's account-type filter for this request.
    Order: ?account_view=... query/form override → session → default."""
    raw = request.values.get('account_view') if request else None
    if raw is None:
        raw = session.get('analytic_account_view')
    return _normalise_account_view(raw)


def _account_view_allowed_gl_ids(client, account_view):
    """Return the list of account.account ids matching the chosen
    Account View, or None when view='all' (no filter).

    Cached on `g` (per request) — a normal analytic render fires this
    helper 3-4 times (current rows, previous rows, P&L) and we don't
    want to redo the search each time. We deliberately don't persist in
    session: with hundreds of accounts the signed cookie would bloat."""
    account_view = _normalise_account_view(account_view)
    allowed_types = ACCOUNT_VIEW_TYPES.get(account_view)
    if allowed_types is None:
        return None  # 'all'

    company_id = client.context.get('company_id') or 0
    cache_key = (account_view, company_id)
    if not hasattr(g, '_account_view_cache'):
        g._account_view_cache = {}
    if cache_key in g._account_view_cache:
        return g._account_view_cache[cache_key]

    acc_fields = client.get_model_fields('account.account')
    has_account_type = 'account_type' in acc_fields
    has_user_type    = 'user_type_id' in acc_fields

    company_dom = []
    if company_id and 'company_id' in acc_fields:
        company_dom = [['company_id', 'in', [int(company_id), False]]]

    ids = []
    if has_account_type:
        try:
            rows = client.execute_kw(
                'account.account', 'search_read',
                [company_dom + [['account_type', 'in', list(allowed_types)]]],
                {'fields': ['id'], 'limit': 100000}) or []
        except Exception as e:
            logger.warning(
                "account_view filter: account_type search failed: %s", e)
            rows = []
        ids = [r['id'] for r in rows if r.get('id')]
    elif has_user_type:
        # v15: no account_type. Bulk-classify every visible account via
        # _classify_gl_accounts (which knows the legacy user_type_id +
        # name heuristics) and keep the matches.
        try:
            all_rows = client.safe_search_read(
                'account.account', company_dom, ['id']) or []
        except Exception:
            all_rows = []
        meta = _classify_gl_accounts(client, {r['id'] for r in all_rows if r.get('id')})
        ids = [gid for gid, m in meta.items()
               if (m.get('type') or '') in allowed_types]
    # else: no recognised field — return [] which short-circuits to "no rows".

    g._account_view_cache[cache_key] = ids
    logger.info(
        "Account view filter resolved: view=%s company=%s ids=%d",
        account_view, company_id, len(ids))
    return ids

# Display order + label for each sub-section inside REVENUE / EXPENSES.
# Tuples are (account_type_key, ui_label). Groups with no lines are
# hidden by _build_section_groups, so the surface area is empty for
# servers where, e.g., depreciation accounts aren't used.
PNL_REVENUE_SUBTYPES = [
    ('income',       'Income'),
    ('income_other', 'Other Income'),
]
PNL_EXPENSE_SUBTYPES = [
    ('expense_direct_cost',  'Cost of Revenue'),
    ('expense',              'Expenses'),
    ('expenses',             'Expenses'),   # absorbs the alias above
    ('expense_depreciation', 'Depreciation'),
]


def _build_section_groups(lines, subtypes, section_total):
    """Bucket already-classified lines into ordered sub-groups by type.

    Each output group looks like:
      {'type', 'label', 'lines', 'subtotal',
       'pct', 'pct_display'}  — pct is share of the section total.

    Sub-groups with no lines are dropped (template / PDF / Excel only
    render what came back).
    """
    # When two subtype keys map to the same label (e.g. 'expense' +
    # 'expenses'), merge them into one bucket keyed by label.
    label_index = {}
    order = []
    for type_key, label in subtypes:
        if label not in label_index:
            label_index[label] = {
                'type':  type_key, 'label': label, 'lines': [],
                'subtotal': 0.0,
            }
            order.append(label)

    type_to_label = {tk: lb for tk, lb in subtypes}
    leftover = []
    for ln in lines:
        t = (ln.get('type') or '').lower()
        lb = type_to_label.get(t)
        if lb and lb in label_index:
            label_index[lb]['lines'].append(ln)
            label_index[lb]['subtotal'] += ln['amount']
        else:
            leftover.append(ln)

    if leftover:
        lb = 'Other'
        label_index.setdefault(lb, {
            'type': '', 'label': lb, 'lines': [], 'subtotal': 0.0})
        if lb not in order:
            order.append(lb)
        for ln in leftover:
            label_index[lb]['lines'].append(ln)
            label_index[lb]['subtotal'] += ln['amount']

    out = []
    for lb in order:
        g = label_index[lb]
        if not g['lines']:
            continue
        g['lines'].sort(key=lambda x: x['amount'], reverse=True)
        if section_total > 0:
            p = (g['subtotal'] / section_total) * 100.0
            g['pct'] = p
            g['pct_display'] = '%.1f%%' % p
        else:
            g['pct'] = 0.0
            g['pct_display'] = '—'
        out.append(g)
    return out


def _classify_gl_accounts(client, gid_set):
    """Return {gid: {'name', 'code', 'type'}} for every GL account id.

    The 'type' value is normalised to one of:
      'income' | 'income_other'              → revenue
      'expense' | 'expense_depreciation' | 'expense_direct_cost' → expense
      anything else (or '')                  → other / balance sheet

    Version compatibility:
      • v16+: account_type is a string field on account.account — read it
        directly in a single bulk call.
      • v15:  no account_type field. Read user_type_id, then batch-read
        the corresponding account.account.type rows. We pick the
        revenue/expense bucket from the legacy 'type' enum + the name
        text ('Income', 'Other Income', 'Expense', 'Cost of Revenue').
    """
    if not gid_set:
        return {}
    gid_list = list(gid_set)
    acc_fields_set = client.get_model_fields('account.account')
    has_account_type = 'account_type' in acc_fields_set
    has_user_type    = 'user_type_id' in acc_fields_set

    fields = ['id', 'name', 'display_name', 'code']
    if has_account_type: fields.append('account_type')
    if has_user_type:    fields.append('user_type_id')
    try:
        accs = client.execute_kw(
            'account.account', 'read',
            [gid_list], {'fields': fields}) or []
    except Exception as e:
        logger.warning("Cost-center P&L: account.account read failed: %s", e)
        accs = []

    # v15 prep: harvest user_type ids and fetch their type/name.
    v15_meta = {}
    if (not has_account_type) and has_user_type:
        ut_ids = []
        for r in accs:
            ut = r.get('user_type_id')
            if isinstance(ut, list) and ut and not isinstance(ut[0], bool):
                ut_ids.append(ut[0])
        if ut_ids:
            try:
                rows = client.execute_kw(
                    'account.account.type', 'read',
                    [list(set(ut_ids))],
                    {'fields': ['id', 'name', 'type']}) or []
            except Exception as e:
                logger.info("v15 user-type read failed: %s", e)
                rows = []
            for tr in rows:
                v15_meta[tr.get('id')] = {
                    'name': (tr.get('name') or '').lower(),
                    'type': (tr.get('type') or '').lower(),
                }

    def _v15_atype(ut_pair):
        if not (isinstance(ut_pair, list) and ut_pair):
            return ''
        meta = v15_meta.get(ut_pair[0], {})
        legacy = meta.get('type', '')   # receivable | payable | liquidity | other | equity
        ut_name = meta.get('name', '')
        # Map legacy balance-sheet enums onto the v16+ vocabulary so the
        # Account View filter can treat both versions uniformly.
        if legacy == 'receivable': return 'asset_receivable'
        if legacy == 'payable':    return 'liability_payable'
        if legacy == 'liquidity':  return 'asset_cash'
        if legacy == 'equity':     return 'equity'
        # 'other' is overloaded — fall through to keyword heuristics.
        # P&L-side keywords first (specific before generic).
        if 'depreciation' in ut_name:
            return 'expense_depreciation'
        if ('cost of revenue' in ut_name or 'cost of sale' in ut_name
                or 'cost of good' in ut_name or 'direct cost' in ut_name):
            return 'expense_direct_cost'
        if 'other income' in ut_name:
            return 'income_other'
        if 'income' in ut_name or 'revenue' in ut_name or 'sale' in ut_name:
            return 'income'
        if 'expense' in ut_name or 'cost' in ut_name:
            return 'expense'
        # Balance-sheet keyword fallbacks for the 'other' enum bucket.
        if 'prepay' in ut_name:
            return 'asset_prepayments'
        if 'fixed' in ut_name and 'asset' in ut_name:
            return 'asset_fixed'
        if 'non-current asset' in ut_name or 'non current asset' in ut_name:
            return 'asset_non_current'
        if 'current asset' in ut_name:
            return 'asset_current'
        if 'non-current liabilit' in ut_name or 'non current liabilit' in ut_name:
            return 'liability_non_current'
        if 'current liabilit' in ut_name:
            return 'liability_current'
        if 'unaffected' in ut_name and 'earning' in ut_name:
            return 'equity_unaffected'
        return ''

    out = {}
    for r in accs:
        gid = r.get('id')
        if not gid:
            continue
        dn = r.get('display_name')
        nm = r.get('name')
        label = (dn if dn and dn is not False
                 else (nm if nm and nm is not False else ''))
        code = r.get('code') if r.get('code') and r.get('code') is not False else ''
        atype = ''
        if has_account_type:
            v = r.get('account_type')
            if v and v is not False:
                atype = str(v).lower()
        if not atype and has_user_type:
            atype = _v15_atype(r.get('user_type_id'))
        out[gid] = {
            'name': label or '',
            'code': code or '',
            'type': atype,
        }
    return out


def _empty_pnl_payload():
    """Shape-compatible empty result used when the Account View filter
    yields zero GL accounts. Keeps downstream rendering safe."""
    return {
        'revenue_groups': [],
        'expense_groups': [],
        'revenue_lines':  [],
        'expense_lines':  [],
        'other_lines':    [],
        'total_revenue':  0.0,
        'total_expenses': 0.0,
        'total_other':    0.0,
        'net':            0.0,
        'margin_pct':     0.0,
        'margin_display': '—',
    }


def _compute_cost_center_pnl(client, account_id, date_from, date_to,
                             account_view='all'):
    """Build a P&L statement for a single analytic account.

    Returns:
      {
        'revenue_lines':  [{'id','name','code','amount','type'}, ...],
        'expense_lines':  [...],
        'other_lines':    [...],  # non-P&L (assets / liabilities / equity)
        'total_revenue':  float,
        'total_expenses': float,
        'total_other':    float,  # signed sum across "other" accounts
        'net':            float,  # revenue - expenses
        'margin_pct':     float,
        'margin_display': '%.1f%%' | '—',
      }

    Classification is done by the accounting account's TYPE
    (account.account.account_type on v16+, or v15's user_type_id), not
    by amount sign — so a refund or reversal doesn't flip an account
    into the wrong section.

    Version compatibility for the analytic line lookup:
      • V15/V16/V17: filter on account_id / auto_account_id, group by
                     general_account_id (single read_group).
      • V18/V19:     fallback walk through analytic_distribution +
                     x_plan*_id / plan*_id when account_id is False.
    """
    aid = int(account_id)
    line_fields = client.get_model_fields('account.analytic.line')
    company_id = client.context.get('company_id') or 0
    line_company_dom = _analytic_line_company_dom(client, line_fields, company_id)

    date_dom = []
    if date_from:
        date_dom.append(['date', '>=', date_from])
    if date_to:
        date_dom.append(['date', '<=', date_to])

    # Account View filter — same GL-account whitelist used by the
    # analytic page so the P&L report stays consistent with what the
    # KPI cards / charts are showing.
    allowed_gl_ids = _account_view_allowed_gl_ids(client, account_view)
    view_dom = []
    if allowed_gl_ids is not None:
        if not allowed_gl_ids:
            # Filter yields no GL accounts — short-circuit to empty.
            return _empty_pnl_payload()
        view_dom = [['general_account_id', 'in', allowed_gl_ids]]

    has_general = 'general_account_id' in line_fields
    if 'auto_account_id' in line_fields:
        account_field = 'auto_account_id'
    elif 'account_id' in line_fields:
        account_field = 'account_id'
    else:
        account_field = None

    # ---- Primary path: one read_group, no sign filter. Classification
    # happens later from account_type.
    groups = []
    if account_field and has_general:
        dom = (line_company_dom + date_dom + view_dom +
               [[account_field, '=', aid]])
        groups = client.safe_read_group(
            'account.analytic.line', dom,
            ['amount:sum'], ['general_account_id']) or []

    # ---- Fallback for v18+ Analytic Plans (account_field is False on rows).
    if not groups:
        groups = _cost_center_pnl_via_distribution(
            client, aid, line_fields,
            line_company_dom + date_dom + view_dom)

    # ---- Aggregate raw per-GL signed amounts.
    raw = {}    # gid -> {'name', 'code', 'type', 'amount': signed sum}
    for g in groups:
        ga = g.get('general_account_id')
        gid, gname = None, ''
        if isinstance(ga, list) and ga and not isinstance(ga[0], bool):
            gid = ga[0]
            gname = (ga[1] if len(ga) > 1 and ga[1]
                     and ga[1] is not False else '')
        elif isinstance(ga, int) and not isinstance(ga, bool):
            gid = ga
        if not gid:
            continue
        amt = g.get('amount') or 0
        slot = raw.setdefault(gid, {
            'name': gname, 'code': '', 'type': '', 'amount': 0.0,
        })
        if gname and not slot['name']:
            slot['name'] = gname
        slot['amount'] += amt

    # ---- One bulk read on account.account for names + types.
    meta = _classify_gl_accounts(client, set(raw.keys()))
    for gid, slot in raw.items():
        m = meta.get(gid) or {}
        if m.get('name'):  # canonical label wins over the m2o tuple's display
            slot['name'] = m['name']
        if m.get('code'):
            slot['code'] = m['code']
        slot['type'] = m.get('type') or ''

    # ---- Bucket into revenue / expense / other based on account_type.
    rev_lines, exp_lines, oth_lines = [], [], []
    for gid, s in raw.items():
        amt = s['amount']
        t = (s.get('type') or '').lower()
        base = {
            'id':   gid,
            'name': s['name'] or 'Unassigned',
            'code': s['code'] or '',
            'type': t,
        }
        if t in PNL_REVENUE_TYPES:
            # Revenue posts to analytic as POSITIVE in standard Odoo. Take
            # the absolute value so a single refund (negative net) still
            # displays sensibly; negative net revenue is unusual but if it
            # happens the sign is preserved in the raw total below.
            base['amount'] = abs(amt)
            if base['amount'] > 0:
                rev_lines.append(base)
        elif t in PNL_EXPENSE_TYPES:
            base['amount'] = abs(amt)
            if base['amount'] > 0:
                exp_lines.append(base)
        else:
            # Balance-sheet movement — keep the signed amount so users can
            # tell whether assets/liabilities increased or decreased.
            base['amount'] = amt
            if amt != 0:
                oth_lines.append(base)

    rev_lines.sort(key=lambda x: x['amount'], reverse=True)
    exp_lines.sort(key=lambda x: x['amount'], reverse=True)
    oth_lines.sort(key=lambda x: abs(x['amount']), reverse=True)

    total_revenue  = sum(x['amount'] for x in rev_lines)
    total_expenses = sum(x['amount'] for x in exp_lines)

    # Each line carries pct = share of its own section's subtotal, so the
    # template + exporters can render without re-summing. 1 decimal place.
    def _attach_pct(lines, total):
        if total <= 0:
            for ln in lines:
                ln['pct'] = 0.0
                ln['pct_display'] = '—'
            return
        for ln in lines:
            p = (ln['amount'] / total) * 100.0
            ln['pct'] = p
            ln['pct_display'] = '%.1f%%' % p

    _attach_pct(rev_lines, total_revenue)
    _attach_pct(exp_lines, total_expenses)
    # Other section uses |amount| / |total_other| so signed amounts in
    # opposite directions don't cancel out in the share calculation.
    total_other_abs = sum(abs(x['amount']) for x in oth_lines)
    if total_other_abs > 0:
        for ln in oth_lines:
            p = (abs(ln['amount']) / total_other_abs) * 100.0
            ln['pct'] = p
            ln['pct_display'] = '%.1f%%' % p
    else:
        for ln in oth_lines:
            ln['pct'] = 0.0
            ln['pct_display'] = '—'
    total_other    = sum(x['amount'] for x in oth_lines)
    net = total_revenue - total_expenses
    if total_revenue > 0:
        margin_pct = (net / total_revenue) * 100.0
        margin_display = '%.1f%%' % margin_pct
    else:
        margin_pct = 0.0
        margin_display = '—'

    revenue_groups = _build_section_groups(
        rev_lines, PNL_REVENUE_SUBTYPES, total_revenue)
    expense_groups = _build_section_groups(
        exp_lines, PNL_EXPENSE_SUBTYPES, total_expenses)

    logger.info(
        "Cost-center P&L aid=%s rev=%d (%d grps) exp=%d (%d grps) other=%d "
        "totals=(R%.2f, E%.2f, O%.2f)",
        aid, len(rev_lines), len(revenue_groups),
        len(exp_lines), len(expense_groups), len(oth_lines),
        total_revenue, total_expenses, total_other)

    return {
        'revenue_groups': revenue_groups,
        'expense_groups': expense_groups,
        'revenue_lines':  rev_lines,
        'expense_lines':  exp_lines,
        'other_lines':    oth_lines,
        'total_revenue':  total_revenue,
        'total_expenses': total_expenses,
        'total_other':    total_other,
        'net':            net,
        'margin_pct':     margin_pct,
        'margin_display': margin_display,
    }


def _cost_center_pnl_via_distribution(client, account_id, line_fields_set, base_dom):
    """V18+ Analytic Plans fallback for the cost-center P&L.

    read_group can't filter on the JSON column `analytic_distribution`, so
    we pull the company/date-scoped lines and walk them client-side. A
    line is attributed to the requested account when either:
      • analytic_distribution has a key matching the account id
        (including composite "51,93" multi-plan keys), or
      • any of the x_plan*_id / plan*_id fields point at the account.
    The amount attributed is amount × percentage / 100.

    Returns a list of read_group-shaped rows
    [{'general_account_id': [gid, name] | False, 'amount': float}, ...]
    so the caller (which classifies by account_type) can treat the
    output identically to the primary read_group path.
    """
    aid = int(account_id)
    has_distribution = 'analytic_distribution' in line_fields_set
    plan_account_fields = sorted(
        f for f in line_fields_set
        if (f.startswith('x_plan') or f.startswith('plan'))
           and f.endswith('_id')
           and f not in ('account_id', 'auto_account_id')
    )

    read_fields = ['id', 'amount', 'date']
    if 'general_account_id' in line_fields_set:
        read_fields.append('general_account_id')
    if has_distribution:
        read_fields.append('analytic_distribution')
    read_fields.extend(plan_account_fields)

    lines = client.safe_search_read(
        'account.analytic.line', base_dom, read_fields) or []

    # gid -> {'name': str, 'amount': signed sum}
    buckets = {}

    def _share_for_line(ln):
        amount = ln.get('amount') or 0
        share = 0.0
        dist = ln.get('analytic_distribution') if has_distribution else None
        if isinstance(dist, dict) and dist:
            for key, pct in dist.items():
                try:
                    pct_f = float(pct or 0) / 100.0
                except (TypeError, ValueError):
                    continue
                for tok in str(key).split(','):
                    tok = tok.strip()
                    if tok.isdigit() and int(tok) == aid:
                        share += amount * pct_f
            if share != 0:
                return share
        for f in plan_account_fields:
            v = ln.get(f)
            if isinstance(v, bool):
                continue
            if isinstance(v, list) and v and v[0] == aid:
                return amount
            if isinstance(v, int) and v == aid:
                return amount
        return 0.0

    for ln in lines:
        share = _share_for_line(ln)
        if not share:
            continue
        ga = ln.get('general_account_id')
        if isinstance(ga, list) and ga and not isinstance(ga[0], bool):
            gid = ga[0]
            gname = ga[1] if len(ga) > 1 and ga[1] and ga[1] is not False else ''
        elif isinstance(ga, int) and not isinstance(ga, bool):
            gid, gname = ga, ''
        else:
            gid, gname = 0, 'Unallocated'
        slot = buckets.setdefault(gid, {'name': gname, 'amount': 0.0})
        if not slot['name'] and gname:
            slot['name'] = gname
        slot['amount'] += share

    logger.info(
        "Cost-center P&L fallback: aid=%s scanned=%d buckets=%d "
        "(has_distribution=%s plan_fields=%s)",
        aid, len(lines), len(buckets), has_distribution, plan_account_fields)

    out = []
    for gid, s in buckets.items():
        ga_pair = [gid, s['name']] if gid else False
        out.append({'general_account_id': ga_pair, 'amount': s['amount']})
    return out


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


def _compute_kpi(client, move_type, date_from, date_to, range_key, compare_yoy):
    """Compute the four headline KPI cards (count / total / paid / unpaid)
    plus the previous-period comparison for the Invoices/Bills Overview
    Period selector. Intentionally independent of search, status, aging,
    and cashflow filters — those drive the table, not the headline.

    Fires the four queries (current+previous count+totals) in parallel
    using fresh XML-RPC clients since the underlying ServerProxy is not
    thread-safe."""

    def _fresh():
        return OdooClient(client.url, client.db, client.uid, client.password,
                          context=dict(client.context))

    def _domain(df, dt):
        d = [['move_type', '=', move_type], ['state', '!=', 'cancel']]
        if df:
            d.append(['invoice_date', '>=', df])
        if dt:
            d.append(['invoice_date', '<=', dt])
        return d

    domain = _domain(date_from, date_to)
    prev_from, prev_to, prev_label = _previous_date_range(
        range_key, date_from, date_to, year_over_year=compare_yoy)
    prev_domain = _domain(prev_from, prev_to)

    def _count(dom):
        return _fresh().safe_count('account.move', dom)

    def _totals(dom):
        return _fresh().safe_read_group(
            'account.move', dom,
            ['amount_total:sum', 'amount_residual:sum'], [])

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    try:
        f_count       = pool.submit(_count, domain)
        f_totals      = pool.submit(_totals, domain)
        f_prev_count  = pool.submit(_count, prev_domain)
        f_prev_totals = pool.submit(_totals, prev_domain)
        try:
            count = f_count.result(timeout=30)
        except Exception:
            count = 0
        try:
            totals = (f_totals.result(timeout=30) or [{}])[0]
        except Exception:
            totals = {}
        try:
            prev_count = f_prev_count.result(timeout=30)
        except Exception:
            prev_count = 0
        try:
            prev_totals = (f_prev_totals.result(timeout=30) or [{}])[0]
        except Exception:
            prev_totals = {}
    finally:
        pool.shutdown(wait=False)

    def _shape(c, t):
        total = t.get('amount_total', 0) or 0
        residual = t.get('amount_residual', 0) or 0
        return {
            'count':  c,
            'total':  total,
            'unpaid': residual,
            'paid':   total - residual,
        }

    stats = _shape(count, totals)
    prev_stats = _shape(prev_count, prev_totals)
    compare_pct = {
        'count':  _pct_change(stats['count'],  prev_stats['count']),
        'total':  _pct_change(stats['total'],  prev_stats['total']),
        'paid':   _pct_change(stats['paid'],   prev_stats['paid']),
        'unpaid': _pct_change(stats['unpaid'], prev_stats['unpaid']),
    }
    return {
        'stats':         stats,
        'compare_stats': prev_stats,
        'compare_label': f'vs {prev_label}',
        'compare_pct':   compare_pct,
        'prev_label':    prev_label,
    }


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


@app.route('/financial/analytic/account-view', methods=['POST'])
@login_required
def set_analytic_account_view():
    """Persist the Account View filter (P&L / Balance Sheet / All) in the
    session so it survives navigation. Front-end calls this on toggle then
    re-renders the page."""
    raw = request.form.get('account_view') or request.args.get('account_view')
    if not raw and request.is_json:
        try:
            raw = (request.get_json(silent=True) or {}).get('account_view')
        except Exception:
            raw = None
    view = _normalise_account_view(raw)
    session['analytic_account_view'] = view
    return jsonify({
        'ok': True,
        'account_view':       view,
        'account_view_label': ACCOUNT_VIEW_LABELS[view],
    })


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
# Assets — version-portable model + field resolution
# ---------------------------------------------------------------------------

# v15/v16 ship 'account.asset.asset'; v17+ collapse it to 'account.asset'.
# We probe live fields_get so a third-party module (OCA on community) that
# ships only one of the two still resolves correctly.
ASSET_MODEL_CANDIDATES = ('account.asset', 'account.asset.asset')

ASSET_STATE_LABELS = {
    'draft':     'Draft',
    'open':      'Running',
    'close':     'Closed',
    'paused':    'Paused',
    'cancel':    'Cancelled',
    'cancelled': 'Cancelled',
    'model':     'Model',
}


def _resolve_asset_model(client):
    """Pick the right asset model for this Odoo version.

    v17+ folded `account_asset` into `account` under the model name
    `account.asset`; v15/v16 keep the legacy `account.asset.asset`. We
    prefer the modern name, but fall back to a live fields_get probe so
    OCA / customised installs are detected correctly.
    """
    cached = getattr(g, '_asset_model', None)
    if cached is not None:
        return cached or None

    ver = getattr(client, 'version_major', 0) or 0
    ordered = (('account.asset.asset', 'account.asset')
               if ver and ver <= 16
               else ('account.asset', 'account.asset.asset'))
    chosen = None
    for m in ordered:
        try:
            if client.get_model_fields(m):
                chosen = m
                break
        except Exception:
            continue
    g._asset_model = chosen or ''
    return chosen


def _build_asset_fields(client, model):
    """Build a version-portable field list for the asset model.

    Older versions exposed `category_id`; v17+ replaced it with account
    fields. We always include `name`, `state`, `original_value`, and
    `value_residual` when present, and skip anything missing so a single
    fields_get error doesn't black-hole the whole search_read."""
    available = client.get_model_fields(model)
    wanted = [
        'name', 'state', 'active',
        'acquisition_date', 'first_depreciation_date', 'date',
        'original_value', 'value_residual', 'salvage_value',
        'category_id', 'account_asset_id', 'currency_id',
    ]
    return [f for f in wanted if f in available]


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

        # Overview Period — independent of the main range/search/aging
        # filters. Drives the four headline KPI cards + their YoY compare.
        # Defaults to YTD and survives any change to the page-level filters.
        raw_kpi_range    = (request.args.get('kpi_range', '') or '').strip()
        raw_kpi_from     = request.args.get('kpi_date_from', '')
        raw_kpi_to       = request.args.get('kpi_date_to', '')
        kpi_compare_yoy  = request.args.get('kpi_compare_yoy',
                              request.args.get('compare_yoy')) == '1'
        kpi_range = raw_kpi_range if raw_kpi_range in DATE_RANGE_KEYS else 'ytd'
        kpi_from, kpi_to, kpi_range = _resolve_date_range(
            kpi_range, raw_kpi_from, raw_kpi_to)

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

        # ---- Headline KPIs use the Overview Period only — never the main
        # range / search / aging / status / cashflow filters. Comparison
        # fires alongside via the same helper.
        kpi_payload = _compute_kpi(
            c, move_type, kpi_from, kpi_to, kpi_range, kpi_compare_yoy)

        total = c.safe_count('account.move', table_domain)
        records = c.safe_search_read('account.move', table_domain,
            ['id', 'name', 'partner_id', 'invoice_date', 'invoice_date_due',
             'amount_untaxed', 'amount_tax',
             'amount_total', 'amount_residual', 'currency_id', 'state', 'payment_state'],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order='invoice_date desc')

        ctx['records'] = records
        ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ctx['total_count'] = total
        ctx['status_filter'] = status_filter
        ctx['aging_filter'] = aging_filter
        ctx['today_iso'] = today_str()
        ctx['stats'] = kpi_payload['stats']

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

        # KPI comparison + period label come from the helper above, scoped to
        # the Overview Period rather than the main filter.
        ctx['compare_stats'] = kpi_payload['compare_stats']
        ctx['compare_label'] = kpi_payload['compare_label']
        ctx['compare_pct']   = kpi_payload['compare_pct']
        ctx['compare_yoy']   = kpi_compare_yoy
        ctx['kpi_range']     = kpi_range
        ctx['kpi_date_from'] = kpi_from
        ctx['kpi_date_to']   = kpi_to
        ctx['kpi_period_label'] = _format_period_label(
            kpi_range, kpi_from, kpi_to)

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
        asset_model = _resolve_asset_model(c)
        if not asset_model:
            ctx['error'] = 'Assets module may not be installed on this Odoo instance.'
            ctx['records'] = []
            ctx['stats'] = {'count': 0, 'original_value': 0,
                            'residual_value': 0, 'depreciated': 0}
            ctx['asset_state_filter'] = 'all'
            ctx['asset_state_options'] = []
        else:
            asset_fields = c.get_model_fields(asset_model)
            read_fields  = _build_asset_fields(c, asset_model)

            state_filter = (request.args.get('state_filter', 'all') or 'all').strip()
            valid_states = {'all', 'draft', 'open', 'close', 'cancel', 'paused', 'model'}
            if state_filter not in valid_states:
                state_filter = 'all'

            domain = []
            # Show archived rows too — Odoo defaults `active=True`, and a fair
            # number of running assets get archived to hide them from the UI
            # without being closed.
            if 'active' in asset_fields:
                domain.append(['active', 'in', [True, False]])
            if search:
                domain.append(['name', 'ilike', search])
            if state_filter != 'all' and 'state' in asset_fields:
                # 'cancel' covers both 'cancel' and 'cancelled' across versions.
                if state_filter == 'cancel':
                    domain.append(['state', 'in', ['cancel', 'cancelled']])
                else:
                    domain.append(['state', '=', state_filter])

            try:
                total = c.safe_count(asset_model, domain)
                # Order on whatever date-ish field this version exposes; fall
                # back to `id desc` so a missing column doesn't return [].
                order_field = next((f for f in
                    ('acquisition_date', 'first_depreciation_date', 'date')
                    if f in asset_fields), None)
                order_clause = (order_field + ' desc') if order_field else 'id desc'
                records = c.safe_search_read(asset_model, domain, read_fields,
                    limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, order=order_clause)

                # Normalise the date field name + state label so the template
                # stays version-agnostic.
                for r in records:
                    r['acquisition_date_display'] = (
                        r.get('acquisition_date')
                        or r.get('first_depreciation_date')
                        or r.get('date') or '')
                    st = r.get('state') or ''
                    r['state_label'] = ASSET_STATE_LABELS.get(st, st or '—')

                # Sum totals using the same domain so KPI == table count.
                grp_fields = []
                if 'original_value' in asset_fields:
                    grp_fields.append('original_value:sum')
                if 'value_residual' in asset_fields:
                    grp_fields.append('value_residual:sum')
                totals = {}
                if grp_fields:
                    grps = c.safe_read_group(asset_model, domain, grp_fields, [])
                    totals = grps[0] if grps else {}

                ctx['records'] = records
                ctx['total_pages'] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
                ctx['total_count'] = total
                ctx['stats'] = {
                    'count': total,
                    'original_value': totals.get('original_value', 0) or 0,
                    'residual_value': totals.get('value_residual', 0) or 0,
                    'depreciated': (totals.get('original_value', 0) or 0)
                                   - (totals.get('value_residual', 0) or 0),
                }
                ctx['asset_state_filter'] = state_filter
                ctx['asset_state_options'] = [
                    ('all',    'All States'),
                    ('draft',  'Draft'),
                    ('open',   'Running'),
                    ('close',  'Closed'),
                    ('cancel', 'Cancelled'),
                ]
                logger.info("Assets tab: model=%s count=%d fields=%s",
                            asset_model, total, read_fields)
            except Exception as e:
                logger.warning("Assets tab failed for model %s: %s", asset_model, e)
                ctx['error'] = 'Could not read assets from this Odoo instance.'
                ctx['records'] = []
                ctx['stats'] = {'count': 0, 'original_value': 0,
                                'residual_value': 0, 'depreciated': 0}
                ctx['asset_state_filter'] = state_filter
                ctx['asset_state_options'] = []

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
        # Resolve the Account View filter — query param first, then session.
        account_view_active = _current_account_view()
        session['analytic_account_view'] = account_view_active
        ctx['account_view']        = account_view_active
        ctx['account_view_label']  = ACCOUNT_VIEW_LABELS[account_view_active]
        ctx['account_view_options'] = [
            ('pnl',     ACCOUNT_VIEW_LABELS['pnl']),
            ('balance', ACCOUNT_VIEW_LABELS['balance']),
            ('all',     ACCOUNT_VIEW_LABELS['all']),
        ]

        # ---- Independent KPI period (default YTD). Driven by its own
        # set of query params so the main Search/Period filter below
        # never touches the KPI cards.
        kpi_range = (request.args.get('kpi_range', 'ytd') or 'ytd').strip()
        if kpi_range not in DATE_RANGE_KEYS:
            kpi_range = 'ytd'
        kpi_from_raw = request.args.get('kpi_date_from', '')
        kpi_to_raw   = request.args.get('kpi_date_to', '')
        kpi_from, kpi_to, kpi_range = _resolve_date_range(
            kpi_range, kpi_from_raw, kpi_to_raw)
        kpi_compare_yoy = request.args.get('kpi_compare_yoy') == '1'
        kpi_payload = _compute_analytic_kpi_payload(
            c, kpi_from, kpi_to, kpi_range, kpi_compare_yoy,
            account_view=account_view_active)
        ctx['kpi_stats']         = kpi_payload['stats']
        ctx['kpi_compare_stats'] = kpi_payload.get('compare_stats')
        ctx['kpi_compare_pct']   = kpi_payload.get('compare_pct', {}) or {}
        ctx['kpi_compare_label'] = kpi_payload.get('compare_label', '')
        ctx['kpi_range']         = kpi_range
        ctx['kpi_date_from']     = kpi_from
        ctx['kpi_date_to']       = kpi_to
        ctx['kpi_period_label']  = kpi_payload['period_label']
        ctx['kpi_compare_yoy']   = kpi_compare_yoy

        # Budget vs Actual availability — checked once here so the
        # template can render the section in its disabled state (lock
        # icon + helpful message) without an extra round-trip.
        ctx['budget_available'] = _budget_available(c)
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
                rows = _compute_analytic(
                    c, date_from, date_to,
                    account_view=account_view_active)
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

        # Previous-period comparison — same Account View filter so the
        # comparison stays apples-to-apples.
        prev_from, prev_to, prev_label = _previous_date_range(
            range_key, date_from, date_to)
        try:
            prev_rows = (_compute_analytic(
                c, prev_from, prev_to, account_view=account_view_active)
                if prev_from else [])
        except Exception:
            prev_rows = []
        prev_summary = _analytic_summary(prev_rows)

        # Revenue Contribution % — each row's share of the total revenue
        # across the currently-visible cost centres. Recomputed AFTER the
        # search filter so the denominator reflects what the user sees.
        total_revenue_visible = sum((r.get('revenue') or 0) for r in rows)
        for r in rows:
            rev = r.get('revenue') or 0
            if rev > 0 and total_revenue_visible > 0:
                pct = (rev / total_revenue_visible) * 100.0
                r['revenue_contribution_pct']     = pct
                r['revenue_contribution_display'] = '%.1f%%' % pct
            else:
                r['revenue_contribution_pct']     = 0.0
                r['revenue_contribution_display'] = '—'

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
        ctx['total_revenue_visible'] = total_revenue_visible
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

        # All analytic accounts (company-scoped) for the Cost Center P&L
        # dropdown. Cheap call — typically a few dozen rows. Include
        # archived ones so historical P&Ls still work.
        acc_fields_set = c.get_model_fields('account.analytic.account')
        cc_company_dom = []
        company_id_ctx = c.context.get('company_id') or 0
        if company_id_ctx and 'company_id' in acc_fields_set:
            cc_company_dom = [['company_id', 'in',
                               [int(company_id_ctx), False]]]
        archived_dom = ([['active', 'in', [True, False]]]
                        if 'active' in acc_fields_set else [])
        try:
            cc_list = c.safe_search_read(
                'account.analytic.account',
                archived_dom + cc_company_dom,
                ['id', 'name', 'display_name', 'code'],
                order='name asc') or []
        except Exception:
            cc_list = []
        ctx['all_analytic_accounts'] = [
            {
                'id':   r.get('id'),
                'name': (r.get('display_name') if r.get('display_name')
                         and r.get('display_name') is not False
                         else r.get('name') or '#%s' % r.get('id')),
                'code': (r.get('code') if r.get('code')
                         and r.get('code') is not False else ''),
            }
            for r in cc_list if r.get('id')
        ]

    return render_template('financial.html', **ctx)


@app.route('/financial/kpi-stats')
@login_required
def financial_kpi_stats():
    """JSON endpoint feeding the Overview Period KPI selector. Returns the
    four headline KPI cards + comparison values for the requested range,
    independent of every other filter on the page."""
    tab = request.args.get('tab', 'invoices')
    if tab not in ('invoices', 'bills'):
        return jsonify({'error': 'invalid tab'}), 400
    move_type = 'out_invoice' if tab == 'invoices' else 'in_invoice'

    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    if range_key not in DATE_RANGE_KEYS:
        range_key = 'ytd'
    raw_from = request.args.get('date_from', '')
    raw_to   = request.args.get('date_to', '')
    date_from, date_to, range_key = _resolve_date_range(
        range_key, raw_from, raw_to)
    compare_yoy = request.args.get('compare_yoy') == '1'

    c = get_client()
    payload = _compute_kpi(c, move_type, date_from, date_to, range_key, compare_yoy)
    payload['range_key']    = range_key
    payload['date_from']    = date_from
    payload['date_to']      = date_to
    payload['period_label'] = _format_period_label(range_key, date_from, date_to)
    payload['compare_yoy']  = compare_yoy
    return jsonify(payload)


def _compute_analytic_kpi_payload(client, date_from, date_to, range_key,
                                  compare_yoy, account_view='all'):
    """Build the Analytic Overview Period KPI payload.

    Mirrors _compute_kpi for the Invoices/Bills tabs: returns the four
    headline metrics (Cost Centers, Revenue, Costs, Net P/L) for the
    requested range, plus a year-over-year comparison when compare_yoy
    is on. Both the current and previous windows honour the Account View
    filter so cards stay consistent with the rest of the analytic page."""
    rows = _compute_analytic(
        client, date_from, date_to, account_view=account_view)
    summary = _analytic_summary(rows)

    payload = {
        'stats':         summary,
        'range_key':     range_key,
        'date_from':     date_from,
        'date_to':       date_to,
        'period_label':  _format_period_label(range_key, date_from, date_to),
        'compare_yoy':   bool(compare_yoy),
        'compare_pct':   {},
    }
    if compare_yoy and date_from and date_to:
        prev_from, prev_to, prev_label = _previous_date_range(
            range_key, date_from, date_to, year_over_year=True)
        if prev_from and prev_to:
            try:
                prev_rows = _compute_analytic(
                    client, prev_from, prev_to, account_view=account_view)
            except Exception:
                prev_rows = []
            prev_summary = _analytic_summary(prev_rows)
            payload['compare_stats'] = prev_summary
            payload['compare_pct'] = {
                'count':   _pct_change(summary['count'],   prev_summary['count']),
                'revenue': _pct_change(summary['revenue'], prev_summary['revenue']),
                'costs':   _pct_change(summary['costs'],   prev_summary['costs']),
                'net':     _pct_change(summary['net'],     prev_summary['net']),
            }
            payload['compare_label'] = 'vs %s' % prev_label
            payload['compare_from']  = prev_from
            payload['compare_to']    = prev_to
    return payload


@app.route('/financial/analytic/kpi-stats')
@login_required
def financial_analytic_kpi_stats():
    """JSON endpoint for the Analytic tab's Overview Period selector.
    Independent of the main Search/Period filter — the analytic page's
    KPI cards respond only to this endpoint's range."""
    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    if range_key not in DATE_RANGE_KEYS:
        range_key = 'ytd'
    raw_from = request.args.get('date_from', '')
    raw_to   = request.args.get('date_to', '')
    date_from, date_to, range_key = _resolve_date_range(
        range_key, raw_from, raw_to)
    compare_yoy = request.args.get('compare_yoy') == '1'

    c = get_client()
    account_view = _current_account_view()
    payload = _compute_analytic_kpi_payload(
        c, date_from, date_to, range_key, compare_yoy,
        account_view=account_view)
    payload['account_view']       = account_view
    payload['account_view_label'] = ACCOUNT_VIEW_LABELS[account_view]
    return jsonify(payload)


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
    account_view = _current_account_view()
    try:
        rows = _compute_analytic(c, date_from, date_to,
                                 account_view=account_view)
    except Exception:
        rows = []
    summary = _analytic_summary(rows)
    return jsonify({
        'range_key':    range_key,
        'date_from':    date_from,
        'date_to':      date_to,
        'period_label': _format_period_label(range_key, date_from, date_to),
        'account_view':       account_view,
        'account_view_label': ACCOUNT_VIEW_LABELS[account_view],
        'rows':         rows,
        'summary':      summary,
    })


@app.route('/api/analytic/debug')
@login_required
def api_analytic_debug():
    """Dump raw Odoo records so we can see the exact field shape. Returns
    the resolved analytic-line field, the first 3 raw lines (with both
    account_id AND auto_account_id when present), the first 3 accounts,
    and read_group results for whichever line-account fields exist —
    so we can compare which one actually holds the data on this server."""
    c = get_client()
    try:
        line_fields_set = c.get_model_fields('account.analytic.line')
    except Exception as e:
        line_fields_set = set()
        line_fields_err = str(e)
    else:
        line_fields_err = None

    has_account_id      = 'account_id' in line_fields_set
    has_auto_account_id = 'auto_account_id' in line_fields_set

    # Resolution the dashboard uses (prefer auto_account_id when present)
    if has_auto_account_id:
        resolved_field = 'auto_account_id'
    elif has_account_id:
        resolved_field = 'account_id'
    else:
        resolved_field = None
    plan_field = c.pick_field('account.analytic.account', 'plan_id')

    # Surface every line-field whose name mentions 'account' so we can spot
    # variants like analytic_account_id on customised installs.
    account_like_fields = sorted(
        f for f in line_fields_set if 'account' in f.lower())

    # Analytic Plans path: detect the JSON distribution field + any
    # plan-specific m2o columns (x_plan*_id / plan*_id).
    has_distribution = 'analytic_distribution' in line_fields_set
    plan_account_fields = sorted(
        f for f in line_fields_set
        if (f.startswith('x_plan') or f.startswith('plan'))
           and f.endswith('_id')
           and f not in ('account_id', 'auto_account_id')
    )

    # Sample 3 raw lines pulling both candidate fields. Pulling a missing
    # field would error — only request the ones that exist.
    line_sample_fields = ['id', 'amount', 'date', 'name']
    if has_account_id:      line_sample_fields.append('account_id')
    if has_auto_account_id: line_sample_fields.append('auto_account_id')
    try:
        sample_lines = c.safe_search_read(
            'account.analytic.line', [], line_sample_fields, limit=3) or []
    except Exception as e:
        sample_lines = [{'error': str(e)}]

    # First 5 accounts (active + archived) so we can verify search_read
    # against account.analytic.account actually returns data.
    acc_fields = ['id', 'name', 'display_name', 'code', 'active']
    if plan_field:
        acc_fields.append(plan_field)
    try:
        sample_accounts = c.safe_search_read(
            'account.analytic.account',
            [['active', 'in', [True, False]]],
            acc_fields, limit=5) or []
        if not sample_accounts:
            sample_accounts = c.safe_search_read(
                'account.analytic.account', [], acc_fields, limit=5) or []
    except Exception as e:
        sample_accounts = [{'error': str(e)}]

    # Count accounts the dashboard can see (mirrors the index used by
    # _compute_analytic). If this is 0, names will all be "Unassigned".
    try:
        account_count = c.safe_count(
            'account.analytic.account',
            [['active', 'in', [True, False]]])
    except Exception:
        account_count = -1

    # read_group with both candidates so we can compare which one has
    # non-False keys.
    def _try_group(field):
        if field not in line_fields_set:
            return {'skipped': 'field not on model'}
        try:
            rows = c.safe_read_group(
                'account.analytic.line', [], ['amount:sum'], [field]) or []
            return rows[:5]
        except Exception as e:
            return [{'error': str(e)}]

    # ---- Multi-company diagnostics ----
    selected_company_id = session.get('company_id') or 0
    company_dom = _analytic_line_company_dom(c, line_fields_set, selected_company_id)
    # Lines visible to this user *without* any company filter (uses only
    # the context that OdooClient already injects). If this is >0 but the
    # filtered count is 0, the company_dom path is wrong.
    try:
        count_no_filter = c.safe_count('account.analytic.line', [])
    except Exception:
        count_no_filter = -1
    try:
        count_with_filter = c.safe_count('account.analytic.line', company_dom)
    except Exception:
        count_with_filter = -1

    # Pull ALL fields for first 3 records so we can spot a non-standard
    # company linkage (move_line_id, project_id, etc.). Use read() after
    # search() so we don't have to enumerate the field list.
    try:
        ids = c.execute_kw('account.analytic.line', 'search',
                           [[]], {'limit': 3})
        sample_lines_full = c.execute_kw(
            'account.analytic.line', 'read', [ids]) if ids else []
    except Exception as e:
        sample_lines_full = [{'error': str(e)}]

    logger.info(
        "Analytic /api/analytic/debug: company_id=%s "
        "lines_total=%s lines_with_filter=%s company_dom=%s sample=%s",
        selected_company_id, count_no_filter, count_with_filter,
        company_dom, sample_lines_full[:1])

    return jsonify({
        'odoo_version':              getattr(c, 'version_string', None),
        'odoo_version_major':        getattr(c, 'version_major', None),
        'edition':                   session.get('odoo_edition'),
        'selected_company_id':       selected_company_id,
        'client_context':            dict(c.context),
        'resolved_line_field':       resolved_field,
        'has_account_id':            has_account_id,
        'has_auto_account_id':       has_auto_account_id,
        'plan_field':                plan_field,
        'account_like_line_fields':  account_like_fields,
        'analytic_line_field_count': len(line_fields_set),
        'analytic_line_fields_err':  line_fields_err,
        'has_analytic_distribution': has_distribution,
        'plan_account_fields':       plan_account_fields,
        'sample_lines':              sample_lines,
        'sample_lines_full':         sample_lines_full,
        'sample_accounts':           sample_accounts,
        'account_count_visible':     account_count,
        'group_by_account_id':       _try_group('account_id'),
        'group_by_auto_account_id':  _try_group('auto_account_id'),
        'company_dom':               company_dom,
        'line_count_no_filter':      count_no_filter,
        'line_count_with_filter':    count_with_filter,
    })


def _resolve_pnl_request_args():
    """Parse + validate the inputs shared by the P&L JSON and export
    endpoints. Returns (account_id:int, range_key, date_from, date_to,
    compare_mode, error_response_or_None)."""
    raw_id = (request.args.get('account_id', '') or '').strip()
    if not raw_id.isdigit():
        return (0, '', '', '', 'none',
                (jsonify({'error': 'account_id required'}), 400))
    account_id = int(raw_id)
    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    raw_from  = request.args.get('date_from', '')
    raw_to    = request.args.get('date_to', '')
    if range_key not in DATE_RANGE_KEYS:
        range_key = 'ytd'
    date_from, date_to, range_key = _resolve_date_range(
        range_key, raw_from, raw_to)
    compare_mode = (request.args.get('compare', 'none') or 'none').lower()
    if compare_mode not in ('none', 'yoy', 'prev'):
        compare_mode = 'none'
    return account_id, range_key, date_from, date_to, compare_mode, None


def _pnl_friendly_date(iso):
    """Render an ISO date string as 'May 16, 2025' for the comparison label."""
    try:
        return date.fromisoformat(iso).strftime('%b %-d, %Y')
    except (ValueError, TypeError):
        try:
            # Windows/Linux without %-d support — fall back to zero-padded.
            return date.fromisoformat(iso).strftime('%b %d, %Y')
        except Exception:
            return iso or ''


def _resolve_pnl_compare_range(compare_mode, range_key, date_from, date_to):
    """Return (prev_from, prev_to, label) for the chosen comparison.

    compare_mode:
      'none' → ('', '', '')
      'yoy'  → same window shifted back one year (Same Period Last Year)
      'prev' → the same-duration window immediately before the current
               (Jan-May 2026 → Aug-Dec 2025)
    """
    if compare_mode == 'none' or not date_from or not date_to:
        return '', '', ''
    if compare_mode == 'yoy':
        pf, pt, _lbl = _previous_date_range(
            range_key, date_from, date_to, year_over_year=True)
        if not pf or not pt:
            return '', '', ''
        return pf, pt, '%s – %s' % (
            _pnl_friendly_date(pf), _pnl_friendly_date(pt))
    # 'prev' — same-duration immediately preceding window.
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except (ValueError, TypeError):
        return '', '', ''
    duration_days = (dt - df).days + 1  # inclusive
    prev_to = df - timedelta(days=1)
    prev_from = prev_to - timedelta(days=duration_days - 1)
    return (prev_from.isoformat(), prev_to.isoformat(),
            '%s – %s' % (_pnl_friendly_date(prev_from.isoformat()),
                         _pnl_friendly_date(prev_to.isoformat())))


def _pnl_change_strings(cur, prev):
    """Return (change_amount, change_pct, change_pct_display).

    change_pct uses |prev| as denominator so a swing from -100 to +100 is
    +200% rather than -200%. Falls back to '—' when prev is 0 (division
    is undefined; the line is "new").
    """
    cur = cur or 0
    prev = prev or 0
    diff = cur - prev
    if prev:
        pct = (diff / abs(prev)) * 100.0
        return diff, pct, '%+.1f%%' % pct
    # No previous baseline — emerging or one-shot line. Keep change in
    # SAR (still meaningful) but blank the pct.
    return diff, None, '—'


def _stitch_pnl_comparison(current_pnl, previous_pnl):
    """Mutate `current_pnl` in place to add previous_amount + change +
    change_pct at line, sub-group, section, and net levels.

    For accounts that existed in the previous window but not the current
    one, we inject zero-current rows so the comparison surfaces the
    decline rather than silently dropping the account.
    """
    # ---- 1. Augment current line lists with previous-only accounts.
    def _index_lines(lines):
        return {ln.get('id'): ln for ln in (lines or []) if ln.get('id')}

    def _augment(section_key, current_pnl, prev_pnl):
        cur_lines = current_pnl.get(section_key) or []
        cur_ids = {ln.get('id') for ln in cur_lines}
        for prev in prev_pnl.get(section_key) or []:
            pid = prev.get('id')
            if pid and pid not in cur_ids:
                cur_lines.append({
                    'id':            pid,
                    'name':          prev.get('name'),
                    'code':          prev.get('code'),
                    'type':          prev.get('type'),
                    'amount':        0.0,
                    'pct':           0.0,
                    'pct_display':   '—',
                })
        current_pnl[section_key] = cur_lines

    _augment('revenue_lines', current_pnl, previous_pnl)
    _augment('expense_lines', current_pnl, previous_pnl)
    _augment('other_lines',   current_pnl, previous_pnl)

    # Rebuild groups so newly-injected zero rows land in the right
    # sub-bucket. Totals are unchanged (added rows are 0).
    current_pnl['revenue_groups'] = _build_section_groups(
        current_pnl['revenue_lines'], PNL_REVENUE_SUBTYPES,
        current_pnl.get('total_revenue') or 0)
    current_pnl['expense_groups'] = _build_section_groups(
        current_pnl['expense_lines'], PNL_EXPENSE_SUBTYPES,
        current_pnl.get('total_expenses') or 0)

    # ---- 2. Annotate every line with previous_amount + change.
    def _annotate_lines(cur_lines, prev_index):
        for ln in cur_lines:
            prev_amt = (prev_index.get(ln.get('id')) or {}).get('amount') or 0
            d, p, s = _pnl_change_strings(ln.get('amount') or 0, prev_amt)
            ln['previous_amount']     = prev_amt
            ln['change']              = d
            ln['change_pct']          = p
            ln['change_pct_display']  = s

    _annotate_lines(current_pnl['revenue_lines'],
                    _index_lines(previous_pnl.get('revenue_lines')))
    _annotate_lines(current_pnl['expense_lines'],
                    _index_lines(previous_pnl.get('expense_lines')))
    _annotate_lines(current_pnl['other_lines'],
                    _index_lines(previous_pnl.get('other_lines')))

    # ---- 3. Annotate each sub-group's subtotal.
    def _group_index(groups):
        return {(g.get('label') or ''): (g.get('subtotal') or 0)
                for g in (groups or [])}

    def _annotate_groups(cur_groups, prev_subtotals):
        for g in cur_groups:
            prev = prev_subtotals.get(g.get('label') or '', 0)
            d, p, s = _pnl_change_strings(g.get('subtotal') or 0, prev)
            g['previous_subtotal']    = prev
            g['change']               = d
            g['change_pct']           = p
            g['change_pct_display']   = s

    _annotate_groups(current_pnl.get('revenue_groups') or [],
                     _group_index(previous_pnl.get('revenue_groups')))
    _annotate_groups(current_pnl.get('expense_groups') or [],
                     _group_index(previous_pnl.get('expense_groups')))

    # ---- 4. Section totals + Net.
    def _set_change(prefix, cur_total, prev_total):
        d, p, s = _pnl_change_strings(cur_total, prev_total)
        current_pnl['previous_' + prefix] = prev_total
        current_pnl[prefix + '_change']             = d
        current_pnl[prefix + '_change_pct']         = p
        current_pnl[prefix + '_change_pct_display'] = s

    _set_change('total_revenue',  current_pnl.get('total_revenue'),
                                  previous_pnl.get('total_revenue'))
    _set_change('total_expenses', current_pnl.get('total_expenses'),
                                  previous_pnl.get('total_expenses'))
    _set_change('total_other',    current_pnl.get('total_other'),
                                  previous_pnl.get('total_other'))
    _set_change('net',            current_pnl.get('net'),
                                  previous_pnl.get('net'))


def _compute_cost_center_pnl_with_compare(client, account_id, range_key,
                                          date_from, date_to, compare_mode,
                                          account_view='all'):
    """Compute the P&L for one cost center, optionally stitched against
    a Same-Period-Last-Year or Previous-Period window. The Account View
    filter is applied to both windows so the comparison is apples-to-
    apples."""
    pnl = _compute_cost_center_pnl(
        client, account_id, date_from, date_to, account_view=account_view)
    pnl['compare_mode']  = 'none'
    pnl['compare_label'] = ''

    if compare_mode in ('yoy', 'prev'):
        prev_from, prev_to, label = _resolve_pnl_compare_range(
            compare_mode, range_key, date_from, date_to)
        if prev_from and prev_to:
            prev_pnl = _compute_cost_center_pnl(
                client, account_id, prev_from, prev_to,
                account_view=account_view)
            _stitch_pnl_comparison(pnl, prev_pnl)
            pnl['compare_mode']  = compare_mode
            pnl['compare_label'] = label
            pnl['compare_from']  = prev_from
            pnl['compare_to']    = prev_to
    return pnl


# ---------------------------------------------------------------------------
# Budget vs Actual (Odoo Budget module)
# ---------------------------------------------------------------------------

BUDGET_MODULES = ('account_budget', 'om_account_budget')
BUDGET_MODEL   = 'crossovered.budget.lines'


def _budget_available(client):
    """Return True iff Odoo's budget module is installed and the line
    model is readable for this user."""
    installed = set(session.get('installed_modules') or [])
    if not any(m in installed for m in BUDGET_MODULES):
        # Cached module list may be stale on long sessions — fall back to
        # a live model probe so a freshly-installed module lights up
        # without a logout.
        try:
            fields = client.get_model_fields(BUDGET_MODEL)
        except Exception:
            fields = set()
        return bool(fields)
    try:
        return bool(client.get_model_fields(BUDGET_MODEL))
    except Exception:
        return False


def _empty_budget_payload():
    return {
        'available':       True,
        'lines':           [],
        'total_budget':    0.0,
        'total_actual':    0.0,
        'total_variance':  0.0,
        'achievement_pct': 0.0,
    }


def _classify_budget_post_revenue(client, post_ids):
    """For each account.budget.post id, return True if it tracks
    revenue-side accounts (income / income_other), False otherwise.

    We look at the linked account_ids and pick the section by majority;
    when there's no clear signal, fall back to False (treat as expense
    budget — by far the more common shape in practice)."""
    if not post_ids:
        return {}
    try:
        posts = client.execute_kw(
            'account.budget.post', 'read',
            [list(set(post_ids))],
            {'fields': ['id', 'name', 'account_ids']}) or []
    except Exception as e:
        logger.info("Budget: account.budget.post read failed: %s", e)
        return {pid: False for pid in post_ids}

    all_account_ids = set()
    for p in posts:
        for a in (p.get('account_ids') or []):
            all_account_ids.add(a)
    account_types = (_classify_gl_accounts(client, all_account_ids)
                     if all_account_ids else {})

    out = {}
    for p in posts:
        pid = p.get('id')
        if not pid:
            continue
        n_rev = n_exp = 0
        for a in (p.get('account_ids') or []):
            t = (account_types.get(a, {}).get('type') or '').lower()
            if t in PNL_REVENUE_TYPES:
                n_rev += 1
            elif t in PNL_EXPENSE_TYPES:
                n_exp += 1
        is_revenue = n_rev > 0 and n_rev >= n_exp
        out[pid] = is_revenue
    return out


def _compute_budget_vs_actual(client, account_id, date_from, date_to):
    """Read crossovered.budget.lines for one analytic account inside the
    date window. Each line carries:
      • name (from the budget post or the parent crossovered.budget)
      • budget (planned_amount)
      • actual (practical_amount)
      • variance = budget - actual
      • variance_pct = variance / budget * 100   (0 when budget = 0)
      • is_revenue  (per the post's linked GL accounts)
      • status: 'on_track' | 'over' | 'under_utilized'

    Lines whose date range overlaps the requested window are included.
    """
    aid = int(account_id)
    line_fields = client.get_model_fields(BUDGET_MODEL)
    if not line_fields:
        return _empty_budget_payload()

    has_planned       = 'planned_amount'       in line_fields
    has_practical     = 'practical_amount'     in line_fields
    has_general_post  = 'general_budget_id'    in line_fields
    has_crossovered   = 'crossovered_budget_id' in line_fields
    has_analytic      = 'analytic_account_id'  in line_fields
    has_dfrom         = 'date_from'            in line_fields
    has_dto           = 'date_to'              in line_fields

    if not (has_analytic and has_planned):
        logger.info(
            "Budget: model %s missing analytic_account_id/planned_amount "
            "(found fields: %d) — treating as unavailable", BUDGET_MODEL,
            len(line_fields))
        return _empty_budget_payload()

    domain = [['analytic_account_id', '=', aid]]
    # Include any budget line whose own range overlaps the requested
    # window. Standard interval-overlap test.
    if date_from and has_dto:
        domain.append(['date_to',   '>=', date_from])
    if date_to and has_dfrom:
        domain.append(['date_from', '<=', date_to])
    if 'company_id' in line_fields:
        cid = client.context.get('company_id') or 0
        if cid:
            domain.append(['company_id', 'in', [int(cid), False]])

    read_fields = ['id', 'analytic_account_id']
    if has_planned:      read_fields.append('planned_amount')
    if has_practical:    read_fields.append('practical_amount')
    if has_general_post: read_fields.append('general_budget_id')
    if has_crossovered:  read_fields.append('crossovered_budget_id')
    if has_dfrom:        read_fields.append('date_from')
    if has_dto:          read_fields.append('date_to')

    try:
        rows = client.safe_search_read(
            BUDGET_MODEL, domain, read_fields,
            order='date_from asc' if has_dfrom else None) or []
    except Exception as e:
        logger.warning("Budget: search failed for analytic_account=%s: %s",
                       aid, e)
        return _empty_budget_payload()

    post_ids = []
    for r in rows:
        gb = r.get('general_budget_id')
        if isinstance(gb, list) and gb:
            post_ids.append(gb[0])
    is_revenue_by_post = _classify_budget_post_revenue(client, post_ids)

    out_lines = []
    total_budget = 0.0
    total_actual = 0.0
    for r in rows:
        budget = float(r.get('planned_amount')   or 0)
        actual = float(r.get('practical_amount') or 0)
        gb = r.get('general_budget_id')
        post_id = gb[0] if (isinstance(gb, list) and gb
                            and not isinstance(gb[0], bool)) else None
        is_revenue = bool(is_revenue_by_post.get(post_id, False))

        # Display name: prefer the post name, fall back to crossovered
        # budget name, finally "Budget #id".
        name = ''
        if isinstance(gb, list) and len(gb) > 1 and gb[1] and gb[1] is not False:
            name = gb[1]
        if not name:
            cb = r.get('crossovered_budget_id')
            if isinstance(cb, list) and len(cb) > 1 and cb[1] and cb[1] is not False:
                name = cb[1]
        if not name:
            name = 'Budget #%s' % r.get('id')

        variance     = budget - actual
        variance_pct = (variance / abs(budget) * 100.0) if budget else 0.0

        if budget > 0 and actual > budget:
            status = 'over'
        elif budget > 0 and actual < 0.5 * budget:
            status = 'under_utilized'
        else:
            status = 'on_track'

        out_lines.append({
            'id':            r.get('id'),
            'name':          name,
            'budget':        budget,
            'actual':        actual,
            'variance':      variance,
            'variance_pct':  variance_pct,
            'status':        status,
            'is_revenue':    is_revenue,
            'date_from':     r.get('date_from') if has_dfrom else None,
            'date_to':       r.get('date_to')   if has_dto   else None,
        })
        total_budget += budget
        total_actual += actual

    total_variance  = total_budget - total_actual
    achievement_pct = ((total_actual / total_budget) * 100.0
                       if total_budget else 0.0)

    out_lines.sort(key=lambda L: abs(L['variance']), reverse=True)

    logger.info(
        "Budget vs Actual: aid=%s rows=%d budget=%.2f actual=%.2f "
        "variance=%.2f achievement=%.1f%%",
        aid, len(out_lines), total_budget, total_actual,
        total_variance, achievement_pct)

    return {
        'available':       True,
        'lines':           out_lines,
        'total_budget':    total_budget,
        'total_actual':    total_actual,
        'total_variance':  total_variance,
        'achievement_pct': achievement_pct,
    }


def _resolve_cost_center_name(client, account_id):
    """Return a display label for one analytic account: '[CODE] Name'."""
    accs = client.safe_search_read(
        'account.analytic.account', [['id', '=', int(account_id)]],
        ['id', 'name', 'display_name', 'code']) or []
    if not accs:
        return '#%s' % account_id
    a = accs[0]
    dn = a.get('display_name')
    nm = a.get('name')
    label = (dn if dn and dn is not False
             else (nm if nm and nm is not False else '#%s' % account_id))
    code = a.get('code')
    if code and code is not False:
        return '[%s] %s' % (code, label)
    return label


@app.route('/financial/cost-center-pnl')
@login_required
def financial_cost_center_pnl():
    """JSON endpoint for the Cost Center P&L Statement panel. Computes
    revenue / expenses grouped by general_account_id (the accounting
    account) for one analytic account over a period.

    Optional `compare=yoy|prev` runs a second pass for Same-Period-Last-
    Year or Previous-Period and stitches the result so each line carries
    previous_amount + change + change_pct."""
    (account_id, range_key, date_from, date_to, compare_mode,
     err) = _resolve_pnl_request_args()
    if err:
        return err

    c = get_client()
    account_view = _current_account_view()
    try:
        pnl = _compute_cost_center_pnl_with_compare(
            c, account_id, range_key, date_from, date_to, compare_mode,
            account_view=account_view)
    except Exception as e:
        logger.exception("Cost-center P&L failed for account_id=%s", account_id)
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'account_id':       account_id,
        'cost_center_name': _resolve_cost_center_name(c, account_id),
        'range_key':        range_key,
        'date_from':        date_from,
        'date_to':          date_to,
        'period_label':     _format_period_label(range_key, date_from, date_to),
        'account_view':       account_view,
        'account_view_label': ACCOUNT_VIEW_LABELS[account_view],
        **pnl,
    })


@app.route('/financial/cost-center-pnl/export/<fmt>')
@login_required
def export_cost_center_pnl(fmt):
    """PDF or Excel export of the Cost Center P&L Statement."""
    if fmt not in ('pdf', 'excel'):
        flash('Invalid export format.', 'danger')
        return redirect(url_for('financial', tab='analytic'))

    (account_id, range_key, date_from, date_to, compare_mode,
     err) = _resolve_pnl_request_args()
    if err:
        # err is a (response, status) tuple from _resolve_pnl_request_args
        return err

    c = get_client()
    account_view = _current_account_view()
    try:
        pnl = _compute_cost_center_pnl_with_compare(
            c, account_id, range_key, date_from, date_to, compare_mode,
            account_view=account_view)
    except Exception as e:
        logger.exception("Cost-center P&L export failed for account_id=%s", account_id)
        flash('Could not generate P&L: %s' % e, 'danger')
        return redirect(url_for('financial', tab='analytic'))

    cc_name      = _resolve_cost_center_name(c, account_id)
    period_label = _format_period_label(range_key, date_from, date_to)
    company_name = _pnl_company_or_none(c)
    currency     = _pnl_currency_or_blank(c)
    unit         = (request.args.get('unit', 'units') or 'units').lower()
    if unit not in ('units', 'k', 'm'):
        unit = 'units'

    from exporters import export_pnl_pdf, export_pnl_excel
    if fmt == 'pdf':
        buf = export_pnl_pdf(
            company_name=company_name,
            cost_center_name=cc_name,
            period_label=period_label,
            currency=currency,
            pnl=pnl,
            unit=unit,
        )
        return send_file(buf, mimetype='application/pdf',
                         download_name='cost_center_pnl.pdf', as_attachment=True)
    else:
        buf = export_pnl_excel(
            company_name=company_name,
            cost_center_name=cc_name,
            period_label=period_label,
            currency=currency,
            pnl=pnl,
            unit=unit,
        )
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name='cost_center_pnl.xlsx', as_attachment=True,
        )


@app.route('/financial/budget-vs-actual')
@login_required
def financial_budget_vs_actual():
    """JSON endpoint for the Budget vs Actual section. Returns
    {'available': False, 'reason': '...'} when the module isn't
    installed (or the model isn't readable) so the front-end can
    render a helpful empty state without an error."""
    raw_id = (request.args.get('account_id', '') or '').strip()
    if not raw_id.isdigit():
        return jsonify({'error': 'account_id required'}), 400
    account_id = int(raw_id)
    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    if range_key not in DATE_RANGE_KEYS:
        range_key = 'ytd'
    raw_from = request.args.get('date_from', '')
    raw_to   = request.args.get('date_to', '')
    date_from, date_to, range_key = _resolve_date_range(
        range_key, raw_from, raw_to)

    c = get_client()
    if not _budget_available(c):
        return jsonify({
            'available':    False,
            'reason':       'Budget module not installed',
            'period_label': _format_period_label(range_key, date_from, date_to),
        })

    try:
        payload = _compute_budget_vs_actual(c, account_id, date_from, date_to)
    except Exception as e:
        logger.exception("Budget vs Actual failed for account_id=%s", account_id)
        return jsonify({'error': str(e)}), 500

    payload['range_key']        = range_key
    payload['date_from']        = date_from
    payload['date_to']          = date_to
    payload['period_label']     = _format_period_label(range_key, date_from, date_to)
    payload['cost_center_name'] = _resolve_cost_center_name(c, account_id)
    payload['account_id']       = account_id
    return jsonify(payload)


@app.route('/financial/budget-vs-actual/export/<fmt>')
@login_required
def export_budget_vs_actual(fmt):
    """PDF or Excel of the Budget vs Actual table."""
    if fmt not in ('pdf', 'excel'):
        flash('Invalid export format.', 'danger')
        return redirect(url_for('financial', tab='analytic'))
    raw_id = (request.args.get('account_id', '') or '').strip()
    if not raw_id.isdigit():
        flash('A cost center is required.', 'danger')
        return redirect(url_for('financial', tab='analytic'))
    account_id = int(raw_id)
    range_key = (request.args.get('range', 'ytd') or 'ytd').strip()
    if range_key not in DATE_RANGE_KEYS:
        range_key = 'ytd'
    raw_from = request.args.get('date_from', '')
    raw_to   = request.args.get('date_to', '')
    date_from, date_to, range_key = _resolve_date_range(
        range_key, raw_from, raw_to)
    unit = (request.args.get('unit', 'units') or 'units').lower()
    if unit not in ('units', 'k', 'm'):
        unit = 'units'

    c = get_client()
    if not _budget_available(c):
        flash('Budget module is not installed on this Odoo instance.', 'warning')
        return redirect(url_for('financial', tab='analytic'))

    try:
        payload = _compute_budget_vs_actual(c, account_id, date_from, date_to)
    except Exception as e:
        logger.exception("Budget vs Actual export failed for account_id=%s", account_id)
        flash('Could not generate Budget vs Actual: %s' % e, 'danger')
        return redirect(url_for('financial', tab='analytic'))

    cc_name      = _resolve_cost_center_name(c, account_id)
    period_label = _format_period_label(range_key, date_from, date_to)
    company_name = _pnl_company_or_none(c)
    currency     = _pnl_currency_or_blank(c)

    from exporters import export_budget_pdf, export_budget_excel
    if fmt == 'pdf':
        buf = export_budget_pdf(
            company_name=company_name,
            cost_center_name=cc_name,
            period_label=period_label,
            currency=currency,
            payload=payload,
            unit=unit,
        )
        return send_file(buf, mimetype='application/pdf',
                         download_name='budget_vs_actual.pdf', as_attachment=True)
    else:
        buf = export_budget_excel(
            company_name=company_name,
            cost_center_name=cc_name,
            period_label=period_label,
            currency=currency,
            payload=payload,
            unit=unit,
        )
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name='budget_vs_actual.xlsx', as_attachment=True,
        )


def _pnl_company_or_none(client):
    cid = client.context.get('company_id') or 0
    if not cid:
        return ''
    try:
        rows = client.safe_search_read(
            'res.company', [['id', '=', int(cid)]],
            ['id', 'name']) or []
        if rows:
            return rows[0].get('name') or ''
    except Exception:
        pass
    return ''


def _pnl_currency_or_blank(client):
    cid = client.context.get('company_id') or 0
    if not cid:
        return ''
    try:
        rows = client.safe_search_read(
            'res.company', [['id', '=', int(cid)]],
            ['currency_id']) or []
        if rows and isinstance(rows[0].get('currency_id'), list):
            cur_id = rows[0]['currency_id'][0]
            cur_rows = client.safe_search_read(
                'res.currency', [['id', '=', cur_id]],
                ['name', 'symbol']) or []
            if cur_rows:
                return cur_rows[0].get('name') or cur_rows[0].get('symbol') or ''
    except Exception:
        pass
    return ''


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
            rows_a = _compute_analytic(
                c, date_from_a, date_to_a,
                account_view=_current_account_view())
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
