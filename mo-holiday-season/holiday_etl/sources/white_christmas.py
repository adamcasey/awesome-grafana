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
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None)
        grid = max(sheets.values(), key=len)
        # The sheet opens with title rows ('Snow Statistics for Christmas Day'); the real header
        # is the first row that names both a latitude and a longitude column.
        for i in range(min(25, len(grid))):
            cells = [str(c).lower() for c in grid.iloc[i].tolist()]
            if any("lat" in c for c in cells) and any("lon" in c for c in cells):
                df = grid.iloc[i + 1:].reset_index(drop=True)
                df.columns = [" ".join(str(c).split()) for c in grid.iloc[i].tolist()]
                return df.dropna(how="all")
        raise ValueError("white_christmas: no header row with lat/lon in the first 25 rows:\n"
                         + grid.head(12).to_string())

    def inspect(self, raw) -> str:
        df = self._frame(raw)
        return f"shape={df.shape}\ncolumns={list(df.columns)}\n{df.head(8).to_string()}"

    def normalize(self, raw) -> pd.DataFrame:
        df = self._frame(raw)
        cols = list(df.columns)
        m = {
            "station_id": find_col(cols, "id") or find_col(cols, "station"),
            "name": find_col(cols, "name") or find_col(cols, "station"),
            "state": find_col(cols, "state") or find_col(cols, "st"),
            "lat": find_col(cols, "lat"),
            "lon": find_col(cols, "lon"),
            "prob": find_col(cols, "prob") or find_col(cols, "percent") or find_col(cols, "%") or find_col(cols, "chance"),
        }
        if m["state"] is None:  # some station lists fold the state into the name ("ST LOUIS ..., MO")
            m.pop("state")
        missing = [k for k, v in m.items() if v is None]
        expect(not missing, f"white_christmas: could not detect columns {missing}; got {cols}\n{df.head(5).to_string()}")
        out = df[[m[k] for k in m]].copy()
        out.columns = list(m)
        for c in ("station_id", "name", "state"):  # the sheet pads text cells with spaces
            if c in out:
                out[c] = out[c].astype(str).str.strip()
        if "state" in out:
            mo = out["state"].astype(str).str.upper().str.strip().isin(["MO", "MISSOURI"])
        else:
            mo = out["name"].astype(str).str.upper().str.contains(r"\bMO\b|MISSOURI", regex=True)
        out = out[mo].copy()
        for c in ("lat", "lon", "prob"):
            out[c] = pd.to_numeric(out[c], errors="coerce")
        # Sheet note: '-9999 = missing due to insufficient data'. Those stations have no probability.
        out = out[out["prob"].ne(-9999) & out["prob"].notna()].copy()
        if out["prob"].max() <= 1:  # fraction -> percent
            out["prob"] = out["prob"] * 100
        return out.rename(columns={"prob": "white_christmas_pct"})

    def validate(self, df: pd.DataFrame) -> None:
        expect(len(df) >= 10, f"white_christmas: only {len(df)} Missouri stations")
        expect(df["white_christmas_pct"].between(0, 100).all(), "white_christmas: probability outside 0..100")
        expect(df["lat"].between(35.9, 40.7).all() and df["lon"].between(-95.8, -89.0).all(), "white_christmas: station outside Missouri bbox")
        golden = {"USW00013994": 17.1, "USW00003947": 19.8}  # STL Lambert, KC Intl, read off the NCEI sheet
        for sid, want in golden.items():
            got = df.loc[df["station_id"] == sid, "white_christmas_pct"]
            expect(len(got) == 1 and round(float(got.iloc[0]), 1) == want, f"white_christmas: golden {sid}={want}, got {list(got)}")
