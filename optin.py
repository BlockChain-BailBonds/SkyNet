"""SkyNet ephemeral opt-in enrollment registry.

No persistent identifying records, location traces, raw accelerometer values,
CSI samples, microphones, camera streams, or device IDs are stored here.
Sensor presence is never proof that a person or RuView radio is at the site.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
import secrets
import threading
import time
from datetime import datetime, timezone

CONSENT_VERSION = 'skynet-motion-v1.0'
INVITE_LIFETIME_SECONDS = 900
SESSION_LIFETIME_SECONDS = 1800
HEARTBEAT_WINDOW_SECONDS = 16
MAX_GPS_ACCURACY_M = 100.0
MAX_SITES = 100
MAX_SESSIONS = 500


class EnrollmentError(ValueError):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.http_status = code


def coordinates(lat: object, lon: object) -> tuple[float, float]:
    try:
        a, b = float(lat), float(lon)
    except (TypeError, ValueError) as exc:
        raise EnrollmentError('Valid latitude and longitude are required') from exc
    if not all(map(math.isfinite, (a, b))) or not -90 <= a <= 90 or not -180 <= b <= 180:
        raise EnrollmentError('Coordinates are out of range')
    return a, b


def distance_m(a: float, b: float, c: float, d: float) -> float:
    """Haversine distance; location remains self-reported and spoofable."""
    phi1, phi2 = math.radians(a), math.radians(c)
    dp, dl = phi2 - phi1, math.radians(d - b)
    h = math.sin(dp / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(min(1.0, math.sqrt(h)))


def digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def ensure_object(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise EnrollmentError('Request must be a JSON object')
    return payload


def str_token(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{24,128}', value):
        raise EnrollmentError('Invalid enrollment token', 403)
    return value


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec='seconds')


class EnrollmentRegistry:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.sites: dict[str, dict] = {}
        self.invites: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}

    def _cleanup(self, now: float) -> None:
        for key, invitation in list(self.invites.items()):
            if invitation['expires'] <= now or invitation['consumed']:
                del self.invites[key]
        for key, session in list(self.sessions.items()):
            if session['expires'] <= now or session['revoked'] or now - session['last_seen'] > 60:
                del self.sessions[key]
        referenced = {invitation['site_id'] for invitation in self.invites.values()}
        referenced.update(session['site_id'] for session in self.sessions.values())
        for site_id, site in list(self.sites.items()):
            if site_id not in referenced and now - site['created'] > INVITE_LIFETIME_SECONDS + SESSION_LIFETIME_SECONDS:
                del self.sites[site_id]

    def create_invite(self, payload: object) -> dict:
        obj = ensure_object(payload)
        lat, lon = coordinates(obj.get('lat'), obj.get('lon'))
        label = obj.get('label', '')
        if not isinstance(label, str) or not 3 <= len(label.strip()) <= 120 or any(ord(c) < 32 for c in label):
            raise EnrollmentError('Site label must be 3–120 printable characters')
        try:
            radius_m = float(obj.get('radius_m', 150))
        except (TypeError, ValueError) as exc:
            raise EnrollmentError('Invalid site radius') from exc
        if not math.isfinite(radius_m) or not 100 <= radius_m <= 500:
            raise EnrollmentError('Site radius must be 100–500 meters')
        ids = obj.get('ruview_node_ids', [])
        if not isinstance(ids, list) or len(ids) > 12 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,48}', v) for v in ids):
            raise EnrollmentError('RuView node IDs must be up to 12 short labels')
        now = self.clock()
        with self.lock:
            self._cleanup(now)
            if len(self.sites) >= MAX_SITES:
                raise EnrollmentError('Site capacity reached; restart or archive a deployment', 503)
            site_id = secrets.token_urlsafe(15)
            invitation = secrets.token_urlsafe(32)
            self.sites[site_id] = {'id': site_id, 'lat': lat, 'lon': lon,
                                   'label': label.strip(), 'radius_m': radius_m,
                                   'node_ids': sorted(set(ids)), 'created': now,
                                   'invite_count': 1}
            self.invites[digest(invitation)] = {'site_id': site_id, 'expires': now + INVITE_LIFETIME_SECONDS,
                                                'consumed': False}
            return {'site_id': site_id, 'invite_token': invitation,
                    'expires_at_utc': iso(now + INVITE_LIFETIME_SECONDS),
                    'radius_m': radius_m,
                    'ruview_binding': 'UNVERIFIED' if ids else 'BLOCKED',
                    'note': 'One-use enrollment invitation. Shared invite tokens are bearer secrets.'}

    def invitation_info(self, token: object) -> dict:
        now = self.clock()
        key = digest(str_token(token))
        with self.lock:
            entry = self.invites.get(key)
            if not entry or entry['consumed'] or entry['expires'] <= now:
                raise EnrollmentError('Invitation expired, used, or invalid', 403)
            site = self.sites[entry['site_id']]
            return {'site_label': site['label'], 'radius_m': site['radius_m'],
                    'expires_at_utc': iso(entry['expires']),
                    'permitted_data': ['one-time device geolocation (checked, then discarded)',
                                       'acceleration-derived motion RMS every ~4 seconds',
                                       'sensor sample count and heartbeat'],
                    'not_collected': ['name', 'camera', 'microphone', 'raw GPS trail',
                                      'Wi-Fi traffic', 'Wi-Fi CSI', 'identifying device data'],
                    'consent_version': CONSENT_VERSION}

    def enroll(self, payload: object) -> dict:
        obj = ensure_object(payload)
        key = digest(str_token(obj.get('invite_token')))
        if obj.get('consent_version') != CONSENT_VERSION or obj.get('accept') is not True:
            raise EnrollmentError('Explicit acceptance of current consent terms is required', 403)
        if obj.get('allow_location') is not True or obj.get('allow_motion') is not True:
            raise EnrollmentError('Location and motion permissions must both be explicitly authorized', 403)
        if obj.get('physically_at_site') is not True:
            raise EnrollmentError('Participant must attest to being physically at the site', 403)
        lat, lon = coordinates(obj.get('lat'), obj.get('lon'))
        try:
            accuracy = float(obj.get('accuracy_m'))
        except (TypeError, ValueError) as exc:
            raise EnrollmentError('Geolocation accuracy required') from exc
        if not math.isfinite(accuracy) or not 0 < accuracy <= MAX_GPS_ACCURACY_M:
            raise EnrollmentError('Reported device location is too imprecise; move outdoors or retry', 403)
        now = self.clock()
        with self.lock:
            entry = self.invites.get(key)
            if not entry or entry['consumed'] or entry['expires'] <= now:
                raise EnrollmentError('Invitation no longer valid', 403)
            site = self.sites[entry['site_id']]
            separation = distance_m(lat, lon, site['lat'], site['lon'])
            if separation + accuracy > site['radius_m']:
                raise EnrollmentError('Reported device position does not fall within target zone', 403)
            self._cleanup(now)
            if len(self.sessions) >= MAX_SESSIONS:
                raise EnrollmentError('Active-session limit reached', 503)
            session_token = secrets.token_urlsafe(32)
            session_id = secrets.token_urlsafe(12)
            self.sessions[digest(session_token)] = {'id': session_id, 'site_id': site['id'],
                'started': now, 'last_seen': now, 'expires': now + SESSION_LIFETIME_SECONDS,
                'last_samples': 0, 'total_samples': 0, 'last_rms': None,
                'reported_accuracy_m': round(accuracy), 'revoked': False}
            entry['consumed'] = True
            # Neither exact coordinates nor participant identity are retained.
            return {'session_token': session_token, 'session_id': session_id,
                    'site_id': site['id'], 'expires_at_utc': iso(now + SESSION_LIFETIME_SECONDS),
                    'location_status': 'SELF_REPORTED_WITHIN_ZONE',
                    'hardware_status': 'UNVERIFIED',
                    'note': 'Motion data only; not RuView CSI and not verification of human occupancy.'}

    def sample(self, payload: object) -> dict:
        obj = ensure_object(payload)
        key = digest(str_token(obj.get('session_token')))
        now = self.clock()
        with self.lock:
            session = self.sessions.get(key)
            if not session or session['revoked'] or session['expires'] <= now:
                raise EnrollmentError('Session expired or revoked', 403)
            try:
                count = int(obj.get('samples'))
                rms = obj.get('motion_rms')
                rms = float(rms) if rms is not None else None
            except (ValueError, TypeError) as exc:
                raise EnrollmentError('Invalid motion summary') from exc
            if (not isinstance(obj.get('samples'), int) or isinstance(obj.get('samples'), bool)
                    or not 0 <= count <= 200 or (rms is not None and (not math.isfinite(rms) or not 0 <= rms <= 100))):
                raise EnrollmentError('Motion summary outside accepted bounds')
            if count == 0 and rms is not None or count > 0 and rms is None:
                raise EnrollmentError('Motion RMS and sample count must agree')
            if now - session['last_seen'] < 1:
                raise EnrollmentError('Telemetry rate too high', 429)
            session['last_seen'] = now
            session['last_samples'] = count
            session['total_samples'] += count
            session['last_rms'] = round(rms, 3) if rms is not None else None
            return {'accepted': True, 'state': 'MOTION_SUMMARY' if count else 'NO_MOTION_SAMPLES',
                    'expires_at_utc': iso(session['expires'])}

    def stop(self, payload: object) -> dict:
        key = digest(str_token(ensure_object(payload).get('session_token')))
        with self.lock:
            session = self.sessions.pop(key, None)
            return {'revoked': bool(session), 'state': 'STOPPED'}

    def site_status(self, site_id: object) -> dict:
        if not isinstance(site_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{12,80}', site_id):
            raise EnrollmentError('Invalid site identifier')
        now = self.clock()
        with self.lock:
            site = self.sites.get(site_id)
            if not site:
                raise EnrollmentError('Site not found', 404)
            active = [v for v in self.sessions.values() if v['site_id'] == site_id
                      and not v['revoked'] and now < v['expires']
                      and now - v['last_seen'] <= HEARTBEAT_WINDOW_SECONDS]
            reporting = [v for v in active if v['last_samples'] > 0]
            return {'site_id': site_id, 'site_label': site['label'],
                    'consenting_sessions_active': len(active),
                    'devices_reporting_motion': len(reporting),
                    'last_motion_rms': round(sum(v['last_rms'] for v in reporting if v['last_rms'] is not None) / len(reporting), 3) if reporting else None,
                    'total_motion_samples': sum(v['total_samples'] for v in active),
                    'site_location_status': 'SELF_REPORTED' if active else 'NO_ACTIVE_PARTICIPANT',
                    'ruview_binding': 'UNVERIFIED' if site['node_ids'] else 'BLOCKED',
                    'ruview_registered_node_ids': site['node_ids'],
                    'data_type': 'volunteer device motion, NOT people detection or Wi-Fi CSI',
                    'note': 'No identities, raw location, motion waveforms, or vital signs retained.'}

    def site_nodes(self, site_id: str) -> list[str]:
        with self.lock:
            site = self.sites.get(site_id)
            if not site:
                raise EnrollmentError('Site not found', 404)
            return list(site['node_ids'])
