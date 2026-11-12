import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class SkyNetBrandingTests(unittest.TestCase):
    def test_project_metadata_attribution(self):
        metadata=json.loads((Path(__file__).resolve().parents[1]/'PROJECT_METADATA.json').read_text())
        self.assertEqual(metadata['project_name'], 'SkyNet')
        self.assertEqual(metadata['intellectual_property_attribution'],
                         'Intellectual property by Matthew Blake Ward, in association with 918 Technologies.')
        self.assertIn('third-party', metadata['upstream_sensor_software'].lower())

    def test_attribution_and_dependency_notice(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIn('Matthew Blake Ward', (root/'IP_NOTICE.md').read_text())
        self.assertIn('RuView', (root/'THIRD_PARTY_NOTICES.md').read_text())
        self.assertIn('SkyNet', (root/'static/index.html').read_text())


class ValidationTests(unittest.TestCase):
    def test_reject_bad_geopoint(self):
        for p in [{'lat':['NaN'],'lon':['2']}, {'lat':['91'],'lon':['2']},
                  {'lat':['0'],'lon':['180.1']}, {'lat':['0'],'lon':['0'],'radius_km':['100']}]:
            with self.subTest(p=p), self.assertRaises(ValueError):
                server.geo_point(p)

    def test_bbox_valid(self):
        numbers = [float(x) for x in server.geo_bbox(39, -98, 5).split(',')]
        self.assertEqual(len(numbers), 4)
        self.assertTrue(numbers[0] < -98 < numbers[2])
        self.assertTrue(numbers[1] < 39 < numbers[3])

    def test_ruview_target_restricted(self):
        for u in ['http://evil.example:3000','https://127.0.0.1:3000',
                  'http://user:pw@127.0.0.1:3000','http://8.8.8.8:3000',
                  'http://127.0.0.1:3000/path']:
            with self.subTest(url=u), self.assertRaises(ValueError):
                server.validate_ruview_url(u)
        server.validate_ruview_url('http://127.0.0.1:3000')
        server.validate_ruview_url('http://192.168.1.5:3000', True)
        with self.assertRaises(ValueError):
            server.validate_ruview_url('http://192.168.1.5:3000', False)

    def test_snapshot_marks_simulation_and_unverified_signatures(self):
        def stub(url, extra_headers=None):
            if url.endswith('/health'):
                return {'status':'ok','source':'simulated'}, '0'*64
            if url.endswith('/api/field'):
                return {'events':[{'hello':'world'}], 'dev_signing_key': True,
                        'signer_pubkey_hex':'0011'}, '1'*64
            if url.endswith('/api/v1/mesh'):
                return {'nodes':{'a':{}}}, '2'*64
            return {'motion_score':0.5}, '3'*64
        with patch.object(server, 'fetch_json', side_effect=stub):
            snapshot = server.ruview_snapshot()
        self.assertEqual(snapshot['health']['state'], 'SIMULATED')
        self.assertEqual(snapshot['field']['state'], 'UNVERIFIED')
        self.assertEqual(snapshot['mesh']['data']['node_count'], 1)
        self.assertNotIn('hello', json.dumps(snapshot))

    def test_provenance_only_public_and_no_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, 'DATA_DIR', Path(tmp)), patch.object(server, 'AUDIT_FILE', Path(tmp)/'log.jsonl'):
                server.audit_public_results(40, -100, {'elevation':server.status('test','VERIFIED', 'ok', {'something_private':'should_not_log'},'a'*64)})
                lines = (Path(tmp)/'log.jsonl').read_text()
                self.assertNotIn('something_private', lines)
                self.assertEqual(len(server.evidence()), 1)
                self.assertEqual(server.evidence()[0]['sha256'], 'a'*64)

    def test_point_elevation_parse_and_hash(self):
        with patch.object(server, 'fetch_json', return_value=({'value': 308.17}, 'd'*64)):
            result = server.elevation(39, -98)
        self.assertEqual(result['state'], 'VERIFIED')
        self.assertEqual(result['data']['elevation_m'], 308.17)
        self.assertIn('not proof', result['note'])

    def test_public_feeds_fail_independently(self):
        def get_json(url):
            raise TimeoutError('timeout')
        with patch.object(server, 'fetch_json', side_effect=get_json):
            r = server.lidar_catalog(39,-98,5)
            self.assertEqual(r['state'], 'BLOCKED')
            self.assertIsNone(r['sha256'])

    def test_scan_separates_public_feeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, 'DATA_DIR', Path(tmp)), patch.object(server, 'AUDIT_FILE', Path(tmp)/'log.jsonl'),\
                 patch.object(server, 'elevation', return_value=server.status('e','VERIFIED','ok',sha256='0'*64)),\
                 patch.object(server, 'lidar_catalog', return_value=server.status('l','BLOCKED','unavailable')),\
                 patch.object(server, 'sentinel_catalog', return_value=server.status('s','VERIFIED','ok',sha256='1'*64)),\
                 patch.object(server, 'fires', return_value=server.status('f','BLOCKED','no key')):
                s = server.scan(39,-98,5)
                self.assertEqual(s['cross_sensor_detection'], 'UNVERIFIED')
                self.assertEqual(len(server.evidence()),4)
                self.assertEqual(s['results']['lidar']['state'], 'BLOCKED')

if __name__ == '__main__':
    unittest.main()
