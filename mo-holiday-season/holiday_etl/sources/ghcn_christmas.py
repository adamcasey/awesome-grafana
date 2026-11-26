"""Christmas Day snow depth at Missouri's two big airports (NCEI GHCN-Daily, SNWD).

White Christmas = >= 1 inch of snow on the ground on Dec 25 (NOAA's definition).
A year with no Dec 25 observation is published as null, never as 0.
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from ..base import Source, expect

API = "https://www.ncei.noaa.gov/access/services/data/v1"
STATIONS = {
    # key: (GHCN id, label, lat, lon, first season to report)
    "STL": ("USW00013994", "St. Louis Lambert", 38.7525, -90.3736, 1938),
    "KC": ("USW00003947", "Kansas City Intl", 39.2972, -94.7306, 1972),
}
GOLDEN = {("STL", 2000): 4.0, ("STL", 2002): 6.0, ("KC", 1983): 7.0}


def last_complete_season(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if (today.month, today.day) > (12, 25) else today.year - 1


class GhcnChristmas(Source):
    name = "ghcn_christmas"
    output = "christmas_snow.csv"

    def __init__(self, end_year: int | None = None):
        self.end_year = end_year or last_complete_season()

    def fetch(self, session):
        out = {}
        for key, (sid, *_rest, first) in STATIONS.items():
            r = session.get(API, params={
                "dataset": "daily-summaries", "stations": sid, "dataTypes": "SNWD",
                "startDate": f"{first}-01-01", "endDate": f"{self.end_year}-12-31",
                "format": "csv", "units": "standard",
            }, timeout=120)
            r.raise_for_status()
            out[key] = r.text
        return out

    def normalize(self, raw: dict[str, str]) -> pd.DataFrame:
        frames = []
        for key, text in raw.items():
            sid, label, lat, lon, first = STATIONS[key]
            df = pd.read_csv(io.StringIO(text), dtype={"STATION": str})
            df = df[df["DATE"].str.endswith("-12-25")]
            df = df.assign(year=df["DATE"].str[:4].astype(int))
            df["SNWD"] = pd.to_numeric(df.get("SNWD"), errors="coerce")
            years = pd.DataFrame({"year": range(first, self.end_year + 1)})
            merged = years.merge(df[["year", "SNWD"]], on="year", how="left")
            merged = merged.assign(station=key, station_id=sid, label=label, lat=lat, lon=lon)
            frames.append(merged.rename(columns={"SNWD": "snow_depth_in"}))
        out = pd.concat(frames, ignore_index=True)
        out["white_christmas"] = out["snow_depth_in"].ge(1).astype("Int64").where(out["snow_depth_in"].notna())  # 1/0/null
        out["time"] = pd.to_datetime(out["year"].astype(str) + "-12-25")
        return out[["time", "year", "station", "station_id", "label", "lat", "lon", "snow_depth_in", "white_christmas"]]

    def validate(self, df: pd.DataFrame) -> None:
        expect(df["snow_depth_in"].dropna().between(0, 40).all(), "ghcn: snow depth outside 0..40 in")
        for key in STATIONS:
            sub = df[df["station"] == key]
            expect(sub["snow_depth_in"].notna().mean() > 0.9, f"ghcn: {key} missing >10% of Dec 25 values")
        for (key, year), want in GOLDEN.items():
            got = df.loc[(df["station"] == key) & (df["year"] == year), "snow_depth_in"]
            expect(len(got) == 1 and float(got.iloc[0]) == want, f"ghcn: golden {key} {year}={want}, got {list(got)}")


def summarize(df: pd.DataFrame, start: int = 1991, end: int = 2020) -> pd.DataFrame:
    """Observed white-Christmas rate per station over a window (default: the 1991-2020 normals)."""
    w = df[df["year"].between(start, end)].dropna(subset=["white_christmas"])
    g = w.groupby("station")["white_christmas"].agg(["sum", "count"]).reset_index()
    g["observed_pct"] = (100 * g["sum"] / g["count"]).round(1)
    return g.rename(columns={"sum": "white_years", "count": "years_observed"})
