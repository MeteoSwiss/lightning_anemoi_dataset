"""Read raw THX lightning archive files (.prd / .prd.zip)."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Pipe-separated columns in the THX .prd format
_COLUMNS = ["datetime", "lon", "lat", "current", "nS", "mode", "intra",
            "Ax", "Ki2", "Exc", "Incl", "Arc", "d1", "d2", "d3", "d4", "d5"]
# Some rows omit the trailing " UTC" and use variable-width fractional seconds;
# use format='mixed' with dayfirst=True to handle all variants robustly.


def read_thx_day(
    day: datetime,
    archive_path: str | Path,
    discharge_type: list[str],
) -> pd.DataFrame:
    """Return a DataFrame of lightning strikes for one calendar day.

    Parameters
    ----------
    day:
        UTC date (time component is ignored).
    archive_path:
        Root of the THX archive tree.
    discharge_type:
        Any combination of ``["CG", "IC"]``.
        CG = cloud-to-ground (intra==0), IC = intra-cloud (intra==1).

    Returns
    -------
    DataFrame with columns [lon, lat, current, intra] indexed by UTC datetime.
    Returns an empty DataFrame when the file is missing.
    """
    # Filename format: THX{YY}{JJJ}0000.prd[.zip]  (flat directory, no subdirs)
    stem = f"THX{day.strftime('%y%j')}0000"
    base = Path(archive_path)
    prd = base / f"{stem}.prd"
    prd_zip = base / f"{stem}.prd.zip"

    raw: str | None = None
    if prd.exists():
        raw = prd.read_text(errors="replace")
    elif prd_zip.exists():
        with zipfile.ZipFile(prd_zip) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".prd"))
            raw = zf.read(name).decode(errors="replace")

    if raw is None:
        return pd.DataFrame(columns=["lon", "lat", "current", "intra"])

    df = pd.read_csv(
        io.StringIO(raw),
        sep="|",
        header=None,
        names=_COLUMNS,
        parse_dates=False,
    )

    df["datetime"] = pd.to_datetime(
        df["datetime"].str.strip().str.replace(r"\s*UTC$", "", regex=True),
        format="mixed",
        dayfirst=True,
        utc=True,
    )
    df = df.set_index("datetime")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["current"] = pd.to_numeric(df["current"], errors="coerce")
    df["intra"] = pd.to_numeric(df["intra"], errors="coerce").astype(int)
    df = df[["lon", "lat", "current", "intra"]].dropna()

    # Filter by discharge type
    keep = pd.Series(False, index=df.index)
    if "CG" in discharge_type:
        keep |= df["intra"] == 0
    if "IC" in discharge_type:
        keep |= df["intra"] == 1
    return df[keep]
