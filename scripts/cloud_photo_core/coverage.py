"""Report observable field population independently of processing status."""


def field_coverage(rows):
    fields = (
        'file_metadata.taken_at', 'file_metadata.sha256', 'file_metadata.dhash64',
        'file_metadata.gps_lat', 'file_metadata.camera_model', 'file_metadata.source_kind',
        'vision_tags.subjects', 'vision_tags.scene', 'vision_tags.image_type',
        'vision_tags.people', 'vision_tags.quality', 'vision_tags.ocr_text',
    )
    result = {}
    for field in fields:
        group, key = field.split('.')
        known = sum(row.get(group, {}).get(key) not in (None, '', []) for row in rows)
        result[field] = {'populated': known, 'unknown': len(rows) - known}
    return result
