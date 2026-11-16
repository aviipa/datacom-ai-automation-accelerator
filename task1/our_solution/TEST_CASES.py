#!/usr/bin/env python3
"""
Unit test suite for Task 1: Bug reproduction and verification of process_data_final.py.
"""

import csv
import json
import os
import sys
import tempfile
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

import process_data as legacy_module
import process_data_final as fixed_module


class TestDataProcessor(unittest.TestCase):
    """Tests covering legacy bug reproduction and refactored DataProcessor behavior."""

    def setUp(self) -> None:
        """Create temporary directory and sample CSV fixtures for isolated testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.customers_csv = os.path.join(self.temp_dir.name, "customers.csv")
        self.transactions_csv = os.path.join(self.temp_dir.name, "transactions.csv")

        with open(self.customers_csv, "w", encoding="utf-8", newline="") as f:
            f.write(
                "customer_id,name,email,join_date\n"
                "C001,John Smith,john.smith@email.com,2023-01-15\n"
                "C002,Jane Doe,jane.doe@email.com,2023-02-20\n"
                "C003,Bob Johnson,bob.johnson@email.com,2023-03-10\n"
                "C004,Alice Brown,alice.brown@email.com,2023-04-05\n"
                "C005,Charlie Wilson,charlie.wilson@email.com,2023-05-12 \n"
            )

        with open(self.transactions_csv, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,150.50,2024-01-10,electronics\n"
                "T002,C002,75.25,2024-01-11,clothing\n"
                "T003,C001,200.00,2024-01-12,electronics\n"
                "T004,C003,45.75,2024-01-13,food\n"
                "T005,C002,120.00,2024-01-14,clothing\n"
                "T006,C004,89.99,2024-01-15,books\n"
                "T007,C005,300.00,2024-01-16,electronics\n"
                "T008,C001,25.50,2024-01-17,food\n"
                "T009,C003,180.00,2024-01-18,clothing\n"
                "T010,C002,95.25,2024-01-19,books\n"
            )

    def tearDown(self) -> None:
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def test_legacy_bug_reproduction_dict_of_lists(self) -> None:
        """Reproduce AttributeError on .keys() in legacy code and verify normalized export fix."""
        legacy_out = os.path.join(self.temp_dir.name, "legacy_export.csv")
        fixed_out = os.path.join(self.temp_dir.name, "fixed_export.csv")

        legacy_proc = legacy_module.DataProcessor(self.customers_csv)
        legacy_proc.customers = {
            "C001": ["John Smith", "john.smith@email.com", "2023-01-15", 376.0, 3]
        }
        with self.assertLogs(legacy_module.logger, level="ERROR") as log_ctx:
            self.assertFalse(legacy_proc.export_customer_data(legacy_out, "csv"))
        self.assertTrue(
            any("has no attribute 'keys'" in msg for msg in log_ctx.output),
            f"Expected AttributeError mentioning .keys(), got: {log_ctx.output}",
        )

        fixed_proc = fixed_module.DataProcessor(self.customers_csv)
        fixed_proc.customers = {
            "C001": ["John Smith", "john.smith@email.com", "2023-01-15", 376.0, 3]
        }
        self.assertTrue(fixed_proc.export_customer_data(fixed_out, "csv"))
        with open(fixed_out, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_id"], "C001")
        self.assertEqual(rows[0]["name"], "John Smith")

    def test_legacy_bug_reproduction_list_of_dicts(self) -> None:
        """Reproduce legacy failure on list-typed customers container and verify fixed export."""
        legacy_list_out = os.path.join(self.temp_dir.name, "legacy_list_export.csv")
        fixed_list_out = os.path.join(self.temp_dir.name, "fixed_list_export.csv")

        legacy_proc = legacy_module.DataProcessor(self.customers_csv)
        legacy_proc.customers = [
            {"customer_id": "C001", "name": "John Smith", "email": "john@email.com"}
        ]
        with self.assertLogs(legacy_module.logger, level="ERROR"):
            self.assertFalse(legacy_proc.export_customer_data(legacy_list_out, "csv"))

        fixed_proc = fixed_module.DataProcessor(self.customers_csv)
        fixed_proc.customers = [
            {"customer_id": "C001", "name": "John Smith", "email": "john@email.com"}
        ]
        self.assertTrue(fixed_proc.export_customer_data(fixed_list_out, "csv"))
        with open(fixed_list_out, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_id"], "C001")

    def test_load_data_count_and_fields(self) -> None:
        """Verify load_data() parses all customer rows and initializes aggregates to zero."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        self.assertTrue(processor.load_data())
        self.assertEqual(len(processor.customers), 5)
        self.assertEqual(processor.customers["C001"]["total_spent"], 0.0)
        self.assertEqual(processor.customers["C001"]["transaction_count"], 0)

    def test_load_data_strips_trailing_whitespace(self) -> None:
        """Verify load_data() strips trailing whitespace from CSV field values."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        self.assertTrue(processor.load_data())
        self.assertEqual(processor.customers["C005"]["join_date"], "2023-05-12")

    def test_load_data_missing_file_returns_false(self) -> None:
        """Verify load_data() logs an error and returns False when the CSV is missing."""
        missing = fixed_module.DataProcessor(
            os.path.join(self.temp_dir.name, "missing.csv")
        )
        with self.assertLogs(fixed_module.logger, level="ERROR"):
            self.assertFalse(missing.load_data())

    def test_process_transactions_updates_customer_totals(self) -> None:
        """Verify transaction loading updates customer total_spent and transaction_count."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        self.assertTrue(processor.load_data())
        self.assertTrue(processor.process_transactions(self.transactions_csv))

        self.assertEqual(len(processor.transactions), 10)
        self.assertAlmostEqual(processor.customers["C001"]["total_spent"], 376.00)
        self.assertEqual(processor.customers["C001"]["transaction_count"], 3)
        self.assertAlmostEqual(processor.customers["C002"]["total_spent"], 290.50)
        self.assertEqual(processor.customers["C002"]["transaction_count"], 3)
        self.assertAlmostEqual(processor.customers["C005"]["total_spent"], 300.00)
        self.assertEqual(processor.customers["C005"]["transaction_count"], 1)

    def test_process_transactions_tracks_unknown_customers(self) -> None:
        """Verify unknown-customer transactions are isolated without skewing matched metrics."""
        bad_tx_csv = os.path.join(self.temp_dir.name, "unknown_customer_tx.csv")
        with open(bad_tx_csv, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,100.00,2024-01-10,electronics\n"
                "T002,C999,500.00,2024-01-11,electronics\n"
            )

        processor = fixed_module.DataProcessor(self.customers_csv)
        self.assertTrue(processor.load_data())
        with self.assertLogs(fixed_module.logger, level="WARNING") as log_ctx:
            self.assertTrue(processor.process_transactions(bad_tx_csv))

        self.assertEqual(len(processor.transactions), 1)
        self.assertEqual(len(processor.unmatched_transactions), 1)
        self.assertTrue(any("unknown customer: C999" in m for m in log_ctx.output))

        metrics = processor.calculate_customer_metrics()
        self.assertEqual(metrics["total_transactions"], 1)
        self.assertAlmostEqual(metrics["total_revenue"], 100.00)
        self.assertAlmostEqual(metrics["average_transaction_value"], 100.00)

    def test_process_transactions_skips_invalid_amount(self) -> None:
        """Verify non-numeric transaction amounts log a warning without aborting valid rows."""
        bad_tx_csv = os.path.join(self.temp_dir.name, "bad_amount_tx.csv")
        with open(bad_tx_csv, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,100.00,2024-01-10,electronics\n"
                "T003,C001,not_a_number,2024-01-12,food\n"
            )

        processor = fixed_module.DataProcessor(self.customers_csv)
        self.assertTrue(processor.load_data())
        with self.assertLogs(fixed_module.logger, level="WARNING") as log_ctx:
            self.assertTrue(processor.process_transactions(bad_tx_csv))

        self.assertEqual(len(processor.transactions), 1)
        self.assertTrue(any("invalid amount" in m for m in log_ctx.output))

    def test_calculate_customer_metrics_empty_returns_empty(self) -> None:
        """Verify calculate_customer_metrics() logs an error and returns {} when empty."""
        empty_proc = fixed_module.DataProcessor(self.customers_csv)
        with self.assertLogs(fixed_module.logger, level="ERROR"):
            self.assertEqual(empty_proc.calculate_customer_metrics(), {})

    def test_calculate_customer_metrics_kpis_and_categories(self) -> None:
        """Verify calculated metrics, top_customers ranking, and category_breakdown."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        processor.load_data()
        processor.process_transactions(self.transactions_csv)

        metrics = processor.calculate_customer_metrics()
        self.assertEqual(metrics["total_customers"], 5)
        self.assertEqual(metrics["total_transactions"], 10)
        self.assertAlmostEqual(metrics["total_revenue"], 1282.24)
        self.assertAlmostEqual(metrics["average_transaction_value"], 128.22)
        self.assertEqual(metrics["top_customers"][0]["customer_id"], "C001")
        self.assertEqual(metrics["top_customers"][1]["customer_id"], "C005")
        self.assertEqual(
            metrics["category_breakdown"],
            {"electronics": 3, "clothing": 3, "food": 2, "books": 2},
        )

    def test_find_matches_case_insensitive_token_lookup(self) -> None:
        """Verify indexed case-insensitive token lookup finds matching names."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        processor.load_data()

        john_matches = processor.find_matches("john", field="name")
        cids = {m["customer_id"] for m in john_matches}
        self.assertEqual(cids, {"C001", "C003"})  # John Smith & Bob Johnson

    def test_find_matches_exact_indexed_lookup(self) -> None:
        """Verify O(1) exact indexed lookup requires full field value equality."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        processor.load_data()

        exact_matches = processor.find_matches("john smith", field="name", exact=True)
        self.assertEqual(len(exact_matches), 1)
        self.assertEqual(exact_matches[0]["customer_id"], "C001")
        self.assertEqual(processor.find_matches("john", field="name", exact=True), [])

    def test_find_matches_substring_empty_and_missing_field(self) -> None:
        """Verify partial substring matching, whitespace rejection, and unknown field fallback."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        processor.load_data()

        email_matches = processor.find_matches("alice.brown", field="email")
        self.assertEqual(len(email_matches), 1)
        self.assertEqual(email_matches[0]["customer_id"], "C004")

        self.assertEqual(processor.find_matches("anything", field="nonexistent"), [])
        self.assertEqual(processor.find_matches("   ", field="name"), [])

    def test_export_customer_data_csv_json_and_edge_cases(self) -> None:
        """Verify CSV/JSON exports, empty-dataset header preservation, heterogeneous keys, and invalid format."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        processor.load_data()
        processor.process_transactions(self.transactions_csv)

        csv_out = os.path.join(self.temp_dir.name, "export.csv")
        json_out = os.path.join(self.temp_dir.name, "export.json")
        self.assertTrue(processor.export_customer_data(csv_out, "csv"))
        self.assertTrue(processor.export_customer_data(json_out, "json"))

        with open(csv_out, "r", encoding="utf-8", newline="") as f:
            csv_rows = list(csv.DictReader(f))
        self.assertEqual(len(csv_rows), 5)
        self.assertIn("customer_id", csv_rows[0])

        with open(json_out, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        self.assertIn("C001", json_data)

        empty_proc = fixed_module.DataProcessor(self.customers_csv)
        empty_csv = os.path.join(self.temp_dir.name, "empty.csv")
        self.assertTrue(empty_proc.export_customer_data(empty_csv, "csv"))
        with open(empty_csv, "r", encoding="utf-8", newline="") as f:
            header = f.readline().strip()
        self.assertTrue(header.startswith("customer_id,name,email"))

        hetero_csv = os.path.join(self.temp_dir.name, "hetero.csv")
        processor.customers["C002"]["loyalty_tier"] = "gold"
        self.assertTrue(processor.export_customer_data(hetero_csv, "csv"))

        with self.assertLogs(fixed_module.logger, level="ERROR"):
            self.assertFalse(processor.export_customer_data(csv_out, "xml"))

    def test_generate_reports_and_invalid_type(self) -> None:
        """Verify generation of all valid JSON reports and rejection of unknown report types."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        processor.load_data()
        processor.process_transactions(self.transactions_csv)

        summary_out = os.path.join(self.temp_dir.name, "summary.json")
        metrics_out = os.path.join(self.temp_dir.name, "metrics.json")
        tx_out = os.path.join(self.temp_dir.name, "tx.json")

        self.assertTrue(processor.generate_report("customer_summary", summary_out))
        self.assertTrue(processor.generate_report("metrics", metrics_out))
        self.assertTrue(processor.generate_report("transactions", tx_out))

        with open(summary_out, "r", encoding="utf-8") as f:
            summary_data = json.load(f)
        self.assertEqual(len(summary_data["customers"]), 5)
        self.assertIn("customer_id", summary_data["customers"][0])

        with self.assertLogs(fixed_module.logger, level="ERROR"):
            self.assertFalse(processor.generate_report("invalid_type", summary_out))


if __name__ == "__main__":
    unittest.main()
