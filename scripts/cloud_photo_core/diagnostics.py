"""Local runtime probes; never imply that client delivery was tested."""
import importlib.util
import platform
import sys
import tempfile
from pathlib import Path


def check(directory):
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.cloud-photo-check-', dir=root) as temporary:
        probe = Path(temporary) / 'probe'
        probe.write_text('cloud-photo', encoding='utf-8')
        writable = probe.read_text(encoding='utf-8') == 'cloud-photo'
    report = {'python': platform.python_version(), 'executable': sys.executable,
              'python_supported': sys.version_info >= (3, 10), 'state_writable': writable,
              'pillow_available': importlib.util.find_spec('PIL') is not None,
              'host_visual_model': 'unverified', 'client_media_delivery': 'unverified',
              'cross_session_resume': 'unverified', 'formats': []}
    if report['pillow_available']:
        from PIL import Image, __version__
        Image.init()
        report['pillow_version'] = __version__
        report['pillow_supported'] = tuple(int(part) for part in __version__.split('.')[:2]) >= (9, 1)
        report['formats'] = sorted(Image.OPEN)
    report['local_ready'] = report['python_supported'] and writable and report.get('pillow_supported', False)
    return report
