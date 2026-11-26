"""Hourly electricity demand for the two grids that serve Missouri (EIA-930 via API v2).

MISO covers eastern Missouri (Ameren); SPP ('SWPP') covers western Missouri (Evergy KC).
Window: Thanksgiving week and the same weekdays one week earlier, for an apples-to-apples dip.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import requests

from ..base import Source, SourceUnavailable, expect, require_env

API = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
RESPONDENTS = {"MISO": (40_000, 140_000), "SWPP": (15_000, 70_000)}


def thanksgiving(year: int) -> date:
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + timedelta(weeks=3)


class EiaGrid(Source):
    name = "eia_grid"
    output = "grid_demand_holiday.csv"
    needs_env = ("EIA_API_KEY",)
    columns = ("time", "aligned_time", "respondent", "week", "demand_mw")

    def __init__(self, year: int | None = None):
        self.year = year or date.today().year
        self.tday = thanksgiving(self.year)

    def fetch(self, session):
        start = self.tday - timedelta(days=10)
        end = self.tday + timedelta(days=4)
        params = {
            "api_key": require_env("EIA_API_KEY"), "frequency": "hourly", "data[0]": "value",
            "facets[type][]": "D", "facets[respondent][]": list(RESPONDENTS),
            "start": f"{start}T00", "end": f"{end}T23", "sort[0][column]": "period",
            "sort[0][direction]": "asc", "length": 5000,
        }
        try:
            r = session.get(API, params=params, timeout=90)
            r.raise_for_status()
        except (requests.exceptions.RetryError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise SourceUnavailable(f"EIA API not answering data queries: {exc.__class__.__name__}") from exc
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code >= 500:
                raise SourceUnavailable(f"EIA API returned {exc.response.status_code}") from exc
            raise
        return r.json()

    def normalize(self, raw) -> pd.DataFrame:
        df = pd.DataFrame(raw["response"]["data"])
        df["time"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True)
        df["demand_mw"] = pd.to_numeric(df["value"])
        local = df["time"].dt.tz_convert("America/Chicago")
        df["local_date"] = local.dt.date
        df["week"] = "baseline"
        df.loc[local.dt.date >= self.tday - timedelta(days=3), "week"] = "thanksgiving"
        # Align the baseline week onto Thanksgiving week's clock so both lines overlay.
        df["aligned_time"] = df["time"].where(df["week"] == "thanksgiving", df["time"] + pd.Timedelta(days=7))
        return df[["time", "aligned_time", "respondent", "week", "demand_mw"]].sort_values(["respondent", "time"])

    def validate(self, df: pd.DataFrame) -> None:
        for resp, (lo, hi) in RESPONDENTS.items():
            sub = df[df["respondent"] == resp]
            expect(len(sub) >= 24 * 10, f"eia: {resp} has only {len(sub)} hourly rows")
            expect(sub["demand_mw"].between(lo, hi).all(), f"eia: {resp} demand outside {lo}..{hi} MW")
