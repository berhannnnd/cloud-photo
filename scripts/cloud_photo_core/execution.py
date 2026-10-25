"""Journal provider operations without replaying ambiguous writes or persisting tokens."""
from .plans import compile_steps
from .storage import atomic, read, now


def safe(value):
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items() if not any(s in k.lower() for s in ('token', 'secret', 'authpage', 'qrimage'))}
    if isinstance(value, list):
        return [safe(v) for v in value]
    return value


def state_path(store, plan_id):
    return store.path('plans', plan_id).with_suffix('.operation.json')


def prepare(store, cloud, plan_id):
    with store.lock(plan_id):
        path = state_path(store, plan_id)
        if path.exists():
            return read(path)  # No second submission, even after timeout/crash.
        plan = store.load('plans', plan_id)
        steps = compile_steps(store, plan)
        cloud.capability('orchestrate')
        journal = {'plan_id': plan_id, 'plan_digest': plan['digest'], 'owner': store.owner,
                   'profile': cloud.profile, 'skill_dir': str(cloud.root), 'state': 'UNKNOWN',
                   'updated_at': now(), 'receipt': None}
        atomic(path, journal)
        receipt = cloud.call('cli', 'orchestrate', {'step': steps})
        journal.update(state=receipt['status'], receipt=safe(receipt), updated_at=now(),
                       operation_ref=(receipt.get('data') or {}).get('operationRef'),
                       plan_hash=(receipt.get('data') or {}).get('planHash'))
        atomic(path, journal)
        return journal


def operation(store, cloud, plan_id, action, confirmation=None):
    with store.lock(plan_id):
        path = state_path(store, plan_id)
        journal = read(path)
        plan = store.load('plans', plan_id)
        if (journal['owner'] != store.owner or journal['profile'] != cloud.profile or
                journal['skill_dir'] != str(cloud.root) or journal['plan_digest'] != plan['digest']):
            raise ValueError('operation identity or plan changed')
        prior = journal.get('receipt') or {}
        data = prior.get('data') or {}
        ref = journal.get('operation_ref') or data.get('operationRef')
        plan_hash = journal.get('plan_hash') or data.get('planHash')
        if not ref:
            raise ValueError('no provider operation reference; reconcile manually, do not resubmit')
        journal.update(operation_ref=ref, plan_hash=plan_hash)
        if action == 'status':
            receipt = cloud.call('operation', 'status', {'operation-ref': ref})
        else:
            if confirmation != 'CONFIRM' or journal['state'] != 'CONFIRMATION_REQUIRED' or not plan_hash:
                raise ValueError('only a reviewed pending plan can be confirmed')
            journal.update(state='UNKNOWN', updated_at=now())
            atomic(path, journal)
            confirmed = cloud.call('operation', 'confirm', {'operation-ref': ref, 'plan-hash': plan_hash, 'confirmation': confirmation})
            token = (confirmed.get('data') or {}).get('confirmToken')
            if confirmed['status'] == 'SUCCESS' and token:
                receipt = cloud.call('operation', 'execute', {'operation-ref': ref, 'confirm-token': token})
            elif confirmed['status'] == 'SUCCESS':
                receipt = {'status': 'UNKNOWN', 'data': {'operationRef': ref}, 'error': {'code': 'CONFIRM_TOKEN_MISSING'}}
            else:
                receipt = confirmed
        journal.update(receipt=safe(receipt), state=receipt['status'], updated_at=now())
        atomic(path, journal)
        return journal
