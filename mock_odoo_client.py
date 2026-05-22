"""Mock OdooClient for DEMO_MODE.

Drop-in replacement that satisfies the surface of `OdooClient` used by
`app.py`. Records are pulled from `mock_data.build_dataset()` and filtered
through a small domain evaluator that handles Odoo's prefix-notation
domains for the operators the dashboard actually uses (=, !=, in, not in,
<, <=, >, >=, like, ilike, child_of, &, |, !).

Coverage is intentionally pragmatic — enough to make every page render
with realistic data, not a full Odoo emulator.
"""

import calendar
import logging
from collections import defaultdict
from datetime import date, datetime

from odoo_client import OdooClient
from mock_data import (
    build_dataset, installed_modules, model_fields,
    version_info, DOTTED_ALIASES,
    DEMO_COMPANY_ID, DEMO_COMPANY_NAME,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain evaluation
# ---------------------------------------------------------------------------

def _get_field(rec, field, model, dotted_aliases):
    """Resolve a (possibly-dotted) field path on a record.
    Many2one fields are 2-tuples [id, name]; comparisons against the int form
    return the id, against the string form return the name.
    """
    if '.' in field:
        alias = dotted_aliases.get(model, {}).get(field)
        if alias and alias in rec:
            return rec[alias]
        # Try the first segment only (best-effort)
        head = field.split('.')[0]
        return rec.get(head)
    return rec.get(field)


def _coerce_m2o(value, compare_to):
    """If `value` is a many2one tuple [id, name], pick id or name based on
    the type of `compare_to`. Falsy m2o is represented as False in Odoo."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        if isinstance(compare_to, bool):
            return bool(value[0])
        if isinstance(compare_to, str):
            return value[1]
        return value[0]
    return value


def _eval_leaf(rec, leaf, model, dotted_aliases):
    field, op, value = leaf
    actual = _get_field(rec, field, model, dotted_aliases)

    # Compare against either the id or the name of an m2o based on `value` type.
    if op in ('in', 'not in') and isinstance(value, (list, tuple)) and value:
        sample = value[0]
        actual_cmp = _coerce_m2o(actual, sample)
    else:
        actual_cmp = _coerce_m2o(actual, value)

    # Coerce date strings: Odoo dates are 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'.
    # ISO strings sort correctly, so plain string compare works.
    if op == '=':
        return actual_cmp == value
    if op == '!=':
        return actual_cmp != value
    if op == '<':
        return actual_cmp is not None and actual_cmp < value
    if op == '<=':
        return actual_cmp is not None and actual_cmp <= value
    if op == '>':
        return actual_cmp is not None and actual_cmp > value
    if op == '>=':
        return actual_cmp is not None and actual_cmp >= value
    if op == 'in':
        return actual_cmp in (value or [])
    if op == 'not in':
        return actual_cmp not in (value or [])
    if op == 'like':
        return value in (actual_cmp or '')
    if op == 'ilike':
        return (value or '').lower() in (actual_cmp or '').lower()
    if op == '=ilike':
        return (value or '').lower() == (actual_cmp or '').lower()
    if op == 'child_of':
        return actual_cmp == value
    logger.warning("Mock: unsupported domain operator %r", op)
    return True


def _eval_domain(domain, records, model, dotted_aliases):
    """Apply Odoo prefix-notation domain to `records` and return matches."""
    if not domain:
        return list(records)

    # Normalize to a list of tokens.
    tokens = list(domain)
    # Tuples in domain → leaf (field, op, value). Strings → '&', '|', '!'.

    def evaluate(rec, idx):
        """Return (bool_result, next_idx) consuming from `idx`."""
        token = tokens[idx]
        if isinstance(token, str) and token in ('&', '|', '!'):
            if token == '!':
                v, nxt = evaluate(rec, idx + 1)
                return (not v, nxt)
            v1, nxt = evaluate(rec, idx + 1)
            v2, nxt = evaluate(rec, nxt)
            if token == '&':
                return (v1 and v2, nxt)
            return (v1 or v2, nxt)
        # Leaf
        return (_eval_leaf(rec, token, model, dotted_aliases), idx + 1)

    out = []
    for rec in records:
        # Implicit AND across multiple top-level leaves: keep evaluating until
        # tokens exhausted and AND the results.
        idx = 0
        result = True
        while idx < len(tokens):
            v, nxt = evaluate(rec, idx)
            result = result and v
            idx = nxt
            if not result:
                break
        if result:
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# read_group support
# ---------------------------------------------------------------------------

def _month_label(value):
    """Convert an Odoo date string into the 'November 2025' label that
    Odoo's read_group with `:month` groupby returns."""
    if not value:
        return False
    try:
        d = datetime.fromisoformat(value[:10]).date() if len(value) >= 10 else None
    except ValueError:
        return False
    if not d:
        return False
    return d.strftime('%B %Y')


def _bucket_key(rec, groupby_field, model, dotted_aliases):
    """Compute the bucket key for one record given an Odoo groupby spec.
    Supports `field`, `field:month`, `field:day`, `field:year`.
    Returns (display_label, raw_value_for_field)."""
    if ':' in groupby_field:
        field, granularity = groupby_field.split(':', 1)
    else:
        field, granularity = groupby_field, None

    raw = _get_field(rec, field, model, dotted_aliases)

    if granularity == 'month':
        return _month_label(raw), raw
    if granularity == 'year':
        try:
            return raw[:4] if isinstance(raw, str) else False, raw
        except Exception:
            return False, raw
    if granularity == 'day':
        return raw[:10] if isinstance(raw, str) and len(raw) >= 10 else raw, raw

    # Plain field. Many2one returns the tuple as the bucket so callers can read
    # `g['field']` and get [id, name] just like Odoo does.
    return raw, raw


def _read_group(records, domain, fields_spec, groupby, model, dotted_aliases):
    """Lightweight read_group implementation.

    `fields_spec` is a list like ['amount_total:sum', 'payment_state'].
    `groupby` is a list like ['payment_state'] or ['invoice_date:month'].
    Bare field names are treated like grouping fields too (Odoo includes them
    in the output so callers can read them back).
    """
    matched = _eval_domain(domain, records, model, dotted_aliases)

    # Decode fields_spec into (field, aggregator) tuples.
    field_aggs = []
    for spec in (fields_spec or []):
        if ':' in spec:
            f, agg = spec.split(':', 1)
            field_aggs.append((f, agg))
        else:
            field_aggs.append((spec, None))

    # If no groupby: return a single row with totals across `matched`.
    if not groupby:
        row = {'__count': len(matched)}
        for f, agg in field_aggs:
            if agg == 'sum':
                row[f] = sum(_safe_num(r.get(f)) for r in matched)
            elif agg == 'avg':
                vals = [_safe_num(r.get(f)) for r in matched]
                row[f] = (sum(vals) / len(vals)) if vals else 0
            elif agg == 'count':
                row[f] = sum(1 for r in matched if r.get(f) not in (None, False))
            else:
                # No aggregator on a bare field outside groupby — Odoo would
                # complain; we just pick the first value as a sample.
                row[f] = matched[0].get(f) if matched else False
        return [row]

    # Group by the first groupby spec.
    primary = groupby[0]
    buckets = defaultdict(list)
    bucket_label = {}
    for r in matched:
        label, _raw = _bucket_key(r, primary, model, dotted_aliases)
        # Normalize hashable bucket key for m2o tuples.
        key = tuple(label) if isinstance(label, list) else label
        buckets[key].append(r)
        bucket_label[key] = label

    rows = []
    for key, recs in buckets.items():
        row = {'__count': len(recs)}
        # Echo the grouping field back.
        row[primary] = bucket_label[key]
        # Plain field name without the granularity, so callers reading
        # g['invoice_date'] also see something.
        bare = primary.split(':')[0]
        if bare != primary:
            row[bare] = bucket_label[key]
        for f, agg in field_aggs:
            if agg == 'sum':
                row[f] = sum(_safe_num(r.get(f)) for r in recs)
            elif agg == 'avg':
                vals = [_safe_num(r.get(f)) for r in recs]
                row[f] = (sum(vals) / len(vals)) if vals else 0
            elif agg == 'count':
                row[f] = sum(1 for r in recs if r.get(f) not in (None, False))
            else:
                row[f] = recs[0].get(f) if recs else False
        rows.append(row)

    # Sort chronologically for date-bucket grouping; otherwise leave insertion.
    if primary.endswith(':month'):
        rows.sort(key=lambda r: _month_sort_key(r.get(primary)))
    elif primary.endswith(':day') or primary.endswith(':year'):
        rows.sort(key=lambda r: r.get(primary) or '')
    return rows


def _month_sort_key(label):
    if not label:
        return ''
    try:
        return datetime.strptime(label, '%B %Y').isoformat()
    except (ValueError, TypeError):
        return label


def _safe_num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# search_read field projection + ordering
# ---------------------------------------------------------------------------

def _project(rec, fields):
    if not fields:
        return dict(rec)
    out = {'id': rec.get('id')}
    for f in fields:
        if f in rec:
            out[f] = rec[f]
    return out


def _apply_order(records, order):
    if not order:
        return records
    # Order is a comma-separated list like "invoice_date desc, name asc".
    keys = []
    for piece in order.split(','):
        piece = piece.strip()
        if not piece:
            continue
        if ' ' in piece:
            f, direction = piece.rsplit(None, 1)
            keys.append((f, direction.lower() == 'desc'))
        else:
            keys.append((piece, False))

    def sort_key(r):
        parts = []
        for f, _desc in keys:
            v = r.get(f)
            if isinstance(v, (list, tuple)):
                v = v[1] if len(v) >= 2 else v[0]
            # Normalize None/False so comparison doesn't error.
            parts.append((v is None or v is False, v if v not in (None, False) else ''))
        return parts

    # Sort layered for stable order; do reverse passes in order.
    out = list(records)
    for f, desc in reversed(keys):
        out.sort(
            key=lambda r: (
                (lambda v: (v is None or v is False,
                            v if v not in (None, False) else ''))(
                    (lambda x: x[1] if isinstance(x, (list, tuple)) and len(x) >= 2 else x)(
                        r.get(f)
                    )
                )
            ),
            reverse=desc,
        )
    return out


# ---------------------------------------------------------------------------
# Mock client
# ---------------------------------------------------------------------------

class MockOdooClient(OdooClient):
    """A MockOdooClient that satisfies the OdooClient surface used by app.py."""

    def __init__(self, version_major=18, edition='enterprise', company_id=None):
        super().__init__(
            url='https://demo.olens.local',
            db='olens-demo',
            uid=2,
            password='__demo__',
            version_info=version_info(version_major, edition),
            installed_modules=installed_modules(version_major, edition),
        )
        self._demo_version_major = int(version_major or 18)
        self._demo_edition = edition or 'enterprise'
        self._dataset = build_dataset(self._demo_version_major, self._demo_edition)
        if company_id:
            self.set_company(company_id)
        else:
            self.set_company(DEMO_COMPANY_ID)

    # Override version/edition probes — no XML-RPC needed.

    @property
    def version_major(self):
        return self._demo_version_major

    @property
    def version_string(self):
        return f"{self._demo_version_major}.0"

    def detect_edition(self):
        return self._demo_edition

    def fetch_installed_modules(self):
        return set(self._installed_modules or ())

    def get_model_fields(self, model):
        if model in self._field_cache:
            return self._field_cache[model]
        fields = model_fields(model, self._demo_version_major)
        self._field_cache[model] = fields
        return fields

    # ------------------------------------------------------------------
    # Core query interface
    # ------------------------------------------------------------------

    def _records(self, model):
        return self._dataset.get(model, [])

    def search_read(self, model, domain=None, fields=None,
                    limit=None, offset=0, order=None):
        recs = self._records(model)
        recs = _eval_domain(domain or [], recs, model, DOTTED_ALIASES)
        recs = _apply_order(recs, order)
        if offset:
            recs = recs[offset:]
        if limit is not None:
            recs = recs[:limit]
        return [_project(r, fields) for r in recs]

    def search_count(self, model, domain=None):
        recs = self._records(model)
        return len(_eval_domain(domain or [], recs, model, DOTTED_ALIASES))

    def read_group(self, model, domain, fields, groupby,
                   limit=None, orderby=None, lazy=False):
        recs = self._records(model)
        rows = _read_group(recs, domain or [], fields or [], groupby or [],
                           model, DOTTED_ALIASES)
        if limit is not None:
            rows = rows[:limit]
        return rows

    def safe_count(self, model, domain=None):
        try:
            return self.search_count(model, domain)
        except Exception as e:
            logger.warning("Mock safe_count(%s) failed: %s", model, e)
            return 0

    def safe_read_group(self, model, domain, fields, groupby, **kw):
        try:
            return self.read_group(model, domain, fields, groupby, **kw)
        except Exception as e:
            logger.warning("Mock safe_read_group(%s) failed: %s", model, e)
            return []

    def safe_search_read(self, model, domain=None, fields=None,
                          limit=None, offset=0, order=None):
        try:
            return self.search_read(model, domain, fields, limit, offset, order)
        except Exception as e:
            logger.warning("Mock safe_search_read(%s) failed: %s", model, e)
            return []

    def paginated_search_read(self, model, domain=None, fields=None,
                              batch_size=1000, order=None, max_total=None):
        recs = self.search_read(model, domain, fields, limit=max_total, offset=0,
                                order=order)
        return recs

    # ------------------------------------------------------------------
    # execute_kw — used by a handful of routes for read/search directly
    # ------------------------------------------------------------------

    def execute_kw(self, model, method, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or {}
        if method == 'search_read':
            domain = args[0] if args else []
            return self.search_read(
                model, domain,
                fields=kwargs.get('fields'),
                limit=kwargs.get('limit'),
                offset=kwargs.get('offset', 0),
                order=kwargs.get('order'),
            )
        if method == 'search_count':
            domain = args[0] if args else []
            return self.search_count(model, domain)
        if method == 'read_group':
            return self.read_group(
                model,
                args[0] if len(args) > 0 else [],
                args[1] if len(args) > 1 else [],
                args[2] if len(args) > 2 else [],
                limit=kwargs.get('limit'),
                orderby=kwargs.get('orderby'),
                lazy=kwargs.get('lazy', False),
            )
        if method == 'search':
            domain = args[0] if args else []
            recs = _eval_domain(domain, self._records(model), model, DOTTED_ALIASES)
            limit = kwargs.get('limit')
            if limit is not None:
                recs = recs[:limit]
            return [r['id'] for r in recs]
        if method == 'read':
            ids = args[0] if args else []
            fields = kwargs.get('fields')
            id_set = set(ids if isinstance(ids, list) else [ids])
            return [_project(r, fields) for r in self._records(model)
                    if r.get('id') in id_set]
        if method == 'fields_get':
            field_names = self.get_model_fields(model)
            return {f: {'type': 'char', 'string': f} for f in field_names}
        logger.warning("Mock: unhandled execute_kw method %s.%s", model, method)
        return []
