# 918 CHIMERA LAB LIVE

A live, read-only GitHub repository analysis and capability-combination service. **No mock data is shown in the operator dashboard.** The server fetches current public repository search results, scans repository metadata and root manifests, builds a NetworkX capability graph, and ranks hypotheses about cross-project integration. Each source carries a timestamp and metadata SHA-256 digest.

Original integration design: Matthew Blake Ward in association with 918 Technologies. Upstream repository authors retain all third-party intellectual property.

## Running locally

Python 3.11+:

```bash
python -m pip install -e '.[test]'
CHIMERA_ENV=development python -m chimera serve --port 8189
```

Open `http://127.0.0.1:8189`. Click **Test connection**, then **Run live analysis**. The default search `esp32 sensor` fetches public GitHub repository search results (subject to network and GitHub rate limits).

Or run Docker:

```bash
docker build -t 918-chimera-lab .
docker run --rm -p 8189:8189 -e CHIMERA_ENV=production -e CHIMERA_OPERATOR_KEY='replace-with-strong-random-secret' 918-chimera-lab
```

Never put a GitHub token in the GitHub Pages code, and do not embed the operator key in any committed file.

## Live backend deployment

The repo includes `render.yaml`, a Docker Blueprint for a live Render web service. Create a Render Blueprint linked to the GitHub repo, configure `GITHUB_TOKEN` as a secret (optional, but strongly recommended for production rate limits), and deploy. A Render account and provider authorization are required; committing the Blueprint is **not equivalent to deploying a service**. Restrict the allowed frontend origin in `CHIMERA_CORS_ORIGINS`. Your backend URL will be assigned by your hosting provider.

`CHIMERA_OPERATOR_KEY` is generated at deployment if absent. Obtain it through the backend host's secret-management interface, then paste it in the dashboard; the dashboard keeps it only in tab memory (not a URL, repo file, or browser persistent storage).

## GitHub Pages dashboard

Publish `web/index.html` as the Pages document at `/chimera/` (or the root of a dedicated Pages repo). Set the **HTTPS backend origin** to the live Render backend URL, then enter the operator key. The browser communicates with `GET /api/live` using a real streamed `fetch` request with `X-Operator-Key`. Pages itself is static hosting; the full system is dynamic because the external backend performs real GitHub calls and analysis.

If installed in `BlockChain-BailBonds/SkyNet`, place `web/index.html` at `chimera/index.html` without replacing SkyNet's existing landing page. GitHub Pages publication must be configured for the host repository; the path existing in GitHub alone is not evidence that Pages is enabled.

## API contract

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Live service process heartbeat and status |
| `/api/search?q=esp32%20sensor&limit=6` | GET | GitHub repository search, real results |
| `/api/live?q=esp32%20sensor&limit=6` | GET | SSE status, search, repository, warning, result and done events |
| `/api/scan` | POST | Scan 2–8 named repositories, `{"repositories":["owner/repo", "owner2/repo2"], "fresh":true}` |
| `/api/explain` | POST | Optional local-only Ollama explanation, disabled unless explicitly configured |
| `/api/docs` | GET | OpenAPI documentation |

All scan/search/live/explain endpoints require `X-Operator-Key` when `CHIMERA_OPERATOR_KEY` is configured. **Production mode refuses to run protected actions without this key.** There is a process-local burst limit per connection IP, plus GitHub's own upstream rate limits. Scale-out requires moving rate limits to a shared store or enforcing them at the edge.

## Actual scope

- ✅ Live GitHub REST search and read-only repository metadata collection
- ✅ Fresh timestamps, SHA-256 provenance, explicit retrieval failures, current license SPDX metadata
- ✅ NetworkX repository-to-capability graph and deterministic combination ranking
- ✅ Responsive GitHub Pages-compatible dashboard, streaming progress, evidence JSON export
- ✅ Local tests for input validation, trust gates, classification and HTTP API wiring
- ⚠️ Repository API compatibility is **only a hypothesis** until real adapter code, protocol tests, licensing review and live acceptance are performed
- ⚠️ No global search can prove a particular combination has never been attempted
- ⛔ Does not install, execute, deploy or flash third-party repositories; no autonomous unsandboxed code execution
- ⛔ Does not claim a live deployment without a verified endpoint and host configuration

## Third-party components

Uses [FastAPI](https://github.com/fastapi/fastapi), [NetworkX](https://github.com/networkx/networkx) and [Uvicorn](https://github.com/encode/uvicorn); consult their original licenses and pinned dependency graph when creating releases.
