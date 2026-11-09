"""Tests for time_bins and accumulate functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from lightning_anemoi_dataset.accumulate import time_bins


DAY = datetime(2025, 1, 1, tzinfo=timezone.utc)
GRAN = timedelta(minutes=10)


class TestTimeBins:
    def test_returns_144_bins(self):
        bins = time_bins(DAY, GRAN)
        assert len(bins) == 144  # 24h / 10min

    def test_first_bin_is_end_of_first_window(self):
        """First label should be 00:10 (end of [00:00, 00:10))."""
        bins = time_bins(DAY, GRAN)
        expected = DAY.replace(hour=0, minute=10)
        assert bins[0] == expected

    def test_last_bin_is_midnight_next_day(self):
        """Last label should be 00:00 of the following day."""
        bins = time_bins(DAY, GRAN)
        expected = DAY + timedelta(days=1)
        assert bins[-1] == expected

    def test_bins_are_monotonically_increasing(self):
        bins = time_bins(DAY, GRAN)
        deltas = [(bins[i + 1] - bins[i]).total_seconds() for i in range(len(bins) - 1)]
        assert all(d == GRAN.total_seconds() for d in deltas)

    def test_bin_at_index_covers_preceding_window(self):
        """bin[i] should label the window (bin[i] - gran, bin[i]]."""
        bins = time_bins(DAY, GRAN)
        for i, t_end in enumerate(bins):
            t_start = t_end - GRAN
            # Window [t_start, t_end) must not cross into previous or next period
            assert t_start >= DAY - timedelta(seconds=1)
            assert t_end <= DAY + timedelta(days=1) + timedelta(seconds=1)
