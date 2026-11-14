"""Credential-free official environmental sensor adapters.

These adapters publish measurements, timestamps, units, station identity, and
payload provenance. They do not infer flooding, storms, fires, or safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "public" / "environmental-sensors.json"
MAX_BYTES = 800_000
MAX_FUTURE = timedelta(minutes=10)
FRESH = timedelta(hours=3)
USGS_SITES = ("07164500", "01646500", "11162765")
COOPS_STATIONS = ("9414290", "8771450", "8518750")
NDBC_STATIONS = {
    "41009": {"name": "Canaveral East", "lat": 28.508, "lon": -80.185},
    "42035": {"name": "Galveston, Texas", "lat": 29.232, "lon": -94.413},
    "46026": {"name": "San Francisco", "lat": 37.754, "lon": -122.839},
}
USGS = "https://waterservices.usgs.gov/nwis/iv/"
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NDBC = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"
PARAMETERS = {"00060": "discharge", "00065": "gage_height", "00010": "water_temperature"}
NDBC_FIELDS = {
    "WDIR": ("wind_direction", "degree"), "WSPD": ("wind_speed", "m/s"),
    "GST": ("wind_gust", "m/s"), "WVHT": ("wave_height", "m"),
    "DPD": ("dominant_wave_period", "s"), "PRES": ("air_pressure", "hPa"),
    "ATMP": ("air_temperature", "degC"), "WTMP": ("water_temperature", "degC"),
}

class SensorError(ValueError): pass

def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def utc(value):
    try: result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc: raise SensorError("invalid observation timestamp") from exc
    if result.tzinfo is None: raise SensorError("observation timestamp has no timezone")
    return result.astimezone(timezone.utc)

def _number(value):
    try: result = float(value)
    except (TypeError, ValueError) as exc: raise SensorError("invalid numeric observation") from exc
    if not math.isfinite(result): raise SensorError("non-finite observation")
    return result

def fetch(url, allowed_host):
    if urlsplit(url).scheme != "https" or urlsplit(url).hostname != allowed_host:
        raise SensorError("source URL outside allowlist")
    request = Request(url, headers={"User-Agent": "SkyNet-918-SensorWatch/1.0", "Accept": "application/json,text/plain"})
    with urlopen(request, timeout=20) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname != allowed_host: raise SensorError("redirect outside allowlist")
        raw = response.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES: raise SensorError("empty or oversized sensor response")
    return raw

def normalize_usgs(raw, now):
    try: payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc: raise SensorError("invalid USGS JSON") from exc
    series = payload.get("value", {}).get("timeSeries")
    if not isinstance(series, list): raise SensorError("USGS schema mismatch")
    rows=[]
    for item in series:
        source=item.get("sourceInfo",{}); variable=item.get("variable",{}); blocks=item.get("values")
        codes=variable.get("variableCode",[]); sites=source.get("siteCode",[])
        if not codes or not sites or not isinstance(blocks,list): raise SensorError("USGS series metadata missing")
        code=str(codes[0].get("value","")); site=str(sites[0].get("value",""))
        values=[v for b in blocks for v in b.get("value",[]) if v.get("value") not in (None,"-999999")]
        if not values: continue
        latest=max(values,key=lambda v: utc(v.get("dateTime")))
        observed=utc(latest.get("dateTime")); geo=source.get("geoLocation",{}).get("geogLocation",{})
        rows.append({"network":"USGS","station_id":site,"station_name":str(source.get("siteName",""))[:160],
            "observed_at":stamp(observed),"fresh":-MAX_FUTURE <= now-observed <= FRESH,
            "measurement":PARAMETERS.get(code,"parameter_"+code),"parameter_code":code,
            "value":_number(latest.get("value")),"unit":str(variable.get("unit",{}).get("unitCode",""))[:20],
            "qualifiers":[str(q)[:20] for q in latest.get("qualifiers",[])[:5]],
            "geometry":{"type":"Point","coordinates":[_number(geo.get("longitude")),_number(geo.get("latitude"))]},
            "source_url":USGS,"evidence_status":"OBSERVED_EVENT"})
    return rows

def normalize_coops(raw, station, now):
    try: payload=json.loads(raw)
    except (UnicodeError,json.JSONDecodeError) as exc: raise SensorError("invalid CO-OPS JSON") from exc
    if payload.get("error"): raise SensorError("CO-OPS error response")
    meta=payload.get("metadata",{}); data=payload.get("data")
    if not isinstance(data,list) or not data: raise SensorError("CO-OPS data missing")
    latest=max(data,key=lambda row: str(row.get("t","")))
    try: observed=datetime.strptime(latest["t"],"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (KeyError,ValueError) as exc: raise SensorError("invalid CO-OPS timestamp") from exc
    return [{"network":"NOAA CO-OPS","station_id":station,"station_name":str(meta.get("name",""))[:160],
        "observed_at":stamp(observed),"fresh":-MAX_FUTURE <= now-observed <= FRESH,
        "measurement":"water_level","value":_number(latest.get("v")),"unit":"m","datum":"MLLW",
        "quality_flag":str(latest.get("f",""))[:30],"geometry":{"type":"Point","coordinates":[_number(meta.get("lon")),_number(meta.get("lat"))]},
        "source_url":COOPS,"evidence_status":"OBSERVED_EVENT"}]

def normalize_ndbc(raw, station, now):
    try: lines=raw.decode("ascii").splitlines()
    except UnicodeError as exc: raise SensorError("NDBC response not ASCII") from exc
    content=[line.split() for line in lines if line.strip()]
    if len(content)<3 or content[0][:5] != ["#YY","MM","DD","hh","mm"]: raise SensorError("NDBC schema mismatch")
    names=[x.lstrip("#") for x in content[0]]; values=content[2]
    if len(values) != len(names): raise SensorError("NDBC column mismatch")
    row=dict(zip(names,values))
    try: observed=datetime(int(row["YY"]),int(row["MM"]),int(row["DD"]),int(row["hh"]),int(row["mm"]),tzinfo=timezone.utc)
    except (KeyError,ValueError) as exc: raise SensorError("invalid NDBC timestamp") from exc
    meta=NDBC_STATIONS[station]; results=[]
    for field,(measurement,unit) in NDBC_FIELDS.items():
        if row.get(field) in (None,"MM"): continue
        results.append({"network":"NOAA NDBC","station_id":station,"station_name":meta["name"],"observed_at":stamp(observed),
            "fresh":-MAX_FUTURE <= now-observed <= FRESH,"measurement":measurement,"value":_number(row[field]),"unit":unit,
            "geometry":{"type":"Point","coordinates":[meta["lon"],meta["lat"]]},"source_url":NDBC.format(station=station),
            "evidence_status":"OBSERVED_EVENT"})
    if not results: raise SensorError("NDBC row contains no supported measurements")
    return results

def collect(fetcher=fetch, now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc); observations=[]; sources=[]
    requests=[]
    usgs_url=USGS+"?"+urlencode({"format":"json","sites":",".join(USGS_SITES),"parameterCd":"00060,00065,00010","siteStatus":"active"})
    requests.append(("USGS stream gauges",usgs_url,"waterservices.usgs.gov",lambda raw:normalize_usgs(raw,now)))
    for station in COOPS_STATIONS:
        url=COOPS+"?"+urlencode({"date":"latest","station":station,"product":"water_level","datum":"MLLW","time_zone":"gmt","units":"metric","application":"SkyNet918","format":"json"})
        requests.append(("NOAA CO-OPS "+station,url,"api.tidesandcurrents.noaa.gov",lambda raw,s=station:normalize_coops(raw,s,now)))
    for station in NDBC_STATIONS:
        url=NDBC.format(station=station); requests.append(("NOAA NDBC "+station,url,"www.ndbc.noaa.gov",lambda raw,s=station:normalize_ndbc(raw,s,now)))
    for name,url,host,normalizer in requests:
        try:
            raw=fetcher(url,host); rows=normalizer(raw); observations.extend(rows)
            freshest=any(r["fresh"] for r in rows)
            sources.append({"source":name,"source_url":url,"status":"VERIFIED" if freshest else "UNVERIFIED",
                "detail":f"{len(rows)} schema-validated measurement(s); " + ("fresh" if freshest else "stale"),
                "checked_at":stamp(now),"sha256":hashlib.sha256(raw).hexdigest()})
        except (SensorError,OSError,TimeoutError) as exc:
            sources.append({"source":name,"source_url":url,"status":"BLOCKED","detail":type(exc).__name__+": "+str(exc)[:140],"checked_at":stamp(now)})
    return {"schema_version":"1.0","collected_at":stamp(now),"observations":observations,"sources":sources,
        "interpretation":"Measurements are official station observations. They are not flood, storm, or safety determinations."}

def write_snapshot(path=OUTPUT,fetcher=fetch,now=None):
    result=collect(fetcher,now); path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".tmp"); temp.write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); temp.replace(path); return result

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=OUTPUT); parser.add_argument("--allow-blocked",action="store_true"); args=parser.parse_args(argv)
    result=write_snapshot(args.output); verified=sum(s["status"]=="VERIFIED" for s in result["sources"])
    print(json.dumps({"observations":len(result["observations"]),"verified_sources":verified,"sources":len(result["sources"])}))
    return 0 if verified or args.allow_blocked else 2
if __name__ == "__main__": raise SystemExit(main())
