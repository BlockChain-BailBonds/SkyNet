from __future__ import annotations
from datetime import datetime, timezone

class AlertError(ValueError): pass
def now(): return datetime.now(timezone.utc)
def parse(v): return datetime.fromisoformat(v.replace("Z","+00:00"))
def from_event(e, at=None):
    if e.get("evidence_status") != "OFFICIAL_WARNING": return None
    issued=e["valid_at"]; expires=e.get("expires")
    if not expires or parse(expires) <= (at or now()): return None
    return {"id":e["id"],"event":e["summary"],"event_type":e["hazard"],"source":e["source"],"severity":e.get("severity","Unknown"),"issued":issued,"expires":expires,"area":e.get("area","Unknown"),"evidence_status":"OFFICIAL_WARNING","recommended_source":e.get("source_url"),"status":"ACTIVE","cap":{"identifier":e["id"],"sent":issued,"status":"Actual","msgType":"Alert","scope":"Public"}}
def publish(events, at=None):
    by_id={}
    for event in events:
        alert=from_event(event,at)
        if alert: by_id[alert["id"]]=alert
    return sorted(by_id.values(),key=lambda x:x["issued"],reverse=True)
