"""Persistent full membership snapshots; refinement never escapes its parent."""
from . import query
from .storage import digest


def create(store, rows, spec, *, source, complete=False, parent=None):
    query.validate(spec)
    ids = [r.get('asset_id') for r in rows]
    if any(not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('missing/duplicate asset identity')
    buckets = {'items': [], 'excluded': [], 'unknown': []}
    for row in rows:
        decision = query.evaluate(row, spec)
        bucket = 'unknown' if decision is None else 'items' if decision else 'excluded'
        buckets[bucket].append(row)
    return store.save('results', {
        'schema_version': 'cloud-photo/result-set/v1', 'parent': parent,
        'query': spec, 'source': source, 'source_digest': digest(rows),
        'coverage': {'loaded': len(rows), 'complete': bool(complete)},
        'counts': {key: len(value) for key, value in buckets.items()},
        'decisions': {row['asset_id']: query.trace(row, spec) for row in rows}, **buckets,
    })


def refine(store, parent_id, spec):
    parent = store.load('results', parent_id)
    return create(store, parent['items'], spec, source={'kind': 'result-set', 'id': parent_id},
                  complete=parent['coverage']['complete'], parent=parent_id)


def select(store, parent_id, ids):
    parent = store.load('results', parent_id)
    if not isinstance(ids, list) or len(ids) != len(set(ids)):
        raise ValueError('selection must contain unique asset IDs')
    available = {row['asset_id']: row for row in parent['items']}
    if set(ids) - available.keys():
        raise ValueError('selection escapes parent result')
    return store.save('results', {
        'schema_version': 'cloud-photo/result-set/v1', 'parent': parent_id,
        'source': {'kind': 'explicit-selection'}, 'query': None,
        'coverage': parent['coverage'],
        'items': [available[i] for i in ids],
        'excluded': [r for i, r in available.items() if i not in ids], 'unknown': [],
        'counts': {'items': len(ids), 'excluded': len(available)-len(ids), 'unknown': 0},
    })


def refresh(store, result_id, listing):
    from copy import deepcopy
    from .assets import resolve
    parent = store.load('results', result_id)
    members = parent['items']
    resolution = resolve(members, listing)
    if resolution['counts']['resolved'] != len(members):
        raise ValueError('some references are unresolved; keep prior snapshot and reconcile identity')
    mapped = {r['asset_id']: r for r in resolution['items']}
    rows = deepcopy(members)
    for row in rows:
        item = mapped[row['asset_id']]
        row['source_ref'].update(file_id=item['fileRef'], ref_observed_at=item['ref_observed_at'])
    return store.save('results', {'schema_version':'cloud-photo/result-set/v1', 'parent':result_id,
        'source': {'kind':'reference-refresh'}, 'query': parent.get('query'),
        'coverage':parent['coverage'], 'items':rows, 'excluded':[], 'unknown':[],
        'counts':{'items':len(rows),'excluded':0,'unknown':0}})
