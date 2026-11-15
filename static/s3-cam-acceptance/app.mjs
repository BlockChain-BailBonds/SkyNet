import {crc32, sha256, hex, normalizeSha, normalizeOffset, secureEndpoint, safeEvidenceLink, parseCaptureLog, classifyStatus, MAX_LOG_CHARS} from './protocol.mjs';

const $ = id => document.getElementById(id);
const STEPS = [
  {id:'usb',title:'Read-only USB & chip identification',detail:'Identify the actual chip and USB bridge without writes.',panel:'preflight'},
  {id:'pinout',title:'Board revision & camera pinout',detail:'Require exact schematic, sensor ID, and revision evidence.',panel:'preflight'},
  {id:'image',title:'Image digest & documented offset',detail:'Calculate SHA-256 on local firmware bytes; verify declared offset.',panel:'preflight'},
  {id:'backup',title:'Original firmware backup & hash',detail:'Preserve a readback artifact and its exact-source receipt.',panel:'preflight'},
  {id:'approval',title:'Human flash authorization gate',detail:'Record approval only. No erase/flash control exists here.',panel:'preflight'},
  {id:'boot',title:'Serial boot trace',detail:'Correlate build fingerprint, device ID, and boot output.',panel:'camera'},
  {id:'api',title:'Fresh, matching /api/v1/status',detail:'Check origin, timestamp, source type, and disconnected states.',panel:'gateway'},
  {id:'commands',title:'STATUS / CAM STATUS / CAM CAPTURE',detail:'Require all three command responses in the device log.',panel:'camera'},
  {id:'jpeg',title:'JPEG bytes, CRC32 & markers',detail:'Reject incomplete sequences, invalid markers, and truncated frames.',panel:'camera'},
  {id:'visual',title:'Physical visual camera acceptance',detail:'Require a decoded scene and two source-correlated distinct frames.',panel:'camera'},
  {id:'gateway',title:'Separate SkyNet/RuView evidence relay',detail:'Verify only the exact authenticated ingestion receipt.',panel:'gateway'}
];
const PROFILES = {
  cam: STEPS.map(s => s.id),
  s3: ['usb','boot','api','commands','gateway'],
  cyd: ['usb','boot','commands','gateway']
};
const profileNames = {
  cam:'GOOUUU ESP32-S3 N16R8-CAM',
  s3:'Already-flashed separate S3 (preserve)',
  cyd:'Original ESP32E N4 CYD Pocket'
};
let currentProfile = 'cam';
let records = {cam:[],s3:[],cyd:[]};
let facts = {cam:{},s3:{},cyd:{}};
let frameSet = [];
let frameObjectUrl = '';
let decodedFrame = false;
let syntheticCapture = false;
let toastTimer = 0;

const profileFacts = () => facts[currentProfile];
const profileRecords = () => records[currentProfile];
const step = id => STEPS.find(s => s.id === id);
const currentState = id => [...profileRecords()].reverse().find(r => r.step === id)?.state ?? 'UNVERIFIED';
const statusClass = state => ({VERIFIED:'b-ver',UNVERIFIED:'b-unver',BLOCKED:'b-block',FAILED:'b-fail'}[state] || 'b-unver');
const escapeHTML = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setResult(id, state, message) {
  const el = $(id);
  el.className = 'result' + (state === 'VERIFIED' ? ' ok' : state === 'FAILED' ? ' bad' : state === 'BLOCKED' ? ' block' : '');
  el.textContent = state + ' · ' + message;
}
function toast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3200);
}
function record(id,state,source,note,url='',digest='') {
  if (!PROFILES[currentProfile].includes(id)) throw Error('Step is not part of selected device workflow');
  if (!['VERIFIED','UNVERIFIED','BLOCKED','FAILED'].includes(state)) throw Error('Invalid status');
  if (!['HOST','DEVICE','SIMULATED'].includes(source)) throw Error('Invalid evidence source');
  if (source === 'SIMULATED' && state === 'VERIFIED') throw Error('Simulated data cannot verify physical or host acceptance');
  const data = {time:new Date().toISOString(),profile:currentProfile,step:id,state,source,note:String(note).slice(0,600),url,digest,deviceId:profileFacts().deviceId ?? ''};
  profileRecords().push(data);
  render();
  return data;
}
function goPanel(id) {
  for (const p of document.querySelectorAll('.panel')) p.classList.toggle('is-visible',p.id === 'panel-' + id);
  for (const b of document.querySelectorAll('.nav-item')) b.classList.toggle('active',b.dataset.panel === id);
  document.getElementById('panel-' + id)?.scrollIntoView({behavior:'smooth',block:'start'});
}
function render() {
  const visibleSteps = PROFILES[currentProfile].map(id => step(id));
  const states = visibleSteps.map(s => currentState(s.id));
  for (const name of ['VERIFIED','UNVERIFIED','BLOCKED','FAILED']) {
    const id = 'count' + name.charAt(0) + name.toLowerCase().slice(1);
    $(id).textContent = states.filter(s => s === name).length;
  }
  $('profileLabel').textContent = 'Selected: ' + profileNames[currentProfile];
  $('stepList').innerHTML = visibleSteps.map((s,i) => {
    const state = currentState(s.id);
    const last = [...profileRecords()].reverse().find(r => r.step === s.id);
    return '<div class="step"><span class="index">' + String(i+1).padStart(2,'0') + '</span><div><h3>' + escapeHTML(s.title) + '</h3><p>' + escapeHTML(s.detail) + '</p>' + (last ? '<div class="evidence-hint">' + escapeHTML(last.source + ' · ' + last.note.slice(0,115)) + '</div>' : '') + '</div><span class="badge ' + statusClass(state) + '">' + state + '</span></div>';
  }).join('');
  const next = visibleSteps.find(s => currentState(s.id) !== 'VERIFIED');
  $('nextTitle').textContent = next ? next.title : 'All scoped checks recorded';
  $('nextDescription').textContent = next ? next.detail : 'Recorded checks still require independent review. No deployment or hardware acceptance is implied.';
  $('goNext').dataset.goto = next ? next.panel : 'evidence';
  $('evidenceStep').innerHTML = visibleSteps.map(s => '<option value="' + s.id + '">' + escapeHTML(s.title) + '</option>').join('');
  const rows = [...profileRecords()].reverse();
  $('evidenceRows').innerHTML = rows.length ? rows.map(r => '<tr><td>' + escapeHTML(r.time.replace('T',' ').slice(0,19)) + '</td><td>' + escapeHTML(step(r.step).title) + '</td><td><span class="badge ' + statusClass(r.state) + '">' + r.state + '</span></td><td>' + escapeHTML(r.source) + '</td><td>' + (r.url ? '<a href="' + escapeHTML(r.url) + '" target="_blank" rel="noopener noreferrer">Exact evidence ↗</a>' : escapeHTML(r.note.slice(0,115))) + (r.digest ? '<br><small>SHA256 ' + escapeHTML(r.digest.slice(0,20)) + '…</small>' : '') + '</td></tr>').join('') : '<tr><td colspan="5">No recorded evidence yet</td></tr>';
  $('recordApproval').disabled = currentProfile !== 'cam';
}
function resetPreview() {
  if (frameObjectUrl) URL.revokeObjectURL(frameObjectUrl);
  frameObjectUrl = '';
  frameSet = [];
  decodedFrame = false;
  $('cameraImage').hidden = true;
  $('cameraImage').removeAttribute('src');
  $('cameraPlaceholder').hidden = false;
  $('frameMeta').textContent = 'CRC32 · —\nBytes · —\nSource · UNVERIFIED';
}
function switchProfile(id) {
  if (!PROFILES[id]) return;
  currentProfile = id;
  for (const button of document.querySelectorAll('.profile')) button.classList.toggle('selected',button.dataset.profile === id);
  for (const field of document.querySelectorAll('input:not([type=checkbox]), textarea')) {
    if (field.type === 'file') field.value = '';
    else if (!['statusUrl','gatewayUrl'].includes(field.id)) field.value = '';
  }
  for (const check of document.querySelectorAll('input[type=checkbox]')) check.checked = false;
  resetPreview();
  syntheticCapture = false;
  $('deviceId').value = profileFacts().deviceId ?? '';
  $('bootId').value = profileFacts().bootId ?? '';
  setResult('approvalResult','BLOCKED','Scope is ' + profileNames[id] + '. Only the CAM target may record flash approval.');
  setResult('captureResult','UNVERIFIED','No frame has been loaded for this profile.');
  setResult('statusResult','UNVERIFIED','This profile requires its own live evidence.');
  render();
  goPanel('overview');
}
async function hashFile(file,limit=32*1024*1024) {
  if (!file || !file.size || file.size > limit) throw Error('File missing, empty, or above ' + Math.round(limit/1024/1024) + ' MiB');
  return sha256(new Uint8Array(await file.arrayBuffer()));
}
function safeUrlInput(id) {
  return safeEvidenceLink($(id).value);
}
function selectedId() {
  return String($('deviceId').value).trim();
}
function safeLogHash(log) {
  return sha256(new TextEncoder().encode(log));
}
function setupHandlers() {
  document.querySelectorAll('[data-panel]').forEach(button => button.addEventListener('click',()=>goPanel(button.dataset.panel)));
  document.querySelectorAll('[data-profile]').forEach(button => button.addEventListener('click',()=>switchProfile(button.dataset.profile)));
  $('goNext').addEventListener('click',()=>goPanel($('goNext').dataset.goto));
  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click',async()=>{
    try { await navigator.clipboard.writeText(button.dataset.copy); toast('Command copied. This browser will not transmit it.'); }
    catch { toast('Clipboard permission unavailable. Select and copy the command manually.'); }
  }));
  $('checkIdentity').addEventListener('click',async()=>{
    try {
      const id = selectedId(), log = $('usbLog').value.trim(), bootId = $('bootId').value.trim();
      if (!id || id.length < 5 || id.length > 128) throw Error('Exact chip ID must be 5–128 characters');
      if (!log || log.length > MAX_LOG_CHARS || !log.includes(id)) throw Error('Paste a non-truncated raw host log containing the exact device ID');
      if (currentProfile !== 'cyd' && !/ESP32[- ]?S3/i.test(log)) throw Error('Log does not positively identify ESP32-S3');
      if (currentProfile === 'cyd' && !/ESP32(?![- ]?S3)/i.test(log)) throw Error('Log does not identify an original ESP32-class CYD chip');
      const old = profileFacts().deviceId;
      if (old && old !== id) {
        profileRecords().length = 0;
        facts[currentProfile] = {};
        toast('Device ID changed: prior evidence for this profile invalidated.');
      }
      profileFacts().deviceId = id;
      profileFacts().bootId = bootId;
      const digest = await safeLogHash(log);
      record('usb','VERIFIED','HOST','Host log contains exact S3/CYD chip identity; physical board/photo correlation not independently audited','',digest);
      setResult('identityResult','VERIFIED','Host-only check · SHA-256 ' + digest + '. No flash or readback inferred.');
    } catch(e) {record('usb','FAILED','HOST',e.message);setResult('identityResult','FAILED',e.message);}
  });
  $('recordPinout').addEventListener('click',()=>{
    try {
      if (currentProfile !== 'cam') throw Error('Pinout verification belongs to camera profile');
      const rev = $('boardRev').value.trim(), sensor = $('sensorId').value.trim(), pinout = $('pinout').value.trim();
      const url = safeUrlInput('pinoutUrl');
      if (!rev || !sensor || pinout.length < 60 || !url) throw Error('Require revision, observed sensor, full map, and exact HTTPS reference');
      for (const pin of ['XCLK','SIOD','SIOC','VSYNC','HREF','PCLK']) if (!pinout.toUpperCase().includes(pin)) throw Error('Pin mapping missing ' + pin);
      for (let i=0;i<8;i++) if (!new RegExp('\\bD' + i + '\\b','i').test(pinout)) throw Error('Pin mapping missing D' + i);
      profileFacts().pinout = {revision:rev,sensor,source:url};
      record('pinout','VERIFIED','HOST','Operator supplied board revision and pinout evidence; wiring has not been electrically verified',url);
      setResult('pinoutResult','VERIFIED','Document evidence recorded. GPIO mapping still requires exact-board physical confirmation.');
    } catch(e) {setResult('pinoutResult','FAILED',e.message);record('pinout','FAILED','HOST',e.message);}
  });
  $('checkImage').addEventListener('click',async()=>{
    try {
      const file = $('imageFile').files[0], expected = normalizeSha($('imageSha').value), offset = normalizeOffset($('flashOffset').value), url = safeUrlInput('manifestUrl');
      if (!url) throw Error('Exact firmware/CI manifest link required');
      const actual = await hashFile(file);
      if (actual !== expected) throw Error('SHA-256 mismatch: ' + actual + ' != expected ' + expected);
      if (Number.parseInt(offset,16) + file.size > 16*1024*1024) throw Error('Image exceeds claimed 16 MiB address space; confirm actual flash size');
      profileFacts().image = {name:file.name,size:file.size,sha256:actual,offset,manifest:url};
      record('image','VERIFIED','HOST','Exact local file matches declared SHA-256 and documented offset; not a flash readback',url,actual);
      setResult('imageResult','VERIFIED',file.name + ' · ' + file.size + ' bytes · SHA256 ' + actual + ' · offset ' + offset + '. Host artifact only.');
    } catch(e) {delete profileFacts().image;record('image','FAILED','HOST',e.message);setResult('imageResult','FAILED',e.message);}
  });
  $('checkBackup').addEventListener('click',async()=>{
    try {
      const file = $('backupFile').files[0], url = safeUrlInput('backupUrl');
      if (!url) throw Error('Exact readback procedure/trace URL required');
      const digest = await hashFile(file);
      profileFacts().backup = {name:file.name,size:file.size,sha256:digest,source:url};
      record('backup','VERIFIED','HOST','Local readback file SHA-256 computed; hardware origin depends on supplied trace',url,digest);
      setResult('backupResult','VERIFIED','Hashed ' + file.size + ' bytes, SHA256 ' + digest + '. Physical provenance not independently verified.');
    } catch(e) {delete profileFacts().backup;record('backup','FAILED','HOST',e.message);setResult('backupResult','FAILED',e.message);}
  });
  $('recordApproval').addEventListener('click',()=>{
    try {
      if (currentProfile !== 'cam') throw Error('Only the new CAM profile can record flash approval');
      for (const required of ['usb','image','backup']) if (currentState(required) !== 'VERIFIED') throw Error('Missing verified ' + step(required).title);
      if (!$('approveBox').checked || $('approvePhrase').value !== 'APPROVE FLASH') throw Error('Explicit checkbox and exact approval phrase required');
      if ($('approveId').value.trim() !== profileFacts().deviceId) throw Error('Approval device ID does not match read-only identification');
      if (!profileFacts().image || !profileFacts().backup) throw Error('Image and backup hashes are not present');
      profileFacts().approval = {deviceId:profileFacts().deviceId,image:profileFacts().image.sha256,backup:profileFacts().backup.sha256,offset:profileFacts().image.offset,at:new Date().toISOString()};
      record('approval','VERIFIED','HOST','Operator signed an in-session approval only: no flash, erase, or device modification performed');
      setResult('approvalResult','VERIFIED','Approval recorded for ' + profileFacts().deviceId + '. Actual flasher must obtain separate confirmation.');
    } catch(e) {record('approval','BLOCKED','HOST',e.message);setResult('approvalResult','BLOCKED',e.message);}
  });
  $('checkBoot').addEventListener('click',async()=>{
    try {
      const log = $('bootLog').value;
      const id = profileFacts().deviceId || selectedId(), boot = $('bootId').value.trim() || profileFacts().bootId;
      if (!id || !boot || !log.includes(id) || !log.includes(boot)) throw Error('Boot trace must include the exact selected chip ID and boot/build fingerprint');
      if (!/boot|reset|rst:/i.test(log)) throw Error('Boot/reset marker missing');
      if (log.length > MAX_LOG_CHARS) throw Error('Log is oversized');
      const digest = await safeLogHash(log);
      profileFacts().bootId = boot;
      record('boot','VERIFIED','DEVICE','Operator-supplied exact-ID boot trace parsed, not independently authenticated','',digest);
      setResult('bootResult','VERIFIED','Boot/ID/build markers found. SHA-256 ' + digest + '.');
      const needed = ['STATUS','CAM STATUS','CAM CAPTURE'];
      const missing = needed.filter(cmd => !log.includes(cmd));
      if (missing.length) {
        record('commands','BLOCKED','DEVICE','Missing command receipts: ' + missing.join(', '));
        setResult('bootResult','BLOCKED','Boot markers passed, but commands missing: ' + missing.join(', '));
      } else {
        record('commands','VERIFIED','DEVICE','Three distinct command tokens present in operator-supplied log; firmware responses still require inspection','',digest);
      }
    } catch(e) {record('boot','FAILED','DEVICE',e.message);setResult('bootResult','FAILED',e.message);}
  });
  $('captureFile').addEventListener('change',async()=>{
    try {
      const file = $('captureFile').files[0];
      if (!file) return;
      if (file.size > MAX_LOG_CHARS) throw Error('Capture log file too large');
      $('captureLog').value = await file.text();
      syntheticCapture = false;
      resetPreview();
      toast('Capture log loaded. Not yet verified.');
    } catch(e) {setResult('captureResult','FAILED',e.message);}
  });
  $('captureLog').addEventListener('input',()=>{ resetPreview(); });
  $('syntheticSample').addEventListener('click',()=>{
    const payload = Uint8Array.of(0xff,0xd8,0xff,0xd9);
    const base64 = btoa(String.fromCharCode(...payload));
    $('captureLog').value = 'SYNTHETIC TEST FIXTURE -- NOT DEVICE EVIDENCE\nCAM_BEGIN id=synthetic-1 bytes=4 crc32=' + crc32(payload) + '\nCAM_DATA id=synthetic-1 seq=0 b64=' + base64 + '\nCAM_END id=synthetic-1 bytes=4 crc32=' + crc32(payload) + '\n';
    syntheticCapture = true;
    resetPreview();
    toast('Synthetic protocol fixture only. Not usable for camera acceptance.');
  });
  $('parseCapture').addEventListener('click',()=>{
    resetPreview();
    const text = $('captureLog').value;
    try {
      const result = parseCaptureLog(text);
      frameSet = result.frames;
      const first = frameSet[frameSet.length-1];
      const markerOnly = first.size <= 4;
      const synthetic = syntheticCapture || /SYNTHETIC TEST FIXTURE|SIMULATED|DEMO FRAME/i.test(text);
      const source = synthetic ? 'SIMULATED' : 'DEVICE';
      const state = synthetic ? 'UNVERIFIED' : 'VERIFIED';
      profileFacts().capture = {frames:frameSet.length,lastCrc32:first.crc32,size:first.size,synthetic};
      record('jpeg',state,source,'CRC32, byte count, sequence and JPEG SOI/EOI markers passed (' + frameSet.length + ' frames); decoding/source correlation separate');
      setResult('captureResult',state,result.frames.length + ' complete frame(s); last ' + first.size + ' bytes, CRC32 ' + first.crc32 + '. ' + (synthetic?'SYNTHETIC — not physical evidence.':'Operator-supplied log — physical origin unverified.'));
      $('frameMeta').textContent = 'Frames · ' + frameSet.length + '\nBytes · ' + first.size + '\nCRC32 · ' + first.crc32 + '\nSource · ' + source + '\nJPEG markers · PASS';
      if (!markerOnly) {
        frameObjectUrl = URL.createObjectURL(new Blob([first.bytes],{type:'image/jpeg'}));
        const image = $('cameraImage');
        image.onload = ()=>{ decodedFrame = true; image.hidden=false; $('cameraPlaceholder').hidden=true; };
        image.onerror = ()=>{ decodedFrame=false; setResult('captureResult','FAILED','JPEG byte checks passed, but browser image decoding failed'); record('jpeg','FAILED',source,'JPEG decoder rejected image despite markers/CRC'); };
        image.src = frameObjectUrl;
      }
      if (markerOnly) setResult('captureResult','BLOCKED','Markers/CRC passed for minimal fixture; not a decodable JPEG and not camera acceptance.');
    } catch(e) {
      record('jpeg',syntheticCapture?'UNVERIFIED':'FAILED',syntheticCapture?'SIMULATED':'DEVICE',e.message);
      setResult('captureResult',syntheticCapture?'UNVERIFIED':'FAILED',e.message);
    }
  });
  $('recordVisual').addEventListener('click',()=>{
    try {
      const source = syntheticCapture || profileFacts().capture?.synthetic ? 'SIMULATED' : 'DEVICE';
      if (source === 'SIMULATED') throw Error('Synthetic frames cannot verify camera operation');
      if (!decodedFrame) throw Error('Browser has not decoded a valid JPEG');
      if (frameSet.length < 2 || new Set(frameSet.map(x=>x.crc32)).size < 2) throw Error('Require at least two distinct completed frames from one captured log');
      if (!profileFacts().deviceId || currentState('boot') !== 'VERIFIED') throw Error('Exact-device boot trace not verified');
      if (!($('visualCheck').checked && $('changeCheck').checked && $('sourceCheck').checked)) throw Error('All three visual/source-correlation attestations are required');
      record('visual','VERIFIED','DEVICE','Operator-confirmed visual change and source correlation; not independently audited, not CSI');
      setResult('visualResult','VERIFIED','Operator visual acceptance recorded for exact selected device. CSI/RuView and deployment remain unverified.');
    } catch(e) {record('visual','BLOCKED','DEVICE',e.message);setResult('visualResult','BLOCKED',e.message);}
  });
  $('probeStatus').addEventListener('click',async()=>{
    const bearer = $('statusToken').value;
    $('statusToken').value = '';
    try {
      const url = secureEndpoint($('statusUrl').value);
      const control = new AbortController();
      const timer = setTimeout(()=>control.abort(),8000);
      let response;
      try {
        response = await fetch(url.href,{method:'GET',cache:'no-store',credentials:'omit',redirect:'error',signal:control.signal,headers:{'Accept':'application/json',...(bearer?{'Authorization':'Bearer ' + bearer}:{})}});
      } finally {clearTimeout(timer);}
      if (!response.ok) throw Error('Status HTTP ' + response.status + ' is not healthy');
      const raw = await response.text();
      if (raw.length > 100_000) throw Error('Status JSON exceeds 100 KiB');
      const payload = JSON.parse(raw);
      const verdict = classifyStatus(payload,profileFacts().deviceId);
      $('statusPreview').textContent = JSON.stringify({reported_device_id:payload.device_id ?? payload.deviceId ?? null,timestamp:payload.timestamp ?? payload.observed_at ?? payload.captured_at ?? payload.updated_at ?? null,source:payload.source_type ?? payload.source ?? null,online:payload.online ?? payload.connected ?? null},null,2);
      profileFacts().lastStatus = {state:verdict.state,checkedAt:new Date().toISOString(),endpoint:url.origin + url.pathname};
      record('api',verdict.state,'DEVICE',verdict.reason);
      setResult('statusResult',verdict.state,verdict.reason + ' · ' + (verdict.ageMs===undefined?'':Math.round(verdict.ageMs/1000)+'s old') + '. Network HTTP ' + response.status + '.');
    } catch(e) {
      record('api','BLOCKED','HOST','Disconnected, CORS-denied, timeout, invalid TLS/JSON, or unreachable: ' + e.message);
      setResult('statusResult','BLOCKED','DISCONNECTED · ' + e.message + '. No live source assertion.');
      $('statusPreview').textContent = 'No accepted response';
    }
  });
  $('exportReport').addEventListener('click',()=>{
    const content = JSON.stringify(buildReport(),null,2);
    const blob = new Blob([content],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='skynet-' + currentProfile + '-acceptance-' + new Date().toISOString().slice(0,10) + '.json';
    document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('Sanitized acceptance report exported locally.');
  });
  $('submitReport').addEventListener('click',async()=>{
    const token = $('gatewayToken').value;
    $('gatewayToken').value = '';
    try {
      if (!$('sendConsent').checked) throw Error('Explicit evidence-sharing approval required');
      const url = secureEndpoint($('gatewayUrl').value);
      if (url.pathname === '/' && !url.search) throw Error('Specify the exact authorized gateway ingestion path');
      const body=JSON.stringify(buildReport());
      const control=new AbortController(),timer=setTimeout(()=>control.abort(),8000);
      let response;
      try {
        response=await fetch(url.href,{method:'POST',mode:'cors',credentials:'omit',redirect:'error',cache:'no-store',signal:control.signal,headers:{'Content-Type':'application/json','Accept':'application/json',...(token?{'Authorization':'Bearer '+token}:{})},body});
      } finally {clearTimeout(timer);}
      if (!response.ok) throw Error('Gateway rejected receipt: HTTP ' + response.status);
      const replyText=await response.text();
      if (replyText.length > 20000) throw Error('Oversized gateway response');
      let reply={};
      try {reply=JSON.parse(replyText);}catch{reply={};}
      const receipt=String(reply.receipt_id ?? reply.receiptId ?? '');
      if (!/^[\w.-]{6,128}$/.test(receipt)) {
        record('gateway','UNVERIFIED','HOST','HTTP 2xx but no validated signed/traceable receipt ID; cannot assert ingestion');
        setResult('gatewayResult','UNVERIFIED','HTTP ' + response.status + ' response, but missing receipt ID. Ingestion unconfirmed.');
        return;
      }
      record('gateway','VERIFIED','HOST','HTTPS POST acknowledgment receipt ' + receipt + ' (transport only; server storage not independently audited)');
      setResult('gatewayResult','VERIFIED','HTTPS gateway returned receipt ID ' + receipt + '. Transport acknowledgment only; no RuView/CSI claim.');
    } catch(e) {
      record('gateway','BLOCKED','HOST','No accepted gateway receipt: ' + e.message);
      setResult('gatewayResult','BLOCKED',e.message);
    } finally {$('sendConsent').checked=false;}
  });
  $('saveEvidence').addEventListener('click',()=>{
    try {
      const id=$('evidenceStep').value, state=$('evidenceState').value, source=$('evidenceSource').value;
      const url=safeUrlInput('evidenceUrl'),hash=$('evidenceHash').value.trim();
      if (!url) throw Error('Exact HTTPS evidence URL is required for manual records');
      if (hash) normalizeSha(hash);
      const note=$('evidenceNote').value.trim();
      if (!note || note.length<15) throw Error('Describe exactly what the evidence proves and excludes (15+ characters)');
      if (state==='VERIFIED' && source==='SIMULATED') throw Error('Synthetic staging cannot verify physical claims');
      if (state==='VERIFIED' && !profileFacts().deviceId) throw Error('Identify the selected exact device before a manual verification');
      if (id==='approval' && state==='VERIFIED') throw Error('Approval must pass the dedicated hardware-image gate');
      if (id==='visual' && state==='VERIFIED' && !decodedFrame) throw Error('Visual acceptance must pass the decoded-image gate');
      record(id,state,source,note,url,hash.toLowerCase());
      setResult('evidenceResult',state,'Scoped evidence recorded; source authenticity is operator supplied, not independently authenticated.');
    } catch(e) {setResult('evidenceResult','FAILED',e.message);}
  });
  $('runTests').addEventListener('click',()=>runTests());
  $('clearSession').addEventListener('click',()=>{
    if (!confirm('Clear all in-memory evidence for every profile? This cannot be undone.')) return;
    records={cam:[],s3:[],cyd:[]};facts={cam:{},s3:{},cyd:{}};currentProfile='cam';
    switchProfile('cam');render();toast('Session evidence cleared. No network operation performed.');
  });
}
function buildReport() {
  const list=PROFILES[currentProfile];
  const f=profileFacts();
  // Deliberately exclude raw logs, images, MAC/IP secrets, Wi-Fi credentials, freeform input and auth tokens.
  return {
    schema:'skynet.s3cam.acceptance.v1',generated_at:new Date().toISOString(),profile:currentProfile,
    device_id:f.deviceId || null,build_id:f.bootId || null,
    claims:{flashed:false,camera_physical_acceptance:currentState('visual')==='VERIFIED'?'operator_attested':'unverified',csi_detected:false,ruview_detection_verified:false,live_ingestion_verified:false,production_deployed:false},
    image:f.image ? {sha256:f.image.sha256,size:f.image.size,offset:f.image.offset,manifest:f.image.manifest} : null,
    backup:f.backup ? {sha256:f.backup.sha256,size:f.backup.size,source:f.backup.source} : null,
    approval:f.approval ? {...f.approval,kind:'approval_record_only_no_write'} : null,
    camera:f.capture ? {...f.capture,source:'operator_supplied'} : null,
    status_probe:f.lastStatus || null,
    checks:list.map(id=>({id,state:currentState(id)})),
    evidence:profileRecords().map(r=>({time:r.time,step:r.step,state:r.state,source:r.source,url:r.url||null,digest:r.digest||null,summary:r.note.slice(0,200)}))
  };
}
function runTests(){
  const tests=[];
  const assert=(name,fn)=>{try{if(!fn())throw Error('assertion false');tests.push('PASS  '+name);}catch(e){tests.push('FAIL  '+name+' · '+e.message);}};
  const bytes=Uint8Array.of(0xff,0xd8,0x11,0x22,0xff,0xd9), b64=btoa(String.fromCharCode(...bytes)), crc=crc32(bytes);
  const log='CAM_BEGIN id=local-test bytes=6 crc32='+crc+'\nCAM_DATA id=local-test seq=0 b64='+b64+'\nCAM_END id=local-test bytes=6 crc32='+crc+'\n';
  const rejects=fn=>{try{fn();return false;}catch{return true;}};
  assert('Reference CRC32 123456789 = CBF43926',()=>crc32(new TextEncoder().encode('123456789'))==='CBF43926');
  assert('Complete base64 JPEG transport passes',()=>parseCaptureLog(log).frames[0].crc32===crc);
  assert('Truncated CAM_END rejected',()=>rejects(()=>parseCaptureLog(log.replace(/CAM_END.*\n/,''))));
  assert('Missing sequence rejected',()=>rejects(()=>parseCaptureLog(log.replace('seq=0','seq=1'))));
  assert('CRC32 mismatch rejected',()=>rejects(()=>parseCaptureLog(log.replace('CAM_END id=local-test bytes=6 crc32='+crc,'CAM_END id=local-test bytes=6 crc32=00000000'))));
  const bad=Uint8Array.of(0x00,0xd8,0x11,0x22,0xff,0xd9),badlog='CAM_BEGIN id=bad bytes=6\nCAM_DATA seq=0 hex='+hex(bad)+'\nCAM_END bytes=6 crc32='+crc32(bad);
  assert('Invalid JPEG SOI rejected',()=>rejects(()=>parseCaptureLog(badlog)));
  assert('Valid offset accepted',()=>normalizeOffset('0x10000')==='0x10000');
  assert('Unaligned offset rejected',()=>rejects(()=>normalizeOffset('0x10001')));
  const base={device_id:'real-chip',timestamp:new Date().toISOString()};
  assert('Fresh matching status is scoped to HTTP',()=>classifyStatus(base,'real-chip').state==='VERIFIED');
  assert('Wrong chip ID rejected',()=>classifyStatus(base,'other-chip').state==='FAILED');
  assert('Synthetic report blocked',()=>classifyStatus({...base,synthetic:true},'real-chip').state==='BLOCKED');
  assert('Stale report blocked',()=>classifyStatus({...base,timestamp:new Date(Date.now()-180000).toISOString()},'real-chip').state==='BLOCKED');
  assert('Missing timestamp not live',()=>classifyStatus({device_id:'real-chip'},'real-chip').state==='UNVERIFIED');
  const passed=tests.filter(x=>x.startsWith('PASS')).length;
  $('regressionResult').textContent=tests.join('\n')+'\n\n'+passed+'/'+tests.length+' host-side checks passed.\nNo physical device was tested.';
  toast('Regression run: '+passed+'/'+tests.length+' checks passed.');
}
setupHandlers();
render();
