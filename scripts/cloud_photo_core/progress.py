"""Evidence-based operation progress and non-mutating recovery guidance."""
from .storage import read
from .execution import state_path


def inspect(store, plan_id):
    plan = store.load('plans', plan_id)
    journal_path = state_path(store, plan_id)
    if not journal_path.exists():
        return {'plan_id': plan_id, 'state': 'LOCAL_PLAN', 'assets': plan['asset_count'], 'next': 'cloud-prepare'}
    journal = read(journal_path)
    if journal['owner'] != store.owner or journal['plan_digest'] != plan['digest']:
        raise ValueError('operation identity or plan changed')
    receipt = journal.get('receipt') or {}
    data = receipt.get('data') or {}
    entries = data.get('stepResults') or data.get('steps') or []
    state = journal['state']
    return {'plan_id': plan_id, 'state': state, 'updated_at': journal.get('updated_at'),
        'assets_planned': plan['asset_count'], 'provider_counts': receipt.get('counts'),
        'observed_steps': [{'index': item.get('index'), 'name': item.get('name') or item.get('label'),
                            'status': item.get('status'), 'counts': item.get('counts')} for item in entries],
        'next_action': receipt.get('nextAction'), 'error_code': (receipt.get('error') or {}).get('code'),
        'automatic_replay_allowed': False,
        'recovery': ('Read back destination membership before reporting completion.' if state == 'SUCCESS' else
                     'Confirm the reviewed plan.' if state == 'CONFIRMATION_REQUIRED' else
                     'Query original operation and reconcile destination. Do not submit the original write again.'),
        'note': 'Observed steps are provider evidence, not photo counts or percentage. This command does not poll or restart a process.'}


def reconcile(store, plan_id, listing, group_name=None):
    """Compare a complete public readback; matching metadata is not byte proof."""
    from collections import Counter
    from .storage import digest
    plan = store.load('plans', plan_id)
    groups = plan['groups']
    if group_name is not None:
        groups = [g for g in groups if g['name'] == group_name]
    if len(groups) != 1:
        raise ValueError('select exactly one destination group')
    receipt = read(listing)
    if receipt.get('status') not in ('SUCCESS', 'EMPTY') or (receipt.get('page') or {}).get('complete') is not True:
        raise ValueError('complete successful destination listing required')
    actual = (receipt.get('data') or {}).get('items')
    if not isinstance(actual, list):
        raise ValueError('destination listing has no items')
    source = store.load('results', plan['result_id'])
    if source['digest'] != plan['result_digest']:
        raise ValueError('source digest mismatch')
    rows = {r['asset_id']: r for r in source['items']}
    expected = [rows[i] for i in groups[0]['asset_ids']]
    def key(row):
        meta = row.get('file_metadata', row)
        name, size = meta.get('name'), meta.get('size_bytes', meta.get('size'))
        if not isinstance(name, str) or type(size) is not int or size < 0:
            raise ValueError('readback requires names and sizes')
        return name, size
    wanted, found = Counter(key(r) for r in expected), Counter(key(r) for r in actual)
    ambiguous = any(n > 1 for n in wanted.values()) or any(n > 1 for n in found.values())
    missing = [r['asset_id'] for r in expected if key(r) not in found]
    observed = inspect(store, plan_id)
    terminal = observed['state'] in ('SUCCESS', 'PARTIAL', 'FAILED', 'REJECTED')
    return store.save('reconciliations', {'schema_version': 'cloud-photo/reconciliation/v1',
        'plan_id': plan_id, 'plan_digest': plan['digest'], 'group': groups[0]['name'],
        'listing_digest': digest(receipt), 'operation_state': observed['state'],
        'counts': {'expected': len(expected), 'actual': len(actual),
                   'metadata_matched': sum((wanted & found).values()),
                   'missing': sum((wanted-found).values()), 'extra': sum((found-wanted).values())},
        'ambiguous_metadata': ambiguous, 'missing_asset_ids': missing,
        'can_prepare_remaining': terminal and not ambiguous and bool(missing) and not (found-wanted),
        'automatic_replay_allowed': False,
        'note': 'Caller must verify this listing belongs to the selected target. Metadata equality is not byte equality. Re-check original operation and references before preparing a new remaining-only plan.'})
