"""Deterministic photo origin, folder and coarse location cells from observable evidence.

Rules only read filenames, cloud paths and EXIF camera fields. Anything that no
rule recognises stays unknown; nothing here guesses from image content.
"""
import re

# Ordered: channel rules (screenshot / chat apps / downloads) win over camera
# evidence, because a photo saved from WeChat is still a WeChat image even when
# its original EXIF survived.
NAME_RULES = (
    ('screenshot', re.compile(r'^(screenshot|screen ?shot|scrnli_|snipaste)|截屏|截图|屏幕截图', re.I)),
    ('wechat', re.compile(r'^(mmexport|wx_camera_|微信图片_)', re.I)),
    ('qq', re.compile(r'^(qq图片|qq_pic_|tim图片)', re.I)),
    ('download', re.compile(r'^download(\s*\(\d+\))?\.', re.I)),
    ('phone', re.compile(r'^(pxl_|mvimg_|img_\d{8}_\d{6}|\d{8}_\d{6})', re.I)),
    ('camera', re.compile(r'^(_mg_|dsc[_f]?|_dsc|p\d{7}|dji_)', re.I)),
    ('capture', re.compile(r'^img_\d{4}', re.I)),
)
PATH_RULES = (
    ('screenshot', re.compile(r'/(screenshots?|截屏|截图|屏幕截图)(/|$)', re.I)),
    ('wechat', re.compile(r'/(weixin|wechat|micromsg|微信)(/|$)', re.I)),
    ('qq', re.compile(r'/(qq|qq_images|tim)(/|$)', re.I)),
    ('download', re.compile(r'/(downloads?|下载)(/|$)', re.I)),
    ('capture', re.compile(r'/(dcim|camera|相机|相机胶卷)(/|$)', re.I)),
)
PHONE_MAKES = {
    'apple', 'huawei', 'honor', 'xiaomi', 'redmi', 'oppo', 'vivo', 'oneplus', 'realme', 'samsung',
    'google', 'meizu', 'motorola', 'zte', 'nubia', 'iqoo', 'lenovo', 'sony mobile', 'nothing',
}
CHANNELS = {'screenshot', 'wechat', 'qq', 'download'}
GEOHASH = '0123456789bcdefghjkmnpqrstuvwxyz'
CELL_PRECISIONS = (3, 4, 5)  # ~156km, ~39km, ~5km cells


def folder(path):
    if not isinstance(path, str) or not path.startswith('/'):
        return None
    head = path.rsplit('/', 1)[0]
    return head or '/'


def classify(name, path, make=None, model=None):
    """Return (source_kind, evidence); (None, None) when no rule applies."""
    name = name or (path.rsplit('/', 1)[-1] if isinstance(path, str) else '')
    by_name = next(((kind, f'filename:{m.group(0)}') for kind, rule in NAME_RULES for m in [rule.search(name)] if m), None)
    by_path = next(((kind, f'path:{m.group(1)}') for kind, rule in PATH_RULES for m in [rule.search(path or '')] if m), None)
    for hit in (by_name, by_path):
        if hit and hit[0] in CHANNELS:
            return hit
    make_text = str(make or '').strip()
    if make_text:
        lowered = make_text.casefold()
        is_phone = lowered in PHONE_MAKES or 'iphone' in str(model or '').casefold()
        return ('phone' if is_phone else 'camera'), f'exif:make={make_text}'
    for hit in (by_name, by_path):
        if hit:
            return hit
    return None, None


def annotate(metadata, path):
    """Recompute derived origin fields in place from the merged record."""
    metadata['folder'] = folder(path)
    kind, evidence = classify(metadata.get('name'), path, metadata.get('camera_make'), metadata.get('camera_model'))
    metadata['source_kind'] = kind
    metadata['source_evidence'] = evidence
    return metadata


def geohash(lat, lon, precision):
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    out, bits, value, even = [], 0, 0, True
    while len(out) < precision:
        rng, coord = (lon_range, lon) if even else (lat_range, lat)
        mid = (rng[0] + rng[1]) / 2
        value <<= 1
        if coord >= mid:
            value |= 1
            rng[0] = mid
        else:
            rng[1] = mid
        even, bits = not even, bits + 1
        if bits == 5:
            out.append(GEOHASH[value])
            bits, value = 0, 0
    return ''.join(out)


def geo_cells(lat, lon):
    full = geohash(lat, lon, max(CELL_PRECISIONS))
    return {f'geo_cell_{p}': full[:p] for p in CELL_PRECISIONS}
