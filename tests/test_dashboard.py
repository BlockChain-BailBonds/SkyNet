import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (BASE / 'static/index.html').read_text(encoding='utf-8')

    def test_standalone_copy_matches_backend(self):
        self.assertEqual(self.html, (BASE / 'SkyNet_918_Interactive_Google_Maps.html').read_text(encoding='utf-8'))

    def test_google_map_is_keyed_and_not_embedded_secret(self):
        self.assertIn('maps.googleapis.com/maps/api/js?', self.html)
        self.assertIn('key,loading:', self.html)
        self.assertIn('Use Google Maps', self.html)
        self.assertIn('Google Geocoding', self.html)
        self.assertNotIn('AIzaSy', self.html)

    def test_source_layers_and_read_only_data(self):
        for source in ['USGSShadedReliefOnly', 'MODIS_Terra_CorrectedReflectance_TrueColor',
                       'MODIS_Terra_Land_Surface_Temp_Day', 'GOES-East_ABI_Band13_Clean_Infrared',
                       '/api/scan?', '/api/ruview', '/api/evidence', 'GeoJSON', 'RuView']:
            self.assertIn(source, self.html)
        self.assertIn('No autonomous person detection', self.html)

    def test_attribution_and_no_fake_live_data(self):
        self.assertIn('Matthew Blake Ward', self.html)
        self.assertIn('918 Technologies', self.html)
        self.assertIn('DEMONSTRATION ONLY', self.html)
        self.assertIn('Cross-sensor object detection remains', self.html)
        self.assertIn('const state =', self.html)

    def test_dom_id_uniqueness(self):
        ids = re.findall(r'\bid="([^"]+)"', self.html)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == '__main__':
    unittest.main()
