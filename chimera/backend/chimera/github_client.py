"""Read-only GitHub REST API access with bounded search, provenance and caching."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, unquote, urlencode
from urllib.request import Request, urlopen

MAX_BYTES = 1_500_000
MAX_REPOS = 8
CACHE_TTL_SECONDS = 300
SLUG = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
QUERY = re.compile(r"^[A-Za-z0-9_.+\-/ ]{3,120}$")

class GitHubError(Exception):
    pass

def slug_from_input(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("Repository name must be text")
    s = raw.strip().rstrip("/")
    if s.startswith("https://"):
        u = urlparse(s)
        if u.hostname != "github.com" or u.username or u.password or u.port or u.query or u.fragment:
            raise ValueError("Only github.com HTTPS repository URLs are accepted")
        p = unquote(u.path).strip("/").split("/")
        if len(p) != 2:
            raise ValueError("Use a repository root URL, not a file or branch URL")
        s = "/".join(p)
    if not SLUG.fullmatch(s) or ".." in s or s.startswith("."):
        raise ValueError(f"Invalid GitHub repository: {raw[:150]}")
    return s

def validate_slugs(values: list[str]) -> list[str]:
    if not isinstance(values, list) or not 2 <= len(values) <= MAX_REPOS:
        raise ValueError(f"Supply between 2 and {MAX_REPOS} GitHub repositories")
    result, seen = [], set()
    for raw in values:
        slug = slug_from_input(raw)
        if slug.lower() not in seen:
            result.append(slug)
            seen.add(slug.lower())
    if len(result) < 2:
        raise ValueError("At least two distinct repositories are required")
    return result

def clean_search(raw: str) -> str:
    value = raw.strip()
    if not QUERY.fullmatch(value) or ".." in value:
        raise ValueError("Search must be 3-120 ordinary letters, numbers or topic separators")
    return value

def canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sha256(obj: object) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class GitHubClient:
    def __init__(self, cache_file: str | Path | None = None, token: str | None = None):
        self.cache_file = Path(cache_file or os.environ.get("CHIMERA_CACHE", str(Path.home() / ".cache" / "chimera-lab" / "repos.sqlite3")))
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.cache_file) as db:
            db.execute("CREATE TABLE IF NOT EXISTS repos (slug TEXT PRIMARY KEY, fetched REAL NOT NULL, body TEXT NOT NULL)")

    def _read_api(self, path: str) -> dict | list:
        if not (re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/contents)?", path)
                or re.fullmatch(r"/search/repositories\?[A-Za-z0-9_=&%+.\-]+", path)):
            raise GitHubError("API path rejected")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "918-Chimera-Lab/1.0", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request("https://api.github.com" + path, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=15) as resp:
                if urlparse(resp.geturl()).hostname != "api.github.com":
                    raise GitHubError("Unexpected API redirect")
                data = resp.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise GitHubError("GitHub response too large")
                return json.loads(data)
        except HTTPError as e:
            if e.code in (403, 429):
                raise GitHubError("GitHub API rate limit or authorization restriction; retry after the reset window or set GITHUB_TOKEN") from e
            if e.code == 404:
                raise GitHubError("Repository not found or unavailable") from e
            raise GitHubError(f"GitHub HTTP error {e.code}") from e
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as e:
            raise GitHubError("GitHub metadata could not be retrieved") from e

    def search(self, query: str, limit: int = 8) -> dict:
        q = clean_search(query)
        if not isinstance(limit, int) or not 2 <= limit <= MAX_REPOS:
            raise ValueError(f"Search limit must be between 2 and {MAX_REPOS}")
        params = urlencode({"q": q + " archived:false", "per_page": limit})
        response = self._read_api("/search/repositories?" + params)
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise GitHubError("Unexpected GitHub search payload")
        repos = []
        for obj in response["items"]:
            try:
                repos.append(slug_from_input(str(obj["full_name"])))
            except (KeyError, ValueError, TypeError):
                continue
        return {"query": q, "slugs": repos[:limit], "count": int(response.get("total_count") or 0),
                "incomplete_results": bool(response.get("incomplete_results")), "queried_at": utcnow(),
                "source_url": "https://github.com/search?" + urlencode({"q": q, "type": "repositories"}),
                "source_type": "github_api_live_search"}

    def get(self, slug: str, fresh: bool = True) -> dict:
        slug = slug_from_input(slug)
        with sqlite3.connect(self.cache_file) as db:
            hit = db.execute("SELECT fetched, body FROM repos WHERE slug=?", (slug.lower(),)).fetchone()
        if not fresh and hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
            item = json.loads(hit[1])
            item["cache_hit"] = True
            return item
        repo = self._read_api(f"/repos/{slug}")
        try:
            root = self._read_api(f"/repos/{slug}/contents")
            filenames = [str(item.get("name", ""))[:100] for item in root[:150] if isinstance(item, dict)] if isinstance(root, list) else []
            root_state = "retrieved"
        except GitHubError:
            filenames = []
            root_state = "unavailable"
        if not isinstance(repo, dict) or not repo.get("full_name"):
            raise GitHubError("Unexpected repository metadata")
        license_info = repo.get("license") or {}
        metadata = {
            "slug": repo["full_name"], "description": str(repo.get("description") or "")[:600],
            "homepage": str(repo.get("homepage") or "")[:300],
            "topics": [str(x)[:75] for x in repo.get("topics", [])[:30]],
            "language": str(repo.get("language") or "Unknown")[:60],
            "stars": int(repo.get("stargazers_count") or 0),
            "license": str(license_info.get("spdx_id") or "UNKNOWN")[:80],
            "license_url": f"https://github.com/{repo['full_name']}/blob/{repo.get('default_branch') or 'HEAD'}/LICENSE",
            "pushed_at": repo.get("pushed_at"), "archived": bool(repo.get("archived")),
            "fork": bool(repo.get("fork")), "default_branch": repo.get("default_branch"),
            "root_files": filenames, "root_state": root_state,
            "source_url": f"https://github.com/{repo['full_name']}",
            "api_url": f"https://api.github.com/repos/{repo['full_name']}",
            "fetched_at": utcnow(), "source_type": "github_api",
        }
        metadata["metadata_sha256"] = sha256(metadata)
        metadata["cache_hit"] = False
        with sqlite3.connect(self.cache_file) as db:
            db.execute("INSERT OR REPLACE INTO repos(slug, fetched, body) VALUES (?, ?, ?)", (slug.lower(), time.time(), json.dumps(metadata)))
        return metadata
