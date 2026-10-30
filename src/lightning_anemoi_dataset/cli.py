"""Command-line interface: ``lightning-grid``."""

from __future__ import annotations

import argparse
import logging
from datetime import timedelta
from pathlib import Path

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lightning-grid",
        description="Grid THX lightning data onto ICON-CH1 or INCA/RADAR domains.",
    )
    p.add_argument("--config", required=True, help="YAML configuration file")
    p.add_argument(
        "--grid", choices=["icon", "inca"], default=None,
        help="Override grid_type from config",
    )
    p.add_argument(
        "--date", default=None,
        help="Process a single date (YYYYMMDD). Overrides start/stop in config.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    from .config import Config, _parse_dt

    cfg = Config.from_yaml(args.config)
    if args.grid is not None:
        cfg.grid_type = args.grid

    if args.date is not None:
        cfg.start = _parse_dt(args.date)
        cfg.stop = cfg.start + timedelta(days=1)

    log.info("Grid type  : %s", cfg.grid_type)
    log.info("Period     : %s – %s", cfg.start.date(), cfg.stop.date())
    log.info("Radii (km) : %s", cfg.radius_km)
    log.info("Output     : %s", cfg.output_dir)

    if cfg.grid_type == "icon":
        _run_icon(cfg)
    else:
        _run_inca(cfg)


def _run_icon(cfg) -> None:
    from .accumulate import accumulate_icon
    from .extract import read_thx_day
    from .grids.icon import IconGrid
    from .output import write_icon_day, write_icon_grid

    log.info("Loading ICON grid: %s", cfg.icon_grid_file)
    grid = IconGrid(cfg.icon_grid_file)

    if not cfg.embed_latlon:
        grid_file = Path(cfg.output_dir) / "icon_grid.nc"
        if not grid_file.exists():
            write_icon_grid(grid.clat, grid.clon, Path(cfg.output_dir))
            log.info("Wrote static grid: %s", grid_file.name)
        else:
            log.debug("Static grid already exists: %s", grid_file.name)

    day = cfg.start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < cfg.stop:
        out_file = Path(cfg.output_dir) / f"lightning_icon_{day.strftime('%Y%m%d')}.nc"
        if out_file.exists():
            log.debug("Skip (exists): %s", out_file.name)
            day += timedelta(days=1)
            continue

        strikes = read_thx_day(day, cfg.archive_path, cfg.discharge_type)
        counts = accumulate_icon(strikes, day, cfg.granularity, grid, cfg.radius_km)
        log.info("Processing %s  strikes=%d  count[min=%d max=%d]",
                 day.date(), len(strikes), int(counts.min()), int(counts.max()))
        write_icon_day(counts, day, cfg.granularity, grid.clat, grid.clon,
                       cfg.radius_km, Path(cfg.output_dir), embed_latlon=cfg.embed_latlon)
        day += timedelta(days=1)


def _run_inca(cfg) -> None:
    from .accumulate import accumulate_inca
    from .extract import read_thx_day
    from .grids.inca import IncaGrid
    from .output import write_inca_day, write_inca_grid

    log.info("Building INCA/RADAR grid (EPSG:2056)")
    grid = IncaGrid()

    if not cfg.embed_latlon:
        grid_file = Path(cfg.output_dir) / "inca_grid.nc"
        if not grid_file.exists():
            write_inca_grid(grid.lat, grid.lon, Path(cfg.output_dir))
            log.info("Wrote static grid: %s", grid_file.name)
        else:
            log.debug("Static grid already exists: %s", grid_file.name)

    day = cfg.start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < cfg.stop:
        out_file = Path(cfg.output_dir) / f"lightning_inca_{day.strftime('%Y%m%d')}.nc"
        if out_file.exists():
            log.debug("Skip (exists): %s", out_file.name)
            day += timedelta(days=1)
            continue

        strikes = read_thx_day(day, cfg.archive_path, cfg.discharge_type)
        counts = accumulate_inca(strikes, day, cfg.granularity, grid, cfg.radius_km)
        log.info("Processing %s  strikes=%d  count[min=%d max=%d]",
                 day.date(), len(strikes), int(counts.min()), int(counts.max()))
        write_inca_day(counts, day, cfg.granularity, grid.lat, grid.lon,
                       cfg.radius_km, Path(cfg.output_dir), embed_latlon=cfg.embed_latlon)
        day += timedelta(days=1)


if __name__ == "__main__":
    main()
