"""ICON-CH1 native unstructured grid binning."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial import cKDTree


class IconGrid:
    """Bin lightning strikes onto the ICON-CH1 R19B08 native grid.

    Parameters
    ----------
    grid_file:
        Path to the ICON grid NetCDF (e.g. icon_grid_0001_R19B08_mch.nc).
    radius_km:
        Maximum search radius in km. Strikes farther than this from any
        cell centre are discarded. 0 = no radius cutoff.
    """

    def __init__(self, grid_file: str | Path, radius_km: float = 0.0):
        ds = xr.open_dataset(grid_file, engine="netcdf4")
        self.clat = np.degrees(ds["clat"].values)   # (ncells,)
        self.clon = np.degrees(ds["clon"].values)   # (ncells,)
        self.ncells = len(self.clat)
        self._radius_km = radius_km

        lat_r = np.radians(self.clat)
        lon_r = np.radians(self.clon)
        xyz = np.column_stack([
            np.cos(lat_r) * np.cos(lon_r),
            np.cos(lat_r) * np.sin(lon_r),
            np.sin(lat_r),
        ])
        self._tree = cKDTree(xyz)
        # chord length for radius cutoff
        self._chord_max = (2 * np.sin(np.radians(radius_km / 111.195))) if radius_km > 0 else None

    def bin(self, strikes: pd.DataFrame) -> np.ndarray:
        """Count strikes per cell.

        Parameters
        ----------
        strikes:
            DataFrame with columns ``lon`` and ``lat`` (WGS84 degrees).

        Returns
        -------
        int32 array of shape ``(ncells,)`` with counts; -1 for no-data cells
        when ``strikes`` is empty.
        """
        counts = np.zeros(self.ncells, dtype=np.int32)
        if strikes.empty:
            return counts

        lat_r = np.radians(strikes["lat"].values)
        lon_r = np.radians(strikes["lon"].values)
        xyz = np.column_stack([
            np.cos(lat_r) * np.cos(lon_r),
            np.cos(lat_r) * np.sin(lon_r),
            np.sin(lat_r),
        ])

        if self._chord_max is not None:
            dists, indices = self._tree.query(xyz, k=1, workers=-1)
            mask = dists <= self._chord_max
            indices = indices[mask]
        else:
            _, indices = self._tree.query(xyz, k=1, workers=-1)

        np.add.at(counts, indices, 1)
        return counts
