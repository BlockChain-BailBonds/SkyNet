import json
from fastapi.testclient import TestClient
from chimera.api import app

client = TestClient(app)

def test_health():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json()['mode'] == 'live_read_only'
    assert r.json()['observed_at']

def test_bad_exact_repository_is_rejected():
    r = client.post('/api/scan', json={'repositories': ['https://example.com/a/b', 'x/y']})
    assert r.status_code == 422

def test_invalid_search_is_rejected():
    r = client.get('/api/search', params={'q': 'curl && exec', 'limit': 4})
    assert r.status_code == 422

def test_explain_disabled(monkeypatch):
    monkeypatch.delenv('OLLAMA_MODEL', raising=False)
    r = client.post('/api/explain', json={'title': 'A test proposal', 'thesis': 'Testable proposal for capabilities', 'repositories': ['a/b', 'c/d'], 'mechanisms': ['file adapter']})
    assert r.status_code == 503

def test_operator_key_required(monkeypatch):
    monkeypatch.setenv('CHIMERA_OPERATOR_KEY', 'a-long-test-key')
    r=client.post('/api/scan', json={'repositories': ['a/b','c/d']})
    assert r.status_code==401

def test_production_requires_auth(monkeypatch):
    monkeypatch.delenv('CHIMERA_OPERATOR_KEY', raising=False)
    monkeypatch.setenv('CHIMERA_ENV','production')
    r=client.get('/api/search', params={'q':'esp32 sensor'})
    assert r.status_code==503

def test_live_sse_with_mocked_github(monkeypatch):
    import chimera.api as api
    base={'description':'IoT sensor MQTT API', 'language':'Python', 'stars':1, 'license':'MIT', 'topics':[], 'root_files':['pyproject.toml'], 'fetched_at':'2026-11-12T00:00:00Z', 'metadata_sha256':'a'*64, 'source_type':'github_api', 'root_state':'retrieved', 'cache_hit':False}
    monkeypatch.delenv('CHIMERA_OPERATOR_KEY', raising=False)
    monkeypatch.setenv('CHIMERA_ENV','development')
    monkeypatch.setattr(api.GitHubClient, 'search', lambda self,q,limit:{'query':q,'slugs':['a/one','b/two'], 'count':2,'queried_at':'2026-11-12', 'incomplete_results':False})
    monkeypatch.setattr(api.GitHubClient, 'get', lambda self,slug,fresh=True:dict(base,slug=slug))
    r=client.get('/api/live?q=esp32%20sensor&limit=2')
    assert r.status_code==200
    assert 'event: repository' in r.text
    assert 'event: result' in r.text
    assert '"source_mode":"github_api_or_mixed"' in r.text
