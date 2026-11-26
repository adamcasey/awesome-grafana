"""Build the Grafana dashboard JSON (classic v1 schema) for the Missouri holiday dashboard.

  python dashboard/build_dashboard.py               # panels read raw GitHub CSVs (published mode)
  python dashboard/build_dashboard.py --inline      # embed any data/*.csv that exists (preview mode)

No template variables, so the dashboard can be shared publicly.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = "https://raw.githubusercontent.com/adamcasey/awesome-grafana/main/mo-holiday-season/data/"
DS = {"type": "yesoreyeram-infinity-datasource", "uid": "grafanacloud-infinity"}
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=APU0000706111"

# Palette: cranberry, pine, gold, snow, cocoa.
RED, PINE, GOLD, SNOW, SLATE = "#C0392B", "#1E8449", "#D4AC0D", "#D6EAF8", "#7F8C8D"

SEASON = 2026
CHRISTMAS_MS = int(datetime(SEASON, 12, 25, tzinfo=ZoneInfo("America/Chicago")).timestamp() * 1000)


class Builder:
    def __init__(self, inline: bool):
        self.inline = inline
        self.panels: list[dict] = []
        self.next_id = 1
        self.y = 0

    # -- queries ---------------------------------------------------------------
    def csv(self, file: str, columns: list[tuple[str, str, str]], ref="A", filter_expr: str = "") -> dict:
        cols = [{"selector": s, "text": t, "type": ty} for s, t, ty in columns]
        q = {"refId": ref, "datasource": DS, "type": "csv", "parser": "backend", "format": "table", "columns": cols}
        if filter_expr:
            q["filterExpression"] = filter_expr
        path = DATA / file
        if self.inline and path.exists():
            import pandas as pd  # preview only: embed just the columns this panel reads
            df = pd.read_csv(path)[list(dict.fromkeys(s for s, _, _ in columns))]
            q.update(source="inline", data=df.to_csv(index=False))
        else:
            q.update(source="url", url=RAW + file, url_options={"method": "GET"})
        return q

    # -- layout ----------------------------------------------------------------
    def add(self, panel: dict, w: int, h: int, x: int = 0, newline: bool = True) -> dict:
        panel = {"id": self.next_id, "datasource": DS, **panel, "gridPos": {"x": x, "y": self.y, "w": w, "h": h}}
        self.next_id += 1
        self.panels.append(panel)
        if newline:
            self.y += h
        return panel

    def row(self, title: str) -> None:
        self.panels.append({"id": self.next_id, "type": "row", "title": title, "collapsed": False,
                            "gridPos": {"x": 0, "y": self.y, "w": 24, "h": 1}, "panels": []})
        self.next_id += 1
        self.y += 1


def text(content: str, title: str = "", transparent=True) -> dict:
    return {"type": "text", "title": title, "transparent": transparent,
            "options": {"mode": "html", "content": content}}


def stat(title, desc, targets, unit="none", color=GOLD, decimals=None, reduce="lastNotNull", field="", text_mode="value"):
    defaults = {"unit": unit, "color": {"mode": "fixed", "fixedColor": color}}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {"type": "stat", "title": title, "description": desc, "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"reduceOptions": {"calcs": [reduce], "fields": field, "values": False},
                        "colorMode": "background", "graphMode": "none", "textMode": text_mode,
                        "justifyMode": "center", "wideLayout": True}}


def source_note(*lines: str) -> str:
    return "<div style='font-size:11px;opacity:.75;line-height:1.4'>" + "<br>".join(lines) + "</div>"


def build(inline: bool) -> dict:
    b = Builder(inline)

    # ---------------------------------------------------------------- header
    b.add(text(
        "<div style='text-align:center;padding:6px 0;background:linear-gradient(90deg,#7b1d1d,#1E5631,#7b1d1d);"
        "border-radius:10px;color:#fff'>"
        "<div style='font-size:30px;font-weight:800;letter-spacing:.5px'>Missouri's Holiday Season, by the Numbers</div>"
        "<div style='font-size:14px;opacity:.9'>Thanksgiving → Christmas, told with public data: Hallmark (made in Kansas City), "
        "NOAA snow records, MDC turkey harvests, BLS prices, EIA grid demand and Highway Patrol counts</div></div>"), w=24, h=3)

    hallmark_cols = [("year", "Season", "string"), ("hc_premieres", "Hallmark Channel", "number"),
                     ("other_networks", "Sister network (HMM / Hallmark Mystery)", "number")]
    snow_cols = [("year", "Year", "string"), ("station", "Station", "string"), ("snow_depth_in", "Snow depth (in)", "number")]

    stats = [
        (stat("Christmas Day is…", "Countdown to Dec 25, 2026 (America/Chicago). Rendered with Grafana's 'from now' unit.",
              [{"refId": "A", "datasource": DS, "type": "csv", "source": "inline", "parser": "backend", "format": "table",
                "data": f"christmas\n{CHRISTMAS_MS}", "columns": [{"selector": "christmas", "text": "Christmas", "type": "number"}]}],
              unit="dateTimeFromNow", color=RED), 5),
        (stat("New Hallmark films, 2026",
              "Countdown to Christmas new original premieres on Hallmark Channel only, the most ever. Source: Hallmark lineup announcement (Sept 2026) as reported by TV Guide.",
              [b.csv("hallmark_premieres.csv", hallmark_cols)], color=GOLD, field="Hallmark Channel"), 5),
        (stat("STL white Christmases, 1991–2020",
              "Share of Dec 25 mornings with ≥1\" of snow on the ground at St. Louis Lambert (GHCN-Daily USW00013994): 7 of 30 years. Same window as NOAA's climate normals.",
              [b.csv("christmas_snow.csv", [("year", "year", "number"), ("station", "station", "string"), ("white_christmas", "white", "number")],
                     filter_expr="station == 'STL' && year >= 1991 && year <= 2020")],
              unit="percentunit", color="#2E86C1", decimals=0, reduce="mean", field="white"), 5),
        (stat("Frozen turkey, $/lb (U.S.)",
              "BLS average price, U.S. city average (FRED APU0000706111), latest month. BLS publishes no Missouri-only series.",
              [{"refId": "A", "datasource": DS, "type": "csv", "source": "url", "parser": "backend", "format": "table",
                "url": FRED, "url_options": {"method": "GET"},
                "columns": [{"selector": "APU0000706111", "text": "$/lb", "type": "number"}]}],
              unit="currencyUSD", color=PINE, decimals=2), 5),
        (stat("Hallmark films since 2018",
              "Sum of verified Hallmark Channel Countdown premieres, 2018–2026 (curated series; see the hero panel).",
              [b.csv("hallmark_premieres.csv", hallmark_cols + [("year", "yr", "number")], filter_expr="yr >= 2018")],
              color=RED, reduce="sum", field="Hallmark Channel"), 4),
    ]
    x = 0
    for i, (p, w) in enumerate(stats):
        b.add(p, w=w, h=5, x=x, newline=(i == len(stats) - 1))
        x += w

    # ---------------------------------------------------------------- hero
    b.row("The Hallmark Christmas movie machine, made in Kansas City")
    hero = {
        "type": "barchart", "title": "New original Christmas movies per season: Hallmark Channel 'Countdown to Christmas'",
        "description": ("Hallmark Channel new original premieres during Countdown to Christmas (gold), stacked with the sister linear network's "
                        "Christmas premieres (red; Hallmark Movies & Mysteries / Hallmark Mystery). Streaming-only titles are excluded. "
                        "Curated from Hallmark announcements: each season's source URL is in curated/hallmark_premieres.csv. "
                        "2021 and 2023 are counted from the published schedules. 2010–2017 are not yet sourced, so they are omitted (not zero). "
                        "Blank red = sister-network count not reliably reported."),
        "targets": [b.csv("hallmark_premieres.csv", hallmark_cols)],
        "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": GOLD}, "custom": {"fillOpacity": 90, "lineWidth": 0}},
                        "overrides": [{"matcher": {"id": "byName", "options": "Sister network (HMM / Hallmark Mystery)"},
                                       "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": RED}}]}]},
        "options": {"stacking": "normal", "showValue": "always", "xField": "Season", "barWidth": 0.8, "groupWidth": 0.7,
                    "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"mode": "multi"}, "xTickLabelRotation": 0},
    }
    b.add(hero, w=17, h=11, newline=False)
    b.add(text(
        "<div style='padding:4px 10px;font-size:14px;line-height:1.5'>"
        "<b style='font-size:18px;color:#D4AC0D'>4 → 34</b><br>Countdown to Christmas <i>started with just four original movies</i> in 2009 (Hallmark). "
        "In 2026 Hallmark Channel is premiering <b>34</b>, a record for the channel.<br><br>"
        "<b>2025's dip to 24:</b> that season the sister network (Hallmark Mystery) launched <b>no</b> new Christmas films, "
        "and Hallmark Channel premiered 24.<br><br>"
        "<b>Why curated?</b> Wikidata tags only 69 Hallmark Channel Christmas films <i>in total</i>, and press totals mix networks "
        "(2018 is reported as 34, 36, 37 or 38). Every bar here has a single definition and a cited source."
        "</div>", title="Reading the chart", transparent=False), w=7, h=11, x=17)

    # ---------------------------------------------------------------- snow
    b.row("I'm dreaming of a white Christmas… am I, though?")
    for i, (key, label, since) in enumerate([("STL", "St. Louis Lambert", 1938), ("KC", "Kansas City International", 1972)]):
        b.add({
            "type": "barchart", "title": f"{label}: snow on the ground Christmas morning, {since}–2025",
            "description": (f"Dec 25 snow depth (SNWD, inches), NCEI GHCN-Daily station {'USW00013994' if key == 'STL' else 'USW00003947'}. "
                            "Blue bars clear NOAA's white-Christmas bar (≥1 inch on the ground). Missing observations are gaps, not zeros. "
                            f"{'(1940 is missing.) ' if key == 'STL' else ''}2026 lands after Dec 25."),
            "targets": [b.csv("christmas_snow.csv", snow_cols, filter_expr=f"station == '{key}'")],
            "fieldConfig": {"defaults": {
                "unit": "lengthin", "min": 0, "decimals": 1,
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [{"color": SLATE, "value": None}, {"color": "#5DADE2", "value": 1}]},
                "custom": {"fillOpacity": 90, "lineWidth": 0, "thresholdsStyle": {"mode": "dashed"}}},
                "overrides": [{"matcher": {"id": "byName", "options": "Year"}, "properties": [{"id": "unit", "value": "string"}]}]},
            "options": {"xField": "Year", "showValue": "never", "barWidth": 0.9, "xTickLabelSpacing": 100,
                        "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "single"}},
        }, w=12, h=8, x=12 * i, newline=(i == 1))

    # -------------------------------------------------------- thanksgiving
    b.row("Thanksgiving: from the Missouri woods to the dinner table")
    b.add({
        "type": "geomap", "title": "Wild turkeys checked in the fall firearms season, by county (latest season)",
        "description": ("MDC yearly harvest summary, 'Fall Turkey Firearms' all-counties table (Oct 1–31), joined to TIGERweb county centroids. "
                        "Bubble size = birds checked. 2025 statewide = 1,950 (asserted against MDC's release)."),
        "targets": [b.csv("turkey_fall_harvest.csv", [("county", "County", "string"), ("lat", "lat", "number"),
                                                     ("lon", "lon", "number"), ("total", "Turkeys", "number"), ("year", "year", "number")],
                          filter_expr="year == 2025")],
        "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "#A04000"}}, "overrides": []},
        "options": {"view": {"id": "coords", "lat": 38.4, "lon": -92.4, "zoom": 6},
                    "controls": {"showZoom": True, "mouseWheelZoom": False},
                    "basemap": {"type": "carto", "config": {"theme": "auto", "showLabels": True}},
                    "layers": [{"type": "markers", "name": "Turkeys", "location": {"mode": "coords", "latitude": "lat", "longitude": "lon"},
                                "config": {"style": {"size": {"field": "Turkeys", "min": 3, "max": 22, "fixed": 5},
                                                     "color": {"fixed": "#A04000"}, "opacity": 0.75,
                                                     "symbol": {"mode": "fixed", "fixed": "img/icons/marker/circle.svg"}},
                                           "showLegend": True}, "tooltip": True}]},
    }, w=10, h=11, newline=False)
    b.add({
        "type": "barchart", "title": "Statewide fall firearms turkey harvest by season",
        "description": "Sum of MDC county rows per season (fall firearms portion, Oct 1–31). Seasons before 2015 aren't ingested yet.",
        "targets": [b.csv("turkey_fall_harvest.csv", [("year", "Season", "string"), ("total", "Turkeys", "number")])],
        "transformations": [{"id": "groupBy", "options": {"fields": {"Season": {"aggregations": [], "operation": "groupby"},
                                                                     "Turkeys": {"aggregations": ["sum"], "operation": "aggregate"}}}}],
        "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "#A04000"}, "custom": {"fillOpacity": 85, "lineWidth": 0}}, "overrides": []},
        "options": {"xField": "Season", "showValue": "auto", "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"}},
    }, w=7, h=11, x=10, newline=False)
    b.add({
        "type": "timeseries", "title": "What the store bird costs: frozen whole turkey, $/lb",
        "description": "BLS CPI average price, frozen whole turkey per lb, U.S. city average (FRED APU0000706111). National series; there is no Missouri-only series.",
        "timeFrom": "20y", "hideTimeOverride": False,
        "targets": [{"refId": "A", "datasource": DS, "type": "csv", "source": "url", "parser": "backend", "format": "timeseries",
                     "url": FRED, "url_options": {"method": "GET"},
                     "columns": [{"selector": "observation_date", "text": "Month", "type": "timestamp", "timestampFormat": "2006-01-02"},
                                 {"selector": "APU0000706111", "text": "$/lb", "type": "number"}]}],
        "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 2, "color": {"mode": "fixed", "fixedColor": PINE},
                                     "custom": {"lineWidth": 2, "fillOpacity": 15, "gradientMode": "opacity", "spanNulls": True}}, "overrides": []},
        "options": {"legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "single"}},
    }, w=7, h=11, x=17)

    # ---------------------------------------------------------------- grid
    b.row("The grid takes Thanksgiving off (then the lights go up)")
    b.add({
        "type": "timeseries", "title": "Hourly electricity demand: Thanksgiving week vs. the week before",
        "description": ("EIA-930 hourly demand (MW) for MISO (serves eastern Missouri) and SPP (western Missouri). The baseline week is shifted +7 days so the same weekdays overlay. "
                        "Empty while EIA's data API is unavailable (it returned 504s throughout Thanksgiving 2026); "
                        "the scheduled ETL fills it on the first run that gets through."),
        "timeFrom": "14d", "hideTimeOverride": False,
        "targets": [b.csv("grid_demand_holiday.csv", [("aligned_time", "time", "timestamp"), ("respondent", "grid", "string"),
                                                     ("week", "week", "string"), ("demand_mw", "MW", "number")])],
        "transformations": [{"id": "partitionByValues", "options": {"fields": ["grid", "week"], "keepFields": False}}],
        "fieldConfig": {"defaults": {"unit": "megwatt", "color": {"mode": "palette-classic"},
                                     "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}]},
                                     "custom": {"lineWidth": 2, "thresholdsStyle": {"mode": "off"}}}, "overrides": []},
        "options": {"legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
    }, w=24, h=9)

    # --------------------------------------------------------------- farms
    b.row("Farms behind the feast and the tree")
    b.add({
        "type": "barchart", "title": "Missouri's rank among states in turkeys raised",
        "description": "USDA NASS Quick Stats, turkeys raised (head), state level. Rank computed across states per year.",
        "targets": [b.csv("nass_mo.csv", [("year", "Year", "string"), ("rank", "Rank", "number"),
                                         ("series", "series", "string"), ("state_alpha", "state_alpha", "string")],
                          filter_expr="series == 'turkeys_raised' && state_alpha == 'MO'")],
        "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": GOLD}}, "overrides": []},
        "options": {"xField": "Year", "showValue": "always", "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"}},
    }, w=12, h=8, newline=False)
    b.add({
        "type": "table", "title": "Christmas tree farms by Missouri county (2022 Census of Agriculture)",
        "description": "USDA NASS Census of Agriculture, Christmas trees, county level. '(D)' cells are withheld by NASS to avoid disclosing individual farms and stay blank.",
        "targets": [b.csv("nass_mo.csv", [("county_name", "County", "string"), ("year", "Census", "string"),
                                         ("short_desc", "Measure", "string"), ("value_num", "Value", "number"),
                                         ("series", "series", "string"), ("year", "census_year", "number")],
                          filter_expr="series == 'christmas_tree_ops' && census_year == 2022")],
        "options": {"showHeader": True, "sortBy": [{"displayName": "Value", "desc": True}]},
    }, w=12, h=8, x=12)

    # -------------------------------------------------------------- safety
    b.row("Drive home safe: Highway Patrol holiday counting periods")
    b.add({
        "type": "barchart", "title": "Thanksgiving weekend: crashes investigated by troopers",
        "description": ("MSHP holiday counting-period releases (6 p.m. Wednesday to 11:59 p.m. Sunday). These are troop-investigated crashes only. "
                        "MSHP's 'statewide' figures (all agencies) are a different measure and are kept separate."),
        "targets": [b.csv("mshp_holiday.csv", [("year", "Year", "string"), ("crashes", "Crashes", "number"),
                                              ("injuries", "Injuries", "number"), ("dwi_arrests", "DWI arrests", "number"),
                                              ("scope", "scope", "string"), ("holiday", "holiday", "string")],
                          filter_expr="scope == 'troop' && holiday == 'thanksgiving'")],
        "fieldConfig": {"defaults": {"custom": {"fillOpacity": 85, "lineWidth": 0}}, "overrides": [
            {"matcher": {"id": "byName", "options": "Crashes"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": SLATE}}]},
            {"matcher": {"id": "byName", "options": "Injuries"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": GOLD}}]},
            {"matcher": {"id": "byName", "options": "DWI arrests"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": RED}}]}]},
        "options": {"xField": "Year", "showValue": "always", "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"}},
    }, w=12, h=8, newline=False)
    b.add({
        "type": "barchart", "title": "Thanksgiving weekend, all agencies statewide: crashes, injuries, deaths",
        "description": "From the 'Statewide, N people died…' line of the following year's MSHP release. Every law-enforcement agency, not just troopers.",
        "targets": [b.csv("mshp_holiday.csv", [("year", "Year", "string"), ("crashes", "Crashes", "number"),
                                              ("injuries", "Injuries", "number"), ("fatalities", "Deaths", "number"),
                                              ("scope", "scope", "string"), ("holiday", "holiday", "string")],
                          filter_expr="scope == 'statewide_all_agencies' && holiday == 'thanksgiving'")],
        "fieldConfig": {"defaults": {"custom": {"fillOpacity": 85, "lineWidth": 0}}, "overrides": [
            {"matcher": {"id": "byName", "options": "Crashes"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": SLATE}}]},
            {"matcher": {"id": "byName", "options": "Injuries"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": GOLD}}]},
            {"matcher": {"id": "byName", "options": "Deaths"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": RED}}]}]},
        "options": {"xField": "Year", "showValue": "always", "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"}},
    }, w=12, h=8, x=12)

    # -------------------------------------------------------------- footer
    b.add(text(source_note(
        "<b>Sources:</b> Hallmark Channel lineup announcements (curated, per-season URLs in <code>curated/hallmark_premieres.csv</code>) · "
        "NOAA NCEI GHCN-Daily (USW00013994, USW00003947) · Missouri Department of Conservation turkey harvest summaries · "
        "U.S. Census TIGERweb · BLS via FRED (APU0000706111) · EIA-930 · USDA NASS Quick Stats · Missouri State Highway Patrol releases.",
        "<b>Definitions:</b> white Christmas = ≥1\" of snow on the ground Dec 25 (NOAA). Hallmark counts = new originals on Hallmark Channel; the sister linear network is stacked "
        "separately; streaming-only titles are excluded. MSHP troop and statewide figures are different measures.",
        "Code &amp; ETL: github.com/adamcasey/awesome-grafana/tree/main/mo-holiday-season"), transparent=True), w=24, h=3)

    return {
        "title": "Missouri's Holiday Season, by the Numbers",
        "uid": "mo-holiday-season",
        "tags": ["missouri", "holiday", "awesome-grafana", "linkedin"],
        "timezone": "America/Chicago",
        "editable": True,
        "graphTooltip": 0,
        "time": {"from": "now-30d", "to": "now"},
        "timepicker": {"hidden": True},
        "refresh": "",
        "schemaVersion": 39,
        "templating": {"list": []},
        "annotations": {"list": []},
        "links": [{"title": "Code & ETL on GitHub", "type": "link", "targetBlank": True,
                   "url": "https://github.com/adamcasey/awesome-grafana/tree/main/mo-holiday-season"}],
        "panels": b.panels,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inline", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "dashboard" / "mo-holiday-season.json"))
    a = ap.parse_args()
    Path(a.out).write_text(json.dumps(build(a.inline), indent=2, ensure_ascii=False))
    print("wrote", a.out)
