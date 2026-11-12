# SkyNet v0.3 — Interactive Google Maps / Earth observation UI

Original project IP attributed to Matthew Blake Ward, in association with 918 Technologies. Third-party rights are separate.

## Test the HTML immediately

Open **`SkyNet_918_Interactive_Google_Maps.html`** in a web browser with internet access. You can also open **`static/index.html`** from the extracted project. Neither file contains a secret API key.

The page starts with a **free OpenStreetMap-based basemap**, using Leaflet from its CDN. Basemap tiles, NASA overlays and the Photon geocoder require internet. Enter a street address/place and press **Locate address**. The keyless search sends the text to the public Photon service on demand and may be throttled or fail. A direct **View target in Google Maps** action works without an API key.

Enter latitude/longitude manually when a geocoding service is unavailable. The map displays a pin plus a 0.1–20 km radius. Map clicks select another target. The **Illustrative demo** toggle shows three synthetic geometries clearly labeled as demonstration, not detections. Import **GeoJSON** for your own features.

## Enable interactive Google Maps within SkyNet

1. Create a Google Maps Platform project and a Maps JavaScript API key in the Google Cloud console. A no-cost Demo Key may be available for prototyping, subject to restrictions. Standard API keys generally require billing.
2. Enable **Maps JavaScript API**. Configure **website / HTTP referrer restrictions** for the origin hosting SkyNet (for example `http://localhost:8787/*` and `http://127.0.0.1:8787/*`) and restrict the key to the Maps JavaScript API. Depending on current Google billing configuration, the in-map Geocoder may require additional API enablement. Check Google Cloud's quota/usage controls.
3. Run `python3 server.py` from the project directory and open `http://127.0.0.1:8787`.
4. Paste the restricted key in the **Map provider** input and press **Use Google Maps**. Now Google road/satellite/terrain basemaps and SkyNet markers/overlays are rendered on the interactive map. Keys are not persisted by SkyNet, but Google Maps JavaScript necessarily sends browser-side API keys to Google. Do not use unrestricted keys.

Google Maps JS API reference: https://developers.google.com/maps/documentation/javascript/load-maps-js-api
Google Maps key setup: https://developers.google.com/maps/documentation/javascript/get-api-key
Google Maps URLs (no key): https://developers.google.com/maps/documentation/urls/get-started

## Connect the existing read-only backend

```bash
cd 918_skynet_ruview
python3 server.py
```

Open `http://127.0.0.1:8787`. Public-sensor data needs internet. By default RuView is read from `http://127.0.0.1:3000`; this is *not* a claim that RuView is installed or working. See `README.md` for LAN opt-in and optional FIRMS key.

- **Query sensors** retrieves USGS EPQS elevation, 3DEP LiDAR product **catalog metadata**, Copernicus Sentinel-1 radar product **catalog metadata**, and NASA FIRMS geographic hotspot points when a FIRMS MAP_KEY was supplied server-side.
- **NASA optical, surface temperature and GOES IR** are WMS raster overlays through NASA GIBS, shown only if matching tiles exist for your selected day and area.
- **USGS shaded elevation relief** is DEM-derived hillshade, not a new LiDAR flight or direct underground scanner.
- **RuView** displays server health, mesh count, field event count and CSI frame presence as metadata only. RuView data is not geolocated on the public map and sensor simulation is not treated as hardware acceptance.
- **Import GeoJSON**: up to 2 MB, 1,000 features, 100,000 coordinates, with WGS84 longitude/latitude order; local geometry is unverified by default. **Export session JSON** makes a reproducible frontend event manifest (not raw RuView CSI).
- **Evidence**: if running the backend, it retains SHA-256 of fetched public response bodies plus source metadata (no raw response bytes). Individual source status means retrieval success only, not confirmed target detection.

## Limitations

This release does **not** implement 3D LAS/LAZ rendering, raw Sentinel SAR image processing, true LiDAR-scanning of an address, live NOAA spacecraft position sensing, wall penetration by public datasets, human tracking, underground imaging or independently validated cross-sensor anomaly classification. It does not automatically fetch data simply because a location is entered.

This viewer should be operated on a trusted private machine. Avoid public hosting without authentication and additional source-license/privacy reviews. The gateway supports separate, explicitly consented enrollment POST routes; the public observation endpoints remain read-only.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Voluntary SMS sensor invitation

See `SMS_ENROLLMENT_GUIDE.md`. The operator dashboard contains a private SMS invitation section. The recipient uses a hosted HTTPS `/join` consent page. This cannot be served from the standalone HTML file alone.
