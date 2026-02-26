#!/usr/bin/env python3
"""
Phase 3: Inventory layers, decide embed vs PMTiles, produce outputs.

Rules:
  - < 50 MB  → GeoJSON in data/processed/  (embedded in map)
  - >= 50 MB → PMTiles via tippecanoe in data/tiles/
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import force_2d

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TILES_DIR = PROJECT_ROOT / "data" / "tiles"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
TILES_DIR.mkdir(parents=True, exist_ok=True)

SIZE_THRESHOLD_MB = 5  # gpkg MB threshold; GeoJSON is typically 3-5x larger


def tippecanoe_convert(gpkg_path: Path, layer_id: int, layer_name: str):
    """Convert a large layer to PMTiles using tippecanoe."""
    safe_name = layer_name.replace(" ", "_").replace("/", "-")
    output_path = TILES_DIR / f"{layer_id:02d}_{safe_name}.pmtiles"

    if output_path.exists():
        print(f"  ✓ PMTiles already exists: {output_path.name}")
        return output_path

    # Choose zoom range by layer type.
    # GitHub Pages has a 100 MB file limit, so we tune zoom ranges aggressively.
    # Buildings layer is skipped — too large for static hosting (handled separately).
    if layer_name in ("Rivers", "Water Bodies"):
        min_zoom, max_zoom = 6, 10
        extra_flags = ["--drop-densest-as-needed", "--simplification=20", "--no-progress-indicator"]
    elif layer_name in ("Drilling Suitability",):
        min_zoom, max_zoom = 6, 12
        extra_flags = ["--drop-densest-as-needed", "--simplification=15", "--no-progress-indicator"]
    else:
        min_zoom, max_zoom = 7, 12
        extra_flags = ["--drop-densest-as-needed", "--simplification=8", "--no-progress-indicator"]

    # Export gpkg → GeoJSON temp file first (tippecanoe needs GeoJSON or FlatGeobuf)
    temp_geojson = PROCESSED_DIR / f"_temp_{layer_id:02d}.geojson"
    print(f"  Exporting to temp GeoJSON for tippecanoe…")
    gdf = gpd.read_file(gpkg_path, engine="pyogrio")
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    # Drop Z/M coordinates to avoid geometry export errors
    gdf["geometry"] = force_2d(gdf.geometry)
    gdf.to_file(temp_geojson, driver="GeoJSON", engine="pyogrio")

    cmd = [
        "tippecanoe",
        f"--minimum-zoom={min_zoom}",
        f"--maximum-zoom={max_zoom}",
        "--force",
        f"--layer={safe_name}",
        f"--output={output_path}",
    ] + extra_flags + [str(temp_geojson)]
    print(f"  Running tippecanoe (zoom {min_zoom}–{max_zoom})…")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  tippecanoe stderr: {result.stderr[:500]}")
        raise RuntimeError(f"tippecanoe failed with exit code {result.returncode}")

    # Clean up temp file
    temp_geojson.unlink(missing_ok=True)

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"  ✓ PMTiles saved: {output_path.name} ({size_mb:.1f} MB)")
    return output_path


def to_geojson(gpkg_path: Path, layer_id: int, layer_name: str):
    """Convert small layer to GeoJSON in processed/."""
    safe_name = layer_name.replace(" ", "_").replace("/", "-")
    out_path = PROCESSED_DIR / f"{layer_id:02d}_{safe_name}.geojson"

    if out_path.exists():
        print(f"  ✓ GeoJSON already exists: {out_path.name}")
        return out_path

    gdf = gpd.read_file(gpkg_path, engine="pyogrio")
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)

    # Drop Z/M coordinates to avoid export errors
    gdf["geometry"] = force_2d(gdf.geometry)

    # Light simplification for polygon layers
    if gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).any():
        gdf["geometry"] = gdf["geometry"].simplify(0.0001, preserve_topology=True)
        print(f"  Simplified polygon geometries (tolerance 0.0001°)")

    gdf.to_file(out_path, driver="GeoJSON", engine="pyogrio")
    size_mb = out_path.stat().st_size / 1_048_576
    print(f"  ✓ GeoJSON saved: {out_path.name} ({size_mb:.1f} MB, {len(gdf):,} features)")
    return out_path


def main():
    gpkg_files = sorted(RAW_DIR.glob("*.gpkg"))
    if not gpkg_files:
        print("No .gpkg files found in data/raw/ — run 01_download_layers.py first.")
        sys.exit(1)

    # ── Inventory ───────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("LAYER INVENTORY")
    print("="*80)
    print(f"{'File':<55} {'Features':>10} {'MB (gpkg)':>10} {'Geom':>12}")
    print("-"*90)

    records = []
    for gpkg in gpkg_files:
        try:
            gdf = gpd.read_file(gpkg, engine="pyogrio")
            size_mb = gpkg.stat().st_size / 1_048_576
            geom_type = gdf.geometry.geom_type.iloc[0] if len(gdf) > 0 else "empty"
            n = len(gdf)
        except Exception as exc:
            size_mb = gpkg.stat().st_size / 1_048_576
            geom_type = "ERROR"
            n = 0
            print(f"  ERROR reading {gpkg.name}: {exc}")

        stem = gpkg.stem
        layer_id = int(stem.split("_")[0])
        layer_name = " ".join(stem.split("_")[1:]).replace("_", " ")
        decision = "PMTiles" if size_mb >= SIZE_THRESHOLD_MB else "GeoJSON"
        print(f"{gpkg.name:<55} {n:>10,} {size_mb:>10.1f} {geom_type:>12}  → {decision}")
        records.append({"path": gpkg, "id": layer_id, "name": layer_name,
                        "size_mb": size_mb, "n": n, "decision": decision})

    # ── Process each layer ──────────────────────────────────────────────────────
    manifest = {}  # layer_id → {"type": "geojson"|"pmtiles", "path": str, "name": str}

    print("\n\n" + "="*80)
    print("PROCESSING LAYERS")
    print("="*80)

    ARCGIS_SERVICE = (
        "https://services5.arcgis.com/FKwcDz27wRAj4HUT/arcgis/rest/services"
        "/Minnesota_Department_of_Commerce_TENs_Suitability_Mapping_Tool_WFL1/FeatureServer"
    )

    for rec in records:
        print(f"\nLayer {rec['id']}: {rec['name']} ({rec['size_mb']:.1f} MB → {rec['decision']})")

        # Buildings layer: too large for static hosting (2.9M polygons → ~1.5 GB PMTiles).
        # Fall back to loading from the original public ArcGIS service at high zoom.
        if rec["id"] == 0:
            print("  → Too large for static hosting; using ArcGIS service fallback")
            manifest[rec["id"]] = {
                "type": "arcgis",
                "url": f"{ARCGIS_SERVICE}/0",
                "name": rec["name"],
                "features": rec["n"],
                "note": "Loaded dynamically from ArcGIS service at zoom 14+",
            }
            continue

        try:
            if rec["decision"] == "GeoJSON":
                out = to_geojson(rec["path"], rec["id"], rec["name"])
                manifest[rec["id"]] = {
                    "type": "geojson",
                    "path": str(out.relative_to(PROJECT_ROOT)),
                    "name": rec["name"],
                    "features": rec["n"],
                }
            else:
                out = tippecanoe_convert(rec["path"], rec["id"], rec["name"])
                safe_name = rec["name"].replace(" ", "_").replace("/", "-")
                manifest[rec["id"]] = {
                    "type": "pmtiles",
                    "path": str(out.relative_to(PROJECT_ROOT)),
                    "name": rec["name"],
                    "layer_name": safe_name,  # tippecanoe internal layer name
                    "features": rec["n"],
                }
        except Exception as exc:
            print(f"  ✗ ERROR processing layer {rec['id']}: {exc}")
            manifest[rec["id"]] = {
                "type": "error",
                "path": "",
                "name": rec["name"],
                "error": str(exc),
                "features": rec["n"],
            }

    # Save manifest for the map builder
    manifest_path = PROJECT_ROOT / "data" / "layer_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n✓ Manifest saved to {manifest_path}")

    print("\n\nSUMMARY:")
    geojson_layers = [v for v in manifest.values() if v["type"] == "geojson"]
    pmtiles_layers = [v for v in manifest.values() if v["type"] == "pmtiles"]
    arcgis_layers  = [v for v in manifest.values() if v["type"] == "arcgis"]
    error_layers   = [v for v in manifest.values() if v["type"] == "error"]
    print(f"  GeoJSON (embedded):    {len(geojson_layers)} layers")
    print(f"  PMTiles (tiled):       {len(pmtiles_layers)} layers")
    print(f"  ArcGIS service (live): {len(arcgis_layers)} layers")
    print(f"  Errors:                {len(error_layers)} layers")


if __name__ == "__main__":
    main()
