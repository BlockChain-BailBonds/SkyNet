"""Deterministic repository affordance model: evidence is not proof of novelty."""
from __future__ import annotations
from itertools import combinations
import math
import re
import networkx as nx
from .github_client import sha256, utcnow

CAPABILITIES = {
    "sensing": ("sensor", "iot", "csi", "radar", "camera", "wifi sensing", "esp32", "telemetry", "spatial intelligence"),
    "geospatial": ("geospatial", "mapping", "maps", "gis", "location", "vector tile", "geography", "satellite", "maplibre"),
    "environment": ("weather", "climate", "forecast", "air quality", "meteorology", "earthquake", "ocean", "meteorological"),
    "reasoning": ("llm", "language model", "ai", "machine learning", "inference", "ollama", "agent", "neural"),
    "networking": ("mesh", "messaging", "mqtt", "lorawan", "networking", "radio", "bluetooth", "websocket", "meshtastic"),
    "trust": ("policy", "cryptography", "authentication", "security", "provenance", "verification", "opa", "attestation"),
    "graph": ("graph", "network analysis", "networkx", "visualisation", "visualization", "cytoscape"),
    "hardware": ("firmware", "embedded", "microcontroller", "idf", "arduino", "platformio", "rtos", "driver"),
    "storage": ("database", "storage", "ipfs", "content-addressed", "archival", "sqlite", "object store"),
    "documents": ("document", "markdown", "pdf", "text extraction", "ocr", "office", "markitdown"),
}
PORTS = {
    "http": ("api", "http", "rest", "web service", "webserver", "server"),
    "mqtt": ("mqtt",),
    "websocket": ("websocket", "socket.io"),
    "python": ("python", "pyproject.toml", "setup.py"),
    "javascript": ("javascript", "typescript", "package.json", "node.js"),
    "cli": ("cli", "command line", "terminal"),
    "file": ("json", "csv", "parquet", "file", "yaml"),
}
PERMISSIVE = {"MIT", "APACHE-2.0", "BSD-3-CLAUSE", "BSD-2-CLAUSE", "ISC", "UNLICENSE"}
RECIPROCAL = {"GPL-2.0", "GPL-3.0", "GPL-3.0-ONLY", "GPL-3.0-OR-LATER", "AGPL-3.0", "AGPL-3.0-ONLY", "AGPL-3.0-OR-LATER", "LGPL-3.0", "MPL-2.0"}

def _matches(hay: str, needles: tuple[str, ...]) -> list[str]:
    found = []
    for token in needles:
        # Bound single-word tokens to avoid matching ordinary substrings.
        pattern = r"(?<!\w)" + re.escape(token) + r"(?!\w)" if " " not in token else re.escape(token)
        if re.search(pattern, hay):
            found.append(token)
    return found

def annotate(repo: dict) -> dict:
    r = dict(repo)
    body = " ".join([str(r.get("slug", "")), str(r.get("description", "")), str(r.get("language", "")), " ".join(r.get("topics", [])), " ".join(r.get("root_files", []))]).lower()
    caps = {name: hits for name, keywords in CAPABILITIES.items() if (hits := _matches(body, keywords))}
    ports = {name: hits for name, keywords in PORTS.items() if (hits := _matches(body, keywords))}
    r["capabilities"] = caps
    r["ports"] = ports
    r["classification_status"] = "keyword_heuristic_only"
    return r

def license_review(repos: list[dict]) -> dict:
    ids = {str(r.get("license") or "UNKNOWN").upper() for r in repos}
    if any(x in {"UNKNOWN", "NOASSERTION", "OTHER"} or x.startswith("LICENSE") for x in ids):
        status = "blocked_pending_manual_license_review"
        note = "At least one license is missing or nonstandard; do not copy, redistribute, or link its code without review."
    elif all(x in PERMISSIVE for x in ids):
        status = "preliminary_permissive_only"
        note = "These reported SPDX identifiers are broadly permissive; preserve attribution and verify full license files and dependencies."
    else:
        status = "manual_copyleft_or_mixed_license_review"
        note = "Reciprocal or mixed licenses detected; integration/derivative and distribution obligations depend on actual linking and deployment."
    return {"status": status, "licenses": sorted(ids), "note": note, "legal_conclusion": False}

def _bridge(a: dict, b: dict) -> dict:
    pa, pb = set(a.get("ports", {})), set(b.get("ports", {}))
    shared = sorted(pa & pb)
    if shared:
        return {"from": a["slug"], "to": b["slug"], "mechanism": "candidate shared: " + ", ".join(shared), "evidence": shared, "status": "unverified_api_compatibility"}
    if "http" in pa | pb:
        return {"from": a["slug"], "to": b["slug"], "mechanism": "proposed HTTP adapter", "evidence": [], "status": "adapter_required"}
    return {"from": a["slug"], "to": b["slug"], "mechanism": "proposed JSON/file bridge", "evidence": [], "status": "adapter_required"}

def _product_name(caps: set[str]) -> tuple[str, str, str]:
    if {"sensing", "environment", "geospatial"} <= caps:
        return ("Counterfactual Earth Lens", "Compare consented local sensing against weather context and spatial geography to isolate anomalies.", "Test whether local signal shifts coincide with forecast conditions before inferring a physical event.")
    if {"sensing", "networking", "trust"} <= caps:
        return ("Witness Mesh", "Move consented sensor receipts through intermittent mesh networks with policy-controlled release.", "Check authenticated receipts and missing-node gaps across mesh partitions.")
    if {"hardware", "graph", "trust"} <= caps:
        return ("Pin-Safe Firmware Genome", "Build an explainable constraint graph for device firmware adaptations before any flash operation.", "Propose pin/resource constraints and produce a human approval gate; do not flash hardware.")
    if {"documents", "graph", "reasoning"} <= caps:
        return ("Living Evidence Compiler", "Convert documents to citation-linked graphs that answer questions with traceable evidence.", "Compare graph-linked claims against the exact source passages.")
    if {"geospatial", "reasoning", "environment"} <= caps:
        return ("Forecast Story Atlas", "Turn geographic forecast changes into spatially linked, uncertainty-aware explanations.", "Validate forecast changes with archived input snapshots and attributable data.")
    if {"sensing", "reasoning", "graph"} <= caps:
        return ("Observation Logic Loom", "Build structured and falsifiable hypotheses from observed sensor state transitions.", "Test alternative hypotheses against replayed, consented signal sequences.")
    if {"networking", "storage", "trust"} <= caps:
        return ("Delay-Tolerant Proof Courier", "Store and verify authenticated payload receipts across disconnected transports.", "Replay transfers across a synthetic network partition and verify content hashes.")
    labels = ", ".join(sorted(caps)[:4]) if caps else "unclassified capabilities"
    return ("Capability Chimera", f"Fuse complementary open-source systems spanning {labels} with explicit adapter contracts.", "Validate a one-way JSON input/output contract before attempting any deeper integration.")

def fuse(repos: list[dict], maximum: int = 12) -> dict:
    if len(repos) < 2:
        raise ValueError("At least two repositories required")
    annotated = [annotate(r) for r in repos]
    all_caps = sorted({c for r in annotated for c in r["capabilities"]})
    graph = nx.Graph()
    for r in annotated:
        graph.add_node(r["slug"], kind="repository")
        for c in r["capabilities"]:
            graph.add_node(c, kind="capability")
            graph.add_edge(r["slug"], c, kind="has_capability")
    combos = []
    for subset in combinations(annotated, min(3, len(annotated))):
        cats = [set(x["capabilities"]) for x in subset]
        cover = set().union(*cats)
        diversity = min(1.0, len(cover) / 5.0)
        pairwise = list(combinations(cats, 2))
        uncommon = sum(1 - len(a & b) / max(1, len(a | b)) for a, b in pairwise) / len(pairwise)
        bridges = [_bridge(a, b) for a, b in combinations(subset, 2)]
        bridging = sum(1 if b["evidence"] else 0.25 for b in bridges) / len(bridges)
        review = license_review(list(subset))
        lic = 1.0 if review["status"] == "preliminary_permissive_only" else 0.40 if review["status"].startswith("manual") else 0.15
        score = round(100 * (0.35 * diversity + 0.30 * uncommon + 0.20 * bridging + 0.15 * lic))
        title, concept, experiment = _product_name(cover)
        key = [r["slug"] for r in subset]
        recipe = {
            "id": sha256(key)[:16], "title": title, "thesis": concept,
            "experiment": experiment, "repos": key,
            "capabilities": sorted(cover), "score": score,
            "score_type": "diversity_and_feasibility_heuristic_not_global_novelty",
            "bridges": bridges,
            "license_review": review,
            "implementation": [
                {"step": 1, "work": "Review upstream licenses, dependencies, stability, and threat model", "state": "not_started"},
                {"step": 2, "work": "Define a versioned JSON boundary with mock producer and consumer", "state": "not_started"},
                {"step": 3, "work": "Build read-only adapters in an isolated environment", "state": "not_started"},
                {"step": 4, "work": "Replay synthetic fixtures and verify byte-for-byte output hashes", "state": "not_started"},
                {"step": 5, "work": "Connect authorized live sources; compare against independently recorded evidence", "state": "not_started"},
            ],
            "validation_status": "concept_only_unverified",
        }
        combos.append(recipe)
    combos.sort(key=lambda p: (-p["score"], p["id"]))
    # Canonical recipe is distinct by inputs; titles may repeat by design.
    result = {
        "schema_version": "1.0",
        "created_at": utcnow(),
        "source_mode": "fixture" if all(r.get("source_type") == "fixture" for r in repos) else "github_api_or_mixed",
        "repositories": annotated,
        "capabilities": all_caps,
        "graph": nx.node_link_data(graph, edges="links"),
        "proposals": combos[:maximum],
        "proposals_total": len(combos),
        "warnings": [
            "No claim of worldwide novelty, patentability, or freedom to operate.",
            "Keyword heuristics are not verified API compatibility.",
            "No upstream code was copied, cloned, built, or executed.",
            "Concept tests are not hardware, model, integration, or production acceptance.",
        ],
    }
    result["analysis_sha256"] = sha256({k: v for k, v in result.items() if k not in ("created_at", "analysis_sha256")})
    return result
