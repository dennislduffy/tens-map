#!/usr/bin/env python3
"""
Download all layers from the MN Commerce TENs Suitability Mapping Tool ArcGIS Feature Service.
Saves each layer as a GeoPackage in data/raw/.
Uses chunk-based pagination and is fully resumable.
"""

import json
import os
import time
import requests
import geopandas as gpd
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_URL = (
    "https://services5.arcgis.com/FKwcDz27wRAj4HUT/arcgis/rest/services"
    "/Minnesota_Department_of_Commerce_TENs_Suitability_Mapping_Tool_WFL1/FeatureServer"
)
PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CHUNKS_DIR = PROJECT_ROOT / "data" / "raw" / "_chunks"
RAW_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

TIMEOUT = 120
MAX_RETRIES = 5
BACKOFF_BASE = 4  # seconds


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_json(url: str, params: dict = None, label: str = "") -> dict:
    """GET with retry + exponential backoff."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise ValueError(f"API error: {data['error']}")
            return data
        except Exception as exc:
            wait = BACKOFF_BASE ** attempt
            print(f"  [{label}] Attempt {attempt}/{MAX_RETRIES} failed: {exc}. "
                  f"Retrying in {wait}s…")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(wait)


def get_layer_meta(layer_id: int) -> dict:
    url = f"{BASE_URL}/{layer_id}?f=json"
    return get_json(url, label=f"meta:{layer_id}")


def download_layer(layer_id: int, layer_name: str):
    """Download a full layer to a GeoPackage, using resumable chunk files."""
    safe_name = layer_name.replace(" ", "_").replace("/", "-")
    gpkg_path = RAW_DIR / f"{layer_id:02d}_{safe_name}.gpkg"

    if gpkg_path.exists():
        print(f"  ✓ Already exists: {gpkg_path.name} — skipping")
        return True

    # Get server maxRecordCount
    meta = get_layer_meta(layer_id)
    max_count = meta.get("maxRecordCount", 2000)
    batch = min(max_count, 12000)
    geom_type = meta.get("geometryType", "unknown")
    print(f"  Layer meta: geometryType={geom_type}, maxRecordCount={max_count}, using batch={batch}")

    # Count total features
    count_params = {
        "where": "1=1",
        "returnCountOnly": "true",
        "f": "json",
    }
    count_data = get_json(
        f"{BASE_URL}/{layer_id}/query",
        params=count_params,
        label=f"count:{layer_id}"
    )
    total = count_data.get("count", 0)
    print(f"  Total features: {total:,}")

    if total == 0:
        print("  No features — skipping.")
        return True

    # Paginate through chunks
    offset = 0
    chunk_files = []
    start_time = time.time()
    downloaded_so_far = 0

    while offset < total:
        chunk_file = CHUNKS_DIR / f"{layer_id:02d}_chunk_{offset:08d}.geojson"
        chunk_files.append(chunk_file)

        if chunk_file.exists():
            # Count features in existing chunk to update progress counter
            try:
                with open(chunk_file) as f:
                    cdata = json.load(f)
                n = len(cdata.get("features", []))
                downloaded_so_far += n
                offset += batch
                continue
            except Exception:
                pass  # Re-download corrupted chunk

        params = {
            "where": "1=1",
            "outFields": "*",
            "resultRecordCount": batch,
            "resultOffset": offset,
            "f": "geojson",
        }
        data = get_json(
            f"{BASE_URL}/{layer_id}/query",
            params=params,
            label=f"layer:{layer_id} offset:{offset}"
        )

        features = data.get("features", [])
        n = len(features)

        with open(chunk_file, "w") as f:
            json.dump(data, f)

        downloaded_so_far += n
        elapsed = time.time() - start_time
        rate = downloaded_so_far / elapsed if elapsed > 0 else 1
        remaining = (total - downloaded_so_far) / rate if rate > 0 else 0
        pct = 100 * downloaded_so_far / total if total > 0 else 100
        print(
            f"  [{layer_name}] {downloaded_so_far:>8,}/{total:,} ({pct:5.1f}%) "
            f"| elapsed {elapsed/60:.1f}m | ETA {remaining/60:.1f}m"
        )

        offset += batch

        if n < batch:
            # Server returned fewer than requested — we've reached the end
            break

    # Combine all chunks into a single GeoPackage
    print(f"  Combining {len(chunk_files)} chunk(s) into {gpkg_path.name}…")
    gdfs = []
    for cf in chunk_files:
        if not cf.exists():
            continue
        try:
            gdf = gpd.read_file(cf, engine="pyogrio")
            if len(gdf) > 0:
                gdfs.append(gdf)
        except Exception as exc:
            print(f"  Warning: could not read {cf.name}: {exc}")

    if not gdfs:
        print("  No data read from chunks — skipping GeoPackage creation.")
        return False

    combined = gpd.pd.concat(gdfs, ignore_index=True) if len(gdfs) > 1 else gdfs[0]
    # Make it a GeoDataFrame
    if not isinstance(combined, gpd.GeoDataFrame):
        combined = gpd.GeoDataFrame(combined)

    combined.to_file(gpkg_path, driver="GPKG", engine="pyogrio")
    size_mb = gpkg_path.stat().st_size / 1_048_576
    print(f"  ✓ Saved {gpkg_path.name} ({size_mb:.1f} MB, {len(combined):,} features)")

    # Clean up chunk files for this layer
    for cf in chunk_files:
        if cf.exists():
            cf.unlink()

    return True


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("Fetching service metadata…")
    service_meta = get_json(f"{BASE_URL}?f=json", label="service")
    layers = service_meta.get("layers", [])
    print(f"Found {len(layers)} layers:\n")
    for layer in layers:
        print(f"  {layer['id']:>3}: {layer['name']}")
    print()

    failed = []
    for layer in layers:
        lid = layer["id"]
        lname = layer["name"]
        print(f"\n{'='*60}")
        print(f"Layer {lid}: {lname}")
        print(f"{'='*60}")
        try:
            download_layer(lid, lname)
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed.append((lid, lname, str(exc)))

    print("\n\n" + "="*60)
    print("DOWNLOAD COMPLETE")
    print("="*60)
    if failed:
        print(f"\nFailed layers ({len(failed)}):")
        for lid, lname, err in failed:
            print(f"  Layer {lid} '{lname}': {err}")
    else:
        print("All layers downloaded successfully.")

    # Print inventory
    print("\nInventory of downloaded files:")
    print(f"{'File':<55} {'Features':>10} {'MB':>8}")
    print("-" * 75)
    for gpkg in sorted(RAW_DIR.glob("*.gpkg")):
        try:
            gdf = gpd.read_file(gpkg, engine="pyogrio")
            size_mb = gpkg.stat().st_size / 1_048_576
            print(f"{gpkg.name:<55} {len(gdf):>10,} {size_mb:>8.1f}")
        except Exception as exc:
            size_mb = gpkg.stat().st_size / 1_048_576
            print(f"{gpkg.name:<55} {'ERROR':>10} {size_mb:>8.1f}  ({exc})")


if __name__ == "__main__":
    main()
