# Data

Raw data is **not** stored in this repository (size and licences). This folder is filled when you run the notebook.

| File / source | How to get it | Licence |
|---|---|---|
| `aoi.geojson` (Tinigua NNP boundary) | Downloaded from RUNAP by section 1 of `notebooks/01_analysis.ipynb` and cached here | © Parques Nacionales Naturales de Colombia |
| Sentinel-2 L2A bands | Read in place from the public COGs (Earth Search, AWS); nothing is saved here | Free and open Copernicus data |
| ESA WorldCover 10 m 2021 v200 | Read in place from the public COGs on AWS; nothing is saved here | CC BY 4.0 |

If the RUNAP service is down, save the boundary by hand as `data/aoi.geojson` (EPSG:4326) and run the notebook again.

Small sample files used for tests can go in `data/sample/`, which is versioned.
