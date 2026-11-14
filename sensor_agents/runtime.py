"""Sensor-specific evidence agents and guarded training for SkyNet.

Every supported ingress/egress is accounted for with a SHA-256 hash chain.
Only validated public numeric observations can produce shadow training models.
No credential, private payload, or model parameter is exposed on GitHub Pages.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(obj: Any) -> str:
    return hashlib.sha256(obj if isinstance(obj, bytes) else canonical(obj)).hexdigest()


def at_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None:
        raise ValueError("agent event timestamps require a time zone")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: str
    source_url: str
    field: str | None = None
    unit: str | None = None
    lower: float | None = None
    upper: float | None = None
    min_samples: int = 32

    def __post_init__(self):
        if not self.sensor_id or not self.sensor_id.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise ValueError("invalid sensor ID")
        if not self.source_url.startswith("https://"):
            raise ValueError("sensors require HTTPS public sources")
        if (self.field is None) != (self.unit is None):
            raise ValueError("numeric training requires field and unit")
        if self.field is not None and (self.lower is None or self.upper is None or self.lower >= self.upper):
            raise ValueError("numeric bounds are required")


class Supervisor:
    """Append-only in-memory chain of bounded, non-sensitive source evidence."""

    def __init__(self, specs: list[SensorSpec], now: str):
        at_utc(now)
        self.now = now
        self.specs = {spec.sensor_id: spec for spec in specs}
        if len(self.specs) != len(specs):
            raise ValueError("duplicate sensor IDs")
        self.events: list[dict] = []
        self.states = {key: {"id": key, "source_url": spec.source_url,
                             "input_count": 0, "output_count": 0,
                             "last_status": "UNVERIFIED",
                             "learning": "AWAITING_VALIDATED_OBSERVATIONS",
                             "training_candidate": None, "last_observed_at": None}
                       for key, spec in self.specs.items()}
        self.head = "0" * 64

    def _append(self, sensor_id: str, direction: str, digest: str, status: str, observed_at: str | None):
        if sensor_id not in self.specs:
            raise ValueError("unregistered sensor agent")
        if direction not in {"INPUT", "OUTPUT", "QUARANTINE", "TRAIN_CANDIDATE"}:
            raise ValueError("invalid event direction")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid evidence SHA-256")
        if observed_at is not None:
            at_utc(observed_at)
        event = {"sequence": len(self.events) + 1, "agent_id": sensor_id,
                 "direction": direction, "sha256": digest,
                 "status": status, "observed_at": observed_at,
                 "recorded_at": self.now, "prev_hash": self.head}
        event["chain_hash"] = sha(event)
        self.head = event["chain_hash"]
        self.events.append(event)
        state = self.states[sensor_id]
        if direction == "INPUT":
            state["input_count"] += 1
        elif direction == "OUTPUT":
            state["output_count"] += 1
            state["last_status"] = status
            state["last_observed_at"] = observed_at
        elif direction == "QUARANTINE":
            state["last_status"] = "BLOCKED"
        return event

    def ingress(self, sensor_id: str, raw: bytes):
        if not isinstance(raw, bytes) or len(raw) == 0 or len(raw) > 1_000_000:
            raise ValueError("sensor input empty or exceeds bounded payload limit")
        return self._append(sensor_id, "INPUT", sha(raw), "RECEIVED", None)

    def egress(self, sensor_id: str, normalized: dict):
        if not isinstance(normalized, dict):
            raise ValueError("normalized data must be a dict")
        observed_at = normalized.get("observed_at")
        status = "VERIFIED" if normalized.get("fresh") is True else "UNVERIFIED"
        return self._append(sensor_id, "OUTPUT", sha(normalized), status, observed_at)

    def quarantine(self, sensor_id: str, reason: str):
        # Reason is a constant code from the adapter, not a raw exception that may reveal secrets.
        if reason not in {"FETCH_FAILED", "SCHEMA_REJECTED", "STALE", "POLICY_REJECTED"}:
            raise ValueError("invalid quarantine code")
        return self._append(sensor_id, "QUARANTINE", sha({"code": reason}), "BLOCKED", None)

    def candidate(self, sensor_id: str, samples: list[dict]):
        """Train a descriptive MAD baseline in SHADOW mode; never self-deploy."""
        spec = self.specs[sensor_id]
        if spec.field is None:
            self.states[sensor_id]["learning"] = "NO_NUMERIC_MEASUREMENT"
            return None
        accepted = []
        seen = set()
        cutoff = at_utc(self.now)
        for row in samples:
            if not isinstance(row, dict):
                continue
            timestamp = row.get("observed_at")
            value = row.get("value")
            try:
                dt = at_utc(timestamp)
            except (TypeError, ValueError):
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            value = float(value)
            if not math.isfinite(value) or value < spec.lower or value > spec.upper:
                continue
            if dt > cutoff + timedelta(minutes=6) or timestamp in seen:
                continue
            seen.add(timestamp)
            accepted.append((dt, value))
        accepted.sort()
        if len(accepted) < spec.min_samples:
            self.states[sensor_id]["learning"] = "INSUFFICIENT_VALIDATED_SAMPLES"
            return None
        holdout_count = max(6, len(accepted) // 5)
        if len(accepted) - holdout_count < 24:
            self.states[sensor_id]["learning"] = "INSUFFICIENT_TRAINING_WINDOW"
            return None
        training = [v for _, v in accepted[:-holdout_count]]
        holdout = [v for _, v in accepted[-holdout_count:]]
        median = statistics.median(training)
        mad = statistics.median([abs(v - median) for v in training])
        holdout_mae = sum(abs(v - median) for v in holdout) / len(holdout)
        checkpoint = {
            "agent_id": sensor_id, "model_kind": "robust_descriptive_median_MAD",
            "model_version": "candidate-v1", "unit": spec.unit,
            "median": median, "mad": mad, "holdout_mae": round(holdout_mae, 5),
            "training_samples": len(training), "holdout_samples": len(holdout),
            "window_start": accepted[0][0].isoformat(),
            "window_end": accepted[-1][0].isoformat(),
            "baseline_sha256": sha([{"at": stamp_dt(t), "value": v} for t, v in accepted]),
            "promotion": "AWAITING_OPERATOR_APPROVAL",
            "alerts_enabled": False,
            "training_provenance": "validated bounded public source data; not live sensor authentication",
        }
        self.states[sensor_id]["training_candidate"] = checkpoint
        self.states[sensor_id]["learning"] = "SHADOW_TRAINED_NOT_PROMOTED"
        self._append(sensor_id, "TRAIN_CANDIDATE", sha(checkpoint), "UNVERIFIED", stamp_dt(accepted[-1][0]))
        return checkpoint

    def public_report(self):
        return {
            "schema_version": "1.0",
            "collected_at": self.now,
            "monitor": "SkyNet Sensor-Agent I/O Supervisor",
            "training_policy": "shadow candidates only; operator approval and held-out checks required",
            "events": self.events[-200:],
            "chain_head": self.head,
            "agents": list(self.states.values()),
            "privacy": "Only public-source digests, bounded numeric statistics, and statuses; no raw private samples",
        }


def stamp_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


NOAA_SPECS = [
    SensorSpec("NOAA.GRS", "https://services.swpc.noaa.gov/products/noaa-scales.json"),
    SensorSpec("NOAA.KP", "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
               field="Kp", unit="Kp", lower=0, upper=9),
    SensorSpec("NOAA.GOES_FLARES", "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json"),
    SensorSpec("NOAA.BULLETINS", "https://services.swpc.noaa.gov/products/alerts.json"),
]

HAARP_SPECS = [
    SensorSpec("HAARP.IRI_ARRAY", "https://haarp.gi.alaska.edu/faq"),
    SensorSpec("HAARP.IONOSONDE", "https://haarp.gi.alaska.edu/diagnostic-suite"),
    SensorSpec("HAARP.RIOMETER", "https://ionograms.gi.alaska.edu/riometer/gakona/latest"),
    SensorSpec("HAARP.OBLIQUE_IONOSONDE", "https://ionograms.gi.alaska.edu/ois/cathy_lane/cordova/latest"),
    SensorSpec("HAARP.FLUXGATE", "https://haarp.gi.alaska.edu/diagnostic-suite"),
    SensorSpec("HAARP.VLF", "https://haarp.gi.alaska.edu/diagnostic-suite"),
    SensorSpec("HAARP.INDUCTION_MAGNETOMETER", "https://haarp.gi.alaska.edu/diagnostic-suite"),
    SensorSpec("HAARP.ALL_SKY_CAMERA", "https://haarp.gi.alaska.edu/diagnostic-suite"),
    SensorSpec("HAARP.SEISMIC", "https://haarp.gi.alaska.edu/diagnostic-suite"),
]
