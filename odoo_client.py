import xmlrpc.client
import logging
import socket

logger = logging.getLogger(__name__)


class OdooAuthError(Exception):
    pass


class OdooConnectionError(Exception):
    pass


class OdooClient:
    def __init__(self, url: str, db: str, uid: int, password: str):
        self.url = url.rstrip('/')
        self.db = db
        self.uid = uid
        self.password = password
        self._object = None

    @property
    def _obj(self):
        if self._object is None:
            self._object = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/object',
                allow_none=True
            )
        return self._object

    @classmethod
    def authenticate(cls, url: str, db: str, username: str, password: str) -> 'OdooClient':
        url = url.rstrip('/')
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
            uid = common.authenticate(db, username, password, {})
        except (socket.gaierror, ConnectionRefusedError, OSError) as e:
            raise OdooConnectionError(f"Cannot reach Odoo server: {e}")
        except Exception as e:
            raise OdooConnectionError(f"Connection error: {e}")
        if not uid:
            raise OdooAuthError("Invalid credentials or database name")
        return cls(url, db, uid, password)

    def execute_kw(self, model: str, method: str, args=None, kwargs=None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
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
        except Exception:
            return []
