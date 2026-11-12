import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from threading import Thread
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from optin import EnrollmentError, EnrollmentRegistry, CONSENT_VERSION
import server


class DeterministicClock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock()
        self.registry = EnrollmentRegistry(clock=self.clock)
        self.invite = self.registry.create_invite({'lat': 36.15, 'lon': -95.99,
            'label': 'Voluntary test site', 'radius_m': 150, 'ruview_node_ids': ['lab-1']})
        self.start_payload = {'invite_token': self.invite['invite_token'],
            'consent_version': CONSENT_VERSION, 'accept': True, 'allow_location': True,
            'allow_motion': True, 'physically_at_site': True,
            'lat': 36.15, 'lon': -95.99, 'accuracy_m': 20}

    def test_invitation_is_opaque_single_use_and_expires(self):
        self.assertRegex(self.invite['invite_token'], r'^[A-Za-z0-9_-]{24,128}$')
        self.assertNotIn('36.15', self.invite['invite_token'])
        info = self.registry.invitation_info(self.invite['invite_token'])
        self.assertEqual(info['consent_version'], CONSENT_VERSION)
        self.assertNotIn('phone_number', json.dumps(info).lower())
        self.registry.enroll(self.start_payload)
        with self.assertRaises(EnrollmentError):
            self.registry.enroll(self.start_payload)

    def test_expired_invitation_rejected(self):
        self.clock.advance(901)
        with self.assertRaises(EnrollmentError):
            self.registry.invitation_info(self.invite['invite_token'])
        with self.assertRaises(EnrollmentError):
            self.registry.enroll(self.start_payload)

    def test_reject_consent_substitutions(self):
        for key, bad in [('accept', False), ('allow_location', False),
                         ('allow_motion', False), ('physically_at_site', False),
                         ('consent_version', 'skynet-old-version')]:
            with self.subTest(key=key), self.assertRaises(EnrollmentError):
                self.registry.enroll({**self.start_payload, key: bad})

    def test_reject_remote_or_inaccurate_reported_location(self):
        for delta, accuracy in [(0.05, 10), (0, 101), (0.001, 100)]:
            with self.subTest(delta=delta, accuracy=accuracy), self.assertRaises(EnrollmentError):
                self.registry.enroll({**self.start_payload, 'lat': 36.15 + delta, 'accuracy_m': accuracy})

    def test_accept_aggregate_then_stop_and_revoke(self):
        result = self.registry.enroll(self.start_payload)
        self.assertEqual(result['hardware_status'], 'UNVERIFIED')
        self.assertEqual(result['location_status'], 'SELF_REPORTED_WITHIN_ZONE')
        first = self.registry.site_status(result['site_id'])
        self.assertEqual(first['consenting_sessions_active'], 1)
        self.assertEqual(first['devices_reporting_motion'], 0)
        self.clock.advance(5)
        self.registry.sample({'session_token': result['session_token'], 'samples': 8, 'motion_rms': 1.34})
        current = self.registry.site_status(result['site_id'])
        self.assertEqual(current['devices_reporting_motion'], 1)
        self.assertEqual(current['total_motion_samples'], 8)
        self.assertNotIn('device_location', current)
        self.assertTrue(self.registry.stop({'session_token': result['session_token']})['revoked'])
        self.assertEqual(self.registry.site_status(result['site_id'])['consenting_sessions_active'], 0)
        with self.assertRaises(EnrollmentError):
            self.registry.sample({'session_token': result['session_token'], 'samples': 1, 'motion_rms': 1})

    def test_heartbeat_without_motion_not_claimed_as_detection(self):
        result = self.registry.enroll(self.start_payload)
        self.clock.advance(5)
        update = self.registry.sample({'session_token': result['session_token'], 'samples': 0, 'motion_rms': None})
        self.assertEqual(update['state'], 'NO_MOTION_SAMPLES')
        self.assertEqual(self.registry.site_status(result['site_id'])['devices_reporting_motion'], 0)
        self.clock.advance(17)
        self.assertEqual(self.registry.site_status(result['site_id'])['consenting_sessions_active'], 0)

    def test_old_sites_reclaimed_after_expiry(self):
        self.clock.advance(4501)
        other = self.registry.create_invite({'label':'Second site', 'lat': 36.15, 'lon': -95.99})
        self.assertNotIn(self.invite['site_id'], self.registry.sites)
        self.assertIn(other['site_id'], self.registry.sites)

    def test_validation_and_ratelimits(self):
        with self.assertRaises(EnrollmentError):
            self.registry.create_invite({'lat': 'nan', 'lon': 0, 'label':'Site'})
        result = self.registry.enroll(self.start_payload)
        with self.assertRaises(EnrollmentError):
            self.registry.sample({'session_token': result['session_token'], 'samples': 1, 'motion_rms': 1})
        self.clock.advance(2)
        for payload in [{'samples': -1, 'motion_rms': 1}, {'samples': 1, 'motion_rms': 1e300},
                        {'samples': 0, 'motion_rms': 1}, {'samples': 201, 'motion_rms': 1}]:
            with self.subTest(payload=payload), self.assertRaises(EnrollmentError):
                self.registry.sample({'session_token': result['session_token'], **payload})


class URLAndFrontendTests(unittest.TestCase):
    def test_public_https_origin_only(self):
        for raw in ('http://example.com', 'https://localhost', 'https://192.168.1.1',
                    'https://a.example/path', 'https://a.example:8443', 'https://user:pass@example.com'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                server.validate_public_url(raw)
        self.assertEqual(server.validate_public_url('https://skynet.example.com'), 'https://skynet.example.com')

    def test_browser_consent_and_sms_links_present(self):
        root = (ROOT / 'static/index.html').read_text()
        join = (ROOT / 'static/join.html').read_text()
        for term in ['sms:', 'smsCompose', 'copyInvite', 'createInvite', 'X-SkyNet-Admin-Token', 'siteRefresh', 'invite_url']:
            self.assertIn(term, root)
        for term in ['requestPermission()', 'getCurrentPosition', 'visibilitychange',
                     'sendBeacon', 'Stop sharing now', 'devicemotion', 'consent_version']:
            self.assertIn(term, join)
        self.assertNotIn('https://unpkg.com', join)
        self.assertNotIn('<script src=', join)
        self.assertEqual(len(re.findall(r'\bid="([^"]+)"', join)), len(set(re.findall(r'\bid="([^"]+)"', join))))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.srv.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(timeout=3)

    def request(self, path, payload=None, admin=None):
        headers = {}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        if admin is not None:
            headers['X-SkyNet-Admin-Token'] = admin
        req = Request(self.origin + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            with urlopen(req, timeout=5) as r:
                return r.status, r.read(), dict(r.headers)
        except HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_public_join_route_and_protected_admin_invite(self):
        status, body, headers = self.request('/join')
        self.assertEqual(status, 200)
        self.assertIn(b'Agree &amp; start sensor', body)
        self.assertEqual(headers.get('Referrer-Policy'), 'no-referrer')
        with patch.object(server, 'ADMIN_TOKEN', 'test-' + 'x' * 32), patch.object(server, 'PUBLIC_URL', 'https://skynet.example.org'):
            status, body, _ = self.request('/api/sites/invite', {'label':'Consent test', 'lat':36.15, 'lon':-95.99})
            self.assertEqual(status, 403)
            status, body, _ = self.request('/api/sites/invite', {'label':'Consent test', 'lat':36.15, 'lon':-95.99}, 'test-' + 'x'*32)
            self.assertEqual(status, 201)
            result = json.loads(body)
            self.assertTrue(result['invite_url'].startswith('https://skynet.example.org/join#invite='))
            self.assertEqual(result['delivery'], 'OPERATOR_SMS_COMPOSER_ONLY')
            status, info, _ = self.request('/api/enroll/info?invite=' + result['invite_token'])
            self.assertEqual(status, 200)
            self.assertIn(b'not_collected', info)
            status, body, _ = self.request('/api/sites/status?site_id=' + result['site_id'])
            self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main()
