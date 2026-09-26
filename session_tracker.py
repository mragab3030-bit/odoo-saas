"""Active-session tracker for access codes, backed by `sessions.json`.

Enforces `max_sessions` per code (default 1). A file — not an in-process
dict — because gunicorn runs several workers that must share the count;
every read-modify-write holds an exclusive file lock so two simultaneous
logins can't both take the last slot.

Layout:
    {
      "VISION2025": {
        "sessions": [
          {"session_id": "…", "logged_in_at": "…", "last_activity": "…"}
        ],
        "last_seen": "…"
      }
    }
"""
import json
import os
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta

try:
    import fcntl
except ImportError:  # Windows dev machines: single-process lock only
    fcntl = None

SESSIONS_PATH = os.environ.get(
    'SESSIONS_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sessions.json'),
)
IDLE_TIMEOUT = timedelta(minutes=30)
ONLINE_WINDOW = timedelta(minutes=5)
# Don't rewrite the file on every XHR; a coarser heartbeat is plenty
# against a 30-minute timeout.
TOUCH_INTERVAL = timedelta(seconds=30)

_thread_lock = threading.Lock()


def _now():
    return datetime.now().replace(microsecond=0)


def _parse(ts):
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


@contextmanager
def _locked():
    """Yield the tracker dict under an exclusive lock; write it back on exit.

    The lock lives on a side file and the data is replaced atomically, so
    the unlocked fast-path read in touch() never sees a half-written file."""
    with _thread_lock:
        lock_fd = os.open(SESSIONS_PATH + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            data = _read()
            yield data
            tmp = f"{SESSIONS_PATH}.{os.getpid()}.tmp"
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, SESSIONS_PATH)
        finally:
            if fcntl:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def _prune(slot, now):
    """Drop sessions idle past the timeout, remembering when they were last seen."""
    alive = []
    for s in slot.get('sessions', []):
        last = _parse(s.get('last_activity'))
        if last and now - last <= IDLE_TIMEOUT:
            alive.append(s)
        elif last:
            _mark_seen(slot, last)
    slot['sessions'] = alive


def _mark_seen(slot, when):
    prev = _parse(slot.get('last_seen'))
    if prev is None or when > prev:
        slot['last_seen'] = when.isoformat()


def claim(code, max_sessions=1):
    """Take a session slot for `code`. Returns the new session id, or None
    when every slot is already held by an active session."""
    max_sessions = max(1, int(max_sessions or 1))
    now = _now()
    with _locked() as data:
        slot = data.setdefault(code, {})
        _prune(slot, now)
        if len(slot['sessions']) >= max_sessions:
            return None
        sid = secrets.token_urlsafe(16)
        slot['sessions'].append({
            'session_id': sid,
            'logged_in_at': now.isoformat(),
            'last_activity': now.isoformat(),
        })
        _mark_seen(slot, now)
        return sid


def touch(code, sid):
    """Record activity. Returns False when the session is gone — idle past
    the timeout, force-logged-out, or never claimed — so the caller can
    sign the browser out."""
    if not sid:
        return False
    now = _now()
    # Cheap unlocked read first: most requests only need to confirm the
    # session exists and was touched recently.
    current = _find(_read().get(code, {}), sid)
    if current is None:
        return False
    last = _parse(current.get('last_activity'))
    if last and now - last > IDLE_TIMEOUT:
        release(code, sid)
        return False
    if last and now - last < TOUCH_INTERVAL:
        return True
    with _locked() as data:
        slot = data.get(code, {})
        s = _find(slot, sid)
        if s is None:
            return False
        s['last_activity'] = now.isoformat()
        _mark_seen(slot, now)
    return True


def release(code, sid):
    """Free one session (logout)."""
    if not sid:
        return
    with _locked() as data:
        slot = data.get(code)
        if not slot:
            return
        s = _find(slot, sid)
        if s:
            _mark_seen(slot, _parse(s.get('last_activity')) or _now())
            slot['sessions'] = [x for x in slot['sessions'] if x.get('session_id') != sid]


def force_logout(code):
    """Admin: end every session of `code` now."""
    with _locked() as data:
        slot = data.get(code)
        if slot:
            for s in slot.get('sessions', []):
                last = _parse(s.get('last_activity'))
                if last:
                    _mark_seen(slot, last)
            slot['sessions'] = []


def status(code):
    """Admin view: {'state': online|idle|offline, 'active': n,
    'minutes_ago': int|None} — idle means signed in but quiet for longer
    than ONLINE_WINDOW (still holding its slot)."""
    now = _now()
    slot = _read().get(code, {})
    sessions = [s for s in slot.get('sessions', [])
                if (_parse(s.get('last_activity')) or now - 2 * IDLE_TIMEOUT) >= now - IDLE_TIMEOUT]
    last_times = [_parse(s.get('last_activity')) for s in sessions]
    last_times = [t for t in last_times if t]
    newest = max(last_times) if last_times else _parse(slot.get('last_seen'))
    minutes = int((now - newest).total_seconds() // 60) if newest else None
    if not sessions:
        state = 'offline'
    elif newest and now - newest <= ONLINE_WINDOW:
        state = 'online'
    else:
        state = 'idle'
    return {'state': state, 'active': len(sessions), 'minutes_ago': minutes}


def rename(old, new):
    """Keep tracking when an admin renames a code."""
    with _locked() as data:
        if old in data:
            data[new] = data.pop(old)


def forget(code):
    with _locked() as data:
        data.pop(code, None)


def _find(slot, sid):
    return next((s for s in slot.get('sessions', []) if s.get('session_id') == sid), None)


def _read():
    try:
        with open(SESSIONS_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
