"""Conservative path and fingerprint matching; filenames alone are never identities."""
from .storage import now


def path(value):
    if isinstance(value, list) and all(isinstance(p, str) for p in value):
        value = '/' + '/'.join(value)
    if not isinstance(value, str) or not value.startswith('/'):
        return ''
    parts = value.split('/')
    if '..' in parts:
        return ''
    return '/' + '/'.join(p for p in parts if p and p != '.')


def fingerprint(row):
    meta = row.get('file_metadata', row)
    size = meta.get('size_bytes', meta.get('size'))
    modified = meta.get('modified_at', meta.get('updatedAt'))
    from .query import comparable
    if modified:
        parsed = comparable(modified)
        # Preserve fractional seconds and timezone evidence; do not weaken identity.
        if hasattr(parsed, 'strftime'):
            modified = parsed.isoformat()
    return size, modified


def resolve(requested, listing):
    output = []
    for row in requested:
        wanted_path = path(row.get('path') or row.get('source_ref', {}).get('path'))
        wanted_fingerprint = fingerprint(row)
        candidates = [item for item in listing if wanted_path and path(item.get('path') or item.get('namePath')) == wanted_path]
        matches = [item for item in candidates if all(v is not None for v in wanted_fingerprint) and fingerprint(item) == wanted_fingerprint]
        if len(matches) == 1 and matches[0].get('fileRef'):
            output.append({'asset_id': row.get('asset_id'), 'status': 'resolved', 'path': wanted_path,
                           'fileRef': matches[0]['fileRef'], 'ref_observed_at': now()})
        else:
            output.append({'asset_id': row.get('asset_id'), 'status': 'ambiguous' if len(matches) > 1 else 'unresolved', 'path': wanted_path})
    return {'schema_version': 'cloud-photo/ref-resolution/v1', 'items': output,
            'counts': {s: sum(r['status'] == s for r in output) for s in ('resolved', 'ambiguous', 'unresolved')}}
