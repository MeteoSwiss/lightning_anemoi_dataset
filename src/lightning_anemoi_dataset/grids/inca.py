"""INCA 710×640 grid binning (CH1903+/LV95, EPSG:2056)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

# INCA domain constants — LV95 (EPSG:2056), 1 km spacing
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
    """Return 2D WGS84 lat/lon arrays for the INCA grid, shape (NY, NX)."""
    xs = _X0 + np.arange(_NX) * _DX      # easting  for each column
    ys = _Y0 + np.arange(_NY) * _DY      # northing for each row
    xx, yy = np.meshgrid(xs, ys)          # (NY, NX)
    lon, lat = _LV95_TO_WGS84.transform(xx, yy)
    return lat, lon


class IncaGrid:
    """Bin lightning strikes onto the INCA 710×640 regular grid.

    The grid uses the Swiss CH1903+/LV95 (EPSG:2056) projection.
    Strikes are provided in WGS84, converted internally to LV95 before binning.

    Parameters
    ----------
    radius_km:
        Maximum search radius in km. Strikes farther than this from any
        cell centre are discarded. 0 = no radius cutoff.
    inca_grid_file:
        Optional path to an INCA NetCDF to derive/verify grid coordinates.
        If None, the standard 710×640 domain constants are used.
    """

    NX = _NX
    NY = _NY

    def __init__(self, radius_km: float = 0.0, inca_grid_file: str | Path | None = None):
        self._radius_km = radius_km
        self.lat, self.lon = _build_inca_latlon()   # (NY, NX)

        # Build flat KD-tree in LV95 metre space for fast nearest-neighbour
        xs = _X0 + np.arange(_NX) * _DX
        ys = _Y0 + np.arange(_NY) * _DY
        xx, yy = np.meshgrid(xs, ys)                # (NY, NX)
        xy = np.column_stack([xx.ravel(), yy.ravel()])
        self._tree = cKDTree(xy)
        self._radius_m = radius_km * 1_000.0 if radius_km > 0 else None

    def bin(self, strikes: pd.DataFrame) -> np.ndarray:
        """Count strikes per grid cell.

        Parameters
        ----------
        strikes:
            DataFrame with columns ``lon`` and ``lat`` (WGS84 degrees).

        Returns
        -------
        int32 array of shape ``(NY, NX)`` with counts.
        """
        counts = np.zeros(_NY * _NX, dtype=np.int32)
        if strikes.empty:
            return counts.reshape(_NY, _NX)

        sx, sy = _WGS84_TO_LV95.transform(strikes["lon"].values, strikes["lat"].values)
        xy = np.column_stack([sx, sy])

        if self._radius_m is not None:
            dists, indices = self._tree.query(xy, k=1, workers=-1)
            mask = dists <= self._radius_m
            indices = indices[mask]
        else:
            _, indices = self._tree.query(xy, k=1, workers=-1)

        np.add.at(counts, indices, 1)
        return counts.reshape(_NY, _NX)
