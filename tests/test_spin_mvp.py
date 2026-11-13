import json, sys, unittest
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from forecast.pipeline import load_json, usgs, nws, ValidationError
from alerts.engine import publish
from pocket.simulator.device import SimulatedPocket, ReplayError

class ForecastTests(unittest.TestCase):
    def test_usgs_event_normalizes_with_metadata(self):
        e=usgs(load_json(ROOT/'forecast/fixtures/usgs.json'))[0]
        self.assertEqual((e['magnitude'],e['depth_km'],e['source']),(4.2,10,'USGS'))
        self.assertEqual(e['geometry']['coordinates'],[-118.2,34.1])
    def test_nws_warning_produces_scoped_alert(self):
        events=nws(load_json(ROOT/'forecast/fixtures/nws.json'))
        alerts=publish(events,datetime(2026,1,1,0,30,tzinfo=timezone.utc))
        self.assertEqual(alerts[0]['area'],'Test County'); self.assertEqual(alerts[0]['cap']['scope'],'Public')
    def test_duplicate_and_expired_rejected(self):
        event=nws(load_json(ROOT/'forecast/fixtures/nws.json'))[0]
        self.assertEqual(len(publish([event,event],datetime(2026,1,1,0,30,tzinfo=timezone.utc))),1)
        self.assertEqual(publish([event],datetime(2026,1,1,2,tzinfo=timezone.utc)),[])
    def test_bad_timestamps_and_schema_rejected(self):
        bad=load_json(ROOT/'forecast/fixtures/nws.json'); bad['features'][0]['properties']['sent']='yesterday'
        with self.assertRaises(ValidationError): nws(bad)
        with self.assertRaises(ValidationError): usgs({'features':[]})

class PocketTests(unittest.TestCase):
    def test_signature_replay_and_ack(self):
        d=SimulatedPocket(b'x'*32); m=d.sign({'heartbeat':'ok'},timestamp=1000,nonce='n')
        self.assertTrue(d.verify(m,current_time=1000))
        with self.assertRaises(ReplayError): d.verify(m,current_time=1000)
        m2=dict(d.sign({'x':1},timestamp=1000)); m2['signature']='00'
        self.assertFalse(d.verify(m2,current_time=1000))
        self.assertEqual(d.acknowledge('a')['evidence'],'SIMULATED')

class FrontendTests(unittest.TestCase):
    def test_single_entry_views_and_no_credentials(self):
        html=(ROOT/'index.html').read_text(); js=(ROOT/'static/assets/spin.js').read_text()
        for view in ('command','map','agent','forecast','quake','storm','flood','fire','space','sensor','pocket','alerts','history','health','settings'): self.assertIn(f'id="{view}"',html)
        self.assertNotIn('github_pat_',html+js); self.assertNotIn('AIzaSy',html+js)
        self.assertIn('safe(',js)
    def test_manifest_and_evidence_labels(self):
        manifest=json.loads((ROOT/'agent/model-manifest.json').read_text())
        self.assertIn('1B',manifest['models'][0]['name']); self.assertEqual(manifest['transformers_js']['version'],'3.8.1')
        statuses={x['evidence_status'] for x in json.loads((ROOT/'data/public/latest-forecasts.json').read_text())}
        self.assertIn('SIMULATED',statuses); self.assertIn('BLOCKED',statuses)
if __name__=='__main__': unittest.main()
