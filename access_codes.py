"""Access-code store backed by `access_codes.json`.

Each code maps to a client record: stored Odoo credentials (or `mode:
"demo"` for mock data), the modules it may open, an expiry date, and a
read-only flag. The file is re-read on every lookup so edits made in the
admin panel apply to new logins and to sessions already in progress.
"""
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import date

ACCESS_CODES_PATH = os.environ.get(
    'ACCESS_CODES_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'access_codes.json'),
)

# (key, label, sidebar section). Keys are what `modules` in the JSON holds.
ACCESS_MODULES = [
    ('invoices',             'Invoices',             'Finance'),
    ('bills',                'Bills',                'Finance'),
    ('banks',                'Banks',                'Finance'),
    ('assets',               'Assets',               'Finance'),
    ('expenses',             'Expenses',             'Finance'),
    ('analytic',             'Analytic',             'Finance'),
    ('financial-statements', 'Financial Statements', 'Finance'),
    ('stock',                'Stock',                'Inventory'),
    ('movements',            'Movements',            'Inventory'),
    ('valuation',            'Valuation',            'Inventory'),
    ('sales',                'Sales',                'Sales'),
    ('hr',                   'Human Resources',      'Human Resources'),
    ('manufacturing',        'Manufacturing',        'Manufacturing'),
]
ACCESS_MODULE_KEYS = [m[0] for m in ACCESS_MODULES]
FINANCE_MODULES = {m[0] for m in ACCESS_MODULES if m[2] == 'Finance'}
INVENTORY_MODULES = {m[0] for m in ACCESS_MODULES if m[2] == 'Inventory'}

EXPIRING_SOON_DAYS = 7
CODE_RE = re.compile(r'^[A-Z0-9_-]{4,32}$')
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O/1/I

_write_lock = threading.Lock()


def normalize_code(code):
    return (code or '').strip().upper()


def load_codes():
    try:
        with open(ACCESS_CODES_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_codes(codes):
    """Atomic write so a concurrent reader never sees a half-written file."""
    directory = os.path.dirname(ACCESS_CODES_PATH) or '.'
    with _write_lock:
        fd, tmp = tempfile.mkstemp(dir=directory, prefix='.access_codes.', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump(codes, fh, indent=2, ensure_ascii=False)
                fh.write('\n')
            os.replace(tmp, ACCESS_CODES_PATH)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


def parse_expiry(value):
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def is_expired(entry, today=None):
    """True iff today is past the expiry date. A missing expiry never expires;
    an unparseable one is treated as expired so a typo can't grant access."""
    raw = entry.get('expiry')
    if not raw:
        return False
    exp = parse_expiry(raw)
    return exp is None or (today or date.today()) > exp


def lookup_valid(code):
    """Return the entry for `code` if it is active and not expired, else None."""
    code = normalize_code(code)
    if not code:
        return None
    entry = load_codes().get(code)
    if not isinstance(entry, dict):
        return None
    if not entry.get('active') or is_expired(entry):
        return None
    return entry


def allowed_modules(entry):
    """List of module keys, or None meaning every module is allowed."""
    mods = entry.get('modules') or []
    mods = [m for m in mods if m in ACCESS_MODULE_KEYS]
    return mods or None


def max_sessions(entry):
    """Concurrent sessions allowed for a code (default 1)."""
    try:
        return max(1, int(entry.get('max_sessions') or 1))
    except (TypeError, ValueError):
        return 1


def is_demo_entry(entry):
    return (entry.get('mode') or 'live') == 'demo'


def generate_code(existing=()):
    while True:
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        if code not in existing:
            return code


def code_status(entry, today=None):
    """(status_key, days_left) for the admin table."""
    today = today or date.today()
    exp = parse_expiry(entry.get('expiry'))
    if entry.get('expiry') and exp is None:
        return 'expired', None
    if exp is None:
        return 'active', None
    days_left = (exp - today).days
    if days_left < 0:
        return 'expired', days_left
    if days_left < EXPIRING_SOON_DAYS:
        return 'expiring', days_left
    return 'active', days_left
