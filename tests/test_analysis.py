"""Check correction scope and departure-weighted aggregation."""
import unittest
import numpy as np
import pandas as pd
from src.data import correct_aircraft_labels
from src.models import aggregate_expected_gauge, fit_weighted_gauge_model


class AirlineAnalysisTests(unittest.TestCase):
    def test_corrections_preserve_reported_fields_and_carrier_scope(self):
        frame = pd.DataFrame({
            "UNIQUE_CARRIER": ["SQ", "OZ", "XX", "SQ", "SQ"],
            "UNIQUE_CARRIER_NAME": ["Singapore Airlines", "Asiana", "Other", "Singapore Airlines", "Singapore Airlines"],
            "YEAR": [2025, 2024, 2025, 2023, 2025],
            "AIRCRAFT_TYPE_REPORTED": ["359", "359", "359", "882", "359"],
            "AIRCRAFT_DESCRIPTION_REPORTED": ["Airbus A350"] * 3 + ["Airbus A380", "Airbus A350"],
            "REPORTED_SEATS_PER_DEPARTURE": [415, 493, 480, 264, 161],
        })
        result = correct_aircraft_labels(frame)
        self.assertEqual(result.AIRCRAFT_TYPE_ANALYSIS.tolist(), ["882", "882", "359", "637", "359"])
        pd.testing.assert_frame_equal(result[frame.columns], frame)

    def test_weighted_fit_uses_departures(self):
        data = pd.DataFrame({"route": ["a"] * 6, "frequency": [1, 2, 3, 4, 5, 6],
            "departures": [10, 10, 10, 40, 40, 40],
            "seats_per_departure": [202, 199, 198, 190, 189, 182]})
        _, fitted, metrics = fit_weighted_gauge_model(data, ["route"], ["frequency"], "test")
        residual = data.seats_per_departure - fitted
        self.assertAlmostEqual(np.average(residual, weights=data.departures), 0, places=8)
        self.assertIn("In-sample", metrics["evaluation"])

    def test_annual_gauge_uses_capacity_totals(self):
        data = pd.DataFrame({"YEAR": [2025, 2025], "MONTH": [1, 2], "ROUTE": ["A–B"] * 2,
            "UNIQUE_CARRIER": ["XX"] * 2, "UNIQUE_CARRIER_NAME": ["Example"] * 2,
            "US_AIRPORT": ["A"] * 2, "ASIA_AIRPORT": ["B"] * 2,
            "departures": [10, 30], "seats": [2000, 9000], "passengers": [1800, 8100],
            "expected": [210, 260], "residual": [-10, 40], "distance_miles": [6000, 6000]})
        result = aggregate_expected_gauge(data, "expected", "residual").iloc[0]
        self.assertEqual(result.actual_gauge, 275)
        self.assertEqual(result.expected_gauge, 247.5)
        self.assertEqual(result.gauge_residual, 27.5)


if __name__ == "__main__":
    unittest.main()
