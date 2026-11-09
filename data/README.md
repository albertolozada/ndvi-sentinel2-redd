# Data

Raw data is **not** stored in this repository (size and licences). This folder is filled when you run the notebook.

| File / source | How to get it | Licence |
|---|---|---|
| `aoi.geojson` (Tinigua NNP boundary) | Downloaded from RUNAP by section 1 of `notebooks/01_analysis.ipynb` and cached here | © Parques Nacionales Naturales de Colombia |
| Sentinel-2 L2A bands | Read in place from the public COGs (Earth Search, AWS); nothing is saved here | Free and open Copernicus data |
| ESA WorldCover 10 m 2021 v200 | Read in place from the public COGs on AWS; nothing is saved here | CC BY 4.0 |
| Hansen Global Forest Change v1.13 (tree cover loss by year) | Read in place from the public tiles ([download page](https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/download.html)); nothing is saved here. Hansen et al. (2013), *Science* 342:850-853, [doi:10.1126/science.1244693](https://doi.org/10.1126/science.1244693) | CC BY 4.0 |

`data/sample/aoi_tinigua_runap.geojson` is a versioned copy of the RUNAP boundary (EPSG:4326, © Parques Nacionales Naturales de Colombia). The notebook uses it only when the RUNAP service does not answer.

Small sample files used for tests can go in `data/sample/`, which is versioned.
