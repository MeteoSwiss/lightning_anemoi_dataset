"""Write daily NetCDF output files for ICON or INCA/RADAR grids."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

from .accumulate import time_bins


def write_icon_day(
    counts: np.ndarray,
    day: datetime,
    granularity: timedelta,
    clat: np.ndarray,
    clon: np.ndarray,
    radii_km: list[float],
    output_dir: Path,
) -> Path:
    """Write ``lightning_YYYYMMDD.nc`` for ICON native grid.

    Parameters
    ----------
    counts:
        int16 array ``(n_times, n_radii, ncells)``.
    day:
        Calendar day (UTC).
    granularity:
        Time step width.
    clat, clon:
        Cell-centre latitudes / longitudes in degrees ``(ncells,)``.
    radii_km:
        Accumulation radii in km (stored as a coordinate).
    output_dir:
        Directory to write into (created if missing).
    """
    bins = time_bins(day, granularity)
    times = np.array([t.timestamp() for t in bins], dtype="float64")
    radii = np.array(radii_km, dtype="float32")
    ncells = counts.shape[2]

    ds = xr.Dataset(
        {
            "lightning_count": xr.DataArray(
                counts,
                dims=["time", "radius", "ncells"],
                attrs={
                    "long_name": "lightning strike count",
                    "units": "1",
                },
            ),
            "clat": xr.DataArray(
                clat, dims=["ncells"],
                attrs={"standard_name": "latitude", "units": "degrees_north"},
            ),
            "clon": xr.DataArray(
                clon, dims=["ncells"],
                attrs={"standard_name": "longitude", "units": "degrees_east"},
            ),
        },
        coords={
            "time": xr.DataArray(
                times, dims=["time"],
                attrs={"units": "seconds since 1970-01-01 00:00:00 UTC",
                       "calendar": "proleptic_gregorian",
                       "standard_name": "time"},
            ),
            "radius": xr.DataArray(
                radii, dims=["radius"],
                attrs={"long_name": "accumulation radius", "units": "km"},
            ),
            "ncells": np.arange(ncells, dtype=np.int32),
        },
        attrs={
            "Conventions": "CF-1.8",
            "grid_type": "icon",
            "date": day.strftime("%Y-%m-%d"),
        },
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"lightning_{day.strftime('%Y%m%d')}.nc"
    encoding = {
        "lightning_count": {"zlib": True, "complevel": 4, "dtype": "int16", "_FillValue": -1},
        "clat": {"zlib": True, "complevel": 1},
        "clon": {"zlib": True, "complevel": 1},
    }
    ds.to_netcdf(out, encoding=encoding)
    return out


def write_inca_day(
    counts: np.ndarray,
    day: datetime,
    granularity: timedelta,
    lat: np.ndarray,
    lon: np.ndarray,
    radii_km: list[float],
    output_dir: Path,
) -> Path:
    """Write ``lightning_YYYYMMDD.nc`` for INCA/RADAR 710×640 grid.

    Parameters
    ----------
    counts:
        int16 array ``(n_times, n_radii, NY, NX)``.
    day:
        Calendar day (UTC).
    granularity:
        Time step width.
    lat, lon:
        2-D WGS84 arrays ``(NY, NX)``.
    radii_km:
        Accumulation radii in km (stored as a coordinate).
    output_dir:
        Directory to write into (created if missing).
    """
    bins = time_bins(day, granularity)
    times = np.array([t.timestamp() for t in bins], dtype="float64")
    radii = np.array(radii_km, dtype="float32")
    ny, nx = counts.shape[2], counts.shape[3]

    ds = xr.Dataset(
        {
            "lightning_count": xr.DataArray(
                counts,
                dims=["time", "radius", "p_i", "p_j"],
                attrs={
                    "long_name": "lightning strike count",
                    "units": "1",
                },
            ),
            "lat": xr.DataArray(
                lat, dims=["p_i", "p_j"],
                attrs={"standard_name": "latitude", "units": "degrees_north"},
            ),
            "lon": xr.DataArray(
                lon, dims=["p_i", "p_j"],
                attrs={"standard_name": "longitude", "units": "degrees_east"},
            ),
        },
        coords={
            "time": xr.DataArray(
                times, dims=["time"],
                attrs={"units": "seconds since 1970-01-01 00:00:00 UTC",
                       "calendar": "proleptic_gregorian",
                       "standard_name": "time"},
            ),
            "radius": xr.DataArray(
                radii, dims=["radius"],
                attrs={"long_name": "accumulation radius", "units": "km"},
            ),
            "p_i": np.arange(ny, dtype=np.int32),
            "p_j": np.arange(nx, dtype=np.int32),
        },
        attrs={
            "Conventions": "CF-1.8",
            "grid_type": "inca",
            "crs": "EPSG:2056",
            "date": day.strftime("%Y-%m-%d"),
        },
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"lightning_{day.strftime('%Y%m%d')}.nc"
    encoding = {
        "lightning_count": {"zlib": True, "complevel": 4, "dtype": "int16", "_FillValue": -1},
        "lat": {"zlib": True, "complevel": 1},
        "lon": {"zlib": True, "complevel": 1},
    }
    ds.to_netcdf(out, encoding=encoding)
    return out
