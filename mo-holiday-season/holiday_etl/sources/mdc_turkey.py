"""Missouri wild turkey fall firearms harvest by county (MDC yearly harvest summary pages).

Each page holds several tables, each preceded by a title like '2025 Fall Turkey Firearms'
and a 'Top 5 Counties' mini-table. We take the largest table after the fall-firearms
title (the all-counties table) and assert its Total row.
MDC's harvest_table widget is robots-disallowed, so it is deliberately not used.
"""
from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd
from lxml import html as lxml_html

from ..base import Source, expect

PAGE = "https://mdc.mo.gov/hunting-trapping/species/turkey/turkey-reports/turkey-harvest-summaries/{year}-turkey-harvest-summary"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query"
GOLDEN_TOTAL = {2015: 6158, 2016: 3698, 2017: 2901, 2019: 1953, 2022: 1844, 2025: 1950}  # MDC pages' own Total rows
FIRST_YEAR = 2015  # earliest summary page MDC links (slug pattern confirmed 2015-2026)


def fall_firearms_table(page_html: str, year: int) -> pd.DataFrame:
    """Return the all-counties fall firearms table from one summary page.

    Section headings drift by year (verified on MDC pages): 'Fall Turkey Firearms' (2015-16),
    '2017 Fall Turkey Firearm' (singular, 2017/2019), 'Title2022 Fall Turkey Firearms' (no space
    after the Drupal 'Title' label), '2025 Fall Turkey Firearms'. Each section holds a 'Top 5'
    table and an all-counties table; the section ends at the next Spring/Archery/Youth heading
    and the largest table inside it is the all-counties one.
    """
    doc = lxml_html.fromstring(page_html)
    title_re = re.compile(rf"^(?:Title\s*)?(?:{year}\s*)?Fall\s+Turkey\s+Firearms?(?:\s+Report)?$", re.I)
    in_section, candidates = False, []
    for el in doc.iter():
        if el.tag == "table":
            if in_section:
                candidates.append(el)
            continue
        if not isinstance(el.tag, str) or el.find(".//table") is not None:
            continue  # comments, or containers whose text would swallow a whole section
        text = " ".join(el.text_content().split())
        if not text or len(text) > 80:
            continue
        if title_re.match(text):
            in_section = True
        elif in_section and candidates and re.search(r"\b(Spring|Archery|Youth)\b", text, re.I):
            break
    if not candidates:
        raise ValueError(f"{year}: no 'Fall Turkey Firearms' table found")
    tables = [pd.read_html(io.StringIO(lxml_html.tostring(t, encoding="unicode")))[0] for t in candidates]
    return max(tables, key=len)


COLUMN_ALIASES = {  # older pages pluralize and say 'County Total'
    "adult_gobblers": "adult_gobbler", "adult_hens": "adult_hen", "juvenile_gobblers": "juvenile_gobbler",
    "juvenile_hens": "juvenile_hen", "county_total": "total",
}


def norm_county(name: str) -> str:
    n = re.sub(r"\s+County$", "", str(name).strip(), flags=re.I)
    n = n.replace("Saint ", "St. ").replace("St ", "St. ").replace("Ste ", "Ste. ")
    return n.lower()


class MdcTurkey(Source):
    name = "mdc_turkey"
    output = "turkey_fall_harvest.csv"

    def __init__(self, years: list[int] | None = None):
        last = date.today().year if date.today().month >= 11 else date.today().year - 1
        self.years = years or list(range(FIRST_YEAR, last + 1))

    def fetch(self, session):
        pages = {}
        for y in self.years:
            r = session.get(PAGE.format(year=y), timeout=60)
            if r.status_code == 404:
                pages[y] = None  # recorded, and validate() decides if that is fatal
                continue
            r.raise_for_status()
            pages[y] = r.text
        cent = session.get(TIGER, params={
            "where": "STATE='29'", "outFields": "NAME,GEOID,CENTLAT,CENTLON",
            "returnGeometry": "false", "f": "json",
        }, timeout=60)
        cent.raise_for_status()
        return {"pages": pages, "centroids": cent.json()}

    def inspect(self, raw) -> str:
        lines = []
        for y, page in raw["pages"].items():
            if page is None:
                lines.append(f"{y}: 404")
                continue
            doc = lxml_html.fromstring(page)
            titles = [t.strip() for t in doc.xpath("//text()") if re.search(r"\d{4}\s+.*Turkey", t or "") and len(t.strip()) < 80]
            lines.append(f"{y}: {len(doc.xpath('//table'))} tables; titles={titles}")
        return "\n".join(lines)

    def normalize(self, raw) -> pd.DataFrame:
        feats = raw["centroids"]["features"]
        cent = pd.DataFrame([f["attributes"] for f in feats])
        cent["key"] = cent["NAME"].map(norm_county)
        rows = []
        self.missing_years = [y for y, p in raw["pages"].items() if p is None]
        for y, page in raw["pages"].items():
            if page is None:
                continue
            t = fall_firearms_table(page, y)
            t.columns = [COLUMN_ALIASES.get(c, c) for c in (str(c).strip().lower().replace(" ", "_") for c in t.columns)]
            t = t[~t["county"].astype(str).str.lower().isin(["total", "totals"])].copy()
            t["year"] = y
            rows.append(t)
        df = pd.concat(rows, ignore_index=True)
        df["key"] = df["county"].map(norm_county)
        df = df.merge(cent[["key", "GEOID", "CENTLAT", "CENTLON"]], on="key", how="left")
        self.unmatched = sorted(df.loc[df["GEOID"].isna(), "county"].unique())
        df = df.rename(columns={"GEOID": "geoid", "CENTLAT": "lat", "CENTLON": "lon"})
        df["lat"] = pd.to_numeric(df["lat"])
        df["lon"] = pd.to_numeric(df["lon"])
        df["time"] = pd.to_datetime(df["year"].astype(str) + "-10-01")
        keep = ["time", "year", "county", "geoid", "lat", "lon", "adult_gobbler", "adult_hen",
                "juvenile_gobbler", "juvenile_hen", "total", "public_land"]
        return df[[c for c in keep if c in df.columns]]

    def validate(self, df: pd.DataFrame) -> None:
        expect(not getattr(self, "unmatched", []), f"mdc: counties without TIGER centroid: {self.unmatched}")
        expect(len(df["geoid"].unique()) <= 115, "mdc: more than 115 MO county equivalents")
        expect(df["total"].between(0, 1000).all(), "mdc: county total outside 0..1000")
        for y, want in GOLDEN_TOTAL.items():
            if y in df["year"].values:
                got = int(df.loc[df["year"] == y, "total"].sum())
                expect(got == want, f"mdc: golden {y} statewide fall firearms={want}, got {got}")
        expect(2025 in df["year"].values, "mdc: golden year 2025 page missing")
