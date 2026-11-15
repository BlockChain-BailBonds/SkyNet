import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {crc32, sha256, normalizeSha, normalizeOffset, parseCaptureLog, classifyStatus, secureEndpoint, MAX_LOG_CHARS} from '../static/s3-cam-acceptance/protocol.mjs';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const bytes=Uint8Array.from([0xff,0xd8,0x10,0x20,0x30,0xff,0xd9]);
const toBase64=v=>Buffer.from(v).toString('base64');
const makeLog=(b=bytes,id='device-frame')=>{
  const c=crc32(b);
  return 'Boot: ESP32-S3 CAM\nCAM_BEGIN id='+id+' bytes='+b.length+' crc32='+c+'\nCAM_DATA id='+id+' seq=0 b64='+toBase64(b)+'\nCAM_END id='+id+' bytes='+b.length+' crc32='+c+'\n';
};
function throwsMessage(fn,needle) {assert.throws(fn,e=>String(e.message).includes(needle));}
test('CRC32 standard test vector',()=>assert.equal(crc32(new TextEncoder().encode('123456789')),'CBF43926'));
test('SHA256 official abc vector',async()=>assert.equal(await sha256(new TextEncoder().encode('abc')),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'));
test('normalizes exact SHA256 and rejects near matches',()=>{
  assert.equal(normalizeSha('A'.repeat(64)),'a'.repeat(64));
  throwsMessage(()=>normalizeSha('z'.repeat(64)),'64 hexadecimal');
});
test('valid JPEG stream with correlated id and CRC passes',()=>{
  const parsed=parseCaptureLog(makeLog());
  assert.equal(parsed.frames.length,1);
  assert.equal(parsed.frames[0].size,7);
  assert.deepEqual([...parsed.frames[0].bytes],[...bytes]);
  assert.equal(parsed.frames[0].crc32,crc32(bytes));
});
test('hex JPEG transport also supported',()=>{
  const h=Buffer.from(bytes).toString('hex');
  const log='CAM_BEGIN id=hex-1 bytes=7\nCAM_DATA id=hex-1 seq=0 hex='+h+'\nCAM_END id=hex-1 bytes=7 crc32='+crc32(bytes);
  assert.equal(parseCaptureLog(log).frames[0].size,7);
});
test('multiple completed frames accepted',()=>{
  assert.equal(parseCaptureLog(makeLog(bytes,'one')+'\n'+makeLog(bytes,'two')).frames.length,2);
});
test('incomplete capture with missing CAM_END fails',()=>{
  throwsMessage(()=>parseCaptureLog(makeLog().split('CAM_END')[0]),'Truncated');
});
test('incomplete CAM_DATA byte count fails',()=>{
  throwsMessage(()=>parseCaptureLog(makeLog().replace(toBase64(bytes),toBase64(bytes.slice(0,4)))),'byte count');
});
test('out-of-order or missing sequence fails',()=>{
  throwsMessage(()=>parseCaptureLog(makeLog().replace('seq=0','seq=1')),'missing, duplicate');
});
test('orphan data and trailing unmatched begin fail',()=>{
  throwsMessage(()=>parseCaptureLog('CAM_DATA seq=0 hex=ffd8'), 'without CAM_BEGIN');
  throwsMessage(()=>parseCaptureLog(makeLog()+'CAM_BEGIN id=second bytes=100'), 'Truncated');
});
test('overlapping BEGIN must fail',()=>{
  throwsMessage(()=>parseCaptureLog('CAM_BEGIN id=a bytes=100\nCAM_BEGIN id=b bytes=200'),'missing CAM_END');
});
test('wrong CRC32 and header/footer mismatch fail',()=>{
  throwsMessage(()=>parseCaptureLog(makeLog().replace('CAM_END id=device-frame bytes=7 crc32='+crc32(bytes),'CAM_END id=device-frame bytes=7 crc32=12345678')),'CRC32 mismatch');
  throwsMessage(()=>parseCaptureLog(makeLog().replace('CAM_BEGIN id=device-frame bytes=7 crc32='+crc32(bytes),'CAM_BEGIN id=device-frame bytes=7 crc32=99999999')),'CAM_BEGIN/CAM_END CRC32');
});
test('bad JPEG marker fails despite valid CRC32',()=>{
  const damaged=Uint8Array.from([0x00,0xd8,0x10,0x20,0x30,0xff,0xd9]);
  throwsMessage(()=>parseCaptureLog(makeLog(damaged)),'JPEG SOI/EOI');
});
test('malformed base64 and duplicate fields fail',()=>{
  throwsMessage(()=>parseCaptureLog(makeLog().replace(toBase64(bytes),'?bad!')),'malformed base64');
  throwsMessage(()=>parseCaptureLog(makeLog().replace('seq=0','seq=0 seq=0')),'Duplicate protocol field');
});
test('limits oversized logs',()=>{
  throwsMessage(()=>parseCaptureLog('a'.repeat(MAX_LOG_CHARS+1)),'exceeds');
});
test('offset is documented hexadecimal and 4KiB aligned',()=>{
  assert.equal(normalizeOffset('0x10000'),'0x10000');
  assert.equal(normalizeOffset('0x0'),'0x0');
  throwsMessage(()=>normalizeOffset('65536'),'0x hexadecimal');
  throwsMessage(()=>normalizeOffset('0x10001'),'4 KiB-aligned');
});
const NOW=1763170000000;
const reported={device_id:'chip-1234',timestamp:new Date(NOW-1000).toISOString(),online:true};
test('matching fresh API status is transport-only accepted',()=>assert.equal(classifyStatus(reported,'chip-1234',NOW).state,'VERIFIED'));
test('wrong device identity fails',()=>assert.equal(classifyStatus(reported,'chip-wrong',NOW).state,'FAILED'));
test('synthetic status never passes',()=>assert.equal(classifyStatus({...reported,synthetic:true},'chip-1234',NOW).state,'BLOCKED'));
test('stale timestamp and offline status blocked',()=>{
  assert.equal(classifyStatus({...reported,timestamp:new Date(NOW-100000).toISOString()},'chip-1234',NOW).state,'BLOCKED');
  assert.equal(classifyStatus({...reported,connected:false},'chip-1234',NOW).state,'BLOCKED');
});
test('missing timestamp and identity not live',()=>{
  assert.equal(classifyStatus({device_id:'chip-1234'},'chip-1234',NOW).state,'UNVERIFIED');
  assert.equal(classifyStatus({timestamp:new Date(NOW).toISOString()},'chip-1234',NOW).state,'UNVERIFIED');
});
test('future timestamps fail',()=>assert.equal(classifyStatus({...reported,timestamp:new Date(NOW+90000).toISOString()},'chip-1234',NOW).state,'FAILED'));
test('HTTPS only except explicit loopback, no URL credentials',()=>{
  assert.equal(secureEndpoint('https://example.com/api/v1/status').protocol,'https:');
  assert.equal(secureEndpoint('http://127.0.0.1:8787/api/v1/status').protocol,'http:');
  throwsMessage(()=>secureEndpoint('http://example.com/ingest'),'HTTPS required');
  throwsMessage(()=>secureEndpoint('https://user:pass@example.com/status'),'Credentials');
});
