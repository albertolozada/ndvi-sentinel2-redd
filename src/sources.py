"""Public data sources used by the project.

- Protected area boundary: RUNAP (Registro Unico Nacional de Areas Protegidas),
  Parques Nacionales Naturales de Colombia, ArcGIS FeatureServer.
- Land cover: ESA WorldCover 10 m 2021 v200 (CC BY 4.0), public COG tiles on AWS.
- Independent forest loss: Hansen / UMD Global Forest Change v1.13 (2000-2025, CC BY 4.0),
  public GeoTIFF tiles on Google Cloud Storage.

Nothing is stored in the repository: the notebook downloads what it needs into data/.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests

RUNAP_QUERY = (
    "https://mapas.parquesnacionales.gov.co/arcgis/rest/services/pnn/runap/FeatureServer/0/query"
)
RUNAP_FIELDS = [
    "ap_nombre",
    "ap_categoria",
    "area_ha_total_resolucion",
    "area_ha_terrestre_resolucion",
    "area_ha_total_geografica",
    "fecha_inscrita",
]

WORLDCOVER_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)

GFC_URL = (
    "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/"
    "Hansen_GFC-2025-v1.13_{layer}_{tile}.tif"
)

# ESA WorldCover v200 classes
WORLDCOVER_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def load_runap(name: str, category: str | None = None,
               cache: str | Path | None = None, fallback: str | Path | None = None,
               timeout: int = 120, attempts: int = 3) -> gpd.GeoDataFrame:
    """Download a protected area boundary from RUNAP as a GeoDataFrame (EPSG:4326).

    Parameters
    ----------
    name : str
        Part of the area name, e.g. "Tinigua". Matching is case-insensitive.
    category : str, optional
        Part of the category, e.g. "Parque Nacional Natural", to avoid homonyms.
    cache : path, optional
        GeoJSON file. If it exists it is read instead of calling the service;
        otherwise the download is saved there.
    fallback : path, optional
        Versioned copy of the boundary, used only if the service does not answer.
    attempts : int
        The service is sometimes slow or returns server errors: each request is
        retried this many times, waiting a little longer each time.
    """
    if cache is not None and Path(cache).exists():
        return gpd.read_file(cache)

    where = f"UPPER(ap_nombre) LIKE UPPER('%{name}%')"
    if category:
        where += f" AND UPPER(ap_categoria) LIKE UPPER('%{category}%')"
    params = {
        "where": where,
        "outFields": ",".join(RUNAP_FIELDS),
        "outSR": 4326,
        "f": "geojson",
    }

    data, last_error = None, None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(RUNAP_QUERY, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(f"RUNAP service error: {data['error']}")
            break
        except Exception as exc:
            last_error, data = exc, None
            if attempt < attempts:
                wait = 15 * attempt
                print(f"RUNAP attempt {attempt} failed ({exc.__class__.__name__}), retrying in {wait} s")
                time.sleep(wait)

    if data is None:
        if fallback is not None and Path(fallback).exists():
            print(f"RUNAP did not answer ({last_error.__class__.__name__}): "
                  f"using the versioned copy {fallback}")
            return gpd.read_file(fallback)
        raise RuntimeError(f"RUNAP did not answer after {attempts} attempts: {last_error}")

    if not data.get("features"):
        raise ValueError(f"RUNAP: no protected area matches name={name!r}, category={category!r}")

    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    if cache is not None:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        Path(cache).write_text(json.dumps(data), encoding="utf-8")
    return gdf


def worldcover_tiles(bounds_4326) -> list[str]:
    """Names of the 3x3 degree WorldCover tiles (e.g. 'N00W075') covering a bbox."""
    minx, miny, maxx, maxy = bounds_4326
    tiles = []
    for lat in range(int(math.floor(miny / 3) * 3), int(math.ceil(maxy / 3) * 3), 3):
        for lon in range(int(math.floor(minx / 3) * 3), int(math.ceil(maxx / 3) * 3), 3):
            ns = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
            ew = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
            tiles.append(ns + ew)
    return tiles


def worldcover_urls(bounds_4326) -> list[str]:
    return [WORLDCOVER_URL.format(tile=t) for t in worldcover_tiles(bounds_4326)]


def class_names(values) -> list[str]:
    return [WORLDCOVER_CLASSES.get(int(v), f"class {int(v)}") if not np.isnan(v) else "no data"
            for v in values]


def gfc_tiles(bounds_4326) -> list[str]:
    """Names of the 10x10 degree GFC tiles covering a bbox, e.g. '10N_080W'.

    GFC tiles are named after their top-left (north-west) corner.
    """
    minx, miny, maxx, maxy = bounds_4326
    tiles = []
    for top in range(int(math.ceil(maxy / 10) * 10), int(math.floor(miny / 10) * 10), -10):
        if top == miny:  # bbox edge exactly on a tile edge
            continue
        for left in range(int(math.floor(minx / 10) * 10), int(math.ceil(maxx / 10) * 10), 10):
            ns = f"{abs(top):02d}{'N' if top >= 0 else 'S'}"
            ew = f"{abs(left):03d}{'E' if left >= 0 else 'W'}"
            tiles.append(f"{ns}_{ew}")
    return tiles


def gfc_urls(bounds_4326, layer: str = "lossyear") -> list[str]:
    return [GFC_URL.format(layer=layer, tile=t) for t in gfc_tiles(bounds_4326)]
