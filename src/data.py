"""Load public traffic sources and retain an audit trail for quality decisions."""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pandas as pd

T100_COLUMNS = [
    "DEPARTURES_SCHEDULED",
    "DEPARTURES_PERFORMED",
    "PAYLOAD",
    "SEATS",
    "PASSENGERS",
    "FREIGHT",
    "MAIL",
    "DISTANCE",
    "RAMP_TO_RAMP",
    "AIR_TIME",
    "UNIQUE_CARRIER",
    "UNIQUE_CARRIER_NAME",
    "ORIGIN",
    "ORIGIN_CITY_NAME",
    "ORIGIN_COUNTRY",
    "ORIGIN_COUNTRY_NAME",
    "DEST",
    "DEST_CITY_NAME",
    "DEST_COUNTRY",
    "DEST_COUNTRY_NAME",
    "AIRCRAFT_GROUP",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_CONFIG",
    "YEAR",
    "QUARTER",
    "MONTH",
    "CLASS",
]

NUMERIC_COLUMNS = [
    "DEPARTURES_SCHEDULED",
    "DEPARTURES_PERFORMED",
    "PAYLOAD",
    "SEATS",
    "PASSENGERS",
    "FREIGHT",
    "MAIL",
    "DISTANCE",
    "RAMP_TO_RAMP",
    "AIR_TIME",
    "YEAR",
    "QUARTER",
    "MONTH",
]





ASIA_COUNTRIES = {
    "CN": "China",
    "HK": "Hong Kong",
    "ID": "Indonesia",
    "JP": "Japan",
    "KR": "South Korea",
    "MO": "Macau",
    "MY": "Malaysia",
    "PH": "Philippines",
    "SG": "Singapore",
    "TH": "Thailand",
    "TW": "Taiwan",
    "VN": "Vietnam",
}

HAWAII_AIRPORTS = {"HNL", "OGG", "KOA", "LIH"}
GUAM_MARIANAS_AIRPORTS = {"GUM", "SPN"}
ALASKA_AIRPORTS = {"ANC", "FAI"}

def load_t100_year(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=T100_COLUMNS, low_memory=False)
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["AIRCRAFT_TYPE_REPORTED"] = (
        pd.to_numeric(frame["AIRCRAFT_TYPE"], errors="coerce")
        .astype("Int64")
        .astype("string")
        .str.zfill(3)
    )
    return frame.drop(columns="AIRCRAFT_TYPE")


def classify_us_market(airport: str) -> str:
    if airport in HAWAII_AIRPORTS:
        return "Hawaii"
    if airport in GUAM_MARIANAS_AIRPORTS:
        return "Guam / Northern Mariana Islands"
    if airport in ALASKA_AIRPORTS:
        return "Alaska"
    return "Continental U.S."




def aircraft_family(description: object) -> str:
    text = str(description).upper()
    ordered_patterns = [
        ("A380", ["A380", "A-380", "AIRBUS 380"]),
        ("A350", ["A350", "A-350", "AIRBUS 350"]),
        ("A340", ["A340", "A-340", "AIRBUS 340"]),
        ("A330", ["A330", "A-330", "AIRBUS 330"]),
        ("A300/A310", ["A300", "A-300", "A310", "A-310"]),
        ("787", ["787"]),
        ("777", ["777"]),
        ("767", ["767"]),
        ("747", ["747"]),
        ("757", ["757"]),
        ("737", ["737"]),
        ("A320 family", ["A318", "A319", "A320", "A321", "A-318", "A-319", "A-320", "A-321"]),
        ("A220", ["A220", "A-220"]),
        ("MD-11/DC-10", ["MD-11", "DC-10"]),
    ]
    for family, patterns in ordered_patterns:
        if any(pattern in text for pattern in patterns):
            return family
    return "Other / unknown"


def reliable_sum(series: pd.Series) -> float:
    return series.sum(min_count=1)






def correct_aircraft_labels(panel):
    """Apply reviewed carrier-specific labels while preserving reported data."""
    panel = panel.copy()
    panel["AIRCRAFT_TYPE_ANALYSIS"] = panel["AIRCRAFT_TYPE_REPORTED"]
    panel["AIRCRAFT_DESCRIPTION_ANALYSIS"] = (
        panel["AIRCRAFT_DESCRIPTION_REPORTED"]
    )
    panel["AIRCRAFT_CORRECTION"] = "None"

    sq_a380_to_77w = (
        panel["UNIQUE_CARRIER_NAME"]
        .str.contains("Singapore Airlines", case=False, na=False)
        & panel["AIRCRAFT_DESCRIPTION_REPORTED"]
        .str.contains(r"A[- ]?380|A380", case=False, regex=True, na=False)
        & panel["REPORTED_SEATS_PER_DEPARTURE"].between(250, 300)
    )

    panel.loc[sq_a380_to_77w, "AIRCRAFT_TYPE_ANALYSIS"] = "637"
    panel.loc[
        sq_a380_to_77w, "AIRCRAFT_DESCRIPTION_ANALYSIS"
    ] = "Boeing 777-300ER"
    panel.loc[
        sq_a380_to_77w, "AIRCRAFT_CORRECTION"
    ] = "SQ low-seat A380 code treated as 777-300ER"
    panel["SQ_A380_TO_77W_CORRECTION"] = sq_a380_to_77w


    # Apply the author's manual review only to SQ and OZ in the studied years.
    a350_to_a380 = (
        panel["UNIQUE_CARRIER"].isin(["SQ", "OZ"])
        & panel["YEAR"].isin([2019, 2023, 2024, 2025])
        & panel["AIRCRAFT_DESCRIPTION_REPORTED"]
        .str.contains(r"A[- ]?350|A350", case=False, regex=True, na=False)
        & panel["REPORTED_SEATS_PER_DEPARTURE"].ge(400)
    )
    panel.loc[a350_to_a380, "AIRCRAFT_TYPE_ANALYSIS"] = "882"
    panel.loc[a350_to_a380, "AIRCRAFT_DESCRIPTION_ANALYSIS"] = "Airbus A380-800 (manual carrier-specific inference)"
    panel.loc[a350_to_a380, "AIRCRAFT_CORRECTION"] = "SQ/OZ A350-coded 400+ seat record manually assigned to A380"
    panel["A350_TO_A380_CORRECTION"] = a350_to_a380

    return panel


def load_t100_panel(inputs):
    """Build the passenger panel and audit tables without changing reported fields."""
    t100_frames = [
        load_t100_year(inputs[f"T100_{year}"])
        for year in (2019, 2023, 2024, 2025)
    ]
    t100_raw = pd.concat(t100_frames, ignore_index=True)
    for expected_year, frame in zip((2019, 2023, 2024, 2025), t100_frames):
        if set(frame["YEAR"].dropna()) != {expected_year} or set(frame["MONTH"].dropna()) != set(range(1, 13)):
            raise ValueError(f"T100_{expected_year}.zip must contain that full calendar year.")

    aircraft_lookup = pd.read_csv(
        inputs["aircraft_lookup"],
        dtype={"Code": "string"},
    )
    aircraft_lookup["Code"] = aircraft_lookup["Code"].str.zfill(3)
    aircraft_lookup = aircraft_lookup.rename(
        columns={
            "Code": "AIRCRAFT_TYPE_REPORTED",
            "Description": "AIRCRAFT_DESCRIPTION_REPORTED",
        }
    )

    t100_raw = t100_raw.merge(
        aircraft_lookup[
            ["AIRCRAFT_TYPE_REPORTED", "AIRCRAFT_DESCRIPTION_REPORTED"]
        ],
        how="left",
        on="AIRCRAFT_TYPE_REPORTED",
        validate="many_to_one",
    )

    t100_inventory = (
        t100_raw.groupby("YEAR", observed=True)
        .agg(
            rows=("YEAR", "size"),
            months=("MONTH", "nunique"),
            carriers=("UNIQUE_CARRIER", "nunique"),
            origin_airports=("ORIGIN", "nunique"),
            destination_airports=("DEST", "nunique"),
            aircraft_codes=("AIRCRAFT_TYPE_REPORTED", "nunique"),
            aircraft_lookup_match=("AIRCRAFT_DESCRIPTION_REPORTED", lambda x: x.notna().mean()),
        )
        .reset_index()
    )


    us_to_asia = (
        t100_raw["ORIGIN_COUNTRY"].eq("US")
        & t100_raw["DEST_COUNTRY"].isin(ASIA_COUNTRIES)
    )
    asia_to_us = (
        t100_raw["DEST_COUNTRY"].eq("US")
        & t100_raw["ORIGIN_COUNTRY"].isin(ASIA_COUNTRIES)
    )

    scheduled_passenger_base = t100_raw.loc[
        (us_to_asia | asia_to_us)
        & t100_raw["CLASS"].eq("F")
        & t100_raw["DEPARTURES_PERFORMED"].gt(0)
        & t100_raw["SEATS"].gt(0)
    ].copy()

    if scheduled_passenger_base["AIRCRAFT_DESCRIPTION_REPORTED"].isna().any():
        raise ValueError("Unmatched aircraft codes in the analytical market; refresh the reference table.")

    origin_is_us = scheduled_passenger_base["ORIGIN_COUNTRY"].eq("US")
    scheduled_passenger_base["US_AIRPORT"] = np.where(
        origin_is_us,
        scheduled_passenger_base["ORIGIN"],
        scheduled_passenger_base["DEST"],
    )
    scheduled_passenger_base["ASIA_AIRPORT"] = np.where(
        origin_is_us,
        scheduled_passenger_base["DEST"],
        scheduled_passenger_base["ORIGIN"],
    )
    scheduled_passenger_base["ASIA_COUNTRY"] = np.where(
        origin_is_us,
        scheduled_passenger_base["DEST_COUNTRY_NAME"],
        scheduled_passenger_base["ORIGIN_COUNTRY_NAME"],
    )
    scheduled_passenger_base["DIRECTION"] = np.where(
        origin_is_us, "US→Asia", "Asia→US"
    )
    scheduled_passenger_base["ROUTE"] = (
        scheduled_passenger_base["US_AIRPORT"]
        + "–"
        + scheduled_passenger_base["ASIA_AIRPORT"]
    )




    scheduled_passenger_base["US_MARKET"] = (
        scheduled_passenger_base["US_AIRPORT"].map(classify_us_market)
    )
    scheduled_passenger_base["REPORTED_SEATS_PER_DEPARTURE"] = (
        scheduled_passenger_base["SEATS"]
        / scheduled_passenger_base["DEPARTURES_PERFORMED"]
    )

    sample_counts_before_qc = (
        scheduled_passenger_base.groupby("YEAR", observed=True)
        .agg(
            rows=("YEAR", "size"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            seats=("SEATS", "sum"),
            passengers=("PASSENGERS", "sum"),
            freight_lb=("FREIGHT", "sum"),
        )
        .reset_index()
    )

    FREIGHTER_DESCRIPTION_PATTERN = (
        r"freighter|beluga|747[- ]?400f|il[- ]?96[- ]?400t|ilyushiin il-96-400t"
    )

    scheduled_passenger_base["EXPLICIT_FREIGHTER_CODE"] = (
        scheduled_passenger_base["AIRCRAFT_DESCRIPTION_REPORTED"]
        .str.contains(
            FREIGHTER_DESCRIPTION_PATTERN,
            case=False,
            regex=True,
            na=False,
        )
    )

    excluded_freighter_rows = scheduled_passenger_base.loc[
        scheduled_passenger_base["EXPLICIT_FREIGHTER_CODE"]
    ].copy()

    panel = scheduled_passenger_base.loc[
        ~scheduled_passenger_base["EXPLICIT_FREIGHTER_CODE"]
    ].copy()

    panel = correct_aircraft_labels(panel)

    freighter_exclusion_summary = (
        excluded_freighter_rows.groupby(
            ["AIRCRAFT_TYPE_REPORTED", "AIRCRAFT_DESCRIPTION_REPORTED"],
            observed=True,
        )
        .agg(
            rows=("YEAR", "size"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            seats=("SEATS", "sum"),
            passengers=("PASSENGERS", "sum"),
            freight_lb=("FREIGHT", "sum"),
        )
        .reset_index()
    )

    sq_correction_summary = (
        panel.loc[panel["SQ_A380_TO_77W_CORRECTION"]]
        .groupby(
            [
                "YEAR",
                "ROUTE",
                "AIRCRAFT_TYPE_REPORTED",
                "AIRCRAFT_DESCRIPTION_REPORTED",
                "AIRCRAFT_DESCRIPTION_ANALYSIS",
            ],
            observed=True,
        )
        .agg(
            rows=("YEAR", "size"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            seats=("SEATS", "sum"),
            min_reported_gauge=("REPORTED_SEATS_PER_DEPARTURE", "min"),
            median_reported_gauge=("REPORTED_SEATS_PER_DEPARTURE", "median"),
            max_reported_gauge=("REPORTED_SEATS_PER_DEPARTURE", "max"),
        )
        .reset_index()
    )




    WIDEBODY_FAMILIES = {
        "A300/A310", "A330", "A340", "A350", "A380", "747",
        "767", "777", "787", "MD-11/DC-10",
    }

    panel["AIRCRAFT_FAMILY"] = (
        panel["AIRCRAFT_DESCRIPTION_ANALYSIS"].map(aircraft_family)
    )
    panel["WIDEBODY"] = panel["AIRCRAFT_FAMILY"].isin(WIDEBODY_FAMILIES)
    panel["DATE"] = pd.to_datetime(
        dict(
            year=panel["YEAR"].astype(int),
            month=panel["MONTH"].astype(int),
            day=1,
        )
    )
    panel["PASSENGER_LOAD_FACTOR"] = panel["PASSENGERS"] / panel["SEATS"]
    panel["SEATS_PER_DEPARTURE"] = (
        panel["SEATS"] / panel["DEPARTURES_PERFORMED"]
    )
    panel["SMALL_MONTHLY_OPERATION"] = panel["DEPARTURES_PERFORMED"].lt(5)

    # Preserve the reported freight field, then build a separate reliable measure.
    panel["FREIGHT_TONNES_REPORTED"] = panel["FREIGHT"] * 0.00045359237
    panel["FREIGHT_PER_PASSENGER_LB"] = (
        panel["FREIGHT"] / panel["PASSENGERS"].replace(0, np.nan)
    )
    panel["FREIGHT_RATIO_ELIGIBLE"] = (
        panel["PASSENGERS"].gt(0) & panel["FREIGHT"].notna()
    )
    panel["MECHANICAL_200LB_ROW"] = (
        panel["FREIGHT_RATIO_ELIGIBLE"]
        & panel["FREIGHT_PER_PASSENGER_LB"].between(199.5, 200.5)
    )

    freight_reporting_audit = (
        panel.groupby(
            ["YEAR", "UNIQUE_CARRIER", "UNIQUE_CARRIER_NAME"],
            observed=True,
        )
        .agg(
            rows=("YEAR", "size"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            eligible_rows=("FREIGHT_RATIO_ELIGIBLE", "sum"),
            mechanical_200lb_rows=("MECHANICAL_200LB_ROW", "sum"),
            reported_freight_tonnes=("FREIGHT_TONNES_REPORTED", "sum"),
        )
        .reset_index()
    )
    freight_reporting_audit["mechanical_200lb_share"] = (
        freight_reporting_audit["mechanical_200lb_rows"]
        / freight_reporting_audit["eligible_rows"].replace(0, np.nan)
    )
    freight_reporting_audit["unreliable_freight"] = (
        freight_reporting_audit["eligible_rows"].ge(12)
        & freight_reporting_audit["mechanical_200lb_share"].ge(0.60)
    )
    freight_reporting_audit["quality_reason"] = np.where(
        freight_reporting_audit["unreliable_freight"],
        "Freight mechanically follows approximately 200 lb per passenger",
        "No mechanical 200-lb pattern detected",
    )

    unreliable_carrier_years = freight_reporting_audit.loc[
        freight_reporting_audit["unreliable_freight"],
        ["YEAR", "UNIQUE_CARRIER"],
    ].assign(FREIGHT_RELIABLE=False)

    panel = panel.merge(
        unreliable_carrier_years,
        on=["YEAR", "UNIQUE_CARRIER"],
        how="left",
        validate="many_to_one",
    )
    panel["FREIGHT_RELIABLE"] = ~panel["FREIGHT_RELIABLE"].eq(False)
    panel["FREIGHT_QUALITY_REASON"] = np.where(
        panel["FREIGHT_RELIABLE"],
        "No carrier-year mechanical pattern detected",
        "Carrier-year freight follows approximately 200 lb per passenger",
    )
    panel["FREIGHT_TONNES_RELIABLE"] = panel[
        "FREIGHT_TONNES_REPORTED"
    ].where(panel["FREIGHT_RELIABLE"])
    panel["RELIABLE_FREIGHT_DEPARTURES"] = panel[
        "DEPARTURES_PERFORMED"
    ].where(panel["FREIGHT_RELIABLE"], 0)



    annual_market_summary = (
        panel.groupby(["YEAR", "US_MARKET"], observed=True)
        .agg(
            rows=("YEAR", "size"),
            carriers=("UNIQUE_CARRIER", "nunique"),
            routes=("ROUTE", "nunique"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            seats=("SEATS", "sum"),
            passengers=("PASSENGERS", "sum"),
            freight_tonnes_reported=("FREIGHT_TONNES_REPORTED", "sum"),
            freight_tonnes=("FREIGHT_TONNES_RELIABLE", reliable_sum),
            reliable_freight_departures=("RELIABLE_FREIGHT_DEPARTURES", "sum"),
            small_monthly_rows=("SMALL_MONTHLY_OPERATION", "sum"),
        )
        .reset_index()
    )
    annual_market_summary["seats_per_departure"] = (
        annual_market_summary["seats"] / annual_market_summary["departures"]
    )
    annual_market_summary["passenger_load_factor"] = (
        annual_market_summary["passengers"] / annual_market_summary["seats"]
    )
    annual_market_summary["freight_reliable_departure_share"] = (
        annual_market_summary["reliable_freight_departures"]
        / annual_market_summary["departures"]
    )
    annual_market_summary["freight_tonnes_per_departure"] = (
        annual_market_summary["freight_tonnes"]
        / annual_market_summary["reliable_freight_departures"].replace(0, np.nan)
    )


    FAMILY_GAUGE_BOUNDS = {
        "A380": (350, 620),
        "747": (220, 600),
        "777": (180, 520),
        "787": (170, 400),
        "A350": (180, 460),
        "A340": (180, 430),
        "A330": (160, 420),
        "767": (120, 350),
        "A320 family": (70, 260),
        "737": (60, 260),
        "757": (100, 280),
    }

    carrier_code_reference = (
        panel.groupby(
            ["UNIQUE_CARRIER", "AIRCRAFT_TYPE_ANALYSIS"], observed=True
        )
        .agg(
            reference_seats=("SEATS", "sum"),
            reference_departures=("DEPARTURES_PERFORMED", "sum"),
        )
        .reset_index()
    )
    carrier_code_reference["CARRIER_ANALYSIS_TYPE_REFERENCE_GAUGE"] = (
        carrier_code_reference["reference_seats"]
        / carrier_code_reference["reference_departures"]
    )
    panel = panel.merge(
        carrier_code_reference[
            [
                "UNIQUE_CARRIER",
                "AIRCRAFT_TYPE_ANALYSIS",
                "CARRIER_ANALYSIS_TYPE_REFERENCE_GAUGE",
            ]
        ],
        how="left",
        on=["UNIQUE_CARRIER", "AIRCRAFT_TYPE_ANALYSIS"],
        validate="many_to_one",
    )

    bounds = panel["AIRCRAFT_FAMILY"].map(FAMILY_GAUGE_BOUNDS)
    lower_bound = bounds.map(
        lambda value: value[0] if isinstance(value, tuple) else np.nan
    )
    upper_bound = bounds.map(
        lambda value: value[1] if isinstance(value, tuple) else np.nan
    )

    panel["OUTSIDE_BROAD_FAMILY_RANGE"] = (
        panel["SEATS_PER_DEPARTURE"].lt(lower_bound)
        | panel["SEATS_PER_DEPARTURE"].gt(upper_bound)
    )
    panel["LARGE_WITHIN_CARRIER_CODE_DEVIATION"] = (
        (
            panel["SEATS_PER_DEPARTURE"]
            - panel["CARRIER_ANALYSIS_TYPE_REFERENCE_GAUGE"]
        ).abs().gt(40)
        & (
            panel["SEATS_PER_DEPARTURE"]
            / panel["CARRIER_ANALYSIS_TYPE_REFERENCE_GAUGE"]
            - 1
        ).abs().gt(0.20)
    )

    sia_a350_ulr_valid = (
        panel["UNIQUE_CARRIER_NAME"].str.contains(
            "Singapore Airlines", case=False, na=False
        )
        & panel["AIRCRAFT_FAMILY"].eq("A350")
        & panel["SEATS_PER_DEPARTURE"].between(150, 170)
    )
    ana_777_premium_valid = (
        panel["UNIQUE_CARRIER_NAME"].str.contains(
            "All Nippon", case=False, na=False
        )
        & panel["AIRCRAFT_FAMILY"].eq("777")
        & panel["SEATS_PER_DEPARTURE"].between(195, 225)
    )

    panel["KNOWN_VALID_CONFIGURATION"] = sia_a350_ulr_valid | ana_777_premium_valid
    panel["KNOWN_VALID_CONFIGURATION_REASON"] = np.select(
        [sia_a350_ulr_valid, ana_777_premium_valid],
        [
            "Confirmed SIA A350-900ULR low-density configuration",
            "Confirmed ANA premium-heavy 777 configuration",
        ],
        default="",
    )

    panel["PAIR_REVIEW_REASON"] = np.select(
        [
            panel["OUTSIDE_BROAD_FAMILY_RANGE"],
            panel["LARGE_WITHIN_CARRIER_CODE_DEVIATION"],
        ],
        [
            "Outside broad family gauge range",
            "Large deviation from carrier-analysis-type reference gauge",
        ],
        default="",
    )

    known_valid_aircraft_pairs = (
        panel.loc[panel["KNOWN_VALID_CONFIGURATION"]]
        .groupby(
            [
                "YEAR", "UNIQUE_CARRIER_NAME", "ROUTE",
                "AIRCRAFT_TYPE_REPORTED", "AIRCRAFT_DESCRIPTION_REPORTED",
                "AIRCRAFT_FAMILY", "KNOWN_VALID_CONFIGURATION_REASON",
            ],
            observed=True,
        )
        .agg(
            rows=("YEAR", "size"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            min_gauge=("SEATS_PER_DEPARTURE", "min"),
            median_gauge=("SEATS_PER_DEPARTURE", "median"),
            max_gauge=("SEATS_PER_DEPARTURE", "max"),
        )
        .reset_index()
        .sort_values(["departures", "rows"], ascending=False)
    )

    suspicious_aircraft_pairs = (
        panel.loc[
            panel["PAIR_REVIEW_REASON"].ne("")
            & ~panel["SQ_A380_TO_77W_CORRECTION"]
            & ~panel["A350_TO_A380_CORRECTION"]
            & ~panel["KNOWN_VALID_CONFIGURATION"]
            & panel["DEPARTURES_PERFORMED"].ge(5)
        ]
        .groupby(
            [
                "YEAR", "UNIQUE_CARRIER_NAME", "ROUTE",
                "AIRCRAFT_TYPE_REPORTED", "AIRCRAFT_DESCRIPTION_REPORTED",
                "AIRCRAFT_FAMILY", "PAIR_REVIEW_REASON",
            ],
            observed=True,
        )
        .agg(
            rows=("YEAR", "size"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            seats=("SEATS", "sum"),
            min_gauge=("SEATS_PER_DEPARTURE", "min"),
            median_gauge=("SEATS_PER_DEPARTURE", "median"),
            max_gauge=("SEATS_PER_DEPARTURE", "max"),
            reference_gauge=("CARRIER_ANALYSIS_TYPE_REFERENCE_GAUGE", "median"),
        )
        .reset_index()
        .sort_values(["departures", "rows"], ascending=False)
    )


    panel["UNRESOLVED_AIRCRAFT_PAIR"] = (
        panel["PAIR_REVIEW_REASON"].ne("")
        & ~panel["SQ_A380_TO_77W_CORRECTION"]
        & ~panel["A350_TO_A380_CORRECTION"]
        & ~panel["KNOWN_VALID_CONFIGURATION"]
    )

    a350_to_a380_log = (
        panel.loc[panel["A350_TO_A380_CORRECTION"]]
        .groupby(
            [
                "YEAR", "UNIQUE_CARRIER", "UNIQUE_CARRIER_NAME", "ROUTE",
                "AIRCRAFT_TYPE_REPORTED", "AIRCRAFT_DESCRIPTION_REPORTED",
                "AIRCRAFT_DESCRIPTION_ANALYSIS",
            ],
            observed=True,
        )
        .agg(
            rows=("YEAR", "size"),
            departures=("DEPARTURES_PERFORMED", "sum"),
            seats=("SEATS", "sum"),
            min_gauge=("SEATS_PER_DEPARTURE", "min"),
            median_gauge=("SEATS_PER_DEPARTURE", "median"),
            max_gauge=("SEATS_PER_DEPARTURE", "max"),
        )
        .reset_index()
        .sort_values(["departures", "rows"], ascending=False)
    )

    qc_summary = pd.DataFrame(
        {
            "rule": [
                "Explicit freighter rows removed",
                "SQ low-seat A380-coded rows analyzed as 777-300ER",
                "A350-coded 400+ seat rows analyzed as A380 family",
                "Carrier-years with unreliable mechanical freight",
                "Confirmed premium/ULR configurations retained",
                "Remaining unresolved aircraft-seat rows excluded from the model",
            ],
            "count": [
                len(excluded_freighter_rows),
                int(panel["SQ_A380_TO_77W_CORRECTION"].sum()),
                int(panel["A350_TO_A380_CORRECTION"].sum()),
                int(freight_reporting_audit["unreliable_freight"].sum()),
                int(panel["KNOWN_VALID_CONFIGURATION"].sum()),
                int(panel["UNRESOLVED_AIRCRAFT_PAIR"].sum()),
            ],
        }
    )


    return {"panel": panel, "t100_inventory": t100_inventory, "sample_counts_before_qc": sample_counts_before_qc, "qc_summary": qc_summary, "a350_to_a380_log": a350_to_a380_log, "sq_correction_summary": sq_correction_summary, "freighter_exclusion_summary": freighter_exclusion_summary, "freight_reporting_audit": freight_reporting_audit, "known_valid_aircraft_pairs": known_valid_aircraft_pairs, "suspicious_aircraft_pairs": suspicious_aircraft_pairs, "annual_market_summary": annual_market_summary, "excluded_freighter_rows": excluded_freighter_rows}

TAIWAN_AIRLINE_ENGLISH = {
    "中華": "China Airlines",
    "長榮": "EVA Air",
    "國泰": "Cathay Pacific",
    "星宇": "Starlux",
    "香港": "Hong Kong Airlines",
    "香港快運": "HK Express",
    "大灣區": "Greater Bay Airlines",
}





def parse_taiwan_tpe_archive(path: Path) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    with ZipFile(path) as archive:
        workbook_names = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".xls")
            and not name.startswith("__MACOSX")
        ]
        for workbook_name in sorted(workbook_names):
            roc_year = int(Path(workbook_name).name[:3])
            year = roc_year + 1911
            workbook_bytes = BytesIO(archive.read(workbook_name))
            frame = pd.read_excel(
                workbook_bytes,
                sheet_name="53-1",
                header=None,
            )

            route_zh: str | None = None
            for _, row in frame.iloc[9:].iterrows():
                sequence = row.iloc[0]
                route_cell = row.iloc[1]
                airline_cell = row.iloc[2]

                if pd.notna(route_cell):
                    candidate_route = str(route_cell).strip()
                    if "航" not in candidate_route and candidate_route != "總計":
                        route_zh = candidate_route

                sequence_number = pd.to_numeric(sequence, errors="coerce")
                if (
                    pd.isna(sequence_number)
                    or pd.isna(airline_cell)
                    or route_zh is None
                ):
                    continue

                records.append(
                    {
                        "year": year,
                        "route_zh": route_zh,
                        "airline_zh": str(airline_cell).strip(),
                        "flights": pd.to_numeric(row.iloc[3], errors="coerce"),
                        "seats": pd.to_numeric(row.iloc[4], errors="coerce"),
                        "passengers": pd.to_numeric(row.iloc[5], errors="coerce"),
                        "reported_load_factor_pct": pd.to_numeric(
                            row.iloc[6], errors="coerce"
                        ),
                        "inbound_flights": pd.to_numeric(row.iloc[7], errors="coerce"),
                        "inbound_seats": pd.to_numeric(row.iloc[8], errors="coerce"),
                        "inbound_passengers": pd.to_numeric(row.iloc[9], errors="coerce"),
                        "outbound_flights": pd.to_numeric(row.iloc[11], errors="coerce"),
                        "outbound_seats": pd.to_numeric(row.iloc[12], errors="coerce"),
                        "outbound_passengers": pd.to_numeric(row.iloc[13], errors="coerce"),
                    }
                )

    result = pd.DataFrame.from_records(records)
    result["airline"] = (
        result["airline_zh"].map(TAIWAN_AIRLINE_ENGLISH)
        .fillna(result["airline_zh"])
    )
    result["seats_per_flight"] = result["seats"] / result["flights"]
    result["computed_load_factor"] = result["passengers"] / result["seats"]
    result["empty_seats_per_flight"] = (
        result["seats"] - result["passengers"]
    ) / result["flights"]
    result["flight_balance_check"] = (
        result["flights"]
        - result["inbound_flights"]
        - result["outbound_flights"]
    )
    return result


def load_taiwan_data(inputs):
    """Read sheet 53-1 and reconcile traffic totals for the Hong Kong case."""
    tpe_annual = parse_taiwan_tpe_archive(inputs["taiwan_annual"])

    tpe_quality = (
        tpe_annual.groupby("year", observed=True)
        .agg(
            rows=("year", "size"),
            destinations=("route_zh", "nunique"),
            airlines=("airline_zh", "nunique"),
            flights=("flights", "sum"),
            seats=("seats", "sum"),
            passengers=("passengers", "sum"),
            flight_balance_errors=("flight_balance_check", lambda x: x.ne(0).sum()),
        )
        .reset_index()
    )
    tpe_quality["computed_load_factor"] = (
        tpe_quality["passengers"] / tpe_quality["seats"]
    )

    tpe_hkg_airline_year = tpe_annual.loc[
        tpe_annual["route_zh"].eq("香港")
    ].copy()

    tpe_hkg_total = (
        tpe_hkg_airline_year.groupby("year", observed=True)
        .agg(
            flights=("flights", "sum"),
            seats=("seats", "sum"),
            passengers=("passengers", "sum"),
        )
        .reset_index()
    )
    tpe_hkg_total["seats_per_flight"] = (
        tpe_hkg_total["seats"] / tpe_hkg_total["flights"]
    )
    tpe_hkg_total["passenger_load_factor"] = (
        tpe_hkg_total["passengers"] / tpe_hkg_total["seats"]
    )

    tpe_hkg_2019 = (
        tpe_hkg_airline_year.loc[tpe_hkg_airline_year["year"].eq(2019)]
        .rename(
            columns={
                "flights": "flights_2019",
                "seats_per_flight": "seats_per_flight_2019",
                "computed_load_factor": "passenger_load_factor_2019",
                "empty_seats_per_flight": "empty_seats_per_flight_2019",
            }
        )
    )
    tpe_hkg_2025 = (
        tpe_hkg_airline_year.loc[tpe_hkg_airline_year["year"].eq(2025)]
        .rename(
            columns={
                "flights": "flights_2025",
                "seats_per_flight": "seats_per_flight_2025",
                "computed_load_factor": "passenger_load_factor_2025",
                "empty_seats_per_flight": "empty_seats_per_flight_2025",
            }
        )
    )
    tpe_hkg_2019_vs_2025 = tpe_hkg_2019[
        [
            "airline_zh",
            "airline",
            "flights_2019",
            "seats_per_flight_2019",
            "passenger_load_factor_2019",
            "empty_seats_per_flight_2019",
        ]
    ].merge(
        tpe_hkg_2025[
            [
                "airline_zh",
                "flights_2025",
                "seats_per_flight_2025",
                "passenger_load_factor_2025",
                "empty_seats_per_flight_2025",
            ]
        ],
        on="airline_zh",
        how="inner",
        validate="one_to_one",
    )
    tpe_hkg_2019_vs_2025["flight_change_pct"] = (
        tpe_hkg_2019_vs_2025["flights_2025"]
        / tpe_hkg_2019_vs_2025["flights_2019"]
        - 1
    )
    tpe_hkg_2019_vs_2025["gauge_change"] = (
        tpe_hkg_2019_vs_2025["seats_per_flight_2025"]
        - tpe_hkg_2019_vs_2025["seats_per_flight_2019"]
    )
    tpe_hkg_2019_vs_2025["load_factor_change_pp"] = 100 * (
        tpe_hkg_2019_vs_2025["passenger_load_factor_2025"]
        - tpe_hkg_2019_vs_2025["passenger_load_factor_2019"]
    )


    if not tpe_quality["flight_balance_errors"].eq(0).all():
        raise ValueError("Taiwan CAA inbound/outbound flights do not reconcile.")
    if set(tpe_quality["year"]) != {2019, 2023, 2024, 2025}:
        raise ValueError("Taiwan archive must contain 2019 and 2023–2025.")

    return {"tpe_quality": tpe_quality, "tpe_hkg_airline_year": tpe_hkg_airline_year, "tpe_hkg_total": tpe_hkg_total, "tpe_hkg_2019_vs_2025": tpe_hkg_2019_vs_2025}
