"""INCA/RADAR 710×640 grid binning (CH1903+/LV95, EPSG:2056)."""

from __future__ import annotations

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

    def __init__(self):
        self.lat, self.lon = _build_inca_latlon()   # (NY, NX)

        xs = _X0 + np.arange(_NX) * _DX
        ys = _Y0 + np.arange(_NY) * _DY
        xx, yy = np.meshgrid(xs, ys)                # (NY, NX)
        xy = np.column_stack([xx.ravel(), yy.ravel()])
        self._tree = cKDTree(xy)

    def bin(self, strikes: pd.DataFrame, radii_km: list[float]) -> np.ndarray:
        """Count strikes per grid cell for each radius.

        Each strike increments all cells within the given radius (neighbourhood
        count). ``query_ball_point`` is called once per radius.

        Only strikes that fall within the grid tessellation are counted. A strike
        is inside the tessellation when its LV95 coordinates lie within half a cell
        width of the nearest cell centre in both axes — the natural Voronoi boundary
        of the regular 1 km grid (half-diagonal ≈ 0.71 km). Strikes farther outside
        the domain are dropped; without this filter, boundary cells accumulate
        unshared contributions from outside-domain strikes and show inflated counts.

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

        # Drop strikes outside the grid tessellation (Voronoi cells of the regular grid).
        # The tessellation boundary extends half a cell beyond the outermost cell centres.
        in_domain = (
            (sx >= _X0 - _DX / 2) & (sx <= _X0 + (_NX - 0.5) * _DX) &
            (sy >= _Y0 - _DY / 2) & (sy <= _Y0 + (_NY - 0.5) * _DY)
        )
        if not np.any(in_domain):
            return counts.reshape(n_radii, _NY, _NX)
        xy = np.column_stack([sx[in_domain], sy[in_domain]])

        for i, r_km in enumerate(radii_km):
            if r_km == 0:
                # nearest-neighbour only: one cell per strike
                _, nearest = self._tree.query(xy, k=1, workers=-1)
                np.add.at(counts[i], nearest, 1)
            else:
                # neighbourhood count: all cells within r km get +1 per strike
                r_m = r_km * 1_000.0
                for cell_list in self._tree.query_ball_point(xy, r=r_m, workers=-1):
                    if cell_list:
                        np.add.at(counts[i], cell_list, 1)

        return counts.reshape(n_radii, _NY, _NX)
