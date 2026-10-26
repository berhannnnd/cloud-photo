"""Origin, folder and EXIF location indexing; run with: python3 -m unittest discover -s tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from cloud_photo_core import provenance, query, grouping, coverage  # noqa: E402

try:
    from PIL import Image
except ImportError:  # media extraction needs Pillow; pure rules do not.
    Image = None


def runner(*args):
    done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'index_runner.py'), *args],
                          capture_output=True, text=True)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout.strip().splitlines()[-1])


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def read_manifest(path):
    return {r['file_metadata']['name']: r for r in map(json.loads, path.read_text(encoding='utf-8').splitlines())}


class ClassifyTest(unittest.TestCase):
    def test_filename_rules(self):
        cases = {
            'Screenshot_20240301_002600_Gallery.jpg': 'screenshot',
            '截屏2024-03-01 10.00.00.png': 'screenshot',
            'mmexport1704040140425.jpg': 'wechat',
            '微信图片_20240301.jpg': 'wechat',
            'QQ图片20240301.jpg': 'qq',
            'PXL_20231231_235000_775.jpg': 'phone',
            'MVIMG_20231231_235600.jpg': 'phone',
            '_MG_3326.jpg': 'camera',
            'DSC_0012.JPG': 'camera',
            'IMG_8588.jpg': 'capture',
            'download (46).jpg': 'download',
            'wallpaper_235.jpg': None,
        }
        for name, kind in cases.items():
            with self.subTest(name=name):
                self.assertEqual(provenance.classify(name, '/照片/' + name)[0], kind)

    def test_path_rules(self):
        self.assertEqual(provenance.classify('a.jpg', '/备份/Download/a.jpg'), ('download', 'path:Download'))
        self.assertEqual(provenance.classify('a.jpg', '/手机/tencent/MicroMsg/a.jpg')[0], 'wechat')
        self.assertEqual(provenance.classify('a.jpg', '/手机/DCIM/a.jpg')[0], 'capture')
        self.assertEqual(provenance.classify('a.jpg', '/照片/a.jpg'), (None, None))

    def test_channel_beats_exif_and_exif_beats_name(self):
        self.assertEqual(provenance.classify('mmexport1.jpg', '/a/mmexport1.jpg', 'Apple', 'iPhone 15')[0], 'wechat')
        self.assertEqual(provenance.classify('IMG_0001.jpg', '/DCIM/IMG_0001.jpg', 'Apple', 'iPhone 15'),
                         ('phone', 'exif:make=Apple'))
        self.assertEqual(provenance.classify('IMG_0001.jpg', '/DCIM/IMG_0001.jpg', 'Canon', 'EOS R6')[0], 'camera')

    def test_folder(self):
        self.assertEqual(provenance.folder('/照片/2024/a.jpg'), '/照片/2024')
        self.assertEqual(provenance.folder('/a.jpg'), '/')
        self.assertIsNone(provenance.folder(''))


class GeoTest(unittest.TestCase):
    def test_geohash_reference_value(self):
        self.assertEqual(provenance.geohash(57.64911, 10.40744, 11), 'u4pruydqqvj')

    def test_cells_nest(self):
        cells = provenance.geo_cells(30.2741, 120.1551)  # Hangzhou
        self.assertEqual(set(cells), {'geo_cell_3', 'geo_cell_4', 'geo_cell_5'})
        self.assertTrue(cells['geo_cell_5'].startswith(cells['geo_cell_4']))
        self.assertTrue(cells['geo_cell_4'].startswith(cells['geo_cell_3']))

    def test_bbox_query_and_cell_grouping_use_existing_engine(self):
        rows = []
        for i, (lat, lon) in enumerate([(30.27, 120.15), (30.28, 120.16), (48.85, 2.35), (None, None)]):
            meta = {'gps_lat': lat, 'gps_lon': lon}
            if lat is not None:
                meta.update(provenance.geo_cells(lat, lon))
            rows.append({'asset_id': f'a{i}', 'file_metadata': meta})
        spec = query.validate({'all': [
            {'field': 'file_metadata.gps_lat', 'op': 'between', 'value': [30.0, 30.5]},
            {'field': 'file_metadata.gps_lon', 'op': 'between', 'value': [119.9, 120.5]},
        ]})
        self.assertEqual([query.evaluate(r, spec) for r in rows], [True, True, False, None])
        groups = grouping.group(rows, ['file_metadata.geo_cell_4'])
        self.assertEqual(sorted(len(g['asset_ids']) for g in groups), [1, 1, 2])
        self.assertIn('待归类', [g['name'] for g in groups])


class IndexFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ingest(self, items):
        write_jsonl(self.dir / 'listing.jsonl', items)
        runner('ingest', '--input', str(self.dir / 'listing.jsonl'), '--output-dir', str(self.dir / 'idx'))
        return self.dir / 'idx' / 'manifest.jsonl'

    def test_ingest_sets_folder_and_source(self):
        manifest = self.ingest([
            {'fileRef': 'r1', 'name': 'mmexport1704040140425.jpg', 'path': '/照片/微信/mmexport1704040140425.jpg', 'size': 10, 'updatedAt': '2024-01-01T00:00:00Z'},
            {'fileRef': 'r2', 'name': 'wallpaper_1.jpg', 'path': '/壁纸/wallpaper_1.jpg', 'size': 11, 'updatedAt': '2024-01-01T00:00:00Z'},
        ])
        rows = read_manifest(manifest)
        wechat = rows['mmexport1704040140425.jpg']['file_metadata']
        self.assertEqual((wechat['folder'], wechat['source_kind']), ('/照片/微信', 'wechat'))
        self.assertEqual(wechat['source_evidence'], 'filename:mmexport')
        unknown = rows['wallpaper_1.jpg']['file_metadata']
        self.assertEqual((unknown['folder'], unknown['source_kind']), ('/壁纸', None))
        spec = query.validate({'field': 'file_metadata.folder', 'op': 'contains', 'value': '微信'})
        self.assertEqual(query.evaluate(rows['mmexport1704040140425.jpg'], spec), True)
        report = coverage.field_coverage(list(rows.values()))
        self.assertEqual(report['file_metadata.source_kind'], {'populated': 1, 'unknown': 1})

    def test_exif_apply_refines_source_and_reingest_keeps_it(self):
        listing = [{'fileRef': 'r1', 'name': 'IMG_0001.jpg', 'path': '/手机/DCIM/IMG_0001.jpg', 'size': 10, 'updatedAt': '2024-01-01T00:00:00Z'}]
        manifest = self.ingest(listing)
        row = read_manifest(manifest)['IMG_0001.jpg']
        self.assertEqual(row['file_metadata']['source_kind'], 'capture')
        write_jsonl(self.dir / 'labels.jsonl', [{'asset_id': row['asset_id'], 'file_metadata': {'camera_make': 'HUAWEI', 'camera_model': 'P60'}}])
        runner('apply', '--manifest', str(manifest), '--labels', str(self.dir / 'labels.jsonl'))
        meta = read_manifest(manifest)['IMG_0001.jpg']['file_metadata']
        self.assertEqual((meta['source_kind'], meta['source_evidence']), ('phone', 'exif:make=HUAWEI'))
        self.ingest(listing)  # unchanged listing re-scan must not downgrade EXIF evidence
        self.assertEqual(read_manifest(manifest)['IMG_0001.jpg']['file_metadata']['source_kind'], 'phone')


@unittest.skipIf(Image is None, 'Pillow not installed')
class MediaExifTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def photo(self, name, gps=None, make=None, model=None):
        image = Image.new('RGB', (64, 48), (120, 160, 200))
        exif = Image.Exif()
        if make:
            exif[271], exif[272] = make, model
        if gps:
            info = exif.get_ifd(0x8825)
            info[1], info[2], info[3], info[4] = gps
        path = self.dir / f'{name}.jpg'
        image.save(path, exif=exif)
        return path

    def prepare(self, paths):
        from cloud_photo_core import media
        write_jsonl(self.dir / 'downloads.jsonl', [{'asset_id': p.stem, 'status': 'local', 'local_path': str(p)} for p in paths])
        media.prepare(self.dir / 'downloads.jsonl', self.dir / 'media')
        return {r['asset_id']: r['file_metadata'] for r in map(json.loads, (self.dir / 'media' / 'metadata.labels.jsonl').read_text().splitlines())}

    def test_gps_camera_and_cells(self):
        meta = self.prepare([
            self.photo('hz', ('N', (30.0, 16.0, 26.76), 'E', (120.0, 9.0, 18.36)), 'Apple', 'iPhone 15'),
            self.photo('rio', ('S', (22.0, 54.0, 0.0), 'W', (43.0, 12.0, 0.0))),
            self.photo('plain'),
        ])
        hz = meta['hz']
        self.assertAlmostEqual(hz['gps_lat'], 30.274100, places=5)
        self.assertAlmostEqual(hz['gps_lon'], 120.155100, places=5)
        self.assertEqual((hz['gps_source'], hz['camera_make'], hz['camera_model']), ('exif', 'Apple', 'iPhone 15'))
        self.assertEqual(hz['geo_cell_5'], provenance.geo_cells(hz['gps_lat'], hz['gps_lon'])['geo_cell_5'])
        self.assertLess(meta['rio']['gps_lat'], 0)
        self.assertLess(meta['rio']['gps_lon'], 0)
        self.assertNotIn('gps_lat', meta['plain'])
        self.assertNotIn('camera_make', meta['plain'])

    def test_null_island_is_rejected(self):
        meta = self.prepare([self.photo('zero', ('N', (0.0, 0.0, 0.0), 'E', (0.0, 0.0, 0.0)))])
        self.assertNotIn('gps_lat', meta['zero'])


if __name__ == '__main__':
    unittest.main()
