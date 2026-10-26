"""Atomic private state, immutable snapshots and strict structured input."""
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def records(path):
    raw = Path(path).read_text(encoding='utf-8')
    if not raw.strip():
        return []
    try:
        values = [json.loads(raw)]
    except json.JSONDecodeError:
        values = [json.loads(line) for line in raw.splitlines() if line.strip()]
    rows = []
    for value in values:
        if isinstance(value, dict) and 'status' in value and 'schemaVersion' in value:
            if value['status'] not in ('SUCCESS', 'EMPTY'):
                raise ValueError('cannot import a failed/incomplete provider receipt')
            value = (value.get('data') or {}).get('items', [])
        elif isinstance(value, dict):
            for key in ('items', 'results', 'candidates', 'assets'):
                if isinstance(value.get(key), list):
                    value = value[key]
                    break
        rows.extend(value if isinstance(value, list) else [value])
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError('input must contain objects')
    return rows


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


class Store:
    def __init__(self, root, owner):
        if not owner or not owner.strip():
            raise ValueError('host-bound owner is required')
        self.root = Path(root).resolve() / 'owners' / digest(owner)[:24]
        self.owner = owner
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, kind, key):
        if kind not in ('results', 'plans', 'operations', 'reviews', 'requests', 'reconciliations') or not re.fullmatch(r'[a-z]+-[a-f0-9]{32}', key):
            raise ValueError('invalid state reference')
        return self.root / kind / (key + '.json')

    def save(self, kind, value):
        key = kind.rstrip('s') + '-' + uuid.uuid4().hex
        value = {**value, 'id': key, 'owner': self.owner, 'created_at': now()}
        value['digest'] = digest(value)
        atomic(self.path(kind, key), value)
        return value

    def load(self, kind, key):
        value = read(self.path(kind, key))
        payload = {k: v for k, v in value.items() if k != 'digest'}
        if value.get('owner') != self.owner or value.get('digest') != digest(payload):
            raise ValueError('state owner or integrity mismatch')
        return value

    @contextlib.contextmanager
    def lock(self, plan_id):
        path = self.path('plans', plan_id).with_suffix('.lock')
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError('plan is locked; inspect prior process before manual recovery') from None
        try:
            os.close(fd)
            yield
        finally:
            path.unlink(missing_ok=True)


@contextlib.contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('state is locked; inspect the existing writer before recovery') from None
    try:
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)
