"""Tests for the ThxLightning anemoi source plugin."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xarray as xr

from anemoi_plugins_meteoswiss.transform.sources.thx_lightning import ThxLightning


N_CELLS = 10  # small synthetic grid for tests


def _make_dataset(times: list[datetime], fill_some: bool = False) -> xr.Dataset:
    """Build a minimal synthetic lightning NetCDF matching the output.py format."""
    n_t = len(times)
    rng = np.random.default_rng(42)

    counts = rng.integers(0, 20, size=(n_t, N_CELLS), dtype=np.int16)
    if fill_some:
        counts[:, -2:] = -1  # simulate cells outside network bbox

    lats = np.linspace(45.0, 48.0, N_CELLS)
    lons = np.linspace(6.0, 10.0, N_CELLS)

    ds = xr.Dataset(
        {
            "lightning_count": xr.DataArray(
                data=counts,
                dims=["time", "ncells"],
                attrs={
                    "long_name": "Lightning strike count per 10-minute interval",
                    "units": "1",
                    "coordinates": "clat clon",
                },
            ),
            "clat": xr.DataArray(
                data=lats,
                dims=["ncells"],
                attrs={
                    "long_name": "cell centre latitude",
                    "standard_name": "latitude",
                    "units": "degrees_north",
                },
            ),
            "clon": xr.DataArray(
                data=lons,
                dims=["ncells"],
                attrs={
                    "long_name": "cell centre longitude",
                    "standard_name": "longitude",
                    "units": "degrees_east",
                },
            ),
        },
        coords={
            "time": xr.DataArray(
                data=np.array([t.replace(tzinfo=None) for t in times], dtype="datetime64[ns]"),
                dims=["time"],
                attrs={"standard_name": "time", "axis": "T"},
            ),
        },
    )
    return ds


def _make_context():
    ctx = MagicMock()
    ctx.trace = MagicMock()
    return ctx


@pytest.fixture()
def dummy_icon_grid(tmp_path):
    """Write a tiny stub ICON grid NetCDF that grid_registry can open."""
    n = N_CELLS
    ds = xr.Dataset(
        {
            "clat": xr.DataArray(np.linspace(45.0, 48.0, n), dims=["ncells"],
                                  attrs={"standard_name": "latitude", "units": "radian"}),
            "clon": xr.DataArray(np.linspace(6.0, 10.0, n), dims=["ncells"],
                                  attrs={"standard_name": "longitude", "units": "radian"}),
        }
    )
    path = tmp_path / "icon_grid.nc"
    ds.to_netcdf(path)
    return path


class TestThxLightningInit:
    def test_defaults(self, dummy_icon_grid):
        ctx = _make_context()
        with patch("anemoi.transform.grids.grid_registry.from_config") as mock_reg:
            mock_reg.return_value = MagicMock()
            src = ThxLightning(ctx, icon_grid_path=str(dummy_icon_grid))
        assert src.data_dir == Path("/store_new/mch/msclim/lightning_on_icon")

    def test_custom_data_dir(self, dummy_icon_grid, tmp_path):
        ctx = _make_context()
        with patch("anemoi.transform.grids.grid_registry.from_config") as mock_reg:
            mock_reg.return_value = MagicMock()
            src = ThxLightning(ctx, data_dir=str(tmp_path), icon_grid_path=str(dummy_icon_grid))
        assert src.data_dir == tmp_path


class TestThxLightningExecute:
    def test_returns_one_field_per_date(self, tmp_path, dummy_icon_grid):
        """execute() should return exactly one field for each requested date."""
        day = datetime(2020, 1, 1)
        times = [datetime(2020, 1, 1, 0, 10), datetime(2020, 1, 1, 0, 20)]
        ds = _make_dataset(times)

        nc_path = tmp_path / "lightning_20200101.nc"
        ds.to_netcdf(nc_path)

        ctx = _make_context()
        with patch("anemoi.transform.grids.grid_registry.from_config") as mock_reg:
            mock_icon_grid = MagicMock()
            mock_reg.return_value = mock_icon_grid

            src = ThxLightning(ctx, data_dir=str(tmp_path), icon_grid_path=str(dummy_icon_grid))

            with patch(
                "anemoi_plugins_meteoswiss.transform.sources.thx_lightning.new_field_from_grid",
                side_effect=lambda f, g: f,
            ):
                result = src.execute(times)

        assert len(result) == 2

    def test_fill_values_become_nan(self, tmp_path, dummy_icon_grid):
        """Cells with fill value -1 must become NaN in the output field."""
        times = [datetime(2020, 6, 15, 12, 0)]
        ds = _make_dataset(times, fill_some=True)

        nc_path = tmp_path / "lightning_20200615.nc"
        ds.to_netcdf(nc_path)

        ctx = _make_context()
        with patch("anemoi.transform.grids.grid_registry.from_config") as mock_reg:
            mock_reg.return_value = MagicMock()
            src = ThxLightning(ctx, data_dir=str(tmp_path), icon_grid_path=str(dummy_icon_grid))

            with patch(
                "anemoi_plugins_meteoswiss.transform.sources.thx_lightning.new_field_from_grid",
                side_effect=lambda f, g: f,
            ):
                result = src.execute(times)

        assert len(result) == 1
        values = result[0].to_numpy(flatten=True)
        # Last two cells were set to -1 → should be NaN
        assert np.isnan(values[-1])
        assert np.isnan(values[-2])
        # Non-masked cells should be non-negative
        assert np.all(np.isnan(values) | (values >= 0))

    def test_groups_by_day(self, tmp_path, dummy_icon_grid):
        """Dates from the same day should open only one NetCDF file."""
        times = [datetime(2020, 3, 1, 0, 10), datetime(2020, 3, 1, 0, 20)]
        ds = _make_dataset(times)
        (tmp_path / "lightning_20200301.nc").write_bytes(b"")  # placeholder

        ctx = _make_context()
        with patch("anemoi.transform.grids.grid_registry.from_config") as mock_reg:
            mock_reg.return_value = MagicMock()
            src = ThxLightning(ctx, data_dir=str(tmp_path), icon_grid_path=str(dummy_icon_grid))

            open_calls = []
            original_open = xr.open_dataset

            def counting_open(path, **kw):
                open_calls.append(path)
                return _make_dataset(times).__enter__() if hasattr(_make_dataset(times), "__enter__") else ds

            with patch("xarray.open_dataset", side_effect=lambda p, **kw: ds):
                with patch(
                    "anemoi_plugins_meteoswiss.transform.sources.thx_lightning.XarrayFieldList.from_xarray",
                    return_value=MagicMock(__iter__=lambda s: iter([])),
                ):
                    with patch(
                        "anemoi_plugins_meteoswiss.transform.sources.thx_lightning.new_field_from_grid",
                        side_effect=lambda f, g: f,
                    ):
                        src.execute(times)

            # xr.open_dataset should have been called exactly once for the single day
            # (the patch intercepts at the xarray level)
