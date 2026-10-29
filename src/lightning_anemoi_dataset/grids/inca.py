"""INCA/RADAR 710×640 grid binning (CH1903+/LV95, EPSG:2056)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

# INCA/RADAR domain constants — LV95 (EPSG:2056), 1 km spacing
# LV95 easting  = LV03 easting  + 2,000,000
# LV95 northing = LV03 northing + 1,000,000
_NX = 710
_NY = 640
_X0 = 2_255_500.0   # easting of first column centre [m, LV95]
_Y0 =   840_500.0   # northing of first row centre  [m, LV95]
_DX = 1_000.0
_DY = 1_000.0

_WGS84_TO_LV95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
_LV95_TO_WGS84 = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)


def _build_inca_latlon() -> tuple[np.ndarray, np.ndarray]:
    """Return 2D WGS84 lat/lon arrays for the INCA/RADAR grid, shape (NY, NX)."""
    xs = _X0 + np.arange(_NX) * _DX      # easting  for each column
    ys = _Y0 + np.arange(_NY) * _DY      # northing for each row
    xx, yy = np.meshgrid(xs, ys)          # (NY, NX)
    lon, lat = _LV95_TO_WGS84.transform(xx, yy)
    return lat, lon


class IncaGrid:
    """Bin lightning strikes onto the INCA/RADAR 710×640 regular grid.

    The grid uses the Swiss CH1903+/LV95 (EPSG:2056) projection.
    Strikes are provided in WGS84, converted internally to LV95 before binning.
    """

    NX = _NX
    NY = _NY

    def __init__(self, inca_grid_file: str | Path | None = None):
        self.lat, self.lon = _build_inca_latlon()   # (NY, NX)

        xs = _X0 + np.arange(_NX) * _DX
        ys = _Y0 + np.arange(_NY) * _DY
        xx, yy = np.meshgrid(xs, ys)                # (NY, NX)
        xy = np.column_stack([xx.ravel(), yy.ravel()])
        self._tree = cKDTree(xy)

    def bin(self, strikes: pd.DataFrame, radii_km: list[float]) -> np.ndarray:
        """Count strikes per grid cell for each radius.

        The KD-tree is queried once (using the maximum radius) and results are
        thresholded per radius.

        Parameters
        ----------
        strikes:
            DataFrame with columns ``lon`` and ``lat`` (WGS84 degrees).
        radii_km:
            List of 1–3 search radii in km. ``0`` means nearest-neighbour only.

        Returns
        -------
        int32 array of shape ``(n_radii, NY, NX)``.
        """
        n_radii = len(radii_km)
        counts = np.zeros((n_radii, _NY * _NX), dtype=np.int32)

        if strikes.empty:
            return counts.reshape(n_radii, _NY, _NX)

        sx, sy = _WGS84_TO_LV95.transform(strikes["lon"].values, strikes["lat"].values)
        xy = np.column_stack([sx, sy])

        max_radius = max(radii_km)
        max_radius_m = max_radius * 1_000.0

        if max_radius > 0:
            dists, indices = self._tree.query(xy, k=1, workers=-1,
                                              distance_upper_bound=max_radius_m)
            valid = dists < np.inf
        else:
            dists, indices = self._tree.query(xy, k=1, workers=-1)
            valid = np.ones(len(dists), dtype=bool)

        thresholds_m = [r * 1_000.0 if r > 0 else np.inf for r in radii_km]

        for i, thresh in enumerate(thresholds_m):
            mask = valid & (dists <= thresh)
            np.add.at(counts[i], indices[mask], 1)

        return counts.reshape(n_radii, _NY, _NX)
