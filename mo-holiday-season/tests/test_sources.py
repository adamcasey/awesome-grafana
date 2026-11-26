from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from holiday_etl.base import ValidationError
from holiday_etl.sources.eia_grid import thanksgiving
from holiday_etl.sources.ghcn_christmas import GhcnChristmas, last_complete_season, summarize
from holiday_etl.sources.hallmark import Hallmark
from holiday_etl.sources.mdc_turkey import fall_firearms_table, norm_county
from holiday_etl.sources.mshp import Mshp, num, parse_release

FX = Path(__file__).parent / "fixtures"


# --- Hallmark (curated) ------------------------------------------------------
def test_hallmark_curated_file_validates():
    src = Hallmark()
    df = src.normalize(src.fetch(None))
    src.validate(df)
    assert df.set_index("year").loc[2026, "hc_premieres"] == 34
    assert (df["year"] >= 2009).all() and 2015 not in df["year"].values  # TODO rows excluded


def test_hallmark_rejects_unsourced_row(monkeypatch):
    src = Hallmark()
    raw = src.fetch(None)
    raw.loc[raw.year == 2022, "source_url"] = None
    monkeypatch.setattr(src, "fetch", lambda s: raw)
    with pytest.raises(ValidationError, match="source_url"):
        src.validate(src.normalize(raw))


# --- GHCN Christmas snow (fixtures are real NCEI Dec-25 values) ---------------
@pytest.fixture
def snow():
    src = GhcnChristmas(end_year=2025)
    raw = {"STL": (FX / "ghcn_stl_dec25.csv").read_text(), "KC": (FX / "ghcn_kc_dec25.csv").read_text()}
    return src, src.normalize(raw)


def test_ghcn_filters_dec25_and_keeps_missing_as_null(snow):
    src, df = snow
    src.validate(df)
    assert len(df[df.station == "STL"]) == 2025 - 1938 + 1
    stl1940 = df[(df.station == "STL") & (df.year == 1940)].iloc[0]
    assert pd.isna(stl1940.snow_depth_in) and pd.isna(stl1940.white_christmas)


def test_ghcn_observed_rate_matches_hand_count(snow):
    _, df = snow
    s = summarize(df).set_index("station")
    assert s.loc["STL", "white_years"] == 7 and s.loc["STL", "years_observed"] == 30
    assert s.loc["KC", "white_years"] == 8


def test_last_complete_season():
    assert last_complete_season(date(2026, 11, 26)) == 2025
    assert last_complete_season(date(2026, 12, 26)) == 2026


# --- MSHP press releases -------------------------------------------------------
RELEASE_2025 = """<html><body><p>EMPHASIS: Patrol Reports Three Fatalities</p>
<p>During the Thanksgiving holiday counting period, troopers report the following traffic statistics for 2025 (preliminary):</p>
<p>Crashes ─ 304<br>Injuries ─ 82<br>Fatalities ─ 3<br>DWI Arrests ─ 87</p>
<p>Statewide, 11 people died and 571 people were injured in 1,664 traffic crashes over last year's Thanksgiving holiday.</p>
</body></html>"""


def test_mshp_separates_troop_and_statewide_scopes():
    rows = parse_release(RELEASE_2025, "thanksgiving", 2025)
    troop = next(r for r in rows if r["scope"] == "troop")
    state = next(r for r in rows if r["scope"] == "statewide_all_agencies")
    assert troop == dict(holiday="thanksgiving", year=2025, scope="troop", crashes=304, injuries=82, fatalities=3, dwi_arrests=87)
    assert state["year"] == 2024 and state["crashes"] == 1664 and state["fatalities"] == 11


def test_mshp_golden_passes_and_number_words():
    src = Mshp()
    df = src.normalize([("thanksgiving", 2025, RELEASE_2025)])
    src.validate(df)
    assert num("nine") == 9 and num("1,342") == 1342


# --- MDC turkey HTML (synthetic page mirroring the real layout) ----------------
MDC_PAGE = """<html><body>
<div>Title</div><h2>2025 Spring Turkey</h2>
<table><tr><th>County</th><th>Total</th></tr><tr><td>Webster</td><td>383</td></tr></table>
<div>Title</div><h2>2025 Fall Turkey Firearms</h2>
<h3>Top 5 Counties</h3>
<table><tr><th>County</th><th>Total</th></tr><tr><td>Greene</td><td>56</td></tr></table>
<h3>All Counties</h3>
<table><tr><th>County</th><th>Adult Gobbler</th><th>Total</th></tr>
<tr><td>Greene</td><td>10</td><td>56</td></tr><tr><td>Laclede</td><td>8</td><td>42</td></tr>
<tr><td>St. Louis City</td><td>0</td><td>0</td></tr><tr><td>Total</td><td>18</td><td>98</td></tr></table>
<div>Title</div><h2>2025 Fall Turkey Archery</h2>
<table><tr><th>County</th><th>Total</th></tr><tr><td>Greene</td><td>99</td></tr><tr><td>Laclede</td><td>99</td></tr>
<tr><td>Perry</td><td>99</td></tr><tr><td>Texas</td><td>99</td></tr><tr><td>Dent</td><td>99</td></tr></table>
</body></html>"""


def test_mdc_picks_all_counties_fall_firearms_table():
    t = fall_firearms_table(MDC_PAGE, 2025)
    assert list(t["County"]) == ["Greene", "Laclede", "St. Louis City", "Total"]


def test_norm_county_matches_tiger_names():
    assert norm_county("Ste. Genevieve County") == norm_county("Ste. Genevieve")
    assert norm_county("Saint Louis County") == norm_county("St. Louis")


# --- EIA ---------------------------------------------------------------------
def test_thanksgiving_dates():
    assert thanksgiving(2026) == date(2026, 11, 26)
    assert thanksgiving(2025) == date(2025, 11, 27)


# 2015-era layout: no year in the title, plural columns, 'County Total', 'Totals' row
MDC_PAGE_2015 = """<html><body>
<div>Title</div><h2>Spring Total</h2>
<table><tr><th>County</th><th>Total</th></tr><tr><td>Webster</td><td>500</td></tr></table>
<div>Title</div><h2>Fall Turkey Firearms</h2>
<table><tr><th>County</th><th>Adult Gobblers</th><th>Adult Hens</th><th>Juvenile Gobblers</th><th>Juvenile Hens</th><th>County Total</th></tr>
<tr><td>Greene</td><td>40</td><td>50</td><td>30</td><td>60</td><td>180</td></tr>
<tr><td>Totals</td><td>40</td><td>50</td><td>30</td><td>60</td><td>180</td></tr></table>
<div>Title</div><h2>Season Harvest Totals Archery Turkey</h2>
<table><tr><th>County</th><th>Total</th></tr><tr><td>Greene</td><td>9</td></tr><tr><td>Dent</td><td>9</td></tr>
<tr><td>Texas</td><td>9</td></tr><tr><td>Perry</td><td>9</td></tr></table>
</body></html>"""


def test_mdc_handles_2015_layout_and_column_aliases():
    from holiday_etl.sources.mdc_turkey import COLUMN_ALIASES
    t = fall_firearms_table(MDC_PAGE_2015, 2015)
    cols = [COLUMN_ALIASES.get(c, c) for c in (str(c).strip().lower().replace(" ", "_") for c in t.columns)]
    assert cols == ["county", "adult_gobbler", "adult_hen", "juvenile_gobbler", "juvenile_hen", "total"]
    assert list(t["County"]) == ["Greene", "Totals"]


def test_white_christmas_rejects_html_landing_page():
    from holiday_etl.sources.white_christmas import WhiteChristmas
    with pytest.raises(ValueError, match="expected an XLSX"):
        WhiteChristmas()._frame(b"<!DOCTYPE html><html>...")


def test_mdc_title_variants():
    for heading, year in [("Fall Turkey Firearms", 2016), ("2017 Fall Turkey Firearm", 2017),
                          ("Title2022 Fall Turkey Firearms", 2022), ("2025 Fall Turkey Firearms", 2025)]:
        page = MDC_PAGE_2015.replace("<h2>Fall Turkey Firearms</h2>", f"<h2>{heading}</h2>")
        assert list(fall_firearms_table(page, year)["County"]) == ["Greene", "Totals"], heading


def test_white_christmas_finds_header_below_title_rows(tmp_path):
    from holiday_etl.sources.white_christmas import WhiteChristmas
    rows = [["", "", "", "", "", "Snow Statistics for Christmas Day", ""], [""] * 7,
            ["GHCN ID", "Station Name", "State", "Latitude", "Longitude", "Probability of >= 1 inch", "Mean depth"],
            ["USW00013994", "ST LOUIS LAMBERT INTL AP", "MO", 38.75, -90.37, 0.23, 0.5],
            ["USW00014739", "BOSTON LOGAN", "MA", 42.36, -71.01, 0.2, 1.0]]
    path = tmp_path / "wc.xlsx"
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    src = WhiteChristmas()
    df = src.normalize(path.read_bytes())
    assert list(df["station_id"]) == ["USW00013994"] and df["white_christmas_pct"].iloc[0] == 23.0
