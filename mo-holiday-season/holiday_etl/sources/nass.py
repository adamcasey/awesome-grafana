"""USDA NASS Quick Stats: Missouri turkeys raised (rank among states) and Christmas tree farms.

short_desc values below were confirmed with Quick Stats get_param_values for Missouri on 2026-11-26.
The Census files Christmas trees under 'CUT CHRISTMAS TREES' ('CHRISTMAS TREES' matches nothing).
Quick Stats answers 400 when a query matches no rows.
"""
from __future__ import annotations

import pandas as pd

from ..base import Source, expect, require_env

API = "https://quickstats.nass.usda.gov/api/api_GET/"
QUERIES = {
    "turkeys_raised": dict(source_desc="SURVEY", short_desc="TURKEYS - PRODUCTION, MEASURED IN HEAD",
                           agg_level_desc="STATE", year__GE="2000"),
    "christmas_tree_ops": dict(source_desc="CENSUS", short_desc="CUT CHRISTMAS TREES - OPERATIONS WITH AREA IN PRODUCTION",
                               domain_desc="TOTAL", agg_level_desc="COUNTY", state_alpha="MO"),
    "christmas_tree_acres": dict(source_desc="CENSUS", short_desc="CUT CHRISTMAS TREES - ACRES IN PRODUCTION",
                                 domain_desc="TOTAL", agg_level_desc="COUNTY", state_alpha="MO"),
}


class Nass(Source):
    name = "nass"
    output = "nass_mo.csv"
    needs_env = ("NASS_API_KEY",)

    def fetch(self, session):
        key = require_env("NASS_API_KEY")
        out = {}
        for name, q in QUERIES.items():
            r = session.get(API, params={"key": key, "format": "JSON", **q}, timeout=120)
            if r.status_code == 400:  # Quick Stats' way of saying 'no rows match'; say which query
                raise ValueError(f"nass: query {name!r} matched nothing: {r.text[:200]}")
            r.raise_for_status()
            out[name] = r.json().get("data", [])
        return out

    def inspect(self, raw) -> str:
        lines = []
        for name, rows in raw.items():
            descs = sorted({r.get("short_desc") for r in rows})
            lines.append(f"{name}: {len(rows)} rows; short_desc={descs[:20]}")
        return "\n".join(lines)

    def normalize(self, raw) -> pd.DataFrame:
        frames = []
        for name, rows in raw.items():
            df = pd.DataFrame(rows)
            if df.empty:
                continue
            df["value_num"] = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")  # '(D)' -> NaN (suppressed)
            df["suppressed"] = df["Value"].str.strip().eq("(D)")
            df["series"] = name
            frames.append(df[["series", "year", "state_alpha", "county_name", "short_desc", "value_num", "suppressed"]])
        out = pd.concat(frames, ignore_index=True)
        t = out["series"] == "turkeys_raised"
        out.loc[t, "rank"] = out[t].groupby(["year", "short_desc"])["value_num"].rank(ascending=False, method="min")
        return out

    def validate(self, df: pd.DataFrame) -> None:
        t = df[(df["series"] == "turkeys_raised") & (df["state_alpha"] == "MO")]
        expect(len(t) > 0, "nass: no Missouri turkey rows (check QUERIES short_desc; run inspect)")
        expect(t["value_num"].dropna().between(1e6, 5e7).all(), "nass: MO turkeys raised outside 1M..50M head")
