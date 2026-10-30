#!/usr/bin/env python3
"""Plot one day of lightning output — INCA/RADAR or ICON, one page per radius.

Each page has 24 panels (hourly sums of the 10-min data) with country borders.
Output: <stem>_r<radius>km_hourly.png  (one file per radius)

Usage
-----
  python scripts/plot_lightning.py lightning_inca_20250801.nc
  python scripts/plot_lightning.py lightning_icon_20250801.nc
  python scripts/plot_lightning.py lightning_inca_20250801.nc --vmax 20 --outdir /tmp/
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


# ---------------------------------------------------------------------------
# Borders: precompute once from Natural Earth, draw on every panel
# ---------------------------------------------------------------------------

def _load_border_lines() -> list[np.ndarray]:
    """Return list of (N, 2) coordinate arrays [lon, lat] for borders and coastlines."""
    import cartopy.feature as cfeature
    lines = []
    for feat in [
        cfeature.BORDERS.with_scale("50m"),
        cfeature.COASTLINE.with_scale("50m"),
    ]:
        for geom in feat.geometries():
            parts = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
            for g in parts:
                lines.append(np.array(g.coords))  # (N, 2): lon, lat
    return lines


def _draw_borders_latlon(ax, lines, color="0.4", lw=0.4):
    """Overlay borders on axes where x=lon, y=lat — one LineCollection."""
    from matplotlib.collections import LineCollection
    segs = [xy for xy in lines]  # each (N, 2): x=lon, y=lat
    ax.add_collection(LineCollection(segs, colors=color, linewidths=lw, zorder=2))


def _draw_borders_inca(ax, lines, to_pixel, nx, ny, color="0.4", lw=0.4):
    """Overlay borders projected into INCA pixel coordinates — one LineCollection."""
    from matplotlib.collections import LineCollection
    segs = []
    for xy in lines:
        px, py = to_pixel(xy[:, 0], xy[:, 1])
        segs.append(np.column_stack([px, py]))
    ax.add_collection(LineCollection(segs, colors=color, linewidths=lw, zorder=2))
    # Restore axes limits — segments outside domain would expand them
    ax.set_xlim(-0.5, nx - 0.5)
    ax.set_ylim(-0.5, ny - 0.5)


# ---------------------------------------------------------------------------
# INCA: regular 710×640 grid — imshow directly on pixel axes
# ---------------------------------------------------------------------------

def _inca_hourly(ds: xr.Dataset, radius: float) -> np.ndarray:
    arr = np.nan_to_num(
        ds["lightning_count"].sel(radius=radius).values, nan=0.0
    )  # (144, NY, NX)
    return arr.reshape(24, 6, *arr.shape[1:]).sum(axis=1)  # (24, NY, NX)


def _make_inca_pixel_transform(ds: xr.Dataset):
    """Return callable (lons, lats) → (pixel_x, pixel_y) for the INCA grid."""
    from pyproj import Transformer
    to_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
    x0 = float(ds.x.values[0])
    y0 = float(ds.y.values[0])
    dx = float(ds.x.values[1] - ds.x.values[0])
    dy = float(ds.y.values[1] - ds.y.values[0])

    def transform(lons, lats):
        ex, ey = to_lv95.transform(lons, lats)
        return (ex - x0) / dx, (ey - y0) / dy

    return transform


# ---------------------------------------------------------------------------
# ICON: project unstructured cells to a regular lat/lon image for display
# ---------------------------------------------------------------------------

class _IconProjector:
    RES = 0.01  # degrees (~1 km)

    def __init__(self, clat: np.ndarray, clon: np.ndarray):
        res = self.RES
        self._lat_edges = np.arange(clat.min() - res, clat.max() + res * 2, res)
        self._lon_edges = np.arange(clon.min() - res, clon.max() + res * 2, res)
        self._nl = len(self._lat_edges) - 1
        self._nc = len(self._lon_edges) - 1

        ilat = np.digitize(clat, self._lat_edges) - 1
        ilon = np.digitize(clon, self._lon_edges) - 1
        self._ok = (ilat >= 0) & (ilat < self._nl) & (ilon >= 0) & (ilon < self._nc)
        self._flat = (ilat * self._nc + ilon).astype(np.int32)

    def project(self, values: np.ndarray) -> np.ndarray:
        grid = np.zeros(self._nl * self._nc, dtype=np.float32)
        np.add.at(grid, self._flat[self._ok], values[self._ok])
        return grid.reshape(self._nl, self._nc)

    @property
    def extent(self):
        return [self._lon_edges[0], self._lon_edges[-1],
                self._lat_edges[0], self._lat_edges[-1]]


def _icon_hourly(ds: xr.Dataset, radius: float, proj: _IconProjector) -> np.ndarray:
    arr = np.nan_to_num(
        ds["lightning_count"].sel(radius=radius).values, nan=0.0
    )  # (144, ncells)
    hourly_cells = arr.reshape(24, 6, arr.shape[1]).sum(axis=1)  # (24, ncells)
    return np.stack([proj.project(hourly_cells[h]) for h in range(24)])


# ---------------------------------------------------------------------------
# Figure builder (shared)
# ---------------------------------------------------------------------------

def _make_figure(
    hourly: np.ndarray,
    radius: float,
    date_str: str,
    grid_label: str,
    vmax_arg: float | None,
    imshow_kwargs: dict,
    draw_borders_fn,
) -> tuple:
    nonzero = hourly[hourly > 0]
    vmax = (
        vmax_arg if vmax_arg is not None
        else (max(1.0, float(np.percentile(nonzero, 99))) if nonzero.size > 0 else 1.0)
    )

    # "total counts" = sum of all cell counts (a strike within radius of N cells
    # is counted N times, so this is not the number of unique strikes)
    total_counts = int(hourly.sum())

    cmap = plt.cm.hot_r.copy()
    cmap.set_under("white")

    fig, axes = plt.subplots(4, 6, figsize=(20, 14), constrained_layout=True)
    fig.suptitle(
        f"THX lightning ({grid_label}) — {date_str}   "
        f"radius={radius:.0f} km   total counts={total_counts}",
        fontsize=14, fontweight="bold",
    )

    im = None
    for h, ax in enumerate(axes.flat):
        im = ax.imshow(hourly[h], vmin=1e-9, vmax=vmax, cmap=cmap, **imshow_kwargs)
        draw_borders_fn(ax)
        ax.set_title(f"{h:02d}–{h+1:02d} UTC", fontsize=9, pad=2)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(
            0.98, 0.02, f"Σ={int(hourly[h].sum())}",
            transform=ax.transAxes, fontsize=7,
            ha="right", va="bottom", color="steelblue",
        )

    cbar = fig.colorbar(im, ax=axes, shrink=0.55, pad=0.01, aspect=25, extend="max")
    cbar.set_label("cell counts per hour", fontsize=10)

    return fig, vmax


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="24-panel hourly lightning plot (INCA or ICON), one page per radius"
    )
    p.add_argument("ncfile", help="Path to lightning_{inca,icon}_YYYYMMDD.nc")
    p.add_argument(
        "--vmax", type=float, default=None,
        help="Shared colour-scale ceiling for all radii (default: per-radius 99th percentile)",
    )
    p.add_argument(
        "--outdir", default=None,
        help="Output directory for PNGs (default: same directory as input file)",
    )
    args = p.parse_args()

    ncfile = Path(args.ncfile)
    if not ncfile.exists():
        print(f"File not found: {ncfile}", file=sys.stderr)
        sys.exit(1)

    outdir = Path(args.outdir) if args.outdir else ncfile.parent
    outdir.mkdir(parents=True, exist_ok=True)

    ds = xr.open_dataset(ncfile)
    radii = ds.radius.values.tolist()
    date_str = ds.attrs.get("date", "")

    n_times = ds["lightning_count"].sizes["time"]
    if n_times % 6 != 0 or n_times // 6 != 24:
        print(f"Expected 144 time steps (24 h × 6 × 10 min), got {n_times}", file=sys.stderr)
        sys.exit(1)

    print("Loading border data …")
    border_lines = _load_border_lines()

    is_icon = "ncells" in ds["lightning_count"].dims

    if is_icon:
        grid_label = "ICON"
        print("Projecting ICON grid to lat/lon image …")
        proj = _IconProjector(ds["clat"].values, ds["clon"].values)
        imshow_kwargs = dict(origin="lower", extent=proj.extent,
                             aspect="auto", interpolation="nearest")

        def draw_borders_fn(ax):
            _draw_borders_latlon(ax, border_lines)
    else:
        grid_label = "INCA/RADAR"
        to_pixel = _make_inca_pixel_transform(ds)
        nx = ds["lightning_count"].sizes["x"]
        ny = ds["lightning_count"].sizes["y"]
        imshow_kwargs = dict(origin="lower", aspect="equal", interpolation="nearest")

        def draw_borders_fn(ax):
            _draw_borders_inca(ax, border_lines, to_pixel, nx, ny)

    for radius in radii:
        hourly = _icon_hourly(ds, radius, proj) if is_icon else _inca_hourly(ds, radius)

        fig, vmax_used = _make_figure(
            hourly, radius, date_str, grid_label,
            args.vmax, imshow_kwargs, draw_borders_fn,
        )

        out = outdir / f"{ncfile.stem}_r{int(radius):02d}km_hourly.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved: {out}  (vmax={vmax_used:.1f})")

    # cartopy/shapely has a known double-free on interpreter shutdown;
    # flush stdout then skip cleanup since all files are already written and closed.
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
