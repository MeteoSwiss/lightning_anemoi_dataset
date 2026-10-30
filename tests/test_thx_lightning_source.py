"""Tests for the ThxLightning anemoi source plugin."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xarray as xr

from anemoi_plugins_meteoswiss.transform.sources.thx_lightning import ThxLightning


N_CELLS = 10  # small synthetic grid for tests
RADIUS_KM = 8.0


def _make_dataset(times: list[datetime], fill_some: bool = False) -> xr.Dataset:
    """Build a minimal synthetic lightning NetCDF matching the output.py ICON format.

    Dims: (time, radius, ncells) with a single radius=8 km.
    """
    n_t = len(times)
    rng = np.random.default_rng(42)

    counts = rng.integers(0, 20, size=(n_t, 1, N_CELLS), dtype=np.int16).astype(np.float32)
    if fill_some:
        counts[:, :, -2:] = np.nan  # simulate cells outside network bbox

    lats = np.linspace(45.0, 48.0, N_CELLS)
    lons = np.linspace(6.0, 10.0, N_CELLS)

    return xr.Dataset(
        {
            "lightning_count": xr.DataArray(
                data=counts,
                dims=["time", "radius", "ncells"],
                attrs={
                    "long_name": "lightning strike count per grid cell",
                    "units": "1",
                    "resolution": "1km",
                },
            ),
            "clat": xr.DataArray(
                data=lats, dims=["ncells"],
                attrs={"standard_name": "latitude", "units": "degrees_north"},
            ),
            "clon": xr.DataArray(
                data=lons, dims=["ncells"],
                attrs={"standard_name": "longitude", "units": "degrees_east"},
            ),
        },
        coords={
            "time": xr.DataArray(
                data=np.array([t.replace(tzinfo=None) for t in times], dtype="datetime64[ns]"),
                dims=["time"],
                attrs={"standard_name": "time", "axis": "T"},
            ),
            "radius": xr.DataArray(
                data=np.array([RADIUS_KM], dtype="float32"),
                dims=["radius"],
                attrs={"long_name": "accumulation radius", "units": "km"},
            ),
        },
    )


def _make_context():
    ctx = MagicMock()
    ctx.trace = MagicMock()
    return ctx


def _make_source(tmp_path, dummy_icon_grid, **kwargs):
    """Construct ThxLightning with sensible defaults for icon tests."""
    defaults = dict(
        data_dir=str(tmp_path),
        grid_type="icon",
        radius_km=RADIUS_KM,
        icon_grid_path=str(dummy_icon_grid),
    )
    defaults.update(kwargs)
    ctx = _make_context()
    with patch("anemoi.transform.grids.grid_registry.from_config") as mock_reg:
        mock_reg.return_value = MagicMock()
        src = ThxLightning(ctx, **defaults)
    return src


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
    def test_stores_data_dir(self, tmp_path, dummy_icon_grid):
        src = _make_source(tmp_path, dummy_icon_grid)
        assert src.data_dir == tmp_path

    def test_stores_grid_type(self, tmp_path, dummy_icon_grid):
        src = _make_source(tmp_path, dummy_icon_grid, grid_type="icon")
        assert src.grid_type == "icon"

    def test_stores_radius_km(self, tmp_path, dummy_icon_grid):
        src = _make_source(tmp_path, dummy_icon_grid, radius_km=16.0)
        assert src.radius_km == 16.0

    def test_invalid_grid_type(self, tmp_path, dummy_icon_grid):
        with pytest.raises(ValueError, match="grid_type"):
            _make_source(tmp_path, dummy_icon_grid, grid_type="bad")


class TestThxLightningExecute:
    def test_returns_one_field_per_date(self, tmp_path, dummy_icon_grid):
        """execute() should return exactly one field for each requested date."""
        times = [datetime(2020, 1, 1, 0, 10), datetime(2020, 1, 1, 0, 20)]
        ds = _make_dataset(times)

        nc_path = tmp_path / "lightning_icon_20200101.nc"
        ds.to_netcdf(nc_path)

        src = _make_source(tmp_path, dummy_icon_grid)
        with patch(
            "anemoi_plugins_meteoswiss.transform.sources.thx_lightning.new_field_from_grid",
            side_effect=lambda f, g: f,
        ):
            result = src.execute(times)

        assert len(result) == 2

    def test_fill_values_become_nan(self, tmp_path, dummy_icon_grid):
        """Cells with NaN fill must stay NaN in the output field."""
        times = [datetime(2020, 6, 15, 12, 0)]
        ds = _make_dataset(times, fill_some=True)

        nc_path = tmp_path / "lightning_icon_20200615.nc"
        ds.to_netcdf(nc_path)

        src = _make_source(tmp_path, dummy_icon_grid)
        with patch(
            "anemoi_plugins_meteoswiss.transform.sources.thx_lightning.new_field_from_grid",
            side_effect=lambda f, g: f,
        ):
            result = src.execute(times)

        assert len(result) == 1
        values = result[0].to_numpy(flatten=True)
        assert np.isnan(values[-1])
        assert np.isnan(values[-2])
        assert np.all(np.isnan(values) | (values >= 0))

    def test_groups_by_day(self, tmp_path, dummy_icon_grid):
        """Dates from the same day should open only one NetCDF file."""
        times = [datetime(2020, 3, 1, 0, 10), datetime(2020, 3, 1, 0, 20)]
        ds = _make_dataset(times)

        nc_path = tmp_path / "lightning_icon_20200301.nc"
        ds.to_netcdf(nc_path)

        open_calls = []
        real_open = xr.open_dataset

        def counting_open(path, **kw):
            open_calls.append(path)
            return real_open(path, **kw)

        src = _make_source(tmp_path, dummy_icon_grid)
        with patch("xarray.open_dataset", side_effect=counting_open):
            with patch(
                "anemoi_plugins_meteoswiss.transform.sources.thx_lightning.new_field_from_grid",
                side_effect=lambda f, g: f,
            ):
                src.execute(times)

        assert len(open_calls) == 1
