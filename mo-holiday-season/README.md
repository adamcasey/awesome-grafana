# Missouri's Holiday Season, by the Numbers

A Grafana Cloud dashboard covering Thanksgiving through Christmas, built entirely on public data. The hero panel tracks Hallmark's Christmas-movie output; Hallmark is headquartered in Kansas City.

| Panel | Source | Format |
|---|---|---|
| Hallmark Channel "Countdown to Christmas" premieres | Hallmark lineup announcements, curated with per-row source URLs | Curated CSV + validator |
| Christmas-morning snow, STL & KC | NOAA NCEI GHCN-Daily (USW00013994, USW00003947) | NCEI CSV API |
| White-Christmas odds, MO stations | NCEI 1991–2020 normals spreadsheet | XLSX |
| Fall wild-turkey harvest by county | Missouri Dept. of Conservation harvest summaries + TIGERweb centroids | HTML tables + ArcGIS REST |
| Frozen turkey $/lb | BLS via FRED `APU0000706111` | CSV (live in Grafana) |
| Thanksgiving grid demand | EIA-930 (MISO, SPP) | Keyed REST |
| Turkey production rank, Christmas tree farms | USDA NASS Quick Stats | Keyed REST |
| Holiday-weekend crashes | Missouri State Highway Patrol press releases | HTML + regex |

## How it works
```
GitHub Actions (weekly Nov–Jan, daily Dec 26–31)
  └─ python -m holiday_etl run      fetch → normalize → validate (golden numbers) → data/*.csv
        └─ committed to main ──► Grafana Infinity reads raw.githubusercontent.com/.../data/*.csv
```
Every source asserts at least one hand-verified number and **fails the job loudly** instead of publishing bad data:
Hallmark 2026 = 34 · STL Dec 25 2000 = 4.0" · MDC 2025 fall firearms = 1,950 · MSHP Thanksgiving 2025 = 304 troop crashes.

```bash
pip install -r requirements.txt
python -m pytest -q                         # 10 tests, offline fixtures
python -m holiday_etl run --only hallmark   # runs offline (curated)
python -m holiday_etl inspect white_christmas   # dump the raw layout of an unverified file
python dashboard/build_dashboard.py         # regenerate dashboard JSON (raw GitHub mode)
python dashboard/build_dashboard.py --inline --out /tmp/preview.json   # embed local data for preview
```

## Definitions
- **White Christmas** means ≥1" of snow *on the ground* on Dec 25 (NOAA's definition). Missing days are null, never 0.
- **Hallmark counts** are new originals on Hallmark Channel. The sister linear network is stacked separately. Streaming-only titles are excluded. Press totals often mix all three, so they disagree.
- **MSHP figures:** "Crashes ─ N" counts crashes investigated by troopers only. The "Statewide…" sentence covers all agencies for the *prior* year. They are stored as separate scopes.

## Secrets
`EIA_API_KEY` (https://www.eia.gov/opendata/register.php) and `NASS_API_KEY` (https://quickstats.nass.usda.gov/api). Without them the ETL skips those two sources and their panels stay empty.
