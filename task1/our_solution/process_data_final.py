#!/usr/bin/env python3
"""
Refactored Data Processing Script for Customer Analytics.

Processes customer and transaction CSV files, maintains mathematically consistent
customer metrics, supports fast indexed lookups, and safely exports reports in
JSON and CSV formats.
"""

import csv
import heapq
import json
import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_CUSTOMER_FIELDNAMES: Tuple[str, ...] = (
    "customer_id",
    "name",
    "email",
    "join_date",
    "total_spent",
    "transaction_count",
)


class DataProcessor:
    """Processes customer transaction data and generates analytics reports."""

    def __init__(self, input_file: str) -> None:
        """Initialize the data processor with the customer CSV input file path."""
        self.input_file = input_file
        self.customers: Dict[str, Dict[str, Any]] = {}
        self.transactions: List[Dict[str, Any]] = []
        self.unmatched_transactions: List[Dict[str, Any]] = []
        self.reports: Dict[str, Any] = {}
        self._search_index: Dict[str, Dict[str, List[str]]] = {}
        self._index_dirty: bool = True
        self._indexed_signature: Optional[Tuple[int, int]] = None

    @staticmethod
    def _clean_row(row: Dict[Optional[str], Optional[str]]) -> Dict[str, str]:
        """Strip whitespace from CSV keys and string values."""
        cleaned: Dict[str, str] = {}
        for key, value in row.items():
            if key is None:
                continue
            clean_key = key.strip()
            clean_val = value.strip() if isinstance(value, str) else ""
            cleaned[clean_key] = clean_val
        return cleaned

    def _normalize_customer_record(
        self, customer_id: str, raw_data: Any
    ) -> Optional[Dict[str, Any]]:
        """Normalize a customer record into a standard dictionary schema."""
        if isinstance(raw_data, dict):
            return {
                "name": str(raw_data.get("name", "")).strip(),
                "email": str(raw_data.get("email", "")).strip(),
                "join_date": str(raw_data.get("join_date", "")).strip(),
                "total_spent": round(float(raw_data.get("total_spent", 0.0)), 2),
                "transaction_count": int(raw_data.get("transaction_count", 0)),
                **{
                    k: v
                    for k, v in raw_data.items()
                    if k
                    not in {
                        "customer_id",
                        "name",
                        "email",
                        "join_date",
                        "total_spent",
                        "transaction_count",
                    }
                },
            }

        if isinstance(raw_data, (list, tuple)):
            # Support positional sequence: [name, email, join_date, total_spent?, transaction_count?]
            return {
                "name": str(raw_data[0]).strip() if len(raw_data) > 0 else "",
                "email": str(raw_data[1]).strip() if len(raw_data) > 1 else "",
                "join_date": str(raw_data[2]).strip() if len(raw_data) > 2 else "",
                "total_spent": (
                    round(float(raw_data[3]), 2) if len(raw_data) > 3 else 0.0
                ),
                "transaction_count": int(raw_data[4]) if len(raw_data) > 4 else 0,
            }

        if isinstance(raw_data, str):
            return {
                "name": raw_data.strip(),
                "email": "",
                "join_date": "",
                "total_spent": 0.0,
                "transaction_count": 0,
            }

        logger.warning(
            "Skipping unsupported customer record type (%s) for customer_id=%s",
            type(raw_data).__name__,
            customer_id,
        )
        return None

    def _get_normalized_customers(self) -> Dict[str, Dict[str, Any]]:
        """
        Return a normalized mapping of customer_id -> dict regardless of whether
        self.customers is a dict, list of dicts, or contains non-dict entries.
        """
        normalized: Dict[str, Dict[str, Any]] = {}

        if isinstance(self.customers, dict):
            items: Iterable[Tuple[Any, Any]] = self.customers.items()
        elif isinstance(self.customers, list):
            items = []
            temp_items: List[Tuple[str, Any]] = []
            for idx, entry in enumerate(self.customers):
                if isinstance(entry, dict):
                    cid = str(entry.get("customer_id", f"UNKNOWN_{idx}")).strip()
                    temp_items.append((cid, entry))
                elif (
                    isinstance(entry, (list, tuple))
                    and len(entry) == 2
                    and isinstance(entry[1], dict)
                ):
                    temp_items.append((str(entry[0]).strip(), entry[1]))
                else:
                    temp_items.append((f"UNKNOWN_{idx}", entry))
            items = temp_items
        else:
            logger.error(
                "Unsupported customers container type: %s",
                type(self.customers).__name__,
            )
            return normalized

        for raw_cid, raw_data in items:
            cid = str(raw_cid).strip()
            record = self._normalize_customer_record(cid, raw_data)
            if record is not None:
                normalized[cid] = record

        return normalized

    def _rebuild_search_index(self) -> None:
        """Build an exact-value and token lookup index over customer fields."""
        index: Dict[str, Dict[str, List[str]]] = {}
        normalized = self._get_normalized_customers()

        for customer_id, data in normalized.items():
            for field, value in data.items():
                field_index = index.setdefault(field, {})
                normalized_val = str(value).strip().lower()
                if normalized_val:
                    field_index.setdefault(normalized_val, []).append(customer_id)
                    for token in normalized_val.split():
                        if token != normalized_val:
                            field_index.setdefault(token, []).append(customer_id)

        self._search_index = index
        self._index_dirty = False
        self._indexed_signature = (id(self.customers), len(self.customers))

    def load_data(self) -> bool:
        """Load customer data from CSV file into an O(1) lookup dictionary."""
        try:
            loaded_customers: Dict[str, Dict[str, Any]] = {}
            with open(self.input_file, "r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                for line_num, raw_row in enumerate(reader, start=2):
                    row = self._clean_row(raw_row)
                    customer_id = row.get("customer_id", "")
                    if not customer_id:
                        logger.warning(
                            "Skipping row %d in %s: missing customer_id",
                            line_num,
                            self.input_file,
                        )
                        continue

                    loaded_customers[customer_id] = {
                        "name": row.get("name", ""),
                        "email": row.get("email", ""),
                        "join_date": row.get("join_date", ""),
                        "total_spent": 0.0,
                        "transaction_count": 0,
                    }

            self.customers = loaded_customers
            self._rebuild_search_index()
            logger.info("Loaded %d customers", len(self.customers))
            return True
        except FileNotFoundError:
            logger.error("Input file %s not found", self.input_file)
            return False
        except Exception as exc:
            logger.error("Error loading data: %s", exc)
            return False

    def process_transactions(self, transaction_file: str) -> bool:
        """Process transaction data and update customer records using O(1) lookups."""
        try:
            if not isinstance(self.customers, dict):
                self.customers = self._get_normalized_customers()

            self.transactions = []
            self.unmatched_transactions = []

            with open(transaction_file, "r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                for line_num, raw_row in enumerate(reader, start=2):
                    row = self._clean_row(raw_row)
                    transaction_id = row.get("transaction_id", "")
                    customer_id = row.get("customer_id", "")
                    raw_amount = row.get("amount", "")

                    if not transaction_id or not customer_id:
                        logger.warning(
                            "Skipping row %d in %s: missing transaction_id or customer_id",
                            line_num,
                            transaction_file,
                        )
                        continue

                    try:
                        amount = round(float(raw_amount), 2)
                    except (ValueError, TypeError):
                        logger.warning(
                            "Skipping transaction %s (row %d): invalid amount %r",
                            transaction_id,
                            line_num,
                            raw_amount,
                        )
                        continue

                    transaction = {
                        "transaction_id": transaction_id,
                        "customer_id": customer_id,
                        "amount": amount,
                        "date": row.get("date", ""),
                        "category": row.get("category", ""),
                    }

                    # O(1) dictionary lookup
                    customer = self.customers.get(customer_id)
                    if customer is not None:
                        self.transactions.append(transaction)
                        customer["total_spent"] = round(
                            float(customer.get("total_spent", 0.0)) + amount, 2
                        )
                        customer["transaction_count"] = (
                            int(customer.get("transaction_count", 0)) + 1
                        )
                    else:
                        self.unmatched_transactions.append(transaction)
                        logger.warning(
                            "Transaction %s for unknown customer: %s",
                            transaction_id,
                            customer_id,
                        )

            self._index_dirty = True
            logger.info("Processed %d transactions", len(self.transactions))
            return True
        except FileNotFoundError:
            logger.error("Transaction file %s not found", transaction_file)
            return False
        except Exception as exc:
            logger.error("Error processing transactions: %s", exc)
            return False

    def calculate_customer_metrics(self) -> Dict[str, Any]:
        """Calculate customer metrics and statistics efficiently."""
        normalized = self._get_normalized_customers()
        if not normalized:
            logger.error("No customer data available")
            return {}

        total_transactions = len(self.transactions)
        total_revenue = round(
            sum(float(cust.get("total_spent", 0.0)) for cust in normalized.values()),
            2,
        )
        average_transaction_value = (
            round(total_revenue / total_transactions, 2)
            if total_transactions > 0
            else 0.0
        )

        # O(N log k) selection for top 10 customers instead of O(N log N) full sort
        top_entries = heapq.nlargest(
            10,
            normalized.items(),
            key=lambda item: float(item[1].get("total_spent", 0.0)),
        )
        top_customers = [
            {"customer_id": cid, **data} for cid, data in top_entries
        ]

        # Single-pass O(T) category breakdown using Counter
        category_counts = Counter(
            tx.get("category", "uncategorized") for tx in self.transactions
        )

        return {
            "total_customers": len(normalized),
            "total_transactions": total_transactions,
            "total_revenue": total_revenue,
            "average_transaction_value": average_transaction_value,
            "top_customers": top_customers,
            "category_breakdown": dict(category_counts),
        }

    def find_matches(
        self, search_term: str, field: str = "name", exact: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find customers matching the search term in the specified field.

        Uses an O(1) inverted index for exact values/tokens and falls back to
        a single-pass normalized substring scan for partial queries when exact=False.
        """
        if not isinstance(search_term, str) or not search_term.strip():
            return []

        normalized = self._get_normalized_customers()
        current_sig = (id(self.customers), len(self.customers))
        if self._index_dirty or not self._search_index or self._indexed_signature != current_sig:
            self._rebuild_search_index()

        search_term_lower = search_term.strip().lower()
        field_index = self._search_index.get(field, {})

        # Fast O(1) lookup for exact field value or full token match
        indexed_ids = field_index.get(search_term_lower)
        if exact:
            if not indexed_ids:
                return []
            seen = set()
            exact_matches: List[Dict[str, Any]] = []
            for cid in indexed_ids:
                if cid not in seen and cid in normalized:
                    val = str(normalized[cid].get(field, "")).strip().lower()
                    if val == search_term_lower:
                        seen.add(cid)
                        exact_matches.append({"customer_id": cid, **normalized[cid]})
            return exact_matches

        if indexed_ids is not None:
            seen = set()
            matches: List[Dict[str, Any]] = []
            for cid in indexed_ids:
                if cid not in seen and cid in normalized:
                    seen.add(cid)
                    matches.append({"customer_id": cid, **normalized[cid]})
            # Include any partial substring matches not separated by whitespace
            if len(matches) == len(normalized):
                return matches
            for cid, data in normalized.items():
                if cid not in seen and field in data:
                    if search_term_lower in str(data[field]).lower():
                        seen.add(cid)
                        matches.append({"customer_id": cid, **data})
            return matches

        # Single-pass fallback for partial substring queries (e.g. "oh" in "John")
        return [
            {"customer_id": cid, **data}
            for cid, data in normalized.items()
            if field in data and search_term_lower in str(data[field]).lower()
        ]

    def generate_report(self, report_type: str, output_file: str) -> bool:
        """Generate various types of reports and save to JSON file."""
        try:
            normalized = self._get_normalized_customers()
            timestamp = datetime.now().isoformat()

            if report_type == "customer_summary":
                report_data = {
                    "generated_at": timestamp,
                    "customers": [
                        {"customer_id": cid, **data}
                        for cid, data in normalized.items()
                    ],
                }
            elif report_type == "metrics":
                report_data = {
                    "generated_at": timestamp,
                    "metrics": self.calculate_customer_metrics(),
                }
            elif report_type == "transactions":
                report_data = {
                    "generated_at": timestamp,
                    "transactions": self.transactions,
                }
            else:
                logger.error("Unknown report type: %s", report_type)
                return False

            with open(output_file, "w", encoding="utf-8") as file:
                json.dump(report_data, file, indent=2)

            self.reports[report_type] = report_data
            logger.info("Generated %s report: %s", report_type, output_file)
            return True

        except Exception as exc:
            logger.error("Error generating report: %s", exc)
            return False

    def export_customer_data(self, output_file: str, format: str = "csv") -> bool:
        """Export normalized customer data in the specified format ('csv' or 'json')."""
        try:
            export_format = format.strip().lower()
            normalized = self._get_normalized_customers()

            if export_format == "csv":
                fieldnames = list(DEFAULT_CUSTOMER_FIELDNAMES)
                extra_keys = []
                seen_keys = set(fieldnames)
                for data in normalized.values():
                    for key in data.keys():
                        if key not in seen_keys:
                            seen_keys.add(key)
                            extra_keys.append(key)
                fieldnames.extend(extra_keys)

                with open(output_file, "w", encoding="utf-8", newline="") as file:
                    writer = csv.DictWriter(
                        file, fieldnames=fieldnames, extrasaction="ignore"
                    )
                    writer.writeheader()
                    for customer_id, data in normalized.items():
                        row = {"customer_id": customer_id, **data}
                        writer.writerow(row)

            elif export_format == "json":
                with open(output_file, "w", encoding="utf-8") as file:
                    json.dump(normalized, file, indent=2)

            else:
                logger.error("Unsupported format: %s", format)
                return False

            logger.info("Exported customer data to %s", output_file)
            return True

        except Exception as exc:
            logger.error("Error exporting data: %s", exc)
            return False


def main() -> bool:
    """Main function to run the data processing pipeline."""
    processor = DataProcessor("customers.csv")

    if not processor.load_data():
        logger.error("Failed to load customer data")
        return False

    if not processor.process_transactions("transactions.csv"):
        logger.error("Failed to process transactions")
        return False

    steps_ok = [
        processor.generate_report("customer_summary", "customer_summary.json"),
        processor.generate_report("metrics", "metrics.json"),
        processor.generate_report("transactions", "transactions.json"),
        processor.export_customer_data("customers_export.csv", "csv"),
        processor.export_customer_data("customers_export.json", "json"),
    ]

    if all(steps_ok):
        logger.info("Data processing completed successfully")
        return True

    logger.error("Data processing completed with one or more errors")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
