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

        # Tessellation radius: half the max nearest-neighbour chord distance among
        # a strided sample of cell centres. Strikes farther than this from their
        # nearest cell are outside the domain's Voronoi tessellation and are dropped
        # in bin() to prevent boundary cells from accumulating unshared counts.
        stride = max(1, self.ncells // 100_000)
        sample = xyz[::stride]
        nn_dists, _ = self._tree.query(sample, k=2, workers=-1)
        # nn_dists[:, 0] == 0 (each sample point is in the tree); [:, 1] = true NN
        self._domain_chord = float(np.max(nn_dists[:, 1])) / 2

    def bin(self, strikes: pd.DataFrame, radii_km: list[float]) -> np.ndarray:
        """Count strikes per cell for each radius.

        Each strike increments all cells within the given radius (neighbourhood
        count). ``query_ball_point`` is called once per radius.

        Only strikes that fall within the grid tessellation are counted. A strike
        is inside when its nearest cell centre is within ``_domain_chord`` (half
        the maximum inter-cell nearest-neighbour distance, estimated at construction
        time). Strikes farther outside the domain are dropped; without this filter,
        boundary cells accumulate unshared contributions from outside-domain strikes
        and show inflated counts.

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

        # Drop strikes outside the grid tessellation.
        nn_dist, _ = self._tree.query(xyz, k=1, workers=-1)
        in_domain = nn_dist <= self._domain_chord
        if not np.any(in_domain):
            return counts
        xyz = xyz[in_domain]

        for i, r_km in enumerate(radii_km):
            if r_km == 0:
                # nearest-neighbour only: one cell per strike
                _, nearest = self._tree.query(xyz, k=1, workers=-1)
                np.add.at(counts[i], nearest, 1)
            else:
                # neighbourhood count: all cells within r km get +1 per strike
                chord = _km_to_chord(r_km)
                for cell_list in self._tree.query_ball_point(xyz, r=chord, workers=-1):
                    if cell_list:
                        np.add.at(counts[i], cell_list, 1)

        return counts
