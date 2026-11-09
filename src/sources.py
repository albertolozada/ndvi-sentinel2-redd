"""Public data sources used by the project.

- Protected area boundary: RUNAP (Registro Unico Nacional de Areas Protegidas),
  Parques Nacionales Naturales de Colombia, ArcGIS FeatureServer.
- Land cover: ESA WorldCover 10 m 2021 v200 (CC BY 4.0), public COG tiles on AWS.

Nothing is stored in the repository: the notebook downloads what it needs into data/.
"""

from __future__ import annotations

import json
import math
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
               cache: str | Path | None = None, timeout: int = 120) -> gpd.GeoDataFrame:
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
    r = requests.get(RUNAP_QUERY, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"RUNAP service error: {data['error']}")
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
