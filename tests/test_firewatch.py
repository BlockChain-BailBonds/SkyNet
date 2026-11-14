import json
import unittest
from datetime import datetime,timezone

from forecast.firewatch import FireSourceError,collect,normalize,query_url

NOW=datetime(2026,11,14,10,0,tzinfo=timezone.utc)
def fixture(category="WF",modified=1794650100000):
    return json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{
        "OBJECTID":7,"IncidentName":"Test Ridge","IncidentTypeCategory":category,"IncidentSize":125.5,
        "DiscoveryAcres":2.0,"FireDiscoveryDateTime":1794643200000,"ModifiedOnDateTime_dt":modified,
        "PercentContained":35,"POOCity":"Example","POOCounty":"Test","POOState":"US-OK",
        "IrwinID":"{12345678-1234-1234-1234-123456789abc}","ActiveFireCandidate":True,
        "IncidentShortDescription":"Operational test fixture"},"geometry":{"type":"Point","coordinates":[-96.0,36.1]}}]}).encode()

class FireWatchTests(unittest.TestCase):
    def test_wfigs_incident_is_not_thermal_anomaly(self):
        row=normalize(fixture(),NOW)[0]
        self.assertEqual(row["incident_type"],"wildfire"); self.assertEqual(row["reported_acres"],125.5)
        self.assertEqual(row["percent_contained"],35); self.assertEqual(row["evidence_status"],"OBSERVED_EVENT")
        self.assertIn("not a satellite thermal anomaly",row["interpretation"])

    def test_non_wildfire_and_invalid_geometry_rejected(self):
        with self.assertRaises(FireSourceError): normalize(fixture("RX"),NOW)
        bad=json.loads(fixture()); bad["features"][0]["geometry"]["coordinates"]=[999,20]
        with self.assertRaises(FireSourceError): normalize(json.dumps(bad).encode(),NOW)

    def test_future_timestamp_and_invalid_containment_rejected(self):
        with self.assertRaises(FireSourceError): normalize(fixture(modified=1894650100000),NOW)
        bad=json.loads(fixture()); bad["features"][0]["properties"]["PercentContained"]=101
        with self.assertRaises(FireSourceError): normalize(json.dumps(bad).encode(),NOW)

    def test_failure_is_blocked_without_synthetic_incidents(self):
        result=collect(lambda url: (_ for _ in ()).throw(OSError("offline")),NOW)
        self.assertEqual(result["incidents"],[]); self.assertEqual(result["source_status"]["status"],"BLOCKED")
        self.assertIsNone(result["satellite_thermal_anomalies"])

    def test_query_is_bounded_and_filters_wildfire(self):
        url=query_url(); self.assertIn("resultRecordCount=500",url); self.assertIn("IncidentTypeCategory",url)
        self.assertNotIn("token=",url.lower())
if __name__=="__main__": unittest.main()
