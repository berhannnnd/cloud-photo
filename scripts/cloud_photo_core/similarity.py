"""Perceptual candidates for visual review; no automatic survivor selection."""


def similar_candidates(store, result_id, max_distance=4):
    """Generate bounded dHash candidates; never remove or rank a photo as best."""
    import re
    if type(max_distance) is not int or not 0 <= max_distance <= 8:
        raise ValueError('dHash distance must be an integer between 0 and 8')
    source = store.load('results', result_id)
    if len(source['items']) > 10000:
        raise ValueError('similarity review is limited to 10000 photos; narrow the result set')
    known, missing = [], []
    for row in source['items']:
        metadata = row['file_metadata']
        value = metadata.get('dhash64')
        if metadata.get('dhash_method') == 'exif-oriented-dhash64-v1' and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{16}', value):
            known.append((row['asset_id'], int(value, 16)))
        else:
            missing.append(row['asset_id'])
    parent = {asset: asset for asset, _ in known}
    def find(asset):
        while parent[asset] != asset:
            parent[asset] = parent[parent[asset]]
            asset = parent[asset]
        return asset
    edges = []
    for index, (a, first) in enumerate(known):
        for b, second in known[index+1:]:
            distance = (first ^ second).bit_count()
            if distance <= max_distance:
                edges.append({'a': a, 'b': b, 'distance': distance})
                parent[find(b)] = find(a)
                if len(edges) > 20000:
                    raise ValueError('too many similarity candidates; narrow the result set or threshold')
    connected = {}
    for edge in edges:
        connected.setdefault(find(edge['a']), []).append(edge)
    groups = []
    for links in connected.values():
        members = sorted({e[key] for e in links for key in ('a', 'b')})
        groups.append({'asset_ids': members, 'edges': links, 'needs_visual_review': True})
    return store.save('reviews', {'schema_version': 'cloud-photo/similarity-review/v1',
        'result_id': result_id, 'result_digest': source['digest'], 'method': 'dhash64',
        'max_distance': max_distance, 'groups': groups, 'unverified_asset_ids': missing,
        'counts': {'input':len(source['items']), 'hashed':len(known), 'groups':len(groups), 'pairs':len(edges), 'unknown':len(missing)},
        'warning': 'Candidate connectivity is not pairwise equivalence. Review images before selecting survivors.'})
