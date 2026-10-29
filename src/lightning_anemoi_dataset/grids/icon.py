"""ICON-CH1 native unstructured grid binning."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial import cKDTree


def _km_to_chord(radius_km: float) -> float:
    """Convert a great-circle radius in km to unit-sphere chord length."""
    return 2.0 * np.sin(np.radians(radius_km / 111.195))


class IconGrid:
    """Bin lightning strikes onto the ICON-CH1 R19B08 native grid.

    Parameters
    ----------
    grid_file:
        Path to the ICON grid NetCDF (e.g. icon_grid_0001_R19B08_mch.nc).
    """

    def __init__(self, grid_file: str | Path):
        ds = xr.open_dataset(grid_file, engine="netcdf4")
        self.clat = np.degrees(ds["clat"].values)   # (ncells,)
        self.clon = np.degrees(ds["clon"].values)   # (ncells,)
        self.ncells = len(self.clat)

        lat_r = np.radians(self.clat)
        lon_r = np.radians(self.clon)
        xyz = np.column_stack([
            np.cos(lat_r) * np.cos(lon_r),
            np.cos(lat_r) * np.sin(lon_r),
            np.sin(lat_r),
        ])
        self._tree = cKDTree(xyz)

    def bin(self, strikes: pd.DataFrame, radii_km: list[float]) -> np.ndarray:
        """Count strikes per cell for each radius.

        The KD-tree is queried once (using the maximum radius) and results are
        thresholded per radius — one pass over the data regardless of how many
        radii are requested.

        Parameters
        ----------
        strikes:
            DataFrame with columns ``lon`` and ``lat`` (WGS84 degrees).
        radii_km:
            List of 1–3 search radii in km. ``0`` means nearest-neighbour only
            (no distance cutoff).

        Returns
        -------
        int32 array of shape ``(n_radii, ncells)``.
        """
        n_radii = len(radii_km)
        counts = np.zeros((n_radii, self.ncells), dtype=np.int32)

        if strikes.empty:
            return counts

        lat_r = np.radians(strikes["lat"].values)
        lon_r = np.radians(strikes["lon"].values)
        xyz = np.column_stack([
            np.cos(lat_r) * np.cos(lon_r),
            np.cos(lat_r) * np.sin(lon_r),
            np.sin(lat_r),
        ])

        max_radius = max(radii_km)
        if max_radius > 0:
            chord_max = _km_to_chord(max_radius)
            dists, indices = self._tree.query(xyz, k=1, workers=-1, distance_upper_bound=chord_max)
            valid = dists < np.inf   # points within max radius
        else:
            dists, indices = self._tree.query(xyz, k=1, workers=-1)
            valid = np.ones(len(dists), dtype=bool)

        chord_thresholds = [_km_to_chord(r) if r > 0 else np.inf for r in radii_km]

        for i, chord in enumerate(chord_thresholds):
            mask = valid & (dists <= chord)
            np.add.at(counts[i], indices[mask], 1)

        return counts
