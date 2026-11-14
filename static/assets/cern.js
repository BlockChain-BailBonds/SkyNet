/* Independent read-only CERN panel. No operator token, CORS proxy or detector controls. */
const area = document.getElementById('cern');
const escaped = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
}[ch]));
const status = value => {
  const label = ['VERIFIED','UNVERIFIED','BLOCKED','FAILED'].includes(value) ? value : 'UNVERIFIED';
  return '<span class="badge ' + label.toLowerCase() + '">' + label + '</span>';
};
const allowedUrl = input => {
  try {
    const u = new URL(String(input));
    if (u.protocol !== 'https:' || !['opendata.cern.ch','home.cern','vistar-capture.s3.cern.ch'].includes(u.hostname)) return null;
    return u.href;
  } catch { return null; }
};
const link = (url, title) => {
  const permitted = allowedUrl(url);
  return permitted ? '<a target="_blank" rel="noopener noreferrer" href="' + escaped(permitted) + '">' + escaped(title) + '</a>' : '';
};
function render(snapshot) {
  if (!area) return;
  const now = Date.now();
  const age = Date.parse(snapshot?.collected_at || '');
  const fresh = Number.isFinite(age) && now >= age && now - age <= 90 * 60 * 1000;
  const agents = Array.isArray(snapshot?.agents) ? snapshot.agents : [];
  const verified = fresh ? agents.filter(x => x.status === 'VERIFIED').length : 0;
  const seen = snapshot?.collected_at || 'NO SNAPSHOT';
  const common = 'Catalog records and website responses are NOT live CERN sensor data, collision events, or accelerator commands.';
  let html = '<div class="title"><h1>CERN Intelligence Network</h1>' + status(fresh ? 'UNVERIFIED' : 'BLOCKED') + '</div>';
  html += '<p class="fine">Read-only CERN public science monitoring · ' + escaped(common) + '</p>';
  html += '<div class="metrics">' +
    [['Public metadata sources', verified + ' / ' + (agents.length || 6)],
     ['Live detector streams', '0'],
     ['CERN sensor credentials', 'NONE'],
     ['Cross-source correlation', 'BLOCKED']].map(item =>
      '<div class="metric"><strong>' + escaped(item[1]) + '</strong><span>' + escaped(item[0]) + '</span></div>'
    ).join('') + '</div>';
  html += '<article><h2>Acquisition evidence</h2><p>Snapshot published: ' + escaped(seen) +
    ' · freshness: ' + (fresh ? 'RECENT' : 'STALE / NOT AVAILABLE') +
    ' · source success means HTTP content and schema verified, never live physical access.</p>' +
    '<p>SHA-256 response digests and a linked collection ledger are included in the snapshot. Raw CERN datasets are not mirrored.</p>' +
    '<p>' + link('https://opendata.cern.ch/', 'Open Data Portal') + ' · ' +
    link('https://vistar-capture.s3.cern.ch/index.html', 'Public LHC display directory') + ' · ' +
    link('https://home.cern/science/experiments/cloud/', 'CLOUD experiment') + '</p>' +
    '<button id="cernReload" class="quiet">Reload published snapshot</button></article>';
  if (!agents.length) {
    html += '<article><h2>Collector not verified</h2>' + status('BLOCKED') +
      '<p>data/public/cern-status.json was not produced or cannot be loaded. No CERN ingestion evidence is available.</p></article>';
  }
  html += '<div class="cern-grid">' + agents.map(a => {
    const effective = fresh ? a.status : 'UNVERIFIED';
    const records = Array.isArray(a.metadata?.sampled_records) ? a.metadata.sampled_records : [];
    const hasCatalog = a.kind === 'catalog';
    const description = hasCatalog ? 'Released research catalog · ' +
       escaped(a.metadata?.matched_records ?? 'UNKNOWN') + ' matching records' :
       'Website / display directory metadata only; no numeric detector measurements';
    return '<article><div class="row"><b>' + escaped(a.name) + '</b>' + status(effective) + '</div>' +
      '<p>' + description + '</p>' +
      '<p class="fine">Agent ' + escaped(a.id) + ' · Last checked ' + escaped(a.checked_at) +
      ' · ' + escaped(a.reason) + '</p>' +
      '<p class="fine">Source SHA-256: <code>' + escaped(a.response_sha256 || 'NOT AVAILABLE') + '</code></p>' +
      (records.length ? '<details><summary>Sample released records</summary><ul>' +
        records.map(r => '<li>' + link(r.url, r.title) + '</li>').join('') + '</ul></details>' : '') +
      link(a.source_url, 'Official source') + '</article>';
  }).join('') + '</div>';
  html += '<article><h2>Training and inference gate</h2>' + status('BLOCKED') +
    '<p>Metadata is not numeric particle, solar, or atmospheric time-series. Predictive correlation and learning remain disabled until separately authorized, calibrated, time-aligned measurements are validated.</p></article>';
  area.innerHTML = html;
  const reload = document.getElementById('cernReload');
  if (reload) reload.addEventListener('click', load);
}
async function load() {
  try {
    const response = await fetch('./data/public/cern-status.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('snapshot unavailable');
    const snapshot = await response.json();
    if (snapshot?.schema_version !== '1.0' || !Array.isArray(snapshot.agents)) throw new Error('invalid snapshot');
    render(snapshot);
  } catch { render(null); }
}
load();
