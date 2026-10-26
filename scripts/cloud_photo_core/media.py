"""Local image evidence and bounded thumbnails, never guessed semantic labels."""
import hashlib
import math
from pathlib import Path
from .storage import atomic, records, now
from .provenance import geo_cells


def _text(value):
    if isinstance(value, bytes):
        value = value.decode('utf-8', 'ignore')
    value = str(value or '').replace('\x00', '').strip()
    return value or None


def _gps(raw_exif):
    """Decimal degrees from the EXIF GPS IFD; None when absent or implausible."""
    try:
        info = raw_exif.get_ifd(0x8825)
    except (KeyError, TypeError, ValueError):
        return None
    try:
        def degrees(dms, ref, positive, negative, limit):
            direction = (_text(ref) or '').upper()
            if direction not in (positive, negative):
                raise ValueError('missing or invalid GPS direction')
            d, m, sec = (float(x) for x in dms)
            if not all(math.isfinite(x) for x in (d, m, sec)) or not (0 <= d <= limit and 0 <= m < 60 and 0 <= sec < 60):
                raise ValueError('invalid GPS degrees/minutes/seconds')
            value = d + m / 60 + sec / 3600
            if value > limit:
                raise ValueError('GPS coordinate outside range')
            return -value if direction == negative else value
        lat = degrees(info[2], info.get(1), 'N', 'S', 90)
        lon = degrees(info[4], info.get(3), 'E', 'W', 180)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return round(lat, 6), round(lon, 6)


def prepare(downloads, directory):
    from PIL import Image, ImageOps, ExifTags
    destination = Path(directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    labels, tasks, failures = [], [], []
    inputs = records(downloads)
    ids = [item.get('asset_id') for item in inputs]
    if any(not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('missing or duplicate asset_id')
    for item in inputs:
        asset_id = item.get('asset_id')
        if not asset_id:
            raise ValueError('missing asset_id')
        if item.get('status') not in ('downloaded', 'local'):
            failures.append({'asset_id': asset_id, 'reason': 'download-not-successful'})
            continue
        file = Path(item.get('local_path') or '')
        if not item.get('local_path') or not file.is_file():
            failures.append({'asset_id': asset_id, 'reason': 'LOCAL_FILE_MISSING'})
            continue
        if file.stat().st_size == 0:
            failures.append({'asset_id': asset_id, 'reason': 'LOCAL_EMPTY_FILE'})
            continue
        expected_size = item.get('expected_size_bytes')
        if expected_size is not None and file.stat().st_size != expected_size:
            failures.append({'asset_id': asset_id, 'reason': 'LOCAL_SIZE_MISMATCH'})
            continue
        try:
            with Image.open(file) as image:
                raw_exif = image.getexif()
                exif = {ExifTags.TAGS.get(k, str(k)): v for k, v in raw_exif.items()}
                try:
                    exif.update({ExifTags.TAGS.get(k, str(k)): v for k, v in raw_exif.get_ifd(34665).items()})
                except (KeyError, TypeError, ValueError):
                    pass
                gps = _gps(raw_exif)
                im = ImageOps.exif_transpose(image).convert('RGB')
                width, height = im.size
                sample = im.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
                pixels = sample.load()
                dhash = 0
                for y in range(8):
                    for x in range(8):
                        dhash = (dhash << 1) | int(pixels[x, y] > pixels[x+1, y])
                small = im.copy()
                small.thumbnail((768, 768))
                thumb = destination / (hashlib.sha256(asset_id.encode()).hexdigest() + '.jpg')
                small.save(thumb, quality=80)
            h = hashlib.sha256()
            with file.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    h.update(chunk)
            if item.get('expected_sha256') and h.hexdigest() != item['expected_sha256']:
                failures.append({'asset_id': asset_id, 'reason': 'LOCAL_HASH_MISMATCH'})
                continue
            metadata = {'width': width, 'height': height, 'sha256': h.hexdigest(), 'size_bytes': file.stat().st_size,
                        'dhash64': f'{dhash:016x}', 'dhash_method': 'exif-oriented-dhash64-v1',
                        'content_source': 'cloud-download' if item['status'] == 'downloaded' else 'local-file'}
            for key, tag in (('camera_make', 271), ('camera_model', 272), ('software', 305)):
                if _text(raw_exif.get(tag)):
                    metadata[key] = _text(raw_exif.get(tag))
            if gps:
                metadata.update({'gps_lat': gps[0], 'gps_lon': gps[1], 'gps_source': 'exif'}, **geo_cells(*gps))
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
                           'index_state': {'metadata_source': 'local-file', 'updated_at': now()}})
            tasks.append({'asset_id': asset_id, 'thumbnail': str(thumb), 'original': str(file.resolve()),
                          'requested_fields': ['subjects', 'scene', 'actions', 'objects', 'image_type', 'ocr_text', 'people_count', 'quality'],
                          'instruction': 'Use visible evidence. Unknown fields are null; do not infer named identities, dates, or GPS.'})
        except (OSError, ValueError) as exc:
            failures.append({'asset_id': asset_id, 'reason': type(exc).__name__})
    from .manifest import write_manifest
    write_manifest(destination / 'metadata.labels.jsonl', labels)
    write_manifest(destination / 'vision.tasks.jsonl', tasks)
    failure_labels = [{'asset_id': f['asset_id'], 'index_state': {
        'status': 'error', 'error_code': f['reason'], 'error_message': 'Local media preparation failed: ' + f['reason']}}
        for f in failures]
    write_manifest(destination / 'failure.labels.jsonl', failure_labels)
    result = {'status': 'SUCCESS' if not failures else 'PARTIAL' if tasks else 'FAILED',
              'requested': len(inputs), 'media_complete': not failures and bool(inputs),
              'failure_labels': str(destination / 'failure.labels.jsonl'), 'prepared': len(tasks), 'failed': failures, 'metadata_labels': str(destination / 'metadata.labels.jsonl'),
              'vision_tasks': str(destination / 'vision.tasks.jsonl')}
    atomic(destination / 'report.json', result)
    return result
