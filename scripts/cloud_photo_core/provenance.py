"""Deterministic photo origin, folder and coarse location cells from observable evidence.

Rules only read filenames, cloud paths and EXIF camera fields. Anything that no
rule recognises stays unknown; nothing here guesses from image content.
"""
import re

# Filename and folder matches are hints, not proof of capture or transfer history.
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
# Deliberately narrow model families: a manufacturer can sell several device types.
DEVICE_RULES = (
    ('phone', r'apple', r'iphone(?:\s|\d)'),
    ('phone', r'samsung', r'(?:sm-|gt-i|galaxy)'),
    ('camera', r'samsung', r'(?:nx|wb|st|ex)\d'),
    ('phone', r'sony(?: mobile)?', r'(?:xperia|xq-|sov|so-\d)'),
    ('camera', r'sony', r'(?:ilce-|ilca-|dsc-|nex-|slt-)'),
    ('phone', r'google', r'pixel'),
    ('phone', r'huawei', r'(?:p\d|mate\s|nova\s)'),
    ('camera', r'canon', r'(?:canon\s+)?(?:eos|powershot|ixus)'),
    ('camera', r'nikon', r'(?:nikon\s+)?(?:d\d|z\s?\d|coolpix)'),
)
CHANNELS = {'screenshot', 'wechat', 'qq', 'download'}
GEOHASH = '0123456789bcdefghjkmnpqrstuvwxyz'
CELL_PRECISIONS = (3, 4, 5)  # ~156km, ~39km, ~5km cells


def folder(path):
    if not isinstance(path, str) or not path.startswith('/'):
        return None
    head = path.rsplit('/', 1)[0]
    return head or '/'


def origins(name, path, make=None, model=None):
    """Separate device and channel hints, retaining evidence rather than claiming origin."""
    name = name or (path.rsplit('/', 1)[-1] if isinstance(path, str) else '')
    hits = [(kind, f'{source}:{match.group(0)}')
            for source, rules, value in (('filename', NAME_RULES, name), ('path', PATH_RULES, path or ''))
            for kind, rule in rules for match in [rule.search(value)] if match]
    # Keep the legacy path evidence spelling.
    hits = [(kind, evidence.replace('path:/', 'path:').rstrip('/') if evidence.startswith('path:') else evidence)
            for kind, evidence in hits]
    channel = next((hit for hit in hits if hit[0] in CHANNELS), (None, None))
    make_text, model_text = str(make or '').strip(), str(model or '').strip()
    device = (None, None)
    if make_text or model_text:
        kind = next((kind for kind, maker, family in DEVICE_RULES
                     if re.fullmatch(maker, make_text, re.I) and re.match(family, model_text, re.I)), 'capture')
        device = (kind, f'exif:make={make_text};model={model_text}')
    else:
        hit = next((hit for hit in hits if hit[0] not in CHANNELS), None)
        if hit:
            # Naming conventions alone do not establish the physical device type.
            device = ('capture', hit[1])
    return device, channel


def classify(name, path, make=None, model=None):
    """Legacy mixed field: channel first, otherwise device; prefer origins for new queries."""
    device, channel = origins(name, path, make, model)
    return channel if channel[0] else device


def annotate(metadata, path):
    """Recompute derived hints in place from the merged record."""
    metadata['folder'] = folder(path)
    device, channel = origins(metadata.get('name'), path, metadata.get('camera_make'), metadata.get('camera_model'))
    for prefix, result in (('capture_device', device), ('save_channel', channel)):
        metadata[prefix] = result[0]
        metadata[prefix + '_evidence'] = result[1]
        metadata[prefix + '_basis'] = 'rule-inference' if result[0] else None
    metadata['source_kind'], metadata['source_evidence'] = channel if channel[0] else device
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
