"""Local image evidence and bounded thumbnails, never guessed semantic labels."""
import hashlib
from pathlib import Path
from .storage import atomic, records, now


def prepare(downloads, directory):
    from PIL import Image, ImageOps, ExifTags
    destination = Path(directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    labels, tasks, failures = [], [], []
    for item in records(downloads):
        asset_id = item.get('asset_id')
        if not asset_id:
            raise ValueError('missing asset_id')
        if item.get('status') != 'downloaded':
            failures.append({'asset_id': asset_id, 'reason': 'download-not-successful'})
            continue
        file = Path(item['local_path'])
        try:
            with Image.open(file) as image:
                raw_exif = image.getexif()
                exif = {ExifTags.TAGS.get(k, str(k)): v for k, v in raw_exif.items()}
                try:
                    exif.update({ExifTags.TAGS.get(k, str(k)): v for k, v in raw_exif.get_ifd(34665).items()})
                except (KeyError, TypeError, ValueError):
                    pass
                im = ImageOps.exif_transpose(image).convert('RGB')
                width, height = im.size
                small = im.copy()
                small.thumbnail((768, 768))
                thumb = destination / (hashlib.sha256(asset_id.encode()).hexdigest() + '.jpg')
                small.save(thumb, quality=80)
            h = hashlib.sha256()
            with file.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    h.update(chunk)
            metadata = {'width': width, 'height': height, 'sha256': h.hexdigest(), 'size_bytes': file.stat().st_size}
            taken = exif.get('DateTimeOriginal')
            if isinstance(taken, str):
                from datetime import datetime
                try:
                    metadata['taken_at'] = datetime.strptime(taken, '%Y:%m:%d %H:%M:%S').isoformat()
                    metadata['taken_at_source'] = 'exif-local-clock'
                except ValueError:
                    pass
            labels.append({'asset_id': asset_id, 'file_metadata': metadata,
                           'thumbnail_tags': {'orientation': 'landscape' if width > height else 'portrait' if height > width else 'square'},
                           'index_state': {'status': 'partial', 'metadata_source': 'local-file', 'updated_at': now()}})
            tasks.append({'asset_id': asset_id, 'thumbnail': str(thumb), 'original': str(file.resolve()),
                          'requested_fields': ['subjects', 'scene', 'actions', 'objects', 'image_type', 'ocr_text', 'people_count', 'quality'],
                          'instruction': 'Use visible evidence. Unknown fields are null; do not infer named identities, dates, or GPS.'})
        except (OSError, ValueError) as exc:
            failures.append({'asset_id': asset_id, 'reason': type(exc).__name__})
    from .manifest import write_manifest
    write_manifest(destination / 'metadata.labels.jsonl', labels)
    write_manifest(destination / 'vision.tasks.jsonl', tasks)
    result = {'prepared': len(tasks), 'failed': failures, 'metadata_labels': str(destination / 'metadata.labels.jsonl'),
              'vision_tasks': str(destination / 'vision.tasks.jsonl')}
    atomic(destination / 'report.json', result)
    return result
