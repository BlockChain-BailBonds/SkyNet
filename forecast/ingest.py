#!/usr/bin/env python3
"""Fetch bounded official snapshots; failures become explicit source status."""
import json,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from forecast.pipeline import usgs,nws
from alerts.engine import publish
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/public'
SOURCES=[('USGS Earthquakes','https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson',usgs),('NOAA/NWS Alerts','https://api.weather.gov/alerts/active?status=actual',nws)]
def stamp(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def main():
 events=[]; status=[]
 for name,url,normalizer in SOURCES:
  try:
   req=Request(url,headers={'User-Agent':'SkyNet-SPIN/1.0 (public GitHub project)','Accept':'application/geo+json, application/json'})
   with urlopen(req,timeout=20) as r: raw=r.read(5_000_001)
   if len(raw)>5_000_000: raise ValueError('payload too large')
   rows=normalizer(json.loads(raw)); events.extend(rows); status.append({'source':name,'status':'VERIFIED','detail':f'{len(rows)} validated public records','checked_at':stamp()})
  except Exception as e: status.append({'source':name,'status':'BLOCKED','detail':str(e)[:180],'checked_at':stamp()})
 status.extend([{'source':'RuView','status':'BLOCKED','detail':'Private local gateway unavailable in Pages','checked_at':stamp()},{'source':'Pocket telemetry gateway','status':'BLOCKED','detail':'GitHub Pages cannot receive telemetry','checked_at':stamp()}]); OUT.mkdir(parents=True,exist_ok=True)
 (OUT/'latest-forecasts.json').write_text(json.dumps(events,separators=(',',':')),encoding='utf-8'); (OUT/'latest-alerts.json').write_text(json.dumps(publish(events),separators=(',',':')),encoding='utf-8'); (OUT/'source-status.json').write_text(json.dumps(status,separators=(',',':')),encoding='utf-8')
 return 0 if any(s['status']=='VERIFIED' for s in status) else 2
if __name__=='__main__': sys.exit(main())
