# Data sources and setup

Raw traffic archives are kept locally in `data/raw/`. The repository includes executed results and a small public aircraft-code reference table. `results/input_manifest.json` identifies the exact input snapshots by filename, size, and SHA-256 digest; later agency revisions may produce different results.

| Local file | Source and coverage |
| --- | --- |
| `T100_2019.zip` | BTS T-100 International Segment (All Carriers), full 2019 |
| `T100_2023.zip` | Same table, full 2023 |
| `T100_2024.zip` | Same table, full 2024 |
| `T100_2025.zip` | Same table, full 2025 |
| `108_112-114.zip` | Taiwan CAA annual Excel workbooks, ROC years 108, 112, 113, 114 |
| `data/reference/L_AIRCRAFT_TYPE.csv` | Included BTS aircraft-code lookup, retrieved October 7, 2026 |

## U.S. DOT / BTS

Download annual CSV exports from [T-100 International Segment (All Carriers)](https://www.transtats.bts.gov/DL_SelectFields.aspx?QO_fu146_anzr=Nv4Pn44vr45&gnoyr_VQ=FJE). Select all months of each required year and retain all columns. Each supplied ZIP contains one `T_T100I_SEGMENT_ALL_CARRIER.csv`. Keep the ZIPs compressed and rename them as above.

The aircraft lookup comes from the table's AircraftType “Get Lookup Table” link: [official CSV](https://www.transtats.bts.gov/Download_Lookup.asp?Y11x72=Y_NVePeNSg_glcR). It maps reported codes to descriptions. Code 637 combines Boeing 777-300 variants; the more specific SQ 777-300ER analysis label reflects manual review, not additional granularity in the lookup.

Required fields are listed in `src/data.py` as `T100_COLUMNS`. Principal measures are performed departures, available seats, passengers, freight (pounds), distance (miles), carrier, airports/countries, aircraft type, class, year, and month. Class F identifies scheduled passenger/cargo service; this study also requires positive passenger seating and removes explicitly freighter-coded records.

The selected Asian country codes are CN, HK, ID, JP, KR, MO, MY, PH, SG, TH, TW, and VN. Hawaii, Guam/Northern Mariana Islands, and Alaska are classified separately and excluded from the continental model. The annual market descriptions keep unresolved aircraft–seat flags; the model excludes them.

## Taiwan CAA

Use [annual scheduled international/cross-strait load factors by route and airline](https://www.caa.gov.tw/article.aspx?a=1746). Select the Excel files for ROC years 108, 112, 113, and 114 (2019, 2023, 2024, and 2025). Each workbook must include sheet `53-1`, whose title identifies Taiwan Taoyuan International Airport and breakdown by route and airline.

The supplied `108_112-114.zip` already has the required workbooks. If rebuilding it, ZIP the four `.xls` files together, keeping filenames that begin with their three-digit ROC year. The loader ignores macOS metadata entries and reconciles inbound plus outbound flights with the reported total.

## Aircraft and freight decisions

Manual aircraft corrections are confined to the reviewed carrier/year context. SQ A380-coded records averaging 250–300 seats become 777-300ER; SQ/OZ A350-coded records averaging at least 400 seats become A380 in the four study years. Reported codes/descriptions are preserved alongside analysis fields. This does not generalize a seat threshold to every carrier, and it is not tail-number verification.

The author's SQ assessment considered its passenger fleet during the study period, after 747 retirement. Logs record the affected years, routes, seat ranges, departures, and row counts. Unresolved records are flagged separately; manually reviewed SQ ULR and ANA low-density configurations are retained.

Freight is screened at carrier-year level. At least 12 eligible rows and a 60% share near 200 lb per passenger flag unreliable mechanical reporting. The affected freight is set to missing, while capacity and passenger observations remain. Reliable pounds are converted to metric tonnes using 0.00045359237. Passing this rule does not validate every freight observation.
