"""Evidence-based grouping and exact duplicate selection."""
from itertools import product
from .query import field


def group(rows, dimensions, overlap='first'):
    if not dimensions or len(dimensions) > 3 or overlap not in ('first', 'all'):
        raise ValueError('choose 1–3 dimensions and first/all overlap')
    groups = {}
    for row in rows:
        axes = []
        for dim in dimensions:
            if dim == 'all':
                values = ['全部']
            elif dim in ('year', 'month'):
                raw = field(row, 'file_metadata.taken_at')
                if raw:
                    from .query import comparable
                    from datetime import datetime
                    date = comparable(raw)
                    values = [date.strftime('%Y' if dim == 'year' else '%Y-%m')] if isinstance(date, datetime) else ['待归类']
                else:
                    values = ['待归类']
            else:
                if dim.count('.') != 1 or dim.split('.')[0] not in ('file_metadata', 'thumbnail_tags', 'vision_tags'):
                    raise ValueError('invalid grouping field')
                value = field(row, dim)
                values = value if isinstance(value, list) else [value] if value is not None else ['待归类']
                values = sorted(set(str(v) for v in values))
            axes.append(values[:1] if overlap == 'first' else values)
        for key in product(*axes):
            name = ' / '.join(key)
            groups.setdefault(name, []).append(row['asset_id'])
    return [{'name': name, 'asset_ids': ids} for name, ids in sorted(groups.items())]


def deduplicate(store, result_id):
    parent = store.load('results', result_id)
    seen, kept, duplicate, unverified = {}, [], [], []
    for row in parent['items']:
        hash_value = row.get('file_metadata', {}).get('sha256')
        if not hash_value:
            unverified.append(row['asset_id'])
            kept.append(row)
        elif hash_value in seen:
            duplicate.append({'asset_id': row['asset_id'], 'same_as': seen[hash_value], 'reason': 'sha256-equal'})
        else:
            seen[hash_value] = row['asset_id']
            kept.append(row)
    return store.save('results', {'schema_version': 'cloud-photo/result-set/v1',
        'parent': result_id, 'source': {'kind': 'exact-dedupe'}, 'query': None,
        'coverage': parent['coverage'], 'items': kept,
        'excluded': [r for r in parent['items'] if r['asset_id'] in {d['asset_id'] for d in duplicate}],
        'unknown': [], 'duplicates': duplicate, 'unverified_asset_ids': unverified,
        'counts': {'items': len(kept), 'excluded': len(duplicate), 'unknown': 0}})
