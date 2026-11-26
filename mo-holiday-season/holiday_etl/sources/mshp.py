"""Missouri State Highway Patrol holiday counting-period statistics (press releases).

Two DIFFERENT measures appear in each release and are kept apart:
  scope=troop                   'Crashes ─ 304' block: crashes investigated by troopers, this year
  scope=statewide_all_agencies  'Statewide, 11 people died and 571 ... in 1,664 traffic crashes
                                 over last year's ...': every agency, PRIOR year
"""
from __future__ import annotations

import re

import pandas as pd
from lxml import html as lxml_html

from ..base import CURATED_DIR, Source, expect

DASH = r"\s*[─—–\-]+\s*"
WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
GOLDEN = {("thanksgiving", 2025, "troop"): dict(crashes=304, injuries=82, fatalities=3, dwi_arrests=87),
          ("thanksgiving", 2024, "statewide_all_agencies"): dict(crashes=1664, injuries=571, fatalities=11)}


def num(tok: str) -> int:
    tok = tok.strip().lower().replace(",", "")
    return int(tok) if tok.isdigit() else WORDS[tok]


def parse_release(page_html: str, holiday: str, year: int) -> list[dict]:
    text = " ".join(lxml_html.fromstring(page_html).text_content().split())
    rows = []
    block = {}
    for field, label in [("crashes", "Crashes"), ("injuries", "Injuries"), ("fatalities", "Fatalities"), ("dwi_arrests", "DWI Arrests")]:
        m = re.search(label + DASH + r"([\d,]+)", text)
        if m:
            block[field] = int(m.group(1).replace(",", ""))
    if block:
        rows.append(dict(holiday=holiday, year=year, scope="troop", **block))
    m = re.search(r"Statewide,\s*([\w,]+) (?:people|persons) (?:died|were killed) and ([\w,]+) (?:people )?(?:were )?injured in ([\d,]+) traffic crashes", text, re.I)
    if m:
        rows.append(dict(holiday=holiday, year=year - 1, scope="statewide_all_agencies",
                         fatalities=num(m.group(1)), injuries=num(m.group(2)), crashes=num(m.group(3))))
    if not rows:
        raise ValueError(f"mshp: no statistics found in {holiday} {year} release")
    return rows


class Mshp(Source):
    name = "mshp"
    output = "mshp_holiday.csv"

    def fetch(self, session):
        releases = pd.read_csv(CURATED_DIR / "mshp_releases.csv")
        out = []
        for rel in releases.itertuples():
            r = session.get(rel.url, timeout=60)
            r.raise_for_status()
            out.append((rel.holiday, int(rel.year), r.text))
        return out

    def normalize(self, raw) -> pd.DataFrame:
        rows = [row for h, y, page in raw for row in parse_release(page, h, y)]
        df = pd.DataFrame(rows)
        # A prior-year statewide figure may appear in two releases; they must agree.
        dup = df.duplicated(["holiday", "year", "scope"], keep=False)
        if dup.any():
            g = df[dup].groupby(["holiday", "year", "scope"]).nunique(dropna=True)
            expect((g[["crashes", "injuries", "fatalities"]] <= 1).all().all(), "mshp: releases disagree on a figure")
            df = df.drop_duplicates(["holiday", "year", "scope"])
        df["time"] = pd.to_datetime(df["year"].astype(str) + "-11-25")
        return df.sort_values(["holiday", "scope", "year"])[["time", "holiday", "year", "scope", "crashes", "injuries", "fatalities", "dwi_arrests"]]

    def validate(self, df: pd.DataFrame) -> None:
        expect(df["crashes"].between(1, 5000).all(), "mshp: crashes outside 1..5000")
        expect((df["fatalities"] <= df["crashes"]).all(), "mshp: fatalities > crashes")
        for (h, y, scope), want in GOLDEN.items():
            row = df[(df.holiday == h) & (df.year == y) & (df.scope == scope)]
            expect(len(row) == 1, f"mshp: golden row {h} {y} {scope} missing")
            for k, v in want.items():
                expect(int(row.iloc[0][k]) == v, f"mshp: golden {h} {y} {scope} {k}={v}, got {row.iloc[0][k]}")
