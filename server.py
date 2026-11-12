"""SkyNet / RuView: read-only data gateway with explicit opt-in device enrollment.

Python >=3.10, standard library only. Consent sessions stay ephemeral in RAM.
No device-control, flashing, audio/video capture, or persistent participant data.
"""
from __future__ import annotations

import csv
import hashlib
import ipaddress
import hmac
import io
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from optin import EnrollmentError, EnrollmentRegistry

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
AUDIT_FILE = DATA_DIR / 'public_evidence.jsonl'
AUDIT_LOCK = Lock()
MAX_RESPONSE_BYTES = 3_000_000
DEFAULT_RUVIEW_URL = 'http://127.0.0.1:3000'
RUVIEW_URL = os.getenv('RUVIEW_URL', DEFAULT_RUVIEW_URL).rstrip('/')
RUVIEW_ALLOW_LAN = os.getenv('RUVIEW_ALLOW_LAN', '0') == '1'
RUVIEW_API_TOKEN = os.getenv('RUVIEW_API_TOKEN', '').strip()
FIRMS_MAP_KEY = os.getenv('FIRMS_MAP_KEY', '').strip()
HOST = os.getenv('SKYNET_HOST', os.getenv('TERRAMESH_HOST', '127.0.0.1'))
PORT = int(os.getenv('SKYNET_PORT', os.getenv('TERRAMESH_PORT', '8787')))
ADMIN_TOKEN = os.getenv('SKYNET_ADMIN_TOKEN', '').strip()
PUBLIC_URL = os.getenv('SKYNET_PUBLIC_URL', '').strip().rstrip('/')
ENROLLMENT = EnrollmentRegistry()
MAX_POST_BYTES = 4096


def validate_public_url(base: str) -> str:
    """Public SMS destinations must use a fixed explicitly configured HTTPS origin.

    Never derive a public invitation URL from attacker-controlled Host headers.
    """
    if not base:
        return ''
    p = urlparse(base)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.path not in ('', '/') or p.query or p.fragment or p.port not in (None, 443)):
        raise ValueError('SKYNET_PUBLIC_URL must be an HTTPS origin with no path or credentials')
    host = p.hostname.lower()
    if host == 'localhost' or host.endswith('.localhost'):
        raise ValueError('SKYNET_PUBLIC_URL must be a public HTTPS hostname, not localhost')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('SKYNET_PUBLIC_URL must use a public DNS hostname')
    if '.' not in host or host.endswith('.') or len(host) > 253:
        raise ValueError('SKYNET_PUBLIC_URL requires a valid fully qualified hostname')
    return base


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate_ruview_url(base: str, lan_allowed: bool = False) -> None:
    """Fail closed on non-local/unsafe RuView targets; explicit private-LAN opt-in."""
    p = urlparse(base)
    if p.scheme != 'http' or not p.hostname or p.username or p.password or p.path not in ('', '/') or p.query or p.fragment:
        raise ValueError('RUVIEW_URL must be a plain http://host:port URL without credentials/path')
    host = p.hostname.lower()
    if host == 'localhost':
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError('Use localhost or a literal loopback/private IP; DNS hostnames are disabled') from exc
    if address.is_loopback:
        return
    if lan_allowed and address.is_private and not address.is_link_local and not address.is_multicast:
        return
    raise ValueError('Remote RuView blocked; set RUVIEW_ALLOW_LAN=1 for a trusted private IP')


def geo_point(query: dict[str, list[str]]) -> tuple[float, float, float]:
    try:
        lat = float(query.get('lat', [''])[0])
        lon = float(query.get('lon', [''])[0])
        radius = float(query.get('radius_km', ['5'])[0])
    except (ValueError, TypeError) as exc:
        raise ValueError('lat, lon and radius_km must be numbers') from exc
    if not all(map(math.isfinite, (lat, lon, radius))) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 0.1 <= radius <= 20:
        raise ValueError('lat must be -90..90, lon -180..180, radius_km 0.1..20')
    return lat, lon, radius


def geo_bbox(lat: float, lon: float, radius_km: float) -> str:
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.05, math.cos(math.radians(lat))))
    return ','.join(f'{v:.6f}' for v in (max(-180, lon - dlon), max(-90, lat - dlat), min(180, lon + dlon), min(90, lat + dlat)))


class DenyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect rejected on credential-bearing source request')


def fetch_bytes(url: str, timeout: float = 8, extra_headers: dict[str, str] | None = None, no_redirects: bool = False) -> tuple[bytes, str]:
    headers = {'User-Agent': 'SkyNet/0.3 (public-data, read-only)', 'Accept': 'application/json,text/csv;q=0.9'}
    if extra_headers:
        headers.update(extra_headers)
    request = Request(url, headers=headers)
    opener = build_opener(DenyRedirects()) if no_redirects or extra_headers else None
    with (opener.open(request, timeout=timeout) if opener else urlopen(request, timeout=timeout)) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
        if len(content) > MAX_RESPONSE_BYTES:
            raise ValueError('Remote response larger than allowed safety limit')
        return content, response.headers.get('Content-Type', '')


def fetch_json(url: str, extra_headers: dict[str, str] | None = None) -> tuple[object, str]:
    raw, _ = fetch_bytes(url, extra_headers=extra_headers, no_redirects=bool(extra_headers))
    return json.loads(raw.decode('utf-8')), hashlib.sha256(raw).hexdigest()


def status(source: str, state: str, note: str, data: object = None, sha256: str | None = None, capture: str | None = None) -> dict:
    return {'source': source, 'state': state, 'note': note, 'retrieved_at_utc': utc_now(),
            'data_acquired_at_utc': capture, 'sha256': sha256, 'data': data}


def fail(source: str, exc: Exception) -> dict:
    # Do not expose internal remote URLs, credentials, or file paths.
    if isinstance(exc, HTTPError):
        note = f'Upstream HTTP {exc.code}; no data accepted'
    elif isinstance(exc, (URLError, OSError, TimeoutError)):
        note = 'Source unreachable or timed out; no data accepted'
    elif isinstance(exc, (ValueError, KeyError, TypeError, json.JSONDecodeError)):
        note = 'Unexpected source response; parsing rejected'
    else:
        note = f'{type(exc).__name__}; no data accepted'
    return status(source, 'BLOCKED', note)


def ruview_snapshot() -> dict:
    validate_ruview_url(RUVIEW_URL, RUVIEW_ALLOW_LAN)
    out = {}
    endpoints = {'health': '/health', 'mesh': '/api/v1/mesh', 'field': '/api/field', 'sensing': '/api/v1/sensing/latest'}
    for name, path in endpoints.items():
        try:
            auth_headers = {'Authorization': 'Bearer ' + RUVIEW_API_TOKEN} if RUVIEW_API_TOKEN else None
            response, digest = fetch_json(RUVIEW_URL + path, extra_headers=auth_headers)
            if not isinstance(response, dict):
                raise ValueError('Non-object API response')
            if name == 'health':
                origin = str(response.get('source', 'unknown')).lower()
                synthetic = origin in ('simulate', 'simulated', 'simulation', 'synthetic')
                summary = {'server_status': response.get('status'), 'source': origin, 'clients': response.get('clients')}
                out[name] = status('RuView /health', 'SIMULATED' if synthetic else 'VERIFIED',
                                   'Self-reported health, not hardware acceptance', summary, digest)
            elif name == 'mesh':
                nodes = response.get('nodes')
                count = len(nodes) if isinstance(nodes, (list, dict)) else response.get('total')
                out[name] = status('RuView mesh', 'UNVERIFIED',
                                   'Node registry is self-reported; physical placement not validated',
                                   {'node_count': count}, digest)
            elif name == 'field':
                events = response.get('events', [])
                if not isinstance(events, list):
                    raise ValueError('Invalid events list')
                dev = response.get('dev_signing_key')
                out[name] = status('RuView RuField', 'UNVERIFIED',
                                   'Signed field event provenance NOT cryptographically verified by this gateway',
                                   {'egress_safe_event_count': len(events), 'dev_signing_key': dev,
                                    'signer_present': bool(response.get('signer_pubkey_hex'))}, digest)
            else:
                out[name] = status('RuView CSI', 'UNVERIFIED',
                                   'Sensing data present; no physical validity or pose/vitals inference claimed',
                                   {'frame_available': bool(response), 'motion_keys_present': [k for k in ('motion', 'motion_score', 'presence') if k in response]}, digest)
        except Exception as exc:
            out[name] = fail(f'RuView {name}', exc)
    out['hardware_acceptance'] = 'UNVERIFIED'
    out['description'] = 'Local RuView data is never persisted by SkyNet; no raw CSI, identities or vital signs exported.'
    return out


def ruview_site_readiness(site_id: str) -> dict:
    """Read-only site-scoped RuView readiness, NOT a claim of physical geolocation.

Node IDs are operator-declared: matching names in a RuView registry can never
establish sensor placement, field calibration or human occupancy.
    """
    expected = ENROLLMENT.site_nodes(site_id)
    if not expected:
        return {'state': 'BLOCKED', 'reason': 'No RuView node mapping declared for the target site',
                'source_state': 'UNKNOWN', 'matching_nodes': 0, 'physical_placement': 'UNVERIFIED'}
    try:
        validate_ruview_url(RUVIEW_URL, RUVIEW_ALLOW_LAN)
        headers = {'Authorization': 'Bearer ' + RUVIEW_API_TOKEN} if RUVIEW_API_TOKEN else None
        readiness, _ = fetch_json(RUVIEW_URL + '/api/v1/status', extra_headers=headers)
        nodes, _ = fetch_json(RUVIEW_URL + '/api/v1/nodes', extra_headers=headers)
        if not isinstance(readiness, dict):
            raise ValueError('Invalid RuView status response')
        node_values: set[str] = set()
        if isinstance(nodes, dict):
            entries = nodes.get('nodes', nodes)
        else:
            entries = nodes
        if isinstance(entries, dict):
            node_values.update(str(v) for v in entries.keys())
            entries = list(entries.values())
        if isinstance(entries, list):
            for node in entries:
                if isinstance(node, dict):
                    for key in ('node_id', 'id'):
                        if node.get(key) is not None:
                            node_values.add(str(node[key]))
        source_state = str(readiness.get('source_state', 'unknown')).lower()
        source_name = str(readiness.get('source', 'unknown')).lower()
        try:
            age = float(readiness.get('last_frame_age_ms', float('inf')))
        except (ValueError, TypeError):
            age = float('inf')
        match = sorted(set(expected) & node_values)
        live = (source_state in ('live_unverified', 'live')
                and source_name not in ('simulated', 'simulate', 'synthetic', 'simulation')
                and readiness.get('waiting_for_frames') is False
                and math.isfinite(age) and 0 <= age < 5000)
        if not live:
            reason = 'RuView has no fresh, non-synthetic sensing frames'
        elif not match:
            reason = 'No declared node IDs match the RuView registry'
        else:
            reason = 'RuView node registry matches; physical placement and detection remain unverified'
        return {'state': 'UNVERIFIED' if live and match else 'BLOCKED', 'reason': reason,
                'source_state': source_state, 'last_frame_age_ms': age if math.isfinite(age) else None,
                'matching_nodes': len(match), 'declared_nodes': len(expected),
                'physical_placement': 'UNVERIFIED', 'subject_detection': 'NOT_ACCEPTED',
                'privacy': 'No CSI samples or human characteristics exported'}
    except Exception:
        return {'state': 'BLOCKED', 'reason': 'RuView status/nodes unavailable or invalid',
                'matching_nodes': 0, 'physical_placement': 'UNVERIFIED'}

def elevation(lat: float, lon: float) -> dict:
    source = 'USGS EPQS elevation'
    url = 'https://epqs.nationalmap.gov/v1/json?' + urlencode({'x': lon, 'y': lat, 'units': 'Meters', 'wkid': 4326, 'includeDate': 'false'})
    try:
        obj, digest = fetch_json(url)
        value = obj.get('value') if isinstance(obj, dict) else None
        if isinstance(value, str):
            value = float(value)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= -100000:
            raise ValueError('No usable terrain elevation')
        return status(source, 'VERIFIED', 'Public elevation value fetched; not proof of LiDAR feature detection',
                      {'elevation_m': value, 'lat': lat, 'lon': lon}, digest)
    except Exception as exc:
        return fail(source, exc)


def lidar_catalog(lat: float, lon: float, radius_km: float) -> dict:
    source = 'USGS 3DEP LiDAR catalog'
    url = 'https://tnmaccess.nationalmap.gov/api/v1/products?' + urlencode({
        'bbox': geo_bbox(lat, lon, radius_km), 'datasets': 'Lidar Point Cloud (LPC)', 'max': 10,
    })
    try:
        obj, digest = fetch_json(url)
        if not isinstance(obj, dict) or not isinstance(obj.get('items'), list):
            raise ValueError('Missing products/items array')
        items = []
        for item in obj['items'][:10]:
            if not isinstance(item, dict):
                continue
            url_val = item.get('downloadURL', '')
            if not isinstance(url_val, str) or not url_val.startswith('https://'):
                url_val = None
            items.append({'title': str(item.get('title', 'Untitled'))[:200],
                          'date_created': item.get('dateCreated'), 'download_url': url_val,
                          'size_bytes': item.get('sizeInBytes')})
        return status(source, 'VERIFIED', 'Catalog metadata only; point cloud not downloaded or analyzed',
                      {'count_returned': len(items), 'items': items}, digest)
    except Exception as exc:
        return fail(source, exc)


def sentinel_catalog(lat: float, lon: float) -> dict:
    source = 'Copernicus Sentinel-1 radar catalog'
    since = (datetime.now(timezone.utc) - timedelta(days=45)).strftime('%Y-%m-%dT00:00:00.000Z')
    filter_expr = (f"OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon:.6f} {lat:.6f})') "
                   f"and Collection/Name eq 'SENTINEL-1' and ContentDate/Start gt {since}")
    url = 'https://catalogue.dataspace.copernicus.eu/odata/v1/Products?' + urlencode({
        '$filter': filter_expr, '$orderby': 'ContentDate/Start desc', '$top': 5,
        '$select': 'Id,Name,ContentDate,Online',
    })
    try:
        obj, digest = fetch_json(url)
        if not isinstance(obj, dict) or not isinstance(obj.get('value'), list):
            raise ValueError('Missing results array')
        items = []
        for item in obj['value'][:5]:
            if not isinstance(item, dict):
                continue
            items.append({'id': item.get('Id'), 'name': str(item.get('Name', ''))[:250],
                          'capture_time': (item.get('ContentDate') or {}).get('Start') if isinstance(item.get('ContentDate'), dict) else None,
                          'online': item.get('Online')})
        return status(source, 'VERIFIED', 'Radar product catalog only; imagery is not processed for detections',
                      {'count_returned': len(items), 'items': items}, digest)
    except Exception as exc:
        return fail(source, exc)


def fires(lat: float, lon: float, radius_km: float) -> dict:
    source = 'NASA FIRMS active fires'
    if not FIRMS_MAP_KEY:
        return status(source, 'BLOCKED', 'Optional MAP_KEY not configured; NASA public imagery layer remains available')
    # Key is never returned, persisted, or printed to the browser.
    bbox = geo_bbox(lat, lon, radius_km)
    url = 'https://firms.modaps.eosdis.nasa.gov/api/area/csv/' + FIRMS_MAP_KEY + '/VIIRS_SNPP_NRT/' + bbox + '/1'
    try:
        raw, _ = fetch_bytes(url, no_redirects=True)
        digest = hashlib.sha256(raw).hexdigest()
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        items = []
        for idx, item in enumerate(reader):
            if idx >= 100:
                break
            try:
                item_lat = float(item.get('latitude', ''))
                item_lon = float(item.get('longitude', ''))
            except ValueError:
                continue
            if not -90 <= item_lat <= 90 or not -180 <= item_lon <= 180:
                continue
            items.append({'lat': item_lat, 'lon': item_lon, 'acq_date': item.get('acq_date'),
                          'acq_time': item.get('acq_time'), 'confidence': item.get('confidence')})
        return status(source, 'VERIFIED', 'Satellite thermal anomalies, not confirmed fires or point temperatures',
                      {'count_returned': len(items), 'items': items}, digest)
    except Exception as exc:
        return fail(source, exc)


def audit_public_results(lat: float, lon: float, results: dict) -> None:
    """Record provenance for public datasets only; no RuView presence/signal data."""
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    rows = []
    for key, item in results.items():
        if isinstance(item, dict):
            rows.append({'at_utc': utc_now(), 'source': key, 'lat': lat, 'lon': lon,
                         'state': item.get('state'), 'sha256': item.get('sha256'),
                         'record_type': 'upstream-response-hash', 'not_device_acceptance': True})
    with AUDIT_LOCK:
        with AUDIT_FILE.open('a', encoding='utf-8') as out:
            for row in rows:
                out.write(json.dumps(row, separators=(',', ':')) + '\n')


def scan(lat: float, lon: float, radius_km: float) -> dict:
    tasks = {'elevation': lambda: elevation(lat, lon),
             'lidar': lambda: lidar_catalog(lat, lon, radius_km),
             'sentinel1': lambda: sentinel_catalog(lat, lon),
             'firms': lambda: fires(lat, lon, radius_km)}
    # Each adapter handles its own upstream errors; unrelated feeds remain usable.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {key: pool.submit(fn) for key, fn in tasks.items()}
        results = {key: future.result() for key, future in futures.items()}
    audit_public_results(lat, lon, results)
    return {'lat': lat, 'lon': lon, 'radius_km': radius_km, 'scanned_at_utc': utc_now(),
            'results': results, 'cross_sensor_detection': 'UNVERIFIED',
            'note': 'Each feed is independent. Overlaying layers does not validate a shared anomaly.'}


def evidence(limit: int = 30) -> list[dict]:
    if not AUDIT_FILE.exists():
        return []
    # Last 30 evidence items without reading unlimited logs into memory.
    from collections import deque
    with AUDIT_FILE.open('r', encoding='utf-8') as f:
        lines = deque(f, maxlen=limit)
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(result))


class Handler(BaseHTTPRequestHandler):
    server_version = 'SkyNet/0.5'

    def send_json(self, value: object, http_status: int = 200) -> None:
        body = json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')
        self.send_response(http_status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(self), accelerometer=(self), gyroscope=(self)')
        self.end_headers()
        self.wfile.write(body)

    def is_admin(self) -> bool:
        """Bearer admin token (never embedded in shareable enrollment URLs)."""
        return bool(ADMIN_TOKEN) and hmac.compare_digest(
            self.headers.get('X-SkyNet-Admin-Token', ''), ADMIN_TOKEN)

    def require_admin(self) -> None:
        if not ADMIN_TOKEN:
            raise EnrollmentError('Invitations disabled: configure SKYNET_ADMIN_TOKEN', 503)
        if not self.is_admin():
            raise EnrollmentError('Operator authorization required', 403)

    def send_html(self, name: str) -> None:
        body = (ROOT / 'static' / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(self), accelerometer=(self), gyroscope=(self)')
        if name == 'join.html':
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route in ('/', '/index.html'):
            return self.send_html('index.html')
        if route in ('/join', '/join.html'):
            return self.send_html('join.html')
        try:
            if route == '/api/config':
                return self.send_json({'name': 'SkyNet', 'attribution': 'Intellectual property by Matthew Blake Ward, in association with 918 Technologies.',
                                       'version': '0.5', 'ruview_url': RUVIEW_URL,
                                       'public_invitation_origin': PUBLIC_URL or None,
                                       'ruview_observatory': RUVIEW_URL + '/ui/observatory.html',
                                       'firms_enabled': bool(FIRMS_MAP_KEY), 'internet_required_for_layers': True,
                                       'gateway_host': HOST, 'read_only_public_sources': True,
                                       'volunteer_enrollment_enabled': bool(ADMIN_TOKEN),
                                       'source_capabilities': ['RuView CSI summary', 'RuView P1/P2 field event counts', 'USGS elevation',
                                                               'USGS LiDAR catalog', 'Sentinel-1 metadata', 'NASA GIBS visualization',
                                                               'NASA FIRMS optional', 'opt-in volunteer device motion (separate from CSI)']})
            if route == '/api/ruview':
                return self.send_json(ruview_snapshot())
            if route == '/api/scan':
                lat, lon, radius = geo_point(query)
                return self.send_json(scan(lat, lon, radius))
            if route == '/api/evidence':
                return self.send_json(evidence())
            if route == '/api/health':
                return self.send_json({'status': 'ok', 'time_utc': utc_now(), 'sensor_access': 'not_implied'})
            if route == '/api/enroll/info':
                return self.send_json(ENROLLMENT.invitation_info(query.get('invite', [''])[0]))
            if route == '/api/sites/status':
                self.require_admin()
                return self.send_json(ENROLLMENT.site_status(query.get('site_id', [''])[0]))
            if route == '/api/sites/ruview':
                self.require_admin()
                return self.send_json(ruview_site_readiness(query.get('site_id', [''])[0]))
            return self.send_json({'error': 'Route not found'}, 404)
        except EnrollmentError as exc:
            return self.send_json({'error': str(exc)}, exc.http_status)
        except ValueError as exc:
            return self.send_json({'error': str(exc)}, 400)
        except Exception:
            return self.send_json({'error': 'Internal gateway failure; no result accepted'}, 500)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        supported = {'/api/sites/invite', '/api/enroll/start', '/api/enroll/sample', '/api/enroll/stop'}
        if route not in supported:
            return self.send_json({'error': 'Endpoint does not accept writes'}, 405)
        try:
            if route == '/api/sites/invite':
                self.require_admin()
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                raise EnrollmentError('application/json request required', 415)
            try:
                length = int(self.headers.get('Content-Length', '-1'))
            except ValueError as exc:
                raise EnrollmentError('Invalid Content-Length') from exc
            if not 1 <= length <= MAX_POST_BYTES:
                raise EnrollmentError('Request exceeds supported size or has no length', 413)
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            if route == '/api/sites/invite':
                invite = ENROLLMENT.create_invite(payload)
                invite['invite_url'] = (PUBLIC_URL + '/join#invite=' + invite['invite_token']) if PUBLIC_URL else None
                invite['delivery'] = 'OPERATOR_SMS_COMPOSER_ONLY'
                return self.send_json(invite, 201)
            if route == '/api/enroll/start':
                return self.send_json(ENROLLMENT.enroll(payload), 201)
            if route == '/api/enroll/sample':
                return self.send_json(ENROLLMENT.sample(payload))
            if route == '/api/enroll/stop':
                return self.send_json(ENROLLMENT.stop(payload))
        except EnrollmentError as exc:
            return self.send_json({'error': str(exc)}, exc.http_status)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return self.send_json({'error': 'Malformed JSON request'}, 400)
        except Exception:
            return self.send_json({'error': 'Enrollment failed safely'}, 500)

    def log_message(self, message: str, *args: object) -> None:
        # No user-provided coordinates, external URLs or credentials logged.
        print(f'[{utc_now()}] request={self.command} status_path={urlparse(self.path).path}', flush=True)


def main() -> None:
    validate_ruview_url(RUVIEW_URL, RUVIEW_ALLOW_LAN)
    validate_public_url(PUBLIC_URL)
    if ADMIN_TOKEN and len(ADMIN_TOKEN) < 24:
        raise SystemExit('SKYNET_ADMIN_TOKEN must be at least 24 characters')
    if HOST not in ('localhost', '127.0.0.1', '::1') and os.getenv('SKYNET_ALLOW_REMOTE', os.getenv('TERRAMESH_ALLOW_REMOTE', '0')) != '1':
        raise SystemExit('Non-loopback binding requires explicit SKYNET_ALLOW_REMOTE=1; add authentication before exposing')
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'SkyNet local gateway: http://{HOST}:{PORT}', flush=True)
    print(f'RuView read-only source: {RUVIEW_URL}', flush=True)
    print('Opt-in enrollment: ' + ('enabled' if ADMIN_TOKEN else 'disabled; configure SKYNET_ADMIN_TOKEN'), flush=True)
    print('Public HTTPS invitation origin: ' + ('configured' if PUBLIC_URL else 'not configured (SMS disabled)'), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
