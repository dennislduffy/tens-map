#!/usr/bin/env python3
"""
Phase 4: Build the interactive web map.

Generates docs/index.html — a self-contained HTML file that:
- Centers on Minnesota
- Supports OpenStreetMap, satellite, and CartoDB light basemaps
- Loads small layers as inline GeoJSON
- Loads medium layers via fetch from docs/layers/
- Loads large layers as PMTiles via protomaps-leaflet
- Buildings: live from original ArcGIS service at zoom 14+
- Has toggleable layer controls (all off by default)
- Shows popups with the first 5 attributes on click
- Uses distinct colors per layer
"""

import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
LAYERS_DIR = DOCS_DIR / "layers"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
LAYERS_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = DATA_DIR / "layer_manifest.json"

# Inline threshold: GeoJSON files smaller than this are embedded directly in HTML
INLINE_THRESHOLD_BYTES = 2 * 1_048_576  # 2 MB

# ── Layer colors (distinct palette) ──────────────────────────────────────────
COLORS = [
    "#e41a1c",  # red
    "#377eb8",  # blue
    "#4daf4a",  # green
    "#984ea3",  # purple
    "#ff7f00",  # orange
    "#a65628",  # brown
    "#f781bf",  # pink
    "#999999",  # grey
    "#1b9e77",  # teal
    "#d95f02",  # dark orange
    "#7570b3",  # slate blue
    "#e7298a",  # magenta
    "#66a61e",  # olive green
    "#e6ab02",  # gold
    "#a6761d",  # tan
    "#666666",  # dark grey
    "#8dd3c7",  # light teal
    "#fb8072",  # salmon
    "#80b1d3",  # light blue
    "#fdb462",  # peach
    "#b3de69",  # yellow-green
    "#fccde5",  # light pink
    "#d9d9d9",  # light grey
    "#bc80bd",  # lavender
]


def copy_pmtiles(pmtiles_path: Path) -> str:
    """Copy pmtiles file to docs/ and return the relative path for HTML."""
    dest = DOCS_DIR / pmtiles_path.name
    if not dest.exists():
        shutil.copy2(pmtiles_path, dest)
        print(f"  Copied {pmtiles_path.name} → docs/")
    return pmtiles_path.name


def process_geojson(path: Path, layer_id: int) -> dict:
    """
    Decide whether to inline or script-load a GeoJSON file.
    Returns {"mode": "inline", "data": {...}} or {"mode": "script", "js_file": "...", "var_name": "..."}

    Medium layers are wrapped in a JS variable assignment file (e.g. layers/16_School.js:
    window._ld16 = {...};) and loaded via dynamic <script> injection. This works with both
    file:// and http:// — unlike fetch(), which is blocked by browsers on file:// URLs.
    """
    size = path.stat().st_size
    if size <= INLINE_THRESHOLD_BYTES:
        with open(path) as f:
            data = json.load(f)
        return {"mode": "inline", "data": data, "size_mb": size / 1_048_576}
    else:
        var_name = f"_ld{layer_id}"
        js_filename = path.stem + ".js"
        dest_js = LAYERS_DIR / js_filename
        if not dest_js.exists():
            print(f"  Writing {js_filename} → docs/layers/ ({size/1_048_576:.1f} MB)…")
            with open(path) as f:
                data = json.load(f)
            js_content = f"window.{var_name}={json.dumps(data, separators=(',', ':'))};"
            with open(dest_js, "w") as f:
                f.write(js_content)
            print(f"  ✓ Wrote {js_filename}")
        return {"mode": "script", "js_file": f"layers/{js_filename}", "var_name": var_name, "size_mb": size / 1_048_576}


def build_map(manifest: dict):
    """Generate the index.html."""

    # Sort layers by id
    layers = sorted(manifest.items(), key=lambda x: int(x[0]))

    # Prepare layer definitions
    layer_defs = []
    for idx, (lid, meta) in enumerate(layers):
        if meta["type"] == "error":
            continue
        color = COLORS[idx % len(COLORS)]
        entry = {
            "id": int(lid),
            "name": meta["name"],
            "type": meta["type"],
            "color": color,
            "path": meta.get("path", ""),
            "url": meta.get("url", ""),
            "features": meta.get("features", 0),
            "layer_name": meta.get("layer_name", ""),  # tippecanoe internal layer name
            "max_zoom": meta.get("max_zoom", 12),      # highest zoom level stored in PMTiles
        }
        layer_defs.append(entry)

    # Process GeoJSON layers
    geojson_info = {}
    for ld in layer_defs:
        if ld["type"] == "geojson":
            path = PROJECT_ROOT / ld["path"]
            if path.exists():
                geojson_info[ld["id"]] = process_geojson(path, ld["id"])
            else:
                print(f"  Warning: GeoJSON file not found: {path}")

    # Copy PMTiles to docs/
    pmtiles_refs = {}
    for ld in layer_defs:
        if ld["type"] == "pmtiles":
            path = PROJECT_ROOT / ld["path"]
            if path.exists():
                pmtiles_refs[ld["id"]] = copy_pmtiles(path)
            else:
                print(f"  Warning: PMTiles file not found: {path}")

    html = build_html(layer_defs, geojson_info, pmtiles_refs)

    out_path = DOCS_DIR / "index.html"
    with open(out_path, "w") as f:
        f.write(html)
    size_kb = out_path.stat().st_size / 1024
    print(f"✓ Saved {out_path} ({size_kb:.0f} KB)")
    return out_path


def build_html(layer_defs, geojson_info, pmtiles_refs) -> str:
    """Return the full HTML string."""

    layer_js_parts = []

    for ld in layer_defs:
        lid = ld["id"]
        name = ld["name"].replace('"', '\\"').replace("'", "\\'")
        color = ld["color"]
        n_features = ld["features"]
        layer_type = ld["type"]
        # Use the layer_name that tippecanoe actually stored (must match exactly)
        safe_name = ld.get("layer_name") or ld["name"].replace(" ", "_").replace("/", "-")
        max_zoom = ld.get("max_zoom", 12)

        popup_fn = f"""function(feature, layer) {{
      if (feature.properties) {{
        var props = Object.entries(feature.properties).slice(0, 5);
        var rows = props.map(function(kv) {{
          return "<tr><th>" + kv[0] + "</th><td>" + (kv[1] !== null ? kv[1] : "—") + "</td></tr>";
        }}).join("");
        layer.bindPopup("<b>{name}</b><table class='popup-table'>" + rows + "</table>");
      }}
    }}"""

        geojson_opts = f"""{{
      style: function() {{
        return {{color:"{color}",fillColor:"{color}",weight:1.5,opacity:0.8,fillOpacity:0.35}};
      }},
      pointToLayer: function(f, ll) {{
        return L.circleMarker(ll,{{radius:6,fillColor:"{color}",color:"#fff",weight:1,opacity:1,fillOpacity:0.85}});
      }},
      onEachFeature: {popup_fn}
    }}"""

        if layer_type == "geojson" and lid in geojson_info:
            info = geojson_info[lid]
            if info["mode"] == "inline":
                gj = json.dumps(info["data"], separators=(",", ":"))
                js = f"""
  // Layer {lid}: {ld["name"]} (inline GeoJSON, {n_features:,} features)
  (function() {{
    var layer = L.geoJSON({gj}, {geojson_opts});
    overlayLayers["{name} ({n_features:,})"] = layer;
  }})();
"""
            else:
                # "script" mode: data is in a .js file that sets window.<var_name>
                # Loaded via dynamic <script> injection (works with file:// and http://)
                js_file = info["js_file"]
                var_name = info["var_name"]
                js = f"""
  // Layer {lid}: {ld["name"]} (script-loaded GeoJSON, {n_features:,} features)
  (function() {{
    var layerHolder = L.layerGroup();
    var loaded = false;
    layerHolder.on('add', function() {{
      if (loaded) return;
      loaded = true;
      if (window.{var_name}) {{
        L.geoJSON(window.{var_name}, {geojson_opts}).addTo(layerHolder);
      }} else {{
        var s = document.createElement('script');
        s.src = "{js_file}";
        s.onload = function() {{
          L.geoJSON(window.{var_name}, {geojson_opts}).addTo(layerHolder);
        }};
        s.onerror = function() {{
          console.warn("Failed to load {js_file}");
        }};
        document.head.appendChild(s);
      }}
    }});
    overlayLayers["{name} ({n_features:,})"] = layerHolder;
  }})();
"""

        elif layer_type == "pmtiles" and lid in pmtiles_refs:
            fname = pmtiles_refs[lid]
            js = f"""
  // Layer {lid}: {ld["name"]} (PMTiles, {n_features:,} features)
  (function() {{
    var layer = protomapsL.leafletLayer({{
      url: "{fname}",
      maxDataZoom: {max_zoom},
      paintRules: [
        {{
          dataLayer: "{safe_name}",
          symbolizer: new protomapsL.PolygonSymbolizer({{fill:"{color}",opacity:0.35,stroke:"{color}",width:1}})
        }},
        {{
          dataLayer: "{safe_name}",
          symbolizer: new protomapsL.LineSymbolizer({{color:"{color}",width:2}})
        }},
        {{
          dataLayer: "{safe_name}",
          symbolizer: new protomapsL.CircleSymbolizer({{radius:4,fill:"{color}",opacity:0.85}})
        }}
      ],
      labelRules: []
    }});
    layer.on('click', function(e) {{
      if (e.features && e.features.length > 0) {{
        var props = e.features[0].props;
        var entries = Object.entries(props).slice(0, 5);
        var rows = entries.map(function(kv) {{
          return "<tr><th>" + kv[0] + "</th><td>" + (kv[1] !== null ? kv[1] : "—") + "</td></tr>";
        }}).join("");
        L.popup().setLatLng(e.latlng)
          .setContent("<b>{name}</b><table class='popup-table'>" + rows + "</table>")
          .openOn(map);
      }}
    }});
    overlayLayers["{name} ({n_features:,})"] = layer;
  }})();
"""

        elif layer_type == "arcgis":
            arcgis_url = ld["url"]
            js = f"""
  // Layer {lid}: {ld["name"]} (ArcGIS live service — zoom 15+, {n_features:,} features total)
  (function() {{
    var serviceUrl = "{arcgis_url}";
    var layerGroup = L.layerGroup();
    var lastBounds = null;
    var debounceTimer = null;

    function loadFeatures() {{
      var zoom = map.getZoom();
      if (zoom < 15) {{
        layerGroup.clearLayers();
        lastBounds = null;
        return;
      }}
      var bounds = map.getBounds();
      if (lastBounds && lastBounds.contains(bounds)) return;
      lastBounds = bounds.pad(0.1);
      var bbox = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].join(',');
      var url = serviceUrl + '/query?where=1%3D1&geometry=' + bbox
        + '&geometryType=esriGeometryEnvelope&spatialRel=esriSpatialRelIntersects'
        + '&outFields=*&f=geojson&resultRecordCount=1000';
      fetch(url)
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{
          layerGroup.clearLayers();
          L.geoJSON(data, {{
            style: function() {{
              return {{color:"{color}",fillColor:"{color}",weight:1,fillOpacity:0.3}};
            }},
            onEachFeature: function(feature, layer) {{
              if (feature.properties) {{
                var props = Object.entries(feature.properties).slice(0, 5);
                var rows = props.map(function(kv) {{
                  return "<tr><th>"+kv[0]+"</th><td>"+(kv[1]!==null?kv[1]:"—")+"</td></tr>";
                }}).join("");
                layer.bindPopup("<b>{name}</b><table class='popup-table'>"+rows+"</table>");
              }}
            }}
          }}).addTo(layerGroup);
        }})
        .catch(function(e) {{ console.warn("Load error:", e); }});
    }}

    function debouncedLoad() {{
      if (!map.hasLayer(layerGroup)) return;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(loadFeatures, 400);
    }}

    map.on('zoomend moveend', debouncedLoad);
    layerGroup.on('add', function() {{ loadFeatures(); }});

    overlayLayers["{name} ({n_features:,} — zoom 15+)"] = layerGroup;
  }})();
"""
        else:
            continue

        layer_js_parts.append(js)

    all_layer_js = "\n".join(layer_js_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MN Commerce TENs Suitability Map</title>

  <!-- Leaflet -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

  <!-- Protomaps Leaflet (for PMTiles) -->
  <script src="https://unpkg.com/protomaps-leaflet@4.0.0/dist/protomaps-leaflet.js"></script>

  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ height: 100%; overflow: hidden; }}
    #map {{ width: 100%; height: 100vh; }}
    .popup-table {{ border-collapse: collapse; margin-top: 4px; font-size: 12px; min-width: 200px; }}
    .popup-table th {{ text-align: left; padding: 2px 6px 2px 0; color: #555; font-weight: 600; white-space: nowrap; }}
    .popup-table td {{ padding: 2px 0 2px 6px; }}
    .popup-table tr:nth-child(even) {{ background: #f5f5f5; }}
    #attr {{
      position: fixed; bottom: 0; left: 0; right: 0; z-index: 9999;
      background: rgba(255,255,255,0.85); padding: 3px 10px;
      font-size: 11px; color: #444; text-align: center; pointer-events: none;
    }}
    #attr a {{ color: #0078d7; pointer-events: all; }}
    #layer-toggle-btn {{
      position: fixed; top: 10px; right: 10px; z-index: 1001;
      width: 30px; height: 30px; line-height: 28px;
      background: white; border: 2px solid rgba(0,0,0,0.2); border-radius: 4px;
      font-size: 18px; text-align: center; cursor: pointer; color: #444; padding: 0;
    }}
    #layer-toggle-btn:hover {{ background: #f4f4f4; }}
    #layer-toggle-btn.active {{ background: #e8e8e8; }}
    #layer-panel {{
      position: fixed; top: 48px; right: 10px; z-index: 1000;
      max-height: calc(100vh - 68px);
      overflow-y: auto; overflow-x: hidden; scrollbar-width: thin;
      background: white; border-radius: 4px; box-shadow: 0 1px 5px rgba(0,0,0,0.4);
    }}
    #layer-panel::-webkit-scrollbar {{ width: 6px; }}
    #layer-panel::-webkit-scrollbar-thumb {{ background: rgba(0,0,0,0.25); border-radius: 3px; }}
    #layer-panel .leaflet-control-layers {{ box-shadow: none; border-radius: 0; background: transparent; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <button id="layer-toggle-btn" title="Show/hide layers panel">&#9776;</button>
  <div id="layer-panel"></div>
  <div id="attr">
    Data: <a href="https://www.commerce.state.mn.us/" target="_blank">Minnesota Dept. of Commerce</a> |
    Building footprints: ORNL / FEMA
    (<a href="https://disasters.geoplatform.gov/USA_Structures/" target="_blank">USA Structures</a>) |
    Static site proof-of-concept — no ArcGIS Online required
  </div>

  <script>
  // ── Basemaps ────────────────────────────────────────────────────────────────
  var osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{
    attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',maxZoom:19}});

  var satellite = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{attribution:'Tiles © Esri',maxZoom:19}});

  var cartoDB = L.tileLayer(
    'https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',
    {{attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}});

  // ── Map ─────────────────────────────────────────────────────────────────────
  var map = L.map('map',{{center:[46.7296,-94.6859],zoom:7,layers:[cartoDB]}});

  var baseMaps = {{
    "Light (CartoDB)": cartoDB,
    "OpenStreetMap": osm,
    "Satellite (Esri)": satellite
  }};

  // ── Overlay layers ──────────────────────────────────────────────────────────
  var overlayLayers = {{}};

  {all_layer_js}

  // ── Layer control — rendered into a fixed panel outside Leaflet's control flow
  var layerControl = L.control.layers(baseMaps, overlayLayers, {{collapsed:false}}).addTo(map);
  var layerPanel = document.getElementById('layer-panel');
  layerPanel.appendChild(layerControl.getContainer());
  L.DomEvent.disableClickPropagation(layerPanel);
  L.DomEvent.disableScrollPropagation(layerPanel);

  // ── Toggle button ────────────────────────────────────────────────────────────
  var toggleBtn = document.getElementById('layer-toggle-btn');
  toggleBtn.addEventListener('click', function(e) {{
    e.stopPropagation();
    var hidden = layerPanel.style.display === 'none';
    layerPanel.style.display = hidden ? '' : 'none';
    toggleBtn.classList.toggle('active', hidden);
  }});

  </script>
</body>
</html>
"""
    return html


def main():
    if not MANIFEST_PATH.exists():
        print("layer_manifest.json not found — run 02_process_layers.py first.")
        return

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    print(f"Building map from {len(manifest)} layers…")
    build_map(manifest)
    print("\nDone. Open docs/index.html to preview locally.")
    print("Push the docs/ folder to GitHub Pages to deploy.")


if __name__ == "__main__":
    main()
