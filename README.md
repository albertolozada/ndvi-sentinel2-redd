# NDVI and land cover change in Tinigua National Natural Park (Colombia)

![Main result](outputs/maps/preview.png)

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/albertolozada/ndvi-sentinel2-redd/blob/main/notebooks/01_analysis.ipynb)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Dry-season Sentinel-2 NDVI inside a protected area of the Colombian Amazon, 2019 vs 2025 and year by year, crossed with ESA WorldCover and checked against Hansen Global Forest Change, read in place from public COGs with terrio (no GDAL) and cross-checked against GDAL.**

[Resumen en español](#resumen-en-español)

## Question

How much did vegetation (NDVI) drop inside Tinigua National Natural Park between the dry seasons of 2019 and 2025, on which land cover, and how did it evolve year by year?

Tinigua, in the department of Meta, is one of the Colombian national parks most affected by deforestation in recent years ([Mongabay, 2021](https://news.mongabay.com/2021/05/settlers-invading-deforesting-colombian-national-parks-at-an-unstoppable-speed/)). Checking vegetation change from satellite data, with traceable inputs and an explicit CRS, is the same kind of spatial evidence that REDD+ projects and their audits rely on.

## Study area

- **Location:** Tinigua National Natural Park, Meta, Colombia (north-western Amazon)
- **Boundary:** RUNAP, Parques Nacionales Naturales de Colombia, downloaded by the notebook
- **Area:** computed in the UTM zone of the park and compared with the area in RUNAP (section 2 of the notebook)

## Data

| Dataset | Source | Licence | Original CRS | Period |
|---|---|---|---|---|
| Protected area boundary | [RUNAP](https://mapas.parquesnacionales.gov.co/arcgis/rest/services/pnn/runap/FeatureServer), Parques Nacionales Naturales de Colombia | Public data, © Parques Nacionales Naturales de Colombia | EPSG:4686 (served as EPSG:4326) | Current register |
| Sentinel-2 L2A surface reflectance | Copernicus / ESA, via [Earth Search](https://earth-search.aws.element84.com/v1) (Element 84, AWS) | Free and open Copernicus data | UTM (EPSG:326xx) | Dry seasons Dec-Mar, 2019 to 2025 |
| ESA WorldCover 10 m v200 | [ESA / VITO](https://github.com/ESA-WorldCover/esa-worldcover-datasets) | CC BY 4.0 | EPSG:4326 | 2021 |
| Global Forest Change v1.13 (loss year) | [Hansen / UMD / Google / USGS / NASA](https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/download.html) | CC BY 4.0 | EPSG:4326 | 2019-2024 |

Raw data is not stored in this repository. `notebooks/01_analysis.ipynb` downloads it or reads it in place.

Contains modified Copernicus Sentinel data 2018-2025. © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by the ESA WorldCover consortium. Hansen, M. C. et al. (2013), High-Resolution Global Maps of 21st-Century Forest Cover Change, *Science* 342, 850-853; source: Hansen/UMD/Google/USGS/NASA.

## Method

1. Download the park boundary from RUNAP and check its CRS.
2. Reproject to the park's UTM zone (EPSG:32618) for every measurement, and compare the calculated area with the area in RUNAP.
3. Search the dry-season Sentinel-2 L2A scenes (December to March) with the STAC API, and list every scene used.
4. Cross-check terrio against GDAL: the same window of a real band is read with both libraries and compared pixel by pixel.
5. Read red (B04), NIR (B08) and the Scene Classification Layer with terrio, from the COG overview closest to the analysis grid. Convert to reflectance (the +1000 DN offset of products since 25 January 2022 is detected per scene from the pixels), mask clouds and shadows, merge the overlapping tiles of each acquisition, resample onto one 40 m grid and take the per-pixel median NDVI over the clear dates.
6. Normalise between seasons with reference forest (pseudo-invariant pixels): ESA WorldCover 2021 tree cover with NDVI above 0.7 in both seasons. Its median NDVI shift between seasons (for example from processing or atmospheric differences) is removed before measuring change.
7. Flag **potential vegetation loss**: pixels with NDVI above 0.6 in 2019 whose normalised NDVI dropped by more than 0.2 by 2025, excluding permanent water, and cross them with ESA WorldCover 2021.
8. Compare the loss with Hansen Global Forest Change (loss years 2019-2024), also read with terrio: share of our loss confirmed by GFC and share of GFC loss detected, exactly and with one pixel of tolerance.
9. Repeat the composite for every dry season 2019-2025 on a 100 m grid, normalised with the forest that stays above 0.7 in every season.

## Results

*Pending: run the notebook and fill in the main numbers, the main map and a short interpretation.*

## Limitations and data quality

- **CRS used for areas and distances:** EPSG:32618 (WGS 84 / UTM zone 18N)
- **Completeness:** share of the park with valid NDVI in both seasons, and scenes that could not be read, are reported in the notebook
- **NDVI loss is not deforestation:** it also responds to phenology, drought, fire and residual clouds. The comparison with Hansen GFC measures how much of it matches mapped tree cover loss; official data (IDEAM / SMByC) remain the reference for Colombia
- **Clouds:** persistent cloud cover in the Amazon leaves some pixels with few or no clear observations
- **Normalisation:** assumes the reference forest did not change; degradation inside it would be partly removed. The shift removed is reported in the notebook
- **Land cover:** ESA WorldCover is a single date (2021), between the two seasons compared
- **Reflectance offset:** detected per scene from the pixels (5th percentile of clear red DN); the notebook logs the declared and the applied offset of every scene
- **terrio is young (v0.x):** its API may change, which is why the notebook checks it against GDAL on real data

## Reproduce it

**In your browser:** click the "Open in Colab" badge above.

**On your computer:**

```bash
git clone https://github.com/albertolozada/ndvi-sentinel2-redd.git
cd ndvi-sentinel2-redd
conda env create -f environment.yml
conda activate ndvi-sentinel2-redd
jupyter lab notebooks/01_analysis.ipynb
```

## Repository structure

```
├── data/            downloaded data (not versioned, see data/README.md)
├── notebooks/       analysis notebook
├── outputs/maps/    maps and figures used in this README
├── src/
│   ├── geo_checks.py   CRS checks and areas
│   ├── maps.py         location map
│   ├── s2.py           Sentinel-2 search, reading with terrio, NDVI composites
│   ├── sources.py      RUNAP and ESA WorldCover
│   └── validation.py   terrio vs GDAL and comparison with Hansen GFC
└── environment.yml  Python environment
```

## Resumen en español

Este proyecto mide el cambio del NDVI de Sentinel-2 en la estación seca dentro del Parque Nacional Natural Tinigua (Meta, Colombia): compara 2019 con 2025, sigue la evolución año a año, cruza la pérdida potencial de vegetación con la cobertura de ESA WorldCover 2021 y la contrasta con la pérdida de bosque de Hansen Global Forest Change. El límite oficial del parque se descarga del RUNAP, todas las mediciones se hacen en EPSG:32618 y las bandas se leen directamente desde los COG públicos con terrio, una librería en Rust que no necesita GDAL. Como terrio es reciente, el notebook compara su lectura con la de GDAL antes de usarla. La pérdida de NDVI es una señal para revisar, no un mapa de deforestación.

## Author

Alberto Lozada Silva, forestry engineer and carbon project auditor. Portfolio: [albertolozada.github.io](https://albertolozada.github.io) · [LinkedIn](https://www.linkedin.com/in/alberto-lozada-silva/)

## Licence

Code under the MIT License. Data keeps the licence of its original source.
