// SkyNet S3-CAM protocol validators: deterministic, browser/Node-compatible, no I/O.
export const MAX_LOG_CHARS = 3_000_000;
export const MAX_FRAME_BYTES = 4_000_000;
export const MAX_CHUNKS = 8192;
export const MAX_API_AGE_MS = 90_000;

export function crc32(bytes) {
  if (!(bytes instanceof Uint8Array)) throw Error('CRC input must be Uint8Array');
  let crc = 0xffffffff;
  for (const b of bytes) {
    crc ^= b;
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return ((crc ^ 0xffffffff) >>> 0).toString(16).toUpperCase().padStart(8, '0');
}
export function hex(bytes) {
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}
export async function sha256(bytes) {
  if (!(bytes instanceof Uint8Array)) throw Error('SHA-256 input must be Uint8Array');
  if (!globalThis.crypto?.subtle) throw Error('Secure-context Web Crypto is required');
  return hex(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)));
}
export function normalizeSha(value) {
  const v = String(value ?? '').trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(v)) throw Error('Expected SHA-256 must be 64 hexadecimal characters');
  return v;
}
export function normalizeOffset(value) {
  const v = String(value ?? '').trim();
  if (!/^0x[0-9a-f]+$/i.test(v)) throw Error('Specify the documented image offset as 0x hexadecimal');
  const n = Number.parseInt(v.slice(2), 16);
  if (!Number.isSafeInteger(n) || n < 0 || n > 0x00ffffff || n % 0x1000 !== 0) {
    throw Error('Offset must be a valid 4 KiB-aligned address within a 16 MiB image');
  }
  return '0x' + n.toString(16);
}
export function secureEndpoint(value) {
  const url = new URL(String(value).trim());
  if (url.username || url.password || url.hash) throw Error('Credentials or fragments in URL are prohibited');
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) {
    throw Error('HTTPS required; HTTP is permitted only for literal loopback hostnames');
  }
  return url;
}
function fields(text) {
  const result = Object.create(null);
  const matcher = /([a-zA-Z][a-zA-Z0-9_]*)=([^\s]+)/g;
  let m;
  while ((m = matcher.exec(text)) !== null) {
    const key = m[1].toLowerCase();
    if (Object.hasOwn(result, key)) throw Error('Duplicate protocol field: ' + key);
    result[key] = m[2];
  }
  return result;
}
function sizeField(v, label) {
  if (!/^\d+$/.test(String(v ?? ''))) throw Error(label + ' requires decimal unsigned integer');
  const n = Number(v);
  if (!Number.isSafeInteger(n) || n < 0 || n > MAX_FRAME_BYTES) throw Error(label + ' out of range');
  return n;
}
function expectedCrc(v) {
  const normalized = String(v ?? '').replace(/^0x/i, '').toUpperCase();
  if (!/^[0-9A-F]{8}$/.test(normalized)) throw Error('CAM_END must contain an eight-digit CRC32');
  return normalized;
}
function decodeChunk(f) {
  const b64 = f.b64 ?? f.base64;
  if (b64 !== undefined) {
    if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(b64) || !b64.length) {
      throw Error('CAM_DATA has malformed base64 chunk');
    }
    return Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  }
  if (f.hex !== undefined) {
    if (!/^(?:[0-9a-fA-F]{2})+$/.test(f.hex)) throw Error('CAM_DATA has malformed hex chunk');
    return Uint8Array.from(f.hex.match(/.{2}/g), x => Number.parseInt(x, 16));
  }
  throw Error('CAM_DATA requires b64= or hex= payload');
}
export function parseCaptureLog(log) {
  if (typeof log !== 'string' || log.length > MAX_LOG_CHARS) throw Error('Log missing or exceeds 3,000,000 characters');
  const frames = [];
  let frame = null;
  let tokens = 0;
  const lines = log.replace(/\u001b\[[0-9;]*m/g, '').split(/\r?\n/);
  for (const [index, raw] of lines.entries()) {
    const match = raw.match(/\b(CAM_BEGIN|CAM_DATA|CAM_END)\b(.*)$/);
    if (!match) continue;
    tokens++;
    const kind = match[1];
    let f;
    try { f = fields(match[2]); } catch (e) { throw Error('Line ' + (index + 1) + ': ' + e.message); }
    if (kind === 'CAM_BEGIN') {
      if (frame) throw Error('Line ' + (index + 1) + ': prior capture missing CAM_END');
      const bytes = sizeField(f.bytes, 'CAM_BEGIN bytes');
      if (bytes < 4) throw Error('CAM_BEGIN declared JPEG too small');
      if (!f.id || !/^[\w.-]{1,80}$/.test(f.id)) throw Error('CAM_BEGIN requires bounded id=');
      frame = {id: f.id, declared: bytes, chunks: [], length: 0, nextSeq: 0, beginCrc: f.crc32 && expectedCrc(f.crc32)};
      continue;
    }
    if (!frame) throw Error('Line ' + (index + 1) + ': ' + kind + ' without CAM_BEGIN');
    if (f.id && f.id !== frame.id) throw Error('Line ' + (index + 1) + ': capture ID mismatch');
    if (kind === 'CAM_DATA') {
      const seq = sizeField(f.seq, 'CAM_DATA seq');
      if (seq !== frame.nextSeq) throw Error('Line ' + (index + 1) + ': missing, duplicate, or out-of-order CAM_DATA seq');
      if (frame.nextSeq >= MAX_CHUNKS) throw Error('Too many CAM_DATA chunks');
      const chunk = decodeChunk(f);
      if (!chunk.length) throw Error('Empty CAM_DATA chunk');
      frame.length += chunk.length;
      if (frame.length > frame.declared) throw Error('CAM_DATA exceeds CAM_BEGIN byte count');
      frame.chunks.push(chunk);
      frame.nextSeq++;
      continue;
    }
    if (!frame.nextSeq) throw Error('CAM_END without CAM_DATA');
    if (sizeField(f.bytes, 'CAM_END bytes') !== frame.declared || frame.length !== frame.declared) {
      throw Error('CAM_END byte count mismatch or truncated payload');
    }
    const buf = new Uint8Array(frame.length);
    let offset = 0;
    for (const chunk of frame.chunks) { buf.set(chunk, offset); offset += chunk.length; }
    const computed = crc32(buf);
    const stated = expectedCrc(f.crc32);
    if (frame.beginCrc && frame.beginCrc !== stated) throw Error('CAM_BEGIN/CAM_END CRC32 mismatch');
    if (computed !== stated) throw Error('CRC32 mismatch: expected ' + stated + ', calculated ' + computed);
    if (!(buf[0] === 0xff && buf[1] === 0xd8 && buf[buf.length - 2] === 0xff && buf[buf.length - 1] === 0xd9)) {
      throw Error('Invalid JPEG SOI/EOI markers or trailing bytes');
    }
    frames.push({id: frame.id, bytes: buf, size: buf.length, crc32: computed, chunks: frame.nextSeq});
    frame = null;
  }
  if (frame) throw Error('Truncated log: CAM_BEGIN has no matching CAM_END');
  if (!tokens || !frames.length) throw Error('No complete CAM_BEGIN/CAM_DATA/CAM_END capture');
  if (frames.length > 20) throw Error('Excessive capture count; split log');
  return {frames, tokenCount: tokens};
}
export function classifyStatus(payload, expectedId, now = Date.now()) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return {state:'FAILED',reason:'Invalid JSON object'};
  const source = String(payload.source_type ?? payload.source ?? payload.mode ?? '').toLowerCase();
  if (payload.synthetic === true || payload.simulated === true || /synthetic|simulation|mock|demo|fixture/.test(source)) {
    return {state:'BLOCKED',reason:'Synthetic or simulated data is not live device evidence'};
  }
  const id = String(payload.device_id ?? payload.deviceId ?? payload.chip_id ?? '');
  if (!expectedId || !id) return {state:'UNVERIFIED',reason:'Missing expected or reported exact device identifier'};
  if (id !== expectedId) return {state:'FAILED',reason:'Device identifier does not match selected board'};
  const timestamp = payload.timestamp ?? payload.observed_at ?? payload.captured_at ?? payload.updated_at;
  const ms = typeof timestamp === 'number' ? (timestamp < 1e12 ? timestamp * 1000 : timestamp) : Date.parse(String(timestamp ?? ''));
  if (!Number.isFinite(ms)) return {state:'UNVERIFIED',reason:'Missing or invalid device timestamp'};
  const ageMs = now - ms;
  if (ageMs < -30_000) return {state:'FAILED',reason:'Device timestamp is too far in the future',ageMs};
  if (ageMs > MAX_API_AGE_MS) return {state:'BLOCKED',reason:'Device report is stale',ageMs};
  if (payload.connected === false || payload.online === false) return {state:'BLOCKED',reason:'Device reports offline',ageMs};
  return {state:'VERIFIED',reason:'Fresh matching API response (transport only; physical origin still requires correlated logs)',ageMs};
}
export function safeEvidenceLink(value) {
  if (!value) return '';
  const u = secureEndpoint(value);
  if (u.protocol !== 'https:') throw Error('Evidence URL must be HTTPS');
  return u.href;
}
