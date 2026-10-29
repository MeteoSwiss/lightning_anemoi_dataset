"""Accumulate per-strike data into fixed time bins."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


def time_bins(day: datetime, granularity: timedelta) -> list[datetime]:
    """Return UTC bin-start timestamps for one calendar day."""
    midnight = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    n = int(timedelta(days=1) / granularity)
    return [midnight + i * granularity for i in range(n)]


def accumulate_icon(
    strikes: pd.DataFrame,
    day: datetime,
    granularity: timedelta,
    grid,           # IconGrid
    radii_km: list[float],
) -> np.ndarray:
    """Bin strikes into ``(n_times, n_radii, ncells)`` count array.

    Parameters
    ----------
    strikes:
        Full-day DataFrame from :func:`~lightning_anemoi_dataset.extract.read_thx_day`.
    day:
        UTC date (time component ignored).
    granularity:
        Time step width.
    grid:
        :class:`~lightning_anemoi_dataset.grids.icon.IconGrid` instance.
    radii_km:
        List of 1–3 accumulation radii in km.

    Returns
    -------
    int16 array shape ``(n_times, n_radii, ncells)``.
    """
    bins = time_bins(day, granularity)
    n_radii = len(radii_km)
    result = np.zeros((len(bins), n_radii, grid.ncells), dtype=np.int16)

    for i, t in enumerate(bins):
        t_end = t + granularity
        window = strikes[(strikes.index >= t) & (strikes.index < t_end)]
        result[i] = grid.bin(window, radii_km)

    return result


def accumulate_inca(
    strikes: pd.DataFrame,
    day: datetime,
    granularity: timedelta,
    grid,           # IncaGrid
    radii_km: list[float],
) -> np.ndarray:
    """Bin strikes into ``(n_times, n_radii, NY, NX)`` count array.

    Returns
    -------
    int16 array shape ``(n_times, n_radii, NY, NX)``.
    """
    bins = time_bins(day, granularity)
    ny, nx = grid.NY, grid.NX
    n_radii = len(radii_km)
    result = np.zeros((len(bins), n_radii, ny, nx), dtype=np.int16)

    for i, t in enumerate(bins):
        t_end = t + granularity
        window = strikes[(strikes.index >= t) & (strikes.index < t_end)]
        result[i] = grid.bin(window, radii_km)

    return result
