# MN Commerce TENs Suitability Mapping Tool — Static Replica

A self-contained, static web map that replicates the [Minnesota Department of Commerce TENs Suitability Mapping Tool](https://www.commerce.state.mn.us/) (originally hosted on ArcGIS Online Experience Builder), deployable to GitHub Pages at zero cost.

## Purpose

This is a proof of concept demonstrating that expensive ArcGIS Online hosting is unnecessary for this type of application. All 24 data layers are downloaded from the public ArcGIS Feature Service and converted to open formats (GeoJSON / PMTiles).

## Data Source

**ArcGIS Feature Service:**
```
https://services5.arcgis.com/FKwcDz27wRAj4HUT/arcgis/rest/services/
Minnesota_Department_of_Commerce_TENs_Suitability_Mapping_Tool_WFL1/FeatureServer
```

**Building footprint attribution:** Oak Ridge National Laboratory (ORNL); Federal Emergency Management Agency (FEMA) Geospatial Response Office. Public source: https://disasters.geoplatform.gov/USA_Structures/

## Project Structure

```
tens-map/
├── scripts/
│   ├── 01_download_layers.py   # Download all 24 layers from ArcGIS REST API
│   ├── 02_process_layers.py    # Convert to GeoJSON (small) or PMTiles (large)
│   └── 03_build_map.py         # Generate docs/index.html
├── data/
│   ├── raw/                    # Downloaded .gpkg files (not committed — too large)
│   ├── processed/              # GeoJSON outputs for small layers
│   ├── tiles/                  # PMTiles outputs for large layers
│   └── layer_manifest.json     # Inventory used by map builder
├── docs/                       # GitHub Pages output
│   ├── index.html              # The map
│   └── *.pmtiles               # Large-layer tile files
├── learning/
│   └── r_vs_python_geospatial.md
└── README.md
```

## How to Reproduce

**Requirements:**
- macOS with Homebrew
- Python 3.11+
- tippecanoe (installed via Homebrew)

**Python packages:**
```bash
pip3 install geopandas requests pandas shapely folium pyogrio
```

**Steps:**

```bash
# 1. Download all layers (takes ~45–60 min for the ~2.9M building footprints)
python3.11 scripts/01_download_layers.py

# 2. Process layers → GeoJSON or PMTiles
python3.11 scripts/02_process_layers.py

# 3. Build the map
python3.11 scripts/03_build_map.py

# 4. Preview locally
open docs/index.html
```

## Deploying to GitHub Pages

1. Push the `docs/` folder to your GitHub repository
2. In repo Settings → Pages → Source: select `docs/` folder on `main`
3. That's it — no build step required

**Note:** PMTiles files can be large. GitHub Pages has a 1 GB soft limit per repository.

## Architecture Decisions

| Layer size | Format | Rationale |
|-----------|--------|-----------|
| < 50 MB | GeoJSON (inline) | Simple, no tile server needed |
| ≥ 50 MB | PMTiles | Efficient tile delivery, served as static file |

**Why not ArcGIS Online?**
- No annual AGOL subscription required
- No vendor lock-in
- Faster page loads (no Esri JS API overhead)
- Data in open formats (GeoJSON, PMTiles)
- Free hosting on GitHub Pages

## Map Features

- Multiple basemaps: CartoDB Light, OpenStreetMap, Esri Satellite
- 24 toggleable data layers (all off by default)
- Click-to-popup showing feature attributes
- Distinct color per layer
- Centers on Minnesota at zoom 7

## Learning Resources

See [`learning/r_vs_python_geospatial.md`](learning/r_vs_python_geospatial.md) for a side-by-side R ↔ Python geospatial cheat sheet.
