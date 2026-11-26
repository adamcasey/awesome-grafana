"""Hero panel: Hallmark Channel 'Countdown to Christmas' new original premieres.

Curated, not scraped: Wikidata tags only ~69 Hallmark Channel Christmas films in total,
and press totals conflict because outlets mix in sister networks. Each verified row
carries a source URL and a basis ('stated' in an announcement or 'counted' from a
published schedule). This source validates the curated file and publishes it.
"""
from __future__ import annotations

import pandas as pd

from ..base import CURATED_DIR, Source, expect

GOLDEN = {2025: 24, 2026: 34}  # widely reported, HC-only


class Hallmark(Source):
    name = "hallmark"
    output = "hallmark_premieres.csv"

    def fetch(self, session):
        return pd.read_csv(CURATED_DIR / "hallmark_premieres.csv", dtype={"source_url": str})

    def normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        df = raw.copy()
        df["hc_premieres"] = pd.to_numeric(df["hc_premieres"], errors="raise").astype("Int64")
        df["all_networks"] = pd.to_numeric(df["all_networks"], errors="raise").astype("Int64")
        verified = df[df["status"] == "verified"].sort_values("year")
        verified = verified.assign(
            other_networks=(verified["all_networks"] - verified["hc_premieres"]).astype("Int64"),
            # Grafana bar charts want a time-like x; Jan 1 of the season's year.
            time=pd.to_datetime(verified["year"].astype(str) + "-01-01"),
        )
        return verified[["time", "year", "hc_premieres", "other_networks", "all_networks", "basis", "source_url", "note"]]

    def validate(self, df: pd.DataFrame) -> None:
        raw = self.fetch(None)
        expect(raw["year"].is_unique, "hallmark: duplicate years in curated file")
        expect(set(raw["status"]) <= {"verified", "todo"}, "hallmark: unknown status value")
        bad_basis = set(df["basis"]) - {"stated", "counted"}
        expect(not bad_basis, f"hallmark: verified rows need basis stated|counted, got {bad_basis}")
        expect(df["source_url"].fillna("").str.startswith("https://").all(), "hallmark: every verified row needs an https source_url")
        expect(df["hc_premieres"].between(1, 60).all(), "hallmark: HC premieres outside 1..60")
        both = df.dropna(subset=["all_networks"])
        expect((both["all_networks"] >= both["hc_premieres"]).all(), "hallmark: all_networks < HC premieres")
        for year, n in GOLDEN.items():
            got = df.loc[df["year"] == year, "hc_premieres"]
            expect(len(got) == 1 and int(got.iloc[0]) == n, f"hallmark: golden {year}={n}, got {list(got)}")
