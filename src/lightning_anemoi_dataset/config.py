from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import yaml

DEFAULT_ARCHIVE = "/store_new/mch/msclim/hamann/database/lightning/THX"
DEFAULT_ICON_GRID = "/store_new/mch/msclim/pronos/icon_grid_0001_R19B08_mch.nc"

_GRANULARITY_MAP = {
    "10min": 10, "60min": 60, "1h": 60, "24h": 1440, "1d": 1440,
}


@dataclass
class Config:
    start: datetime
    stop: datetime
    grid_type: Literal["icon", "inca"] = "icon"
    granularity: timedelta = field(default_factory=lambda: timedelta(minutes=10))
    discharge_type: list[str] = field(default_factory=lambda: ["CG", "IC"])
    # 1–3 radius values in km. All stored in a single NetCDF with a radius dimension.
    radius_km: list[float] = field(default_factory=lambda: [8.0])
    network_bbox: list[float] = field(default_factory=lambda: [42.5, 50.2, 0.0, 17.0])
    archive_path: str = DEFAULT_ARCHIVE
    icon_grid_file: str = DEFAULT_ICON_GRID
    output_dir: Path = field(default_factory=lambda: Path("."))

    def __post_init__(self):
        if not 1 <= len(self.radius_km) <= 3:
            raise ValueError(f"radius_km must have 1–3 values, got {len(self.radius_km)}")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        with open(path) as f:
            d = yaml.safe_load(f)
        return cls(
            start=_parse_dt(d["start"]),
            stop=_parse_dt(d["stop"], end_of_day=True),
            grid_type=d.get("grid_type", "icon"),
            granularity=_parse_granularity(d.get("granularity", "10min")),
            discharge_type=d.get("discharge_type", ["CG", "IC"]),
            radius_km=_parse_radii(d.get("radius_km", 8.0)),
            network_bbox=d.get("network_bbox", [42.5, 50.2, 0.0, 17.0]),
            archive_path=d.get("archive_path", DEFAULT_ARCHIVE),
            icon_grid_file=d.get("icon_grid_file", DEFAULT_ICON_GRID),
            output_dir=Path(d.get("output_dir", ".")),
        )

    @property
    def steps_per_day(self) -> int:
        return int(timedelta(days=1) / self.granularity)


def _parse_radii(val) -> list[float]:
    if isinstance(val, (int, float)):
        return [float(val)]
    radii = [float(r) for r in val]
    if not 1 <= len(radii) <= 3:
        raise ValueError(f"radius_km must have 1–3 values, got {len(radii)}")
    return radii


def _parse_granularity(val: str | int) -> timedelta:
    if isinstance(val, (int, float)):
        return timedelta(minutes=int(val))
    key = str(val).strip().lower()
    if key in _GRANULARITY_MAP:
        return timedelta(minutes=_GRANULARITY_MAP[key])
    raise ValueError(f"Unknown granularity {val!r}. Use: {', '.join(_GRANULARITY_MAP)}.")


_DATE_ONLY_RE = re.compile(r"^\d{8}$|^\d{4}-\d{2}-\d{2}$")


def _parse_dt(val: str | datetime, *, end_of_day: bool = False) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip()
    is_date_only = bool(_DATE_ONLY_RE.match(s))
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            result = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            if is_date_only and end_of_day:
                result += timedelta(days=1)
            return result
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {val!r}. Use YYYYMMDD or YYYY-MM-DD.")
