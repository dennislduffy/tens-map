# R ↔ Python Geospatial Cheat Sheet

> For someone fluent in R (sf, leaflet, dplyr, here) learning how the same workflows look in Python.
> Side-by-side code examples, not a textbook.

---

## Reading & Writing Spatial Data

| Task | R | Python |
|------|---|--------|
| Read any vector file | `st_read("file.gpkg")` | `gpd.read_file("file.gpkg")` |
| Write GeoPackage | `st_write(gdf, "out.gpkg")` | `gdf.to_file("out.gpkg", driver="GPKG")` |
| Write GeoJSON | `st_write(gdf, "out.geojson")` | `gdf.to_file("out.geojson", driver="GeoJSON")` |
| Fast I/O (large files) | `st_read("file.gpkg", quiet=TRUE)` uses GDAL | Use `engine="pyogrio"` — wraps GDAL directly, ~5–10× faster than default `fiona` |
| Read specific layer | `st_read("file.gpkg", layer = "layer_name")` | `gpd.read_file("file.gpkg", layer="layer_name")` |
| Read with bounding box filter | `st_read("file.gpkg", wkt_filter = st_as_text(bbox))` | `gpd.read_file("file.gpkg", bbox=(xmin, ymin, xmax, ymax))` |

```r
# R
library(sf)
gdf <- st_read("data/raw/00_Buildings.gpkg")
st_write(gdf, "data/processed/buildings.geojson")
```

```python
# Python
import geopandas as gpd
gdf = gpd.read_file("data/raw/00_Buildings.gpkg", engine="pyogrio")
gdf.to_file("data/processed/buildings.geojson", driver="GeoJSON")
```

---

## CRS Handling

| Task | R | Python |
|------|---|--------|
| Check CRS | `st_crs(gdf)` | `gdf.crs` |
| Get EPSG code | `st_crs(gdf)$epsg` | `gdf.crs.to_epsg()` |
| Reproject | `st_transform(gdf, 4326)` | `gdf.to_crs(4326)` |
| Reproject with proj string | `st_transform(gdf, crs = "+proj=utm +zone=15")` | `gdf.to_crs("+proj=utm +zone=15")` |
| Set CRS (no transform) | `st_set_crs(gdf, 4326)` | `gdf.set_crs(4326)` |

```r
# R
st_crs(gdf)        # prints full WKT
st_crs(gdf)$epsg   # e.g. 26915
gdf_wgs <- st_transform(gdf, 4326)
```

```python
# Python
gdf.crs             # prints CRS object
gdf.crs.to_epsg()   # e.g. 26915
gdf_wgs = gdf.to_crs(4326)
```

---

## Geometry Operations

| Task | R (sf) | Python (geopandas/shapely) |
|------|--------|---------------------------|
| Simplify | `st_simplify(gdf, dTolerance = 100)` | `gdf.geometry.simplify(0.001, preserve_topology=True)` |
| Buffer | `st_buffer(gdf, dist = 100)` | `gdf.geometry.buffer(100)` |
| Intersection | `st_intersection(a, b)` | `gpd.overlay(a, b, how="intersection")` |
| Union | `st_union(gdf)` | `gdf.geometry.unary_union` (returns single shape) |
| Dissolve/union by group | `gdf %>% group_by(col) %>% summarise(geometry = st_union(geometry))` | `gdf.dissolve(by="col")` |
| Bounding box | `st_bbox(gdf)` | `gdf.total_bounds` → `[xmin, ymin, xmax, ymax]` |
| Centroid | `st_centroid(gdf)` | `gdf.geometry.centroid` |
| Area | `st_area(gdf)` | `gdf.geometry.area` (in CRS units) |
| Length | `st_length(gdf)` | `gdf.geometry.length` |
| Is valid | `st_is_valid(gdf)` | `gdf.geometry.is_valid` |
| Spatial join | `st_join(x, y, join = st_intersects)` | `gpd.sjoin(x, y, predicate="intersects")` |

```r
# R — simplify polygons
gdf_simple <- st_simplify(gdf, preserveTopology = TRUE, dTolerance = 50)

# R — buffer 1 mile in UTM
gdf_utm <- st_transform(gdf, 26915)
gdf_buf <- st_buffer(gdf_utm, dist = 1609)
```

```python
# Python — simplify polygons (tolerance in CRS units)
gdf["geometry"] = gdf.geometry.simplify(50, preserve_topology=True)

# Python — buffer 1 mile in UTM
gdf_utm = gdf.to_crs(26915)
gdf_buf = gdf_utm.copy()
gdf_buf["geometry"] = gdf_utm.geometry.buffer(1609)
```

**Key difference:** In R, `st_*` functions return a new sf object. In Python, geometry operations on `.geometry` return a GeoSeries (just geometries), not a full GeoDataFrame. Assign back to `gdf["geometry"]` to replace geometries, or use `gdf.copy()` first.

---

## Data Wrangling (dplyr → pandas)

| Task | R (dplyr) | Python (pandas/geopandas) |
|------|-----------|--------------------------|
| Select columns | `select(gdf, col1, col2)` | `gdf[["col1", "col2", "geometry"]]` |
| Filter rows | `filter(gdf, col > 5)` | `gdf[gdf["col"] > 5]` or `gdf.query("col > 5")` |
| Mutate / add column | `mutate(gdf, new = col * 2)` | `gdf["new"] = gdf["col"] * 2` |
| Rename column | `rename(gdf, new_name = old_name)` | `gdf.rename(columns={"old_name": "new_name"})` |
| Group + summarize | `group_by(gdf, col) %>% summarize(n = n())` | `gdf.groupby("col").size().reset_index(name="n")` |
| Dissolve + group | `group_by(gdf, col) %>% summarize(geometry = st_union(geometry))` | `gdf.dissolve(by="col")` |
| Arrange/sort | `arrange(gdf, desc(col))` | `gdf.sort_values("col", ascending=False)` |
| Join (non-spatial) | `left_join(a, b, by = "id")` | `a.merge(b, on="id", how="left")` |
| Count rows | `nrow(gdf)` | `len(gdf)` |
| Column names | `names(gdf)` | `gdf.columns.tolist()` |
| Head | `head(gdf, 10)` | `gdf.head(10)` |
| Drop NAs | `drop_na(gdf, col)` | `gdf.dropna(subset=["col"])` |

```r
# R pipeline
result <- gdf %>%
  filter(type == "hospital") %>%
  select(name, beds, geometry) %>%
  mutate(big = beds > 200) %>%
  arrange(desc(beds))
```

```python
# Python equivalent (no pipe operator by default)
result = (
    gdf[gdf["type"] == "hospital"][["name", "beds", "geometry"]]
    .copy()
    .assign(big=lambda df: df["beds"] > 200)
    .sort_values("beds", ascending=False)
)
```

**gotcha:** pandas `.assign()` is the cleanest mutate equivalent. Direct `gdf["col"] = ...` works but can trigger `SettingWithCopyWarning` if `gdf` is a slice. Use `.copy()` first.

---

## Interactive Mapping

### Concept Mapping

| R leaflet | Python folium | Python leafmap |
|-----------|--------------|----------------|
| `leaflet()` | `folium.Map()` | `leafmap.Map()` |
| `addTiles()` | `folium.TileLayer()` | built-in basemap switcher |
| `addPolygons()` | `folium.GeoJson()` | `m.add_geojson()` |
| `addCircleMarkers()` | `folium.CircleMarker()` | `m.add_points_from_xy()` |
| `addLayersControl()` | `folium.LayerControl()` | `m.add_layer_control()` |
| `addPopups()` | `popup=` arg on layer | `popup=` arg |
| `setView()` | `location=`, `zoom_start=` | `center=`, `zoom=` |
| `saveWidget()` | `m.save("out.html")` | `m.to_html("out.html")` |

```r
# R
library(leaflet)
leaflet(gdf) %>%
  addTiles() %>%
  addPolygons(
    color = "blue", fillOpacity = 0.3,
    popup = ~paste("Name:", name)
  ) %>%
  addLayersControl(overlayGroups = "My Layer")
```

```python
# Python — folium
import folium
m = folium.Map(location=[46.7296, -94.6859], zoom_start=7)
folium.GeoJson(
    gdf,
    style_function=lambda f: {"color": "blue", "fillOpacity": 0.3},
    popup=folium.GeoJsonPopup(fields=["name"])
).add_to(m)
m.save("docs/index.html")
```

**For this project** we used raw Leaflet.js (in HTML) rather than folium, because:
1. We needed PMTiles support (protomaps-leaflet), which folium doesn't wrap
2. We needed layers off by default — folium's layer control is on by default and hard to override
3. The HTML output is smaller and more portable

### When to use what:
- **folium** — quick exploratory maps, no PMTiles needed, small data
- **leafmap** — wraps many backends (folium, ipyleaflet, kepler.gl), good for Jupyter notebooks
- **raw HTML/Leaflet** — production static sites, PMTiles, full control over JS behavior

---

## File Formats

| Format | R | Python | Notes |
|--------|---|--------|-------|
| GeoPackage (.gpkg) | `st_read()` / `st_write()` | `gpd.read_file()` / `.to_file(..., driver="GPKG")` | Preferred single-file format |
| GeoJSON | same | same | Use `driver="GeoJSON"` | Good for web, max ~50 MB |
| Shapefile (.shp) | same | same | Avoid: 10-char field limit, no nulls, multi-file mess |
| FlatGeobuf (.fgb) | `st_read()` via GDAL | `gpd.read_file()` | Streaming-friendly, cloud-native |
| PMTiles (.pmtiles) | not in sf | tippecanoe (CLI) → protomaps-leaflet (JS) | Vector tiles for web maps |
| Parquet/GeoParquet | `sfarrow::read_sf_dataset()` | `gpd.read_parquet()` | Best for analytics on huge data |

---

## Package Management

| Task | R | Python |
|------|---|--------|
| Install package | `install.packages("sf")` | `pip install geopandas` |
| Install from GitHub | `devtools::install_github("r-spatial/sf")` | `pip install git+https://github.com/geopandas/geopandas` |
| Load package | `library(sf)` | `import geopandas as gpd` |
| List installed | `installed.packages()` | `pip list` |
| Virtual environment | `renv` project snapshot | `python -m venv .venv && source .venv/bin/activate` |
| Lock file | `renv.lock` | `requirements.txt` or `pyproject.toml` |

**gotcha:** On macOS, you may have multiple Python versions. `python3` might point to the system Python (3.8 via Xcode CLI tools), while `pip3` installs into Python 3.11 (Homebrew). Always check `which python3` vs `which pip3`. Use `python3.11` explicitly or activate a virtual environment.

---

## Project Structure & Paths

| Task | R | Python |
|------|---|--------|
| Project-relative path | `here("data", "raw", "file.gpkg")` | `Path(__file__).parent.parent / "data" / "raw" / "file.gpkg"` |
| Current working dir | `getwd()` | `Path.cwd()` or `os.getcwd()` |
| List files | `list.files("data/raw", pattern = "\\.gpkg$")` | `list(Path("data/raw").glob("*.gpkg"))` |
| File exists | `file.exists("path")` | `Path("path").exists()` |
| Create directory | `dir.create("path", recursive = TRUE)` | `Path("path").mkdir(parents=True, exist_ok=True)` |
| File size | `file.size("path")` | `Path("path").stat().st_size` |

```r
# R — here package
library(here)
data_path <- here("data", "raw", "buildings.gpkg")
```

```python
# Python — pathlib (built-in, no install needed)
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent  # works regardless of where you run from
data_path = PROJECT_ROOT / "data" / "raw" / "buildings.gpkg"
```

**Key difference:** R's `here()` detects the project root via .Rproj/.git. Python's `Path(__file__)` uses the script's own location — more explicit, but you need to think about where each script lives relative to the project root.

---

## Key Gotchas & Differences

### 1. GeoDataFrame is not a tibble
`gdf` in Python is a `GeoDataFrame` that inherits from `pandas.DataFrame`. It's mutable and index-based. There's no automatic "tidy" printing — use `gdf.head()`.

### 2. Index behavior
pandas retains a numeric index that can get out of sync after filtering/subsetting. Use `reset_index(drop=True)` after filters if you care about clean indices. R tibbles don't have this issue.

### 3. Chaining syntax
R has the pipe `%>%` (magrittr) or `|>` (native, R ≥ 4.1). Python has no built-in pipe. Use method chaining (`.filter().assign().sort_values()`) or intermediate variables. The `pandas` `pipe()` method exists but is rarely used.

### 4. Geometry operations return GeoSeries, not GeoDataFrame
```python
# This returns a GeoSeries (geometry only):
centroids = gdf.geometry.centroid

# To make a new GeoDataFrame:
gdf_centroids = gdf.copy()
gdf_centroids["geometry"] = centroids
```

### 5. CRS on concat/merge
When you `pd.concat()` or `.merge()` GeoDataFrames, the result may lose the CRS. Always check `result.crs` afterward and set it if needed with `result.set_crs(4326)`.

### 6. Coordinate order
GeoJSON spec is `[longitude, latitude]` (x, y). Leaflet/R leaflet uses `(latitude, longitude)`. Shapely uses `(x, y)` = `(lon, lat)`. This is the #1 source of maps appearing in the ocean.

### 7. GDAL under the hood
Both `sf` (R) and `geopandas` (Python) use GDAL for I/O. If something works in QGIS or R, it usually works in Python too. Error messages often leak GDAL error text.

### 8. Memory
Python reads the full file into RAM by default. For truly massive files (> a few GB), consider `pyarrow`/`dask-geopandas` for chunked reads, or use `bbox` filter on `read_file()`. R's `sf` has similar limitations.

---

## This Project's Stack at a Glance

```
Download:   requests (HTTP)  ←→  R: httr / rvest
Parse:      json (stdlib)    ←→  R: jsonlite
Spatial:    geopandas        ←→  R: sf
Tiling:     tippecanoe (CLI) ←→  R: no equivalent
Map HTML:   raw Leaflet.js   ←→  R: leaflet package
Paths:      pathlib.Path     ←→  R: here
```

---

*Generated as part of the MN Commerce TENs Suitability Mapping Tool replication project.*
