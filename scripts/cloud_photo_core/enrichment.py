"""Bound missing-field requests and refresh evidence without widening a selection."""
from copy import deepcopy
from .manifest import read_manifest
from .assets import fingerprint, path
from pathlib import Path

FIELDS = {'subjects', 'scene', 'actions', 'objects', 'image_type', 'people_count', 'people', 'quality', 'ocr_text'}


def request(store, result_id, fields, limit=32):
    if not fields or set(fields) - FIELDS or len(fields) != len(set(fields)):
        raise ValueError('unsupported or duplicate visual fields')
    if not 1 <= limit <= 100:
        raise ValueError('batch limit must be 1–100')
    source = store.load('results', result_id)
    tasks = []
    for row in source['items']:
        missing = [field for field in fields if row['vision_tags'].get(field) in (None, '', [])]
        if missing:
            tasks.append({'asset_id': row['asset_id'], 'source_ref': row['source_ref'], 'fields': missing,
                          'image_requirement': 'original' if set(missing) & {'quality', 'ocr_text'} else 'thumbnail_or_original'})
    return store.save('requests', {'schema_version': 'cloud-photo/enrichment/v1', 'result_id': result_id,
        'result_digest': source['digest'], 'fields': fields, 'tasks': tasks[:limit],
        'counts': {'scope': len(source['items']), 'missing': len(tasks), 'batch': min(limit, len(tasks)),
                   'remaining': max(0, len(tasks)-limit)},
        'instruction': 'Read actual images. Apply labels only to these asset IDs; named identities require user mapping. Refresh result evidence before refining.'})


def refresh(store, result_id, manifest):
    source = store.load('results', result_id)
    current = {r['asset_id']: r for r in read_manifest(Path(manifest))}
    updated = []
    for old in source['items']:
        new = current.get(old['asset_id'])
        if new is None or old['source_ref']['provider'] != new['source_ref']['provider']:
            raise ValueError('selected asset missing or provider changed')
        a, b = old['file_metadata'].get('sha256'), new['file_metadata'].get('sha256')
        if a or b:
            same = bool(a and b and a == b)
        else:
            location = path(old['source_ref'].get('path'))
            same = bool(location and location == path(new['source_ref'].get('path')) and
                        all(v is not None for v in fingerprint(old)) and fingerprint(old) == fingerprint(new))
        if not same:
            raise ValueError('asset content changed or cannot be verified; query the new scope explicitly')
        updated.append(deepcopy(new))
    return store.save('results', {'schema_version': 'cloud-photo/result-set/v1', 'parent': result_id,
        'source': {'kind': 'index-refresh', 'manifest': str(Path(manifest).resolve()), 'prior_digest': source['digest']},
        'query': None, 'coverage': source['coverage'], 'items': updated, 'excluded': [], 'unknown': [],
        'counts': {'items': len(updated), 'excluded': 0, 'unknown': 0}})


def apply(store, request_id, manifest, labels):
    import argparse
    import contextlib
    import io
    from .storage import records, file_lock
    from . import indexing
    job = store.load('requests', request_id)
    source = store.load('results', job['result_id'])
    if source['digest'] != job['result_digest']:
        raise ValueError('request source changed')
    allowed = {task['asset_id']: set(task['fields']) for task in job['tasks']}
    updates = records(labels)
    ids = [row.get('asset_id') for row in updates]
    if not updates or any(not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('empty, missing or duplicate label identity')
    for update in updates:
        asset_id = update['asset_id']
        if asset_id not in allowed or set(update) - {'asset_id', 'vision_tags', 'index_state'}:
            raise ValueError('labels escape the requested batch')
        tags = update.get('vision_tags')
        if not isinstance(tags, dict) or not tags or set(tags) - allowed[asset_id]:
            raise ValueError('labels contain unrequested fields')
        state = update.get('index_state', {})
        if not isinstance(state, dict) or set(state) - {'vision_source', 'vision_revision'}:
            raise ValueError('enrichment cannot override processing status or other provenance')
    with file_lock(Path(manifest).parent / '.index.lock'):
        current = {r['asset_id']: r for r in read_manifest(Path(manifest))}
        old = {r['asset_id']: r for r in source['items']}
        for asset_id in ids:
            if asset_id not in current or current[asset_id]['source_ref']['provider'] != old[asset_id]['source_ref']['provider']:
                raise ValueError('selected asset missing or changed')
            a, b = old[asset_id]['file_metadata'], current[asset_id]['file_metadata']
            if not a.get('sha256') or a['sha256'] != b.get('sha256'):
                raise ValueError('verified unchanged image hash required before applying requested labels')
        with contextlib.redirect_stdout(io.StringIO()):
            indexing.cmd_apply(argparse.Namespace(manifest=manifest, labels=labels, report=None, batch_id=request_id))
    return {'request_id': request_id, 'applied': len(updates), 'requested': len(allowed),
            'next': 'refresh-index on the source result, then refine or generate another enrichment-plan'}
