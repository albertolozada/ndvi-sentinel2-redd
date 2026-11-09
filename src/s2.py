"""Sentinel-2 L2A NDVI composites read with terrio (pure Rust, no GDAL).

Scenes come from the Earth Search STAC API (Element 84, public Sentinel-2 COGs on AWS).
Each band is read in place: only the COG tiles that cover the study area are fetched,
from a reduced-resolution overview when the analysis grid is coarser than the band.

Every scene is resampled onto one common analysis grid (same CRS, origin and pixel
size), clouds are masked with the Scene Classification Layer (SCL) and the composite
is the per-pixel median NDVI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
import terrio.xarray as txr
from terrio.rio.enums import Resampling
from terrio.rio.transform import from_origin

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# SCL classes kept as clear observations:
# 4 vegetation, 5 not vegetated, 6 water, 7 unclassified.
# Dropped: 0 no data, 1 saturated, 2 dark area, 3 cloud shadow,
# 8-9 cloud medium/high probability, 10 thin cirrus, 11 snow.
SCL_CLEAR = (4, 5, 6, 7)

NATIVE_RES = {"red": 10, "nir": 10, "scl": 20}


# ---------------------------------------------------------------- grid

@dataclass
class Grid:
    """Common analysis grid: every layer is resampled onto it."""
    crs: str
    transform: object
    shape: tuple[int, int]  # (rows, cols)
    res: float

    @property
    def bounds(self):
        minx, maxy = self.transform.c, self.transform.f
        return (minx, maxy - self.shape[0] * self.res, minx + self.shape[1] * self.res, maxy)

    @property
    def pixel_area_ha(self) -> float:
        return self.res * self.res / 10_000


def make_grid(aoi: gpd.GeoDataFrame, crs: str, res: float) -> Grid:
    """Grid covering the AOI in a metric CRS, with edges snapped to the pixel size."""
    minx, miny, maxx, maxy = aoi.to_crs(crs).total_bounds
    minx, miny = math.floor(minx / res) * res, math.floor(miny / res) * res
    maxx, maxy = math.ceil(maxx / res) * res, math.ceil(maxy / res) * res
    shape = (int(round((maxy - miny) / res)), int(round((maxx - minx) / res)))
    return Grid(crs=crs, transform=from_origin(minx, maxy, res, res), shape=shape, res=res)


def _empty(grid: Grid) -> xr.DataArray:
    t = grid.transform
    xs = t.c + grid.res * (np.arange(grid.shape[1]) + 0.5)
    ys = t.f - grid.res * (np.arange(grid.shape[0]) + 0.5)
    da = xr.DataArray(np.full(grid.shape, np.nan, dtype="float32"),
                      dims=("y", "x"), coords={"y": ys, "x": xs})
    return da.terrio.write_crs(grid.crs).terrio.write_transform(grid.transform)


# ---------------------------------------------------------------- reading

def _overview_level(native_res: float, target_res: float) -> int | None:
    """Coarsest COG overview whose pixel is not larger than the target pixel.

    Overview 0 is half the native resolution, 1 a quarter, and so on.
    """
    if not native_res or target_res < 2 * native_res:
        return None
    return int(math.floor(math.log2(target_res / native_res))) - 1


def read_to_grid(href: str, grid: Grid, resampling=Resampling.average,
                 native_res: float | None = None) -> xr.DataArray | None:
    """Read a (remote) raster with terrio and resample it onto the analysis grid.

    Returns None when the raster does not overlap the grid.
    """
    level = _overview_level(native_res, grid.res) if native_res else None
    try:
        da = txr.open_rasterio(href, masked=True, overview_level=level)
    except Exception:
        if level is None:
            raise
        da = txr.open_rasterio(href, masked=True)  # no such overview: full resolution
    da = da.squeeze("band", drop=True)

    minx, miny, maxx, maxy = grid.bounds
    pad = 2 * grid.res
    try:  # fetch only the tiles inside the grid
        da = da.terrio.clip_box(minx - pad, miny - pad, maxx + pad, maxy + pad, crs=grid.crs)
    except Exception:
        return None
    out = da.terrio.reproject(grid.crs, shape=grid.shape, transform=grid.transform,
                              resampling=resampling, nodata=np.nan)
    return out.astype("float32")


def scale_offset(item, asset: str) -> tuple[float, float, str]:
    """Scale and offset declared in the STAC metadata of an asset ('raster:bands').

    Falls back to the ESA rule when the item has no 'raster:bands': since processing
    baseline 04.00 (25 Jan 2022) L2A products carry an offset of -1000 DN.
    Reported in the log; the offset actually applied comes from `dn_offset`.
    """
    bands = item.assets[asset].extra_fields.get("raster:bands") or [{}]
    scale, offset = bands[0].get("scale"), bands[0].get("offset")
    if scale is not None:
        return float(scale), float(offset or 0.0), "raster:bands"
    baseline = float(item.properties.get("s2:processing_baseline", 0) or 0)
    return 1e-4, (-0.1 if baseline >= 4 else 0.0), f"processing baseline {baseline:.2f}"


def dn_offset(red_dn: np.ndarray, clear: np.ndarray, baseline: float) -> tuple[int, float]:
    """Offset (in DN) actually present in the pixels: 1000 or 0.

    The STAC metadata does not always state the offset consistently with the stored
    values, so it is decided from the data: with the offset inside the values, every
    land pixel has red >= 1000 DN; vegetation without it has red well below 1000 DN.
    Rule: offset present if baseline >= 4 and the 5th percentile of clear red DN >= 1000.
    Returns (offset_dn, p5_red_dn).
    """
    vals = red_dn[clear & np.isfinite(red_dn)]
    if vals.size == 0:
        return 0, float("nan")
    p5 = float(np.percentile(vals, 5))
    return (1000 if baseline >= 4 and p5 >= 1000 else 0), p5


# ---------------------------------------------------------------- search

def search_items(bbox, datetime: str, max_cloud: float = 60, months=None) -> list:
    """Sentinel-2 L2A items from Earth Search, sorted by date.

    months : optional list of month numbers to keep (e.g. [12, 1, 2, 3] for a dry season).
    """
    from pystac_client import Client

    client = Client.open(EARTH_SEARCH)
    search = client.search(collections=[COLLECTION], bbox=list(bbox), datetime=datetime,
                           query={"eo:cloud_cover": {"lt": max_cloud}})
    items = list(search.items())
    if months:
        items = [i for i in items if i.datetime.month in months]
    return sorted(items, key=lambda i: i.datetime)


def items_table(items) -> pd.DataFrame:
    return pd.DataFrame([{
        "id": i.id,
        "date": i.datetime.date(),
        "mgrs_tile": i.properties.get("s2:mgrs_tile") or i.properties.get("grid:code"),
        "cloud_cover_%": round(i.properties.get("eo:cloud_cover", np.nan), 1),
        "processing_baseline": i.properties.get("s2:processing_baseline"),
        # Earth Search flag about the -1000 DN offset, kept for traceability only:
        # the offset actually used is decided from the pixels (see dn_offset)
        "boa_offset_applied": i.properties.get("earthsearch:boa_offset_applied"),
    } for i in items])


# ---------------------------------------------------------------- NDVI

def scene_ndvi(item, grid: Grid) -> tuple[xr.DataArray | None, dict]:
    """Cloud-masked NDVI of one scene on the analysis grid, plus a log row."""
    log = {"id": item.id, "date": item.datetime.date()}
    scl = read_to_grid(item.assets["scl"].href, grid, Resampling.nearest, NATIVE_RES["scl"])
    if scl is None:
        log["status"] = "outside grid"
        return None, log
    red = read_to_grid(item.assets["red"].href, grid, Resampling.average, NATIVE_RES["red"])
    nir = read_to_grid(item.assets["nir"].href, grid, Resampling.average, NATIVE_RES["nir"])

    clear = scl.isin(SCL_CLEAR)

    scale, meta_offset, meta_src = scale_offset(item, "red")
    baseline = float(item.properties.get("s2:processing_baseline", 0) or 0)
    off_dn, p5 = dn_offset(red.values, clear.values, baseline)
    red = (red - off_dn) * scale
    nir = (nir - off_dn) * scale

    ndvi = ((nir - red) / (nir + red)).where(clear & (nir + red > 0))
    ndvi = ndvi.clip(-1, 1).astype("float32")

    covered = int(scl.notnull().sum())
    log.update({
        "status": "ok",
        "baseline": baseline,
        "metadata_offset": meta_offset,
        "red_p5_dn": round(p5, 0),
        "offset_applied_dn": off_dn,
        "pixels_in_scene": covered,
        "clear_%": round(100 * int(clear.sum()) / covered, 1) if covered else 0.0,
    })
    return ndvi, log


def composite(items, grid: Grid, aoi: gpd.GeoDataFrame | None = None,
              verbose: bool = True) -> tuple[xr.Dataset, pd.DataFrame]:
    """Median NDVI of all clear observations, and number of clear observations per pixel."""
    stack, logs = [], []
    for n, item in enumerate(items, 1):
        try:
            ndvi, log = scene_ndvi(item, grid)
        except Exception as exc:  # keep going, but record the failure
            ndvi, log = None, {"id": item.id, "date": item.datetime.date(),
                               "status": f"error: {exc}"}
        logs.append(log)
        if ndvi is not None:
            stack.append(ndvi.values)
        if verbose:
            print(f"[{n}/{len(items)}] {log['id']}: {log['status']}"
                  + (f", clear {log['clear_%']}%" if log.get("status") == "ok" else ""))

    if not stack:
        raise ValueError("No scene could be read for this grid and period.")

    cube = np.stack(stack)
    template = _empty(grid)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            median = np.nanmedian(cube, axis=0).astype("float32")
    n_clear = np.isfinite(cube).sum(axis=0).astype("int16")

    ds = xr.Dataset({
        "ndvi": template.copy(data=median),
        "n_clear": template.copy(data=n_clear.astype("float32")),
    })
    if aoi is not None:
        ds = mask_to_aoi(ds, aoi, grid)
    return ds, pd.DataFrame(logs)


def mask_to_aoi(obj, aoi: gpd.GeoDataFrame, grid: Grid):
    """Set pixels outside the AOI polygon to NaN (keeps the grid shape)."""
    geoms = aoi.to_crs(grid.crs).geometry.values
    if isinstance(obj, xr.Dataset):
        return xr.Dataset({k: mask_to_aoi(v, aoi, grid) for k, v in obj.data_vars.items()})
    return obj.terrio.write_crs(grid.crs).terrio.clip(geoms, crs=grid.crs, drop=False)


def ndvi_summary(ds: xr.Dataset, grid: Grid, label: str) -> dict:
    v = ds["ndvi"].values
    valid = np.isfinite(v)
    inside = np.isfinite(ds["n_clear"].values)
    return {
        "period": label,
        "mean_ndvi": round(float(np.nanmean(v)), 3) if valid.any() else np.nan,
        "median_ndvi": round(float(np.nanmedian(v)), 3) if valid.any() else np.nan,
        "ndvi_lt_0.5_ha": round(float(((v < 0.5) & valid).sum()) * grid.pixel_area_ha, 1),
        "valid_%_of_aoi": round(100 * float(valid.sum()) / max(int(inside.sum()), 1), 1),
    }
