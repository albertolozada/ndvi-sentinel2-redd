"""Cross-check terrio against GDAL (through rioxarray) on the same data.

terrio is young (v0.x), so the project does not take its numbers on trust: the same
window of a real Sentinel-2 band is read with both libraries and compared pixel by pixel.
"""

from __future__ import annotations

import numpy as np


def compare_window(href: str, bounds, crs: str) -> dict:
    """Read the same window with terrio and with rioxarray (GDAL) and compare.

    bounds : (minx, miny, maxx, maxy) in `crs`. No resampling is done: both
    libraries return the native pixels, so they should be identical.
    """
    import rioxarray  # noqa: F401  (GDAL-based reference)
    import terrio.xarray as txr
    import xarray as xr

    a = txr.open_rasterio(href).squeeze("band", drop=True)
    a = a.terrio.clip_box(*bounds, crs=crs).values

    b = xr.open_dataarray(href, engine="rasterio").squeeze("band", drop=True)
    b = b.rio.clip_box(*bounds, crs=crs).values

    same_shape = a.shape == b.shape
    result = {"terrio_shape": a.shape, "gdal_shape": b.shape, "same_shape": same_shape}
    if same_shape:
        diff = np.abs(a.astype("float64") - b.astype("float64"))
        result.update({
            "pixels": int(a.size),
            "identical_%": round(100 * float((diff == 0).mean()), 4),
            "max_abs_diff": float(diff.max()),
        })
    return result
