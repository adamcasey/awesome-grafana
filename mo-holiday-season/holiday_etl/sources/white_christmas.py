"""NOAA/NCEI 1991-2020 white-Christmas probabilities (spreadsheet linked from climate.gov).

Layout unverified (the workspace cannot reach NCEI): columns are detected by name, and the run
fails loudly if they can't be. Run `python -m holiday_etl inspect white_christmas` first.
"""
from __future__ import annotations

import io

import pandas as pd

from ..base import Source, expect

# ncei.noaa.gov/media/3501 is the HTML landing page; this is the file it links to.
URL = "https://www.ncei.noaa.gov/sites/default/files/2021-12/Christmas_day_snow_statistics_1991-2020_updated.xlsx"
STL_ID, KC_ID = "USW00013994", "USW00003947"


def find_col(cols, *needles):
    for c in cols:
        lc = str(c).lower()
        if all(n in lc for n in needles):
            return c
    return None


class WhiteChristmas(Source):
    name = "white_christmas"
    output = "white_christmas_odds_mo.csv"

    def fetch(self, session):
        r = session.get(URL, timeout=120)
        r.raise_for_status()
        return r.content

    def _frame(self, raw: bytes) -> pd.DataFrame:
        if raw[:2] != b"PK":  # xlsx is a zip; anything else (e.g. an HTML page) is the wrong URL
            raise ValueError(f"white_christmas: expected an XLSX file, got {raw[:40]!r}")
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
        return max(sheets.values(), key=len)

    def inspect(self, raw) -> str:
        df = self._frame(raw)
        return f"shape={df.shape}\ncolumns={list(df.columns)}\n{df.head(5).to_string()}"

    def normalize(self, raw) -> pd.DataFrame:
        df = self._frame(raw)
        cols = list(df.columns)
        m = {
            "station_id": find_col(cols, "id") or find_col(cols, "station"),
            "name": find_col(cols, "name"),
            "state": find_col(cols, "state") or find_col(cols, "st"),
            "lat": find_col(cols, "lat"),
            "lon": find_col(cols, "lon"),
            "prob": find_col(cols, "prob") or find_col(cols, "percent") or find_col(cols, "%"),
        }
        missing = [k for k, v in m.items() if v is None]
        expect(not missing, f"white_christmas: could not detect columns {missing}; got {cols} (run inspect)")
        out = df[[m[k] for k in m]].copy()
        out.columns = list(m)
        out = out[out["state"].astype(str).str.upper().str.strip().isin(["MO", "MISSOURI"])]
        out["prob"] = pd.to_numeric(out["prob"], errors="coerce")
        if out["prob"].max() <= 1:  # fraction -> percent
            out["prob"] = out["prob"] * 100
        return out.rename(columns={"prob": "white_christmas_pct"})

    def validate(self, df: pd.DataFrame) -> None:
        expect(len(df) >= 10, f"white_christmas: only {len(df)} Missouri stations")
        expect(df["white_christmas_pct"].between(0, 100).all(), "white_christmas: probability outside 0..100")
        expect(df["lat"].between(35.9, 40.7).all() and df["lon"].between(-95.8, -89.0).all(), "white_christmas: station outside Missouri bbox")
