# lightning-anemoi-dataset

Anemoi dataset recipes and preprocessing code for MeteoSwiss THX lightning data on the ICON-CH1 native grid and the INCA/RADAR 710×640 domain.

## Getting started

Requires Python 3.12+. Install everything with [uv](https://docs.astral.sh/uv/):

```bash
git clone --recurse-submodules https://github.com/MeteoSwiss/lightning-anemoi-dataset
cd lightning-anemoi-dataset
uv sync
source .venv/bin/activate
```

The workspace installs three packages into `.venv`:

| Package | Source |
|---|---|
| `lightning-anemoi-dataset` | `src/lightning_anemoi_dataset/` (this repo) |
| `anemoi-plugins-meteoswiss` | `packages/anemoi-plugins-meteoswiss/` (submodule) |
| `anemoi-datasets` | `packages/anemoi-datasets/` (submodule) |

## Overview

### Data source

Raw lightning data comes from the [Vaisala THX](https://www.vaisala.com/en/products/systems/lightning-detection) network, archived at MeteoSwiss under:

```
/store_new/mch/msclim/hamann/database/lightning/THX/THX{YY}{JJJ}0000.prd[.zip]
```

Files are in a flat directory (no subdirectories). The filename encodes a 2-digit year and 3-digit day-of-year, e.g. `THX25213` = 2025 day 213 = 2025-08-01.

**Format:** pipe-separated (`|`), one strike per row:

```
date time UTC | lon | lat | current | nS | mode | intra | Ax | Ki2 | Exc | Incl | Arc | ...
```

Key fields:

| Field | Description |
|---|---|
| `date time UTC` | Timestamp to millisecond precision, e.g. `01.01.2020 00:01:23.456 UTC` |
| `lon` / `lat` | Geographic coordinates in decimal degrees (WGS84) |
| `current` | Peak current in kA (positive = positive stroke) |
| `intra` | Discharge type: `0` = cloud-to-ground (CG), `1` = intra-cloud (IC) |

**Coverage:** 2005-01-01 to present (~4,000 zipped + ~300 uncompressed files).

**Network extent:** approximately `lat ∈ [42.5, 50.2]`, `lon ∈ [0.0, 17.0]` (central Europe, centred on Switzerland).

### Grid variants

| Variant | Grid | Cells | CRS | Extra-str |
|---|---|---|---|---|
| **ICON** | ICON-CH1 R19B08 native unstructured | 1,147,980 | WGS84 | *(none)* |
| **INCA/RADAR** | INCA/RADAR 710×640 regular | 454,400 | CH1903+/LV95 (EPSG:2056) | `-inca` |

### Preprocessing

Preprocessing converts raw `.prd` strike files into daily NetCDF files (`lightning_icon_YYYYMMDD.nc` / `lightning_inca_YYYYMMDD.nc`) written to a shared output directory, then consumed by `anemoi-datasets`.

```
lightning-grid --config config/preprocess/icon.yaml   # ICON native grid
lightning-grid --config config/preprocess/inca.yaml   # INCA/RADAR domain
```

Or submit to SLURM:

```bash
sbatch scripts/preprocess.sh icon   # or inca
```

Output directories are set in the YAML configs under `config/preprocess/`.

#### Configuration keys

| Key | Default | Description |
|---|---|---|
| `start` / `stop` | — | Date range (UTC, inclusive). Format: `YYYYMMDD` or `YYYY-MM-DD`. |
| `grid_type` | `icon` | Target grid: `icon` (ICON-CH1 native) or `inca` (710×640 LV95 regular). |
| `granularity` | `10min` | Accumulation window and timestep per output file. Options: `10min`, `60min`, `24h`. |
| `discharge_type` | `[CG, IC]` | Lightning types to include. `CG` = cloud-to-ground (`intra=0`), `IC` = intra-cloud (`intra=1`). |
| `radius_km` | `8.0` | Accumulation radius in km. Accepts a single value or a list of 1–3 values (e.g. `[4, 8, 16]`). All radii are stored together in one NetCDF file under a `radius` dimension — the KD-tree is queried once per time step and thresholded per radius. `0` = nearest-neighbour only. 8 km is used in Coalition4; INCA/RADAR typically uses 8 km; ICAO/WMO thunderstorm proximity threshold is 16 km. |
| `network_bbox` | `[42.5, 50.2, 0.0, 17.0]` | THX network extent as `[lat_min, lat_max, lon_min, lon_max]`. Cells outside this box are masked. |
| `archive_path` | `/store_new/mch/msclim/hamann/database/lightning/THX` | Root of the THX archive tree. Both `.prd` and `.prd.zip` files are supported. |
| `icon_grid_file` | `/store_new/mch/msclim/pronos/icon_grid_0001_R19B08_mch.nc` | ICON-CH1 R19B08 native grid file (1,147,980 cells, ~0.7 km mean spacing). Only used when `grid_type: icon`. |
| `output_dir` | `.` | Shared directory where daily NetCDF files are written (`lightning_icon_YYYYMMDD.nc` or `lightning_inca_YYYYMMDD.nc`). Created if absent. |

#### Distance computation

**ICON** — chord distance on the unit sphere. Cell centres and strikes are converted to 3D Cartesian `(x, y, z)` coordinates; the KD-tree returns the Euclidean (chord) distance, which is a monotone proxy for great-circle distance. The radius cutoff converts km → chord length via `2 × sin(radius_km / 111.195°)`.

**INCA/RADAR** — Euclidean distance in projected metres. Strike coordinates are converted from WGS84 to LV95 (EPSG:2056) via pyproj; the KD-tree operates directly in metre space. Accurate because LV95 has very low metric distortion over the Alpine domain.

In both cases the KD-tree is **queried once per time step** using the largest radius, then results are thresholded for each smaller radius — so adding extra radii has negligible cost.

#### Output format

**ICON** (`grid_type: icon`):
```
lightning_icon_YYYYMMDD.nc
  dims:    time=144 (unlimited), radius=N, ncells=1_147_980
  vars:    lightning_count(time, radius, ncells)  [float32, fill=NaN]
  coords:  clat(ncells), clon(ncells), time(UTC), radius(km), time_bnds(time, bnds)
```

**INCA/RADAR** (`grid_type: inca`):
```
lightning_inca_YYYYMMDD.nc
  dims:    time=144 (unlimited), radius=N, y=640, x=710
  vars:    lightning_count(time, radius, y, x)  [float32, fill=NaN]
  coords:  x(m, LV95), y(m, LV95), lat(y,x), lon(y,x), time(UTC), radius(km), time_bnds(time, bnds)
  mapping: swiss_lv95_coordinates (oblique Mercator, EPSG:2056)
```

Both are written to the same directory (`/store_new/mch/msclim/lightning_gridded`).

Output follows the MeteoSwiss data model standard: CF-1.8, `float32` encoding, `NaN` fill values, `cell_method: "time: sum (bnds: end, interval: 10min)"`, MeteoSwiss global attributes (`institution`, `history`, `references`).

Select a specific radius with xarray: `ds.sel(radius=8.0)`.

#### Typical wall-time estimates (10-min granularity, `radius_km: 8`)

| Period | Approx. wall time |
|---|---|
| 1 day | ~75 s |
| 1 month | ~40 min |
| 1 year | ~8 h |

The `lightning-grid` CLI is implemented in `src/lightning_anemoi_dataset/`:

```
src/lightning_anemoi_dataset/
  config.py       Config dataclass and YAML loader
  extract.py      Raw .prd / .prd.zip reader
  grids/
    icon.py       ICON-CH1 KD-tree spatial binning
    inca.py       INCA/RADAR LV95 KD-tree spatial binning
  accumulate.py   Time-bin strikes into count arrays
  output.py       Write CF-1.8 compliant NetCDF
  cli.py          lightning-grid entry point
```

### Anemoi plugin

The `thx-lightning` anemoi source plugin lives in `packages/anemoi-plugins-meteoswiss/`:

```
src/anemoi_plugins_meteoswiss/transform/sources/thx_lightning.py
```

It reads the preprocessed daily NetCDF files and exposes them as earthkit `FieldList` objects for `anemoi-datasets`.

### Creating a dataset

1. Run preprocessing (once per grid type, idempotent — skips existing files):

```bash
sbatch scripts/preprocess.sh icon
```

2. Build the anemoi dataset:

```bash
sbatch scripts/build.sh icon
# or
sbatch scripts/build.sh inca
```

Dataset configs are under `config/`:

| Config | Grid | Period | Frequency | Radius |
|---|---|---|---|---|
| `varda-lightning-thx-1km-2005-2025-10min-v1.yaml` | ICON | 2005–2025 | 10 min | 8 km |
| `varda-lightning-thx-1km-2005-2025-10min-v1-inca.yaml` | INCA/RADAR | 2005–2025 | 10 min | 8 km |

The preprocessed NetCDF files contain all radii (e.g. `[4, 8, 16]` km) under a `radius` dimension. The `radius_km` parameter in the recipe selects which one to use — so you can build separate datasets for different radii from the same preprocessed files without rerunning preprocessing.

Debug configs for quick smoke tests (6 timesteps, 2020-01-01):

```bash
anemoi-datasets create config/debug/lightning.yaml /tmp/test-icon.zarr
anemoi-datasets create config/debug/lightning-inca.yaml /tmp/test-inca.zarr
```

## Pre-generation checklist

Before generating a production dataset, verify:

- [ ] All changes are committed and pushed (ideally merged to `main`)
- [ ] Config filename follows the anemoi naming convention
- [ ] Submodules point to the right commits (ideally merged to `main`)
- [ ] An annotated Git tag has been pushed (e.g. `v1` or `v1-inca`)
- [ ] A GitHub release has been created from the tag with a dataset description

## Versioning

A dataset is a reproducible build artifact. Its exact content is determined by:

1. **The recipe** — the YAML config under `config/` passed to `anemoi-datasets`
2. **The code** — the pinned commits of the `anemoi-datasets` and `anemoi-plugins-meteoswiss` submodules, plus `src/lightning_anemoi_dataset/`

Both must be versioned together via a Git tag **before** running a production build.

```
varda-lightning-thx-1km-2005-2025-10min-v1        →  tag: v1
varda-lightning-thx-1km-2005-2025-10min-v1-inca   →  tag: v1-inca
```

## Dataset naming

Follows the [anemoi naming convention](https://anemoi.readthedocs.io/projects/datasets/en/latest/building/naming-conventions.html):

```
purpose-content-source-resolution-start-end-frequency-version[-extra-str]
```

| Component | Value |
|---|---|
| purpose | `varda` |
| content | `lightning` |
| source | `thx` |
| resolution | `1km` |
| start / end | `2005` / `2025` |
| frequency | `10min` |
| version | `v1` |
| extra-str | *(none)* for ICON; `-inca` for INCA/RADAR variant |
