"""Frozen classification plans compiled into one provider orchestration."""
import datetime as dt
import re
import shlex
from .adapters.cm_cloud import arguments
from .grouping import group


def command(domain, action, params):
    return shlex.join([domain, action, *arguments(params)])


def batches(refs, build, max_items=500):
    chunk, result = [], []
    for ref in refs:
        if len(chunk) >= max_items or len(build(chunk + [ref])) > 8192:
            if not chunk:
                raise ValueError('single resource exceeds provider step limit')
            result.append(chunk)
            chunk = []
        chunk.append(ref)
        if len(build(chunk)) > 8192:
            raise ValueError('single resource exceeds provider step limit')
    if chunk:
        result.append(chunk)
    return result


def create(store, result_id, target, dimensions, prefix='', overlap='first', destination=None, allow_partial=False):
    result = store.load('results', result_id)
    if not result['items']:
        raise ValueError('empty selection cannot create a plan')
    if not result['coverage']['complete'] and not allow_partial:
        raise ValueError('source coverage incomplete; explicitly choose loaded scope')
    if target not in ('album', 'story', 'folder', 'existing-album'):
        raise ValueError('invalid target')
    if target in ('folder', 'existing-album') and not destination:
        raise ValueError('destination reference required')
    if target == 'existing-album' and dimensions != ['all']:
        raise ValueError('existing album accepts a single all group')
    groups = group(result['items'], dimensions, overlap)
    names = set()
    for item in groups:
        name = re.sub(r'[\\/:*?"<>|;&$`{}\x00-\x1f]', '-', prefix + item['name']).strip()
        if not name or name in ('.', '..') or len(name) > (255 if target == 'folder' else 64) or name in names:
            raise ValueError('invalid/colliding group name; choose another prefix or grouping')
        item['name'] = name
        names.add(name)
    return store.save('plans', {'schema_version': 'cloud-photo/plan/v1', 'result_id': result_id,
        'result_digest': result['digest'], 'target': target, 'destination': destination,
        'dimensions': dimensions, 'overlap': overlap, 'groups': groups,
        'scope': 'loaded' if not result['coverage']['complete'] else 'complete',
        'asset_count': len(result['items']), 'membership_count': sum(len(g['asset_ids']) for g in groups)})


def compile_steps(store, plan):
    result = store.load('results', plan['result_id'])
    if result['digest'] != plan['result_digest']:
        raise ValueError('result snapshot changed')
    rows = {r['asset_id']: r for r in result['items']}
    refs = {}
    for asset_id, row in rows.items():
        source = row['source_ref']
        stamp = source.get('ref_observed_at')
        if not stamp:
            raise ValueError('refresh provider references before preparing a cloud plan')
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds()
        if not 0 <= age < 10*3600:
            raise ValueError('provider reference freshness expired; refresh and rebuild selection')
        ref = source.get('file_id')
        if not isinstance(ref, str) or not ref.startswith('cmr_'):
            raise ValueError('current provider fileRef required')
        refs[asset_id] = ref
    steps = []
    for g in plan['groups']:
        members = [refs[i] for i in g['asset_ids']]
        kind = plan['target']
        if kind == 'story':
            step = command('album', 'create', {'kind': 'story', 'name': g['name'], 'coverRef': members[0], 'fileRefs': members})
            if len(members) > 500 or len(step) > 8192:
                raise ValueError('story exceeds provider limits; choose or explicitly split the selection')
            steps.append(step)
            continue
        if kind == 'folder':
            steps.append(command('files', 'mkdir', {'parentRef': plan['destination'], 'name': g['name']}))
            destination = '?step%d.folderRef' % len(steps)
            build = lambda chunk: command('files', 'copy', {'resources': chunk, 'destinationRef': destination})
            steps.extend(build(chunk) for chunk in batches(members, build, 100))
        else:
            destination = plan['destination'] if kind == 'existing-album' else '?step%d.albumRef' % (len(steps)+1)
            add = lambda chunk: command('album', 'add', {'albumRef': destination, 'fileRefs': chunk})
            create = lambda chunk: command('album', 'create', {'kind': 'album', 'name': g['name'], 'fileRefs': chunk})
            split = batches(members, lambda chunk: max((add(chunk), create(chunk)), key=len))
            if kind == 'album':
                steps.append(create(split.pop(0)))
            steps.extend(add(chunk) for chunk in split)
    if any(len(step) > 8192 for step in steps) or sum(len(step.encode()) for step in steps) > 100000:
        raise ValueError('plan exceeds transport budget; explicitly divide into separately reviewed selections')
    return steps
