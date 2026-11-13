"""SIMULATED device transport. HMAC test identity is not the firmware Ed25519 identity."""
import hashlib, hmac, json, secrets, time
class ReplayError(ValueError): pass
class SimulatedPocket:
    def __init__(self, key=None): self.key=key or secrets.token_bytes(32); self.seen=set(); self.ack=[]
    @property
    def thumbprint(self): return hashlib.sha256(self.key).hexdigest()
    def sign(self, payload, timestamp=None, nonce=None):
        message={"payload":payload,"timestamp":timestamp or int(time.time()),"nonce":nonce or secrets.token_hex(8),"device":self.thumbprint}
        raw=json.dumps(message,sort_keys=True,separators=(",",":")).encode(); message["signature"]=hmac.new(self.key,raw,hashlib.sha256).hexdigest(); return message
    def verify(self, message, current_time=None):
        signature=message.get("signature",""); unsigned={k:v for k,v in message.items() if k!="signature"}; raw=json.dumps(unsigned,sort_keys=True,separators=(",",":")).encode()
        if not hmac.compare_digest(signature,hmac.new(self.key,raw,hashlib.sha256).hexdigest()): return False
        now=current_time or int(time.time()); nonce=message.get("nonce")
        if abs(now-message.get("timestamp",0))>300 or nonce in self.seen: raise ReplayError("stale or replayed message")
        self.seen.add(nonce); return True
    def receive(self, alerts, current_time): self.alerts=[a for a in alerts if a.get("status")=="ACTIVE" and datetime_ts(a["expires"])>current_time]; return self.alerts
    def acknowledge(self, alert_id): self.ack.append(alert_id); return {"alert_id":alert_id,"state":"ACKNOWLEDGED","evidence":"SIMULATED"}
def datetime_ts(value):
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()
