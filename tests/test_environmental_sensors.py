import json
import unittest
from datetime import datetime, timezone

from forecast.environmental_sensors import (
    SensorError, collect, normalize_coops, normalize_ndbc, normalize_usgs,
)

NOW=datetime(2026,11,14,6,0,tzinfo=timezone.utc)

def usgs_fixture():
    return json.dumps({"value":{"timeSeries":[{"sourceInfo":{"siteName":"Arkansas River at Tulsa","siteCode":[{"value":"07164500"}],"geoLocation":{"geogLocation":{"latitude":36.137,"longitude":-96.005}}},"variable":{"variableCode":[{"value":"00065"}],"unit":{"unitCode":"ft"}},"values":[{"value":[{"value":"4.25","qualifiers":["P"],"dateTime":"2026-11-14T05:45:00Z"}]}]}]}}).encode()

def coops_fixture():
    return json.dumps({"metadata":{"id":"9414290","name":"San Francisco","lat":"37.8063","lon":"-122.4659"},"data":[{"t":"2026-11-14 05:54","v":"1.204","s":"0.01","f":"0,0,0,0","q":"p"}]}).encode()

def ndbc_fixture():
    return b"#YY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES ATMP WTMP DEWP VIS PTDY TIDE\n#yr mo dy hr mn degT m/s m/s m sec sec deg hPa degC degC degC nmi hPa ft\n2026 11 14 05 50 120 8.1 10.2 1.7 7.0 5.5 130 1014.2 24.1 25.0 20.1 MM 0.2 MM\n"

class NormalizerTests(unittest.TestCase):
    def test_usgs_real_measurement_metadata(self):
        row=normalize_usgs(usgs_fixture(),NOW)[0]
        self.assertEqual((row["network"],row["station_id"],row["measurement"]),("USGS","07164500","gage_height"))
        self.assertEqual((row["value"],row["unit"]),(4.25,"ft")); self.assertTrue(row["fresh"])
        self.assertEqual(row["evidence_status"],"OBSERVED_EVENT")

    def test_coops_water_level(self):
        row=normalize_coops(coops_fixture(),"9414290",NOW)[0]
        self.assertEqual((row["measurement"],row["value"],row["unit"]),("water_level",1.204,"m"))
        self.assertEqual(row["datum"],"MLLW"); self.assertTrue(row["fresh"])

    def test_ndbc_multiple_instrument_channels(self):
        rows=normalize_ndbc(ndbc_fixture(),"41009",NOW)
        fields={r["measurement"] for r in rows}
        self.assertTrue({"wind_speed","wind_gust","wave_height","air_pressure","water_temperature"} <= fields)
        self.assertTrue(all(r["fresh"] for r in rows))

    def test_missing_and_malformed_values_are_rejected(self):
        with self.assertRaises(SensorError): normalize_coops(b'{"data":[]}',"9414290",NOW)
        with self.assertRaises(SensorError): normalize_ndbc(b"not ndbc", "41009", NOW)
        bad=json.loads(usgs_fixture()); bad["value"]["timeSeries"][0]["values"][0]["value"][0]["value"]="NaN"
        with self.assertRaises(SensorError): normalize_usgs(json.dumps(bad).encode(),NOW)

    def test_collector_isolates_source_failure_and_hashes_evidence(self):
        def fetcher(url,host):
            if "waterservices" in host: return usgs_fixture()
            if "tidesandcurrents" in host: return coops_fixture()
            if "41009" in url: return ndbc_fixture()
            raise OSError("offline fixture")
        report=collect(fetcher,NOW)
        self.assertGreaterEqual(len(report["observations"]),10)
        self.assertEqual(sum(x["status"]=="VERIFIED" for x in report["sources"]),5)
        self.assertEqual(sum(x["status"]=="BLOCKED" for x in report["sources"]),2)
        self.assertTrue(all(len(x["sha256"])==64 for x in report["sources"] if x["status"]!="BLOCKED"))
        self.assertTrue(all("hazard" not in row for row in report["observations"]))
        self.assertTrue(all(row["evidence_status"]=="OBSERVED_EVENT" for row in report["observations"]))

if __name__=="__main__": unittest.main()
