# SkyNet — Third-Party Components and Data

SkyNet is an original integration gateway and dashboard. It can query the following external tools/services or display their data; these resources are not conveyed to Matthew Blake Ward or 918 Technologies by this integration.

| Source | Relationship | Terms / licensing considerations |
| --- | --- | --- |
| [RuView](https://github.com/ruvnet/RuView) | Independent upstream Wi-Fi-sensing software; SkyNet reads its local API | Inspect the exact upstream revision, its license, attribution, API/privacy obligations and source-distribution requirements before bundling or shipping upstream code |
| [USGS 3DEP / TNM](https://www.usgs.gov/3d-elevation-program) | Terrain and LiDAR discovery/elevation information | Preserve source and acquisition metadata; check each delivered dataset for applicable restrictions |
| [Copernicus Data Space](https://dataspace.copernicus.eu/) | Sentinel-1 catalog query | Follow service terms, access and attribution requirements; SkyNet does not bundle Sentinel-1 acquisitions |
| [NASA GIBS](https://www.earthdata.nasa.gov/data/tools/gibs) | Public satellite imagery visualized via remote map layers | Preserve required NASA/source credit and individual layer metadata |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | Optional hotspot data with an individually obtained MAP_KEY | Follow NASA data/service terms and API rules; do not distribute tokens |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | Base map tiles/data | Maintain OpenStreetMap attribution; comply with tile usage policy and ODbL obligations where applicable |
| [Leaflet](https://leafletjs.com/) | Remote browser map library | Observe the applicable upstream software license and attribution requirements |

**Clarification:** A public sensor product, dataset, or open-source codebase does not necessarily authorize unrestricted bulk access, redistribution, private monitoring, or use of upstream brands. Validate each license and service policy against the exact version and use case before public deployment.
