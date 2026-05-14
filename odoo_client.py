import xmlrpc.client
import logging
import socket

logger = logging.getLogger(__name__)


class OdooAuthError(Exception):
    pass


class OdooConnectionError(Exception):
    pass


# Field aliases keyed by a stable internal name.
# The first entry that exists on the model wins; `pick_field` resolves it.
FIELD_ALIASES = {
    'account.move': {
        'move_type':        ['move_type', 'type'],
        'payment_state':    ['payment_state', 'invoice_payment_state'],
        'amount_residual':  ['amount_residual', 'residual'],
        'amount_untaxed':   ['amount_untaxed'],
        'amount_tax':       ['amount_tax'],
        'amount_total':     ['amount_total'],
        'invoice_date':     ['invoice_date', 'date_invoice'],
        'invoice_date_due': ['invoice_date_due', 'date_due'],
    },
    'account.analytic.line': {
        # V17 introduced auto_account_id for multi-plan analytic; the legacy
        # account_id field is still present on most installs.
        'account_id':       ['account_id', 'auto_account_id'],
    },
    'account.analytic.account': {
        'plan_id':          ['plan_id', 'group_id'],
    },
    'hr.attendance': {
        'check_in':         ['check_in'],
        'check_out':        ['check_out'],
        'overtime_hours':   ['overtime_hours'],   # V17+
    },
    'stock.quant': {
        'inventory_date':   ['inventory_date'],            # V17+
        'cyclic_inventory': ['cyclic_inventory_frequency'], # V17+
    },
}


class OdooClient:
    def __init__(self, url: str, db: str, uid: int, password: str,
                 context: dict = None,
                 version_info: dict = None,
                 installed_modules: set = None,
                 field_cache: dict = None):
        self.url = url.rstrip('/')
        self.db = db
        self.uid = uid
        self.password = password
        self.context = dict(context or {})
        self.version_info = dict(version_info) if version_info else {}
        self._installed_modules = (
            set(installed_modules) if installed_modules is not None else None
        )
        self._field_cache = dict(field_cache) if field_cache else {}
        self._object = None

    def set_company(self, company_id: int):
        """Limit subsequent queries to a single company via Odoo's standard context."""
        if company_id:
            self.context['allowed_company_ids'] = [int(company_id)]
            self.context['company_id'] = int(company_id)
        else:
            self.context.pop('allowed_company_ids', None)
            self.context.pop('company_id', None)

    @property
    def _obj(self):
        if self._object is None:
            self._object = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/object',
                allow_none=True
            )
        return self._object

    # ------------------------------------------------------------------
    # Version detection
    # ------------------------------------------------------------------

    @property
    def version_major(self) -> int:
        info = (self.version_info or {}).get('server_version_info') or []
        if info:
            try:
                return int(info[0])
            except (TypeError, ValueError):
                pass
        ver = (self.version_info or {}).get('server_version', '')
        head = str(ver).split('.')[0].split('+')[0].split('~')[0]
        try:
            return int(head)
        except (TypeError, ValueError):
            return 0

    @property
    def version_string(self) -> str:
        ver = (self.version_info or {}).get('server_version') or ''
        if not ver:
            return ''
        # Trim noisy suffixes like "17.0+e" → "17.0"
        return str(ver).split('+')[0]

    # Modules that only ship with Odoo Enterprise. Presence of any of these in
    # ir.module.module (state=installed) is a strong signal the server runs the
    # Enterprise edition. Used as a fallback when the version string lacks the
    # `+e` suffix (older versions, custom builds, hosting providers that strip
    # the suffix, etc.).
    ENTERPRISE_MARKER_MODULES = frozenset({
        'web_studio',
        'documents',
        'account_accountant',
        'voip',
        'mrp_workorder',
        'web_mobile',
        'helpdesk',
        'sign',
    })

    def detect_edition(self) -> str:
        """Return 'enterprise' or 'community'.

        Strategy, in order:
          1. `server_version` string contains `+e` or `enterprise`.
          2. The last element of `server_version_info` carries `'e'`.
          3. Probe an enterprise-only model (`account.asset`). If it answers
             a `fields_get`, the Enterprise codebase is loaded.
          4. Any known enterprise-only module is installed.
        Falls back to 'community' if nothing matches — community is the safer
        default because it hides enterprise-only tabs rather than exposing
        broken links."""
        ver = (self.version_info or {}).get('server_version', '') or ''
        ver_lower = str(ver).lower()
        if '+e' in ver_lower or 'enterprise' in ver_lower:
            return 'enterprise'
        info = (self.version_info or {}).get('server_version_info') or []
        if isinstance(info, list) and info:
            last = info[-1]
            if isinstance(last, str) and last.lower() == 'e':
                return 'enterprise'
        # Probe a known Enterprise-only model. A successful fields_get means
        # the model is registered on the server (Enterprise loaded); any
        # AccessError / Fault / "model not found" means Community.
        try:
            fields = self.execute_kw(
                'account.asset', 'fields_get', [], {'attributes': []})
            if isinstance(fields, dict) and fields:
                # Cache so we don't re-probe on subsequent has_field calls.
                self._field_cache.setdefault('account.asset', set(fields.keys()))
                return 'enterprise'
        except Exception:
            pass
        # Last resort: presence of known enterprise-only modules. Triggers a
        # lazy fetch of ir.module.module the first time it runs.
        try:
            installed = self.fetch_installed_modules()
        except Exception:
            installed = set()
        if installed & self.ENTERPRISE_MARKER_MODULES:
            return 'enterprise'
        return 'community'

    @classmethod
    def fetch_version(cls, url: str) -> dict:
        url = url.rstrip('/')
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
            return common.version() or {}
        except Exception as e:
            logger.warning("Cannot fetch Odoo version from %s: %s", url, e)
            return {}

    @classmethod
    def authenticate(cls, url: str, db: str, username: str, password: str) -> 'OdooClient':
        url = url.rstrip('/')
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
            try:
                version_info = common.version() or {}
            except Exception as e:
                logger.warning("Cannot fetch Odoo version: %s", e)
                version_info = {}
            uid = common.authenticate(db, username, password, {})
        except (socket.gaierror, ConnectionRefusedError, OSError) as e:
            raise OdooConnectionError(f"Cannot reach Odoo server: {e}")
        except Exception as e:
            raise OdooConnectionError(f"Connection error: {e}")
        if not uid:
            raise OdooAuthError("Invalid credentials or database name")
        return cls(url, db, uid, password, version_info=version_info)

    def execute_kw(self, model: str, method: str, args=None, kwargs=None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        if self.context:
            merged_ctx = dict(self.context)
            merged_ctx.update(kwargs.get('context') or {})
            kwargs = dict(kwargs, context=merged_ctx)
        try:
            return self._obj.execute_kw(
                self.db, self.uid, self.password,
                model, method, args, kwargs
            )
        except xmlrpc.client.Fault as e:
            logger.warning("Odoo fault %s.%s: %s", model, method, e.faultString)
            raise
        except Exception as e:
            logger.warning("Odoo error %s.%s: %s", model, method, e)
            raise

    def search_read(self, model: str, domain=None, fields=None,
                    limit=None, offset=0, order=None):
        if domain is None:
            domain = []
        kw = {'fields': fields or [], 'offset': offset}
        if limit is not None:
            kw['limit'] = limit
        if order:
            kw['order'] = order
        return self.execute_kw(model, 'search_read', [domain], kw)

    def search_count(self, model: str, domain=None) -> int:
        return self.execute_kw(model, 'search_count', [domain or []])

    def read_group(self, model: str, domain, fields, groupby,
                   limit=None, orderby=None, lazy=False):
        kw = {'lazy': lazy}
        if limit:
            kw['limit'] = limit
        if orderby:
            kw['orderby'] = orderby
        return self.execute_kw(model, 'read_group', [domain, fields, groupby], kw)

    def safe_count(self, model: str, domain=None) -> int:
        try:
            return self.search_count(model, domain)
        except Exception:
            return 0

    def safe_read_group(self, model: str, domain, fields, groupby, **kw):
        try:
            return self.read_group(model, domain, fields, groupby, **kw)
        except Exception:
            return []

    def safe_search_read(self, model: str, domain=None, fields=None,
                          limit=None, offset=0, order=None):
        try:
            return self.search_read(model, domain, fields, limit, offset, order)
        except Exception as e:
            logger.warning("safe_search_read failed — model=%s order=%r: %s", model, order, e)
            return []

    def paginated_search_read(self, model: str, domain=None, fields=None,
                              batch_size: int = 1000, order=None,
                              max_total: int = None):
        if domain is None:
            domain = []
        results = []
        offset = 0
        while True:
            try:
                batch = self.search_read(model, domain, fields,
                                         limit=batch_size, offset=offset, order=order)
            except Exception as e:
                logger.warning("paginated_search_read failed at offset=%d "
                               "(model=%s): %s", offset, model, e)
                break
            if not batch:
                break
            results.extend(batch)
            if len(batch) < batch_size:
                break
            if max_total is not None and len(results) >= max_total:
                results = results[:max_total]
                break
            offset += batch_size
        return results

    # ------------------------------------------------------------------
    # Compatibility helpers (field + module probes)
    # ------------------------------------------------------------------

    def get_model_fields(self, model: str) -> set:
        """Return the set of field names for `model`, cached. Returns an empty
        set on access errors (model missing, ACL denied, etc.) so callers can
        safely treat unsupported models as "no fields"."""
        if model in self._field_cache:
            return self._field_cache[model]
        try:
            raw = self.execute_kw(model, 'fields_get', [], {'attributes': []})
            fields = set(raw.keys()) if isinstance(raw, dict) else set()
        except Exception as e:
            logger.info("fields_get failed for %s: %s", model, e)
            fields = set()
        self._field_cache[model] = fields
        return fields

    def has_field(self, model: str, field: str) -> bool:
        return field in self.get_model_fields(model)

    def pick_field(self, model: str, candidates, default=None):
        """Return the first candidate field name that exists on `model`,
        else `default`. Accepts an alias key into FIELD_ALIASES too."""
        if isinstance(candidates, str):
            alias_map = FIELD_ALIASES.get(model, {})
            candidates = alias_map.get(candidates, [candidates])
        fields = self.get_model_fields(model)
        for c in candidates:
            if c in fields:
                return c
        return default

    def fetch_installed_modules(self) -> set:
        """Resolve and cache the set of installed module technical names.
        Returns an empty set if the user lacks access to ir.module.module."""
        if self._installed_modules is not None:
            return self._installed_modules
        try:
            rows = self.search_read(
                'ir.module.module',
                [['state', '=', 'installed']],
                fields=['name'])
            self._installed_modules = {r['name'] for r in (rows or []) if r.get('name')}
        except Exception as e:
            logger.info("Cannot list installed modules: %s", e)
            self._installed_modules = set()
        return self._installed_modules

    def has_module(self, name: str) -> bool:
        return name in self.fetch_installed_modules()
