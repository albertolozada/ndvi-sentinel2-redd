"""Checks of the method against independent references.

- terrio against GDAL (through rioxarray): the same window of a real Sentinel-2 band is
  read with both libraries and compared pixel by pixel.
- Potential vegetation loss against Hansen / UMD Global Forest Change (GFC).
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


def gfc_loss_on_grid(urls, grid, first_year: int, last_year: int):
    """Share of each analysis-grid cell lost in GFC between two years (0 to 1).

    GFC 'lossyear' (about 30 m) is read with terrio onto a grid twice as fine as the
    analysis grid (nearest neighbour, so year codes are not mixed), turned into a
    0/1 loss mask for `first_year`..`last_year`, and averaged over 2 x 2 blocks.
    """
    import numpy as np
    from terrio.rio.enums import Resampling
    from terrio.rio.transform import from_origin
    from src.s2 import Grid, read_to_grid, _empty

    fine = Grid(grid.crs, from_origin(grid.transform.c, grid.transform.f, grid.res / 2, grid.res / 2),
                (grid.shape[0] * 2, grid.shape[1] * 2), grid.res / 2)
    code = None
    for url in urls:
        part = read_to_grid(url, fine, Resampling.nearest)
        if part is not None:
            code = part if code is None else code.fillna(part)
    if code is None:
        raise ValueError("No GFC tile overlaps the grid")

    lo, hi = first_year - 2000, last_year - 2000
    v = code.values
    loss = np.where(np.isfinite(v), ((v >= lo) & (v <= hi)).astype("float32"), np.nan)
    rows, cols = grid.shape
    share = loss.reshape(rows, 2, cols, 2).mean(axis=(1, 3))
    return _empty(grid).copy(data=share.astype("float32"))


def _dilate(mask):
    """3 x 3 dilation (one pixel in every direction) without SciPy."""
    import numpy as np
    m = np.pad(mask, 1)
    out = np.zeros_like(mask)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out |= m[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return out


def compare_loss(ours, reference, domain, pixel_area_ha: float) -> dict:
    """Agreement between two boolean loss masks inside a domain.

    Returns areas, the share of our loss also in the reference ('confirmed') and the
    share of reference loss we detect ('detected'), exactly and with one pixel of
    tolerance (a match in any of the 8 neighbours).
    """
    import numpy as np
    a = np.asarray(ours, bool) & np.asarray(domain, bool)
    b = np.asarray(reference, bool) & np.asarray(domain, bool)
    both = a & b
    a_tol = a & _dilate(b)
    b_tol = b & _dilate(a)
    ha = lambda m: round(float(m.sum()) * pixel_area_ha, 1)
    pct = lambda n, d: round(100 * float(n.sum()) / max(float(d.sum()), 1), 1)
    return {
        "our_loss_ha": ha(a),
        "gfc_loss_ha": ha(b),
        "both_ha": ha(both),
        "confirmed_by_gfc_%": pct(both, a),
        "gfc_detected_%": pct(both, b),
        "confirmed_by_gfc_%_1px": pct(a_tol, a),
        "gfc_detected_%_1px": pct(b_tol, b),
    }
