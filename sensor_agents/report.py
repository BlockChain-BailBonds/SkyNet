"""Combine separate read-only NOAA and HAARP agents for the public operator console.

A linked HAARP diagnostic page is not a live instrument sample. A trained
candidate remains shadow-only until reviewed by an authorized operator.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from sensor_agents.runtime import HAARP_SPECS, Supervisor, sha

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "public"

MAP_DOCS = {
    "HAARP.IRI_ARRAY": "HAARP transmission notices",
    "HAARP.RIOMETER": "HAARP SAGO riometer chart",
    "HAARP.OBLIQUE_IONOSONDE": "HAARP oblique ionosonde chart",
    "HAARP.SEISMIC": "HAARP RFE1B FDSN channel metadata",
}


def assemble(solar: dict, haarp: dict, at: str) -> dict:
    if not isinstance(solar, dict) or not isinstance(haarp, dict):
        raise ValueError("agent report input must be JSON objects")
    solar_monitor = solar.get("agent_monitor")
    if not isinstance(solar_monitor, dict) or not isinstance(solar_monitor.get("agents"), list):
        raise ValueError("NOAA agent monitor missing; refuse synthetic success")
    documents = haarp.get("source_documents", {})
    if not isinstance(documents, dict):
        documents = {}
    haarp_monitor = Supervisor(HAARP_SPECS, at)
    for spec in HAARP_SPECS:
        label = MAP_DOCS.get(spec.sensor_id, "HAARP diagnostic catalog")
        entry = documents.get(label)
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if isinstance(digest, str) and len(digest) == 64:
            haarp_monitor.linked_metadata(spec.sensor_id, digest)
        else:
            haarp_monitor.quarantine(spec.sensor_id, "FETCH_FAILED")
    # Independent chained source ledgers, rather than pretending one globally
    # atomic append log across two processes and separate remote requests.
    return {
        "schema_version": "1.0",
        "collected_at": at,
        "agent_count": len(solar_monitor["agents"]) + len(haarp_monitor.states),
        "agents": solar_monitor["agents"] + list(haarp_monitor.states.values()),
        "monitors": {
            "NOAA": {
                "chain_head": solar_monitor["chain_head"],
                "events": solar_monitor["events"],
            },
            "HAARP": {
                "chain_head": haarp_monitor.head,
                "events": haarp_monitor.events,
            },
        },
        "training": {
            "mode": "SHADOW_ONLY",
            "autonomous_model_promotion": False,
            "policy": "Every validated I/O is tracked; training requires numeric, timely, authorized source observations and holdout testing",
            "non_numeric_status": "HAARP source catalogs and transmitter notices cannot train physical sensor models",
        },
    }


def main():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    solar_path = PUBLIC / "space-weather.json"
    haarp_path = PUBLIC / "haarp-status.json"
    if not solar_path.is_file():
        raise SystemExit("NOAA observation snapshot missing: no agent report written")
    solar = json.loads(solar_path.read_text(encoding="utf-8"))
    haarp = json.loads(haarp_path.read_text(encoding="utf-8")) if haarp_path.exists() else {}
    report = assemble(solar, haarp, now)
    out = PUBLIC / "sensor-agents.json"
    temp = out.with_suffix(".tmp")
    temp.write_text(json.dumps(report, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(out)
    print(json.dumps({"agents": report["agent_count"],
                      "shadow_only": report["training"]["autonomous_model_promotion"] is False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
