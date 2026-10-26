"""Apply a bounded media batch, including failures, and emit recovery-only members."""
import argparse
import contextlib
import io
from pathlib import Path
from . import indexing, media
from .manifest import read_manifest, write_manifest
from .storage import atomic, records, file_lock


def run(manifest, batch, downloads, directory):
    manifest, destination = Path(manifest), Path(directory).resolve()
    selected, inputs = records(batch), records(downloads)
    ids = [row.get('asset_id') for row in selected]
    mapped = [row.get('asset_id') for row in inputs]
    if not 1 <= len(ids) <= 100 or any(not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('batch requires 1–100 unique asset IDs')
    if any(not i for i in mapped) or len(mapped) != len(set(mapped)) or set(mapped) - set(ids):
        raise ValueError('download mapping is duplicate or outside batch')
    with file_lock(manifest.parent / '.index.lock'):
        current = {row['asset_id']: row for row in read_manifest(manifest)}
        for row in selected:
            old = current.get(row['asset_id'])
            if old is None or row['source_ref'] != old['source_ref'] or row['file_metadata'] != old['file_metadata']:
                raise ValueError('batch is stale or asset changed; generate a fresh batch')
        by_id = {row['asset_id']: row for row in inputs}
        checked = []
        for asset_id in ids:
            item = dict(by_id.get(asset_id, {'asset_id': asset_id, 'status': 'error'}))
            meta = current[asset_id]['file_metadata']
            item['expected_size_bytes'] = meta.get('size_bytes')
            item['expected_sha256'] = meta.get('sha256')
            checked.append(item)
        destination.mkdir(parents=True, exist_ok=True)
        write_manifest(destination / 'checked-input.jsonl', checked)
        result = media.prepare(destination / 'checked-input.jsonl', destination)
        labels = records(result['metadata_labels']) + records(result['failure_labels'])
        write_manifest(destination / 'index.labels.jsonl', labels)
        with contextlib.redirect_stdout(io.StringIO()):
            indexing.cmd_apply(argparse.Namespace(manifest=str(manifest), labels=str(destination / 'index.labels.jsonl'),
                                                  report=None, batch_id=None))
        updated = {row['asset_id']: row for row in read_manifest(manifest)}
        retryable = {'download-not-successful', 'LOCAL_FILE_MISSING', 'LOCAL_EMPTY_FILE',
                     'LOCAL_SIZE_MISMATCH', 'LOCAL_HASH_MISMATCH'}
        retry_ids = {f['asset_id'] for f in result['failed'] if f['reason'] in retryable}
        write_manifest(destination / 'retry.batch.jsonl', [updated[i] for i in ids if i in retry_ids])
        result.update(index_applied=True, retry_count=len(retry_ids),
                      retry_batch=str(destination / 'retry.batch.jsonl'),
                      needs_review=[f for f in result['failed'] if f['reason'] not in retryable],
                      note='Media completion is not visual indexing completion. Retry downloads into a fresh directory; never replay cloud writes.')
        atomic(destination / 'index-report.json', result)
        return result
