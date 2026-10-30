"""Write daily NetCDF output files for ICON or INCA/RADAR grids.

Follows the MeteoSwiss data model standard (src/data_model):
  - CF-1.8 conventions
  - float32 for all coordinates and variables
  - NaN fill values
  - Swiss LV95 grid mapping variable for INCA/RADAR output
  - time_bnds for accumulated variables
  - MeteoSwiss global attributes
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import xarray as xr

from .accumulate import time_bins

# LV95 grid mapping attributes (oblique Mercator, EPSG:2056)
_LV95_GRID_MAPPING_ATTRS = {
    "grid_mapping_name": "oblique_mercator",
    "longitude_of_projection_origin": "7.43958333",
    "latitude_of_projection_origin": "46.9524056",
    "scale_factor_at_projection_origin": "1.",
    "false_easting": "2600000.",
    "false_northing": "1200000.",
    "reference_ellipsoid_name": "Bessel 1841",
    "prime_meridian_name": "Greenwich",
    "horizontal_datum_name": "CH1903+",
    "inverse_flattening": "299.1528128",
    "azimuth_of_central_line": "90.",
    "semi_major_axis": "6377397.155",
    "crs": "EPSG:2056",
    "geographic_crs_name": "CH1903+ / LV95",
}

_GLOBAL_ATTRS = {
    "Conventions": "CF-1.8",
    "ConventionsURL": "https://cfconventions.org/Data/cf-conventions/cf-conventions-1.8/cf-conventions.pdf",
    "institution": "Federal Office of Meteorology and Climatology MeteoSwiss",
    "references": "http://www.meteoswiss.ch",
    "coordinate_reference": "Pixel center location",
}


def _global_attrs(grid_type: str, day: datetime) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {
        **_GLOBAL_ATTRS,
        "title": f"THX lightning counts on {grid_type.upper()} grid",
        "source": "lightning-anemoi-dataset (lightning-grid CLI)",
        "history": f"Produced {now}",
        "date": day.strftime("%Y-%m-%d"),
    }


def _time_arrays(bins: list[datetime], granularity: timedelta, day: datetime):
    """Return time values, bounds, and units for CF encoding."""
    epoch = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    epoch_str = epoch.strftime("%Y-%m-%d %H:%M:%S")
    units = f"seconds since {epoch_str}"

    t_vals = np.array(
        [(t - epoch).total_seconds() for t in bins], dtype="float32"
    )
    # time_bnds: [start, end] of each accumulation interval
    t_bnds = np.column_stack([
        t_vals,
        t_vals + granularity.total_seconds(),
    ]).astype("float32")

    return t_vals, t_bnds, units


def write_icon_grid(
    clat: np.ndarray,
    clon: np.ndarray,
    output_dir,
) -> Path:
    """Write a static ``icon_grid.nc`` with clat/clon arrays (written once).

    Used when ``embed_latlon=False`` so daily files omit the large 1-D
    clat/clon arrays (~8.8 MB per file).  The plugin loads this file
    to restore coordinates when reading daily files.
    """
    from pathlib import Path
    output_dir = Path(output_dir)

    ncells = len(clat)
    ds = xr.Dataset(
        {
            "clat": xr.DataArray(
                clat.astype("float32"), dims=["ncells"],
                attrs={"standard_name": "latitude", "long_name": "latitude",
                       "units": "degrees_north", "axis": "Y"},
            ),
            "clon": xr.DataArray(
                clon.astype("float32"), dims=["ncells"],
                attrs={"standard_name": "longitude", "long_name": "longitude",
                       "units": "degrees_east", "axis": "X"},
            ),
        },
        coords={"ncells": np.arange(ncells, dtype=np.int32)},
        attrs={**_GLOBAL_ATTRS,
               "title": "ICON-CH1 grid coordinates (static)",
               "source": "lightning-anemoi-dataset (lightning-grid CLI)"},
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "icon_grid.nc"
    ds.to_netcdf(out, encoding={"clat": {"dtype": "float32"}, "clon": {"dtype": "float32"}})
    return out


def write_icon_day(
    counts: np.ndarray,
    day: datetime,
    granularity: timedelta,
    clat: np.ndarray,
    clon: np.ndarray,
    radii_km: list[float],
    output_dir,
    embed_latlon: bool = True,
):
    """Write ``lightning_icon_YYYYMMDD.nc`` for ICON native grid.

    Parameters
    ----------
    counts:
        float32 array ``(n_times, n_radii, ncells)``.
    embed_latlon:
        When False, omit clat/clon from the daily file (~8.8 MB saved per file).
        The plugin then loads them from ``icon_grid.nc`` in the same directory.
    """
    from pathlib import Path
    output_dir = Path(output_dir)

    bins = time_bins(day, granularity)
    t_vals, t_bnds, t_units = _time_arrays(bins, granularity, day)
    radii = np.array(radii_km, dtype="float32")
    ncells = counts.shape[2]
    gran_str = _granularity_str(granularity)

    data_vars = {
        "lightning_count": xr.DataArray(
            counts.astype("float32"),
            dims=["time", "radius", "ncells"],
            attrs={
                "long_name": "lightning strike count per grid cell",
                "standard_name": "number_of_lightning_flashes",
                "units": "1",
                "cell_method": f"time: sum (bnds: end, interval: {gran_str})",
                "temporal_resolution": gran_str,
                "spatial_resolution": "1000 m",
                "resolution": "1km",
            },
        ),
        "time_bnds": xr.DataArray(
            t_bnds, dims=["time", "bnds"],
            attrs={"standard_name": "time_bounds", "long_name": "time bounds",
                   "units": t_units, "calendar": "standard"},
        ),
    }

    if embed_latlon:
        data_vars["clat"] = xr.DataArray(
            clat.astype("float32"), dims=["ncells"],
            attrs={"standard_name": "latitude", "long_name": "latitude",
                   "units": "degrees_north", "axis": "Y"},
        )
        data_vars["clon"] = xr.DataArray(
            clon.astype("float32"), dims=["ncells"],
            attrs={"standard_name": "longitude", "long_name": "longitude",
                   "units": "degrees_east", "axis": "X"},
        )

    ds = xr.Dataset(
        data_vars,
        coords={
            "time": xr.DataArray(
                t_vals, dims=["time"],
                attrs={"standard_name": "time",
                       "long_name": "seconds since analysis or reference time",
                       "units": t_units, "calendar": "standard", "axis": "T",
                       "bounds": "time_bnds"},
            ),
            "radius": xr.DataArray(
                radii, dims=["radius"],
                attrs={"long_name": "accumulation radius", "units": "km"},
            ),
            "ncells": np.arange(ncells, dtype=np.int32),
        },
        attrs=_global_attrs("icon", day),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"lightning_icon_{day.strftime('%Y%m%d')}.nc"
    encoding = {
        "lightning_count": {"zlib": True, "complevel": 4, "dtype": "float32",
                             "_FillValue": float("nan")},
        "time": {"dtype": "float32"},
        "time_bnds": {"dtype": "float32"},
        "radius": {"dtype": "float32"},
    }
    if embed_latlon:
        encoding["clat"] = {"dtype": "float32"}
        encoding["clon"] = {"dtype": "float32"}
    ds.to_netcdf(out, encoding=encoding, unlimited_dims=["time"])
    return out


def write_inca_grid(
    lat: np.ndarray,
    lon: np.ndarray,
    output_dir,
    x_lv95: np.ndarray | None = None,
    y_lv95: np.ndarray | None = None,
) -> Path:
    """Write a static ``inca_grid.nc`` with lat/lon arrays (written once).

    Used when ``embed_latlon=False`` so daily files omit the large 2-D
    lat/lon arrays (~3.6 MB each file).  The plugin loads this file
    to restore coordinates when reading daily files.
    """
    from pathlib import Path
    from .grids.inca import _X0, _Y0, _DX, _DY, _NX, _NY
    output_dir = Path(output_dir)

    if x_lv95 is None:
        x_lv95 = (_X0 + np.arange(_NX) * _DX).astype("float32")
    if y_lv95 is None:
        y_lv95 = (_Y0 + np.arange(_NY) * _DY).astype("float32")

    ds = xr.Dataset(
        {
            "lat": xr.DataArray(
                lat.astype("float32"), dims=["y", "x"],
                attrs={"standard_name": "latitude", "long_name": "latitude",
                       "units": "degrees_north"},
            ),
            "lon": xr.DataArray(
                lon.astype("float32"), dims=["y", "x"],
                attrs={"standard_name": "longitude", "long_name": "longitude",
                       "units": "degrees_east"},
            ),
            "swiss_lv95_coordinates": xr.DataArray(
                np.int32(0), attrs=_LV95_GRID_MAPPING_ATTRS,
            ),
        },
        coords={
            "x": xr.DataArray(
                x_lv95, dims=["x"],
                attrs={"standard_name": "projection_x_coordinate",
                       "long_name": "Swiss easting (LV95)", "units": "m", "axis": "X"},
            ),
            "y": xr.DataArray(
                y_lv95, dims=["y"],
                attrs={"standard_name": "projection_y_coordinate",
                       "long_name": "Swiss northing (LV95)", "units": "m", "axis": "Y"},
            ),
        },
        attrs={**_GLOBAL_ATTRS,
               "title": "INCA/RADAR grid coordinates (static)",
               "source": "lightning-anemoi-dataset (lightning-grid CLI)"},
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "inca_grid.nc"
    ds.to_netcdf(out, encoding={"lat": {"dtype": "float32"}, "lon": {"dtype": "float32"},
                                 "x": {"dtype": "float32"}, "y": {"dtype": "float32"}})
    return out


def write_inca_day(
    counts: np.ndarray,
    day: datetime,
    granularity: timedelta,
    lat: np.ndarray,
    lon: np.ndarray,
    radii_km: list[float],
    output_dir,
    x_lv95: np.ndarray | None = None,
    y_lv95: np.ndarray | None = None,
    embed_latlon: bool = True,
):
    """Write ``lightning_inca_YYYYMMDD.nc`` for INCA/RADAR 710×640 grid.

    Parameters
    ----------
    counts:
        float32 array ``(n_times, n_radii, NY, NX)``.
    lat, lon:
        2-D WGS84 auxiliary coordinate arrays ``(NY, NX)``.
        Embedded in the daily file only when ``embed_latlon=True``.
    embed_latlon:
        When False, omit lat/lon from the daily file (~4 MB → ~0.3 MB).
        The plugin then loads them from ``inca_grid.nc`` in the same directory.
    x_lv95, y_lv95:
        Optional 1-D LV95 easting/northing arrays (NX,) and (NY,).
        If not provided, derived from the INCA/RADAR domain constants.
    """
    from pathlib import Path
    from .grids.inca import _X0, _Y0, _DX, _DY, _NX, _NY
    output_dir = Path(output_dir)

    bins = time_bins(day, granularity)
    t_vals, t_bnds, t_units = _time_arrays(bins, granularity, day)
    radii = np.array(radii_km, dtype="float32")
    ny, nx = counts.shape[2], counts.shape[3]
    gran_str = _granularity_str(granularity)

    if x_lv95 is None:
        x_lv95 = (_X0 + np.arange(_NX) * _DX).astype("float32")
    if y_lv95 is None:
        y_lv95 = (_Y0 + np.arange(_NY) * _DY).astype("float32")

    data_vars = {
        "lightning_count": xr.DataArray(
            counts.astype("float32"),
            dims=["time", "radius", "y", "x"],
            attrs={
                "long_name": "lightning strike count per grid cell",
                "standard_name": "number_of_lightning_flashes",
                "units": "1",
                "cell_method": f"time: sum (bnds: end, interval: {gran_str})",
                "temporal_resolution": gran_str,
                "spatial_resolution": "1000 m",
                "grid_mapping": "swiss_lv95_coordinates",
                "resolution": "1km",
            },
        ),
        "swiss_lv95_coordinates": xr.DataArray(
            np.int32(0), attrs=_LV95_GRID_MAPPING_ATTRS,
        ),
        "time_bnds": xr.DataArray(
            t_bnds, dims=["time", "bnds"],
            attrs={"standard_name": "time_bounds", "long_name": "time bounds",
                   "units": t_units, "calendar": "standard"},
        ),
    }

    if embed_latlon:
        data_vars["lat"] = xr.DataArray(
            lat.astype("float32"), dims=["y", "x"],
            attrs={"standard_name": "latitude", "long_name": "latitude",
                   "units": "degrees_north"},
        )
        data_vars["lon"] = xr.DataArray(
            lon.astype("float32"), dims=["y", "x"],
            attrs={"standard_name": "longitude", "long_name": "longitude",
                   "units": "degrees_east"},
        )

    ds = xr.Dataset(
        data_vars,
        coords={
            "time": xr.DataArray(
                t_vals, dims=["time"],
                attrs={"standard_name": "time",
                       "long_name": "seconds since analysis or reference time",
                       "units": t_units, "calendar": "standard", "axis": "T",
                       "bounds": "time_bnds"},
            ),
            "x": xr.DataArray(
                x_lv95, dims=["x"],
                attrs={"standard_name": "projection_x_coordinate",
                       "long_name": "x-coordinate in Swiss coordinates system lv95, Swiss easting",
                       "units": "m", "axis": "X"},
            ),
            "y": xr.DataArray(
                y_lv95, dims=["y"],
                attrs={"standard_name": "projection_y_coordinate",
                       "long_name": "y-coordinate in Swiss coordinates system lv95, Swiss northing",
                       "units": "m", "axis": "Y"},
            ),
            "radius": xr.DataArray(
                radii, dims=["radius"],
                attrs={"long_name": "accumulation radius", "units": "km"},
            ),
        },
        attrs=_global_attrs("inca", day),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"lightning_inca_{day.strftime('%Y%m%d')}.nc"
    encoding = {
        "lightning_count": {"zlib": True, "complevel": 4, "dtype": "float32",
                             "_FillValue": float("nan")},
        "x": {"dtype": "float32"},
        "y": {"dtype": "float32"},
        "time": {"dtype": "float32"},
        "time_bnds": {"dtype": "float32"},
        "radius": {"dtype": "float32"},
    }
    if embed_latlon:
        encoding["lat"] = {"dtype": "float32"}
        encoding["lon"] = {"dtype": "float32"}
    ds.to_netcdf(out, encoding=encoding, unlimited_dims=["time"])
    return out


def _granularity_str(granularity: timedelta) -> str:
    minutes = int(granularity.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes}min"
    return f"{minutes // 60}h"
