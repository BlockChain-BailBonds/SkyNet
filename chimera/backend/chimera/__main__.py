"""Entrypoint for local web UI and deterministic offline analyses."""
import argparse
import json
from pathlib import Path
import uvicorn
from .api import FIXTURE
from .fusion import fuse
from .github_client import GitHubClient, GitHubError, validate_slugs

def main():
    p = argparse.ArgumentParser(prog="chimera-lab", description="918 Chimera Lab repository composition engine")
    p.add_argument("command", choices=["serve", "demo", "scan"])
    p.add_argument("repositories", nargs="*", help="2-8 GitHub owner/repo names or root URLs for scan")
    p.add_argument("--output", "-o", help="Write analysis JSON to this file for demo/scan")
    p.add_argument("--port", type=int, default=8189)
    args = p.parse_args()
    if args.command == "serve":
        if args.repositories:
            p.error("serve does not take repository inputs")
        uvicorn.run("chimera.api:app", host="127.0.0.1", port=args.port, reload=False, log_level="info")
        return
    if args.command == "demo":
        if args.repositories:
            p.error("demo does not take repository inputs")
        repos = json.loads(FIXTURE.read_text(encoding="utf-8"))
        repos = [dict(r, source_type="fixture", fetched_at=None, metadata_sha256=None, root_state="fixture_only") for r in repos]
    else:
        try:
            slugs = validate_slugs(args.repositories)
            client = GitHubClient()
            repos = [client.get(slug) for slug in slugs]
        except (ValueError, GitHubError) as e:
            p.error(str(e))
    result = fuse(repos)
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")
        print(f"Wrote {target} with {len(result['proposals'])} proposals")
    else:
        print(encoded)

if __name__ == "__main__":
    main()
