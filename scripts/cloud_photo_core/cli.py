"""Thin argument wiring for local workflow and public provider boundary."""
import argparse
import json
from pathlib import Path
import sys
from . import execution, grouping, legacy, media, plans, results, similarity, enrichment, progress, diagnostics
from .adapters.cm_cloud import Cloud, scan, download
from .storage import Store, read


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def summary(value):
    return {key: value[key] for key in ('id', 'digest', 'counts', 'coverage', 'groups', 'asset_count', 'membership_count') if key in value}


def cloud(args):
    return Cloud(args.skill_dir, args.profile, args.python, timeout=args.timeout)


def run(args):
    cmd = args.command
    if cmd == 'environment-check': return diagnostics.check(args.directory)
    if cmd == 'cloud-scan': return scan(cloud(args), args.output, read(args.filters), args.max_pages, args.resume, args.source)
    if cmd == 'cloud-download': return download(cloud(args), args.batch, args.directory, args.output)
    if cmd == 'media-prepare': return media.prepare(args.downloads, args.directory)
    store = Store(args.state_dir, args.owner)
    if cmd == 'reconcile-plan':
        report = progress.reconcile(store, args.plan, args.listing, args.group)
        return {k: report[k] for k in ('id', 'counts', 'operation_state', 'ambiguous_metadata', 'can_prepare_remaining', 'note')}
    if cmd == 'operation-progress': return progress.inspect(store, args.plan)
    if cmd == 'enrichment-apply': return enrichment.apply(store, args.request, args.manifest, args.labels)
    if cmd == 'enrichment-plan': return enrichment.request(store, args.result, args.fields.split(','), args.limit)
    if cmd == 'refresh-index': return summary(enrichment.refresh(store, args.result, args.manifest))
    if cmd == 'query':
        rows = legacy.read_manifest(Path(args.manifest))
        return summary(results.create(store, rows, read(args.spec), source={'kind': 'manifest', 'path': str(Path(args.manifest).resolve())}, complete=args.complete))
    if cmd == 'refine': return summary(results.refine(store, args.result, read(args.spec)))
    if cmd == 'select': return summary(results.select(store, args.result, read(args.ids)))
    if cmd == 'refresh-refs':
        from .storage import records
        return summary(results.refresh(store, args.result, records(args.listing)))
    if cmd == 'similar-candidates':
        review = similarity.similar_candidates(store, args.result, args.distance)
        return {k: review[k] for k in ('id', 'digest', 'counts', 'max_distance', 'warning')}
    if cmd == 'review-show':
        review = store.load('reviews', args.review)
        if args.offset < 0 or args.limit < 1: raise ValueError('invalid page bounds')
        return {**{k: v for k, v in review.items() if k != 'groups'}, 'groups': review['groups'][args.offset:args.offset+args.limit]}
    if cmd == 'dedupe': return summary(grouping.deduplicate(store, args.result))
    if cmd == 'result-show':
        value = store.load('results', args.result)
        if args.offset < 0 or args.limit < 1: raise ValueError('invalid page bounds')
        return {**summary(value), 'parent': value.get('parent'), 'bucket': args.bucket,
                'items': value[args.bucket][args.offset:args.offset+args.limit],
                'total': len(value[args.bucket]), 'offset': args.offset,
                'decisions': {row['asset_id']: value.get('decisions', {}).get(row['asset_id']) for row in value[args.bucket][args.offset:args.offset+args.limit]}}
    if cmd == 'group-plan':
        return summary(plans.create(store, args.result, args.target, args.by.split(','), args.prefix, args.overlap, args.destination, args.allow_partial))
    if cmd == 'plan-show': return store.load('plans', args.plan)
    if cmd == 'cloud-prepare': return execution.prepare(store, cloud(args), args.plan)
    if cmd in ('cloud-execute', 'cloud-status'):
        return execution.operation(store, cloud(args), args.plan, 'execute' if cmd == 'cloud-execute' else 'status', getattr(args, 'confirmation', None))
    raise ValueError('unknown command')


def main():
    parser = argparse.ArgumentParser(description='Cloud Photo: index → query → refine → group → provider plan')
    sub = parser.add_subparsers(dest='command', required=True)
    legacy.register(sub)
    def add(name, state=True, provider=False):
        p = sub.add_parser(name)
        p.set_defaults(func=lambda a: emit(run(a)))
        if state:
            p.add_argument('--state-dir', required=True)
            p.add_argument('--owner', required=True, help='host-bound user identity; not arbitrary chat text')
        if provider:
            p.add_argument('--skill-dir', required=True)
            p.add_argument('--profile', default='default')
            p.add_argument('--python', help='provider Python interpreter')
            p.add_argument('--timeout', type=int, default=120, help='public CLI process deadline in seconds; execute defaults to 1800')
        return p
    p=add('environment-check',state=False);p.add_argument('--directory',required=True)
    p=add('reconcile-plan');p.add_argument('--plan',required=True);p.add_argument('--listing',required=True);p.add_argument('--group')
    p=add('operation-progress');p.add_argument('--plan',required=True)
    p=add('enrichment-apply');p.add_argument('--request',required=True);p.add_argument('--manifest',required=True);p.add_argument('--labels',required=True)
    p=add('enrichment-plan');p.add_argument('--result',required=True);p.add_argument('--fields',required=True);p.add_argument('--limit',type=int,default=32)
    p=add('refresh-index');p.add_argument('--result',required=True);p.add_argument('--manifest',required=True)
    p=add('query');p.add_argument('--manifest', required=True);p.add_argument('--spec', required=True);p.add_argument('--complete', action='store_true', help='source scope is verified complete')
    p=add('refine');p.add_argument('--result', required=True);p.add_argument('--spec', required=True)
    p=add('select');p.add_argument('--result', required=True);p.add_argument('--ids', required=True)
    p=add('refresh-refs');p.add_argument('--result',required=True);p.add_argument('--listing',required=True)
    p=add('similar-candidates');p.add_argument('--result',required=True);p.add_argument('--distance',type=int,default=4)
    p=add('review-show');p.add_argument('--review',required=True);p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=20)
    p=add('dedupe');p.add_argument('--result', required=True)
    p=add('result-show');p.add_argument('--result', required=True);p.add_argument('--bucket', choices=['items','excluded','unknown'], default='items');p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=20)
    p=add('group-plan');p.add_argument('--result',required=True);p.add_argument('--target',choices=['album','story','folder','existing-album'],required=True);p.add_argument('--by',default='all');p.add_argument('--prefix',default='');p.add_argument('--overlap',choices=['first','all'],default='first');p.add_argument('--destination');p.add_argument('--allow-partial',action='store_true')
    p=add('plan-show');p.add_argument('--plan',required=True)
    for name in ('cloud-prepare','cloud-execute','cloud-status'):
        p=add(name,provider=True);p.add_argument('--plan',required=True)
        if name=='cloud-execute':
            p.set_defaults(timeout=1800)
            p.add_argument('--confirmation',choices=['CONFIRM'],required=True,help='only after user confirms the displayed provider plan')
    p=add('cloud-scan',state=False,provider=True);p.add_argument('--source',choices=['search','list'],default='search');p.add_argument('--filters',required=True);p.add_argument('--output',required=True);p.add_argument('--max-pages',type=int,default=100);p.add_argument('--resume',action='store_true')
    p=add('cloud-download',state=False,provider=True);p.add_argument('--batch',required=True);p.add_argument('--directory',required=True);p.add_argument('--output',required=True)
    p=add('media-prepare',state=False);p.add_argument('--downloads',required=True);p.add_argument('--directory',required=True)
    args=parser.parse_args()
    try:
        args.func(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status':'ERROR','message':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
    return 0
