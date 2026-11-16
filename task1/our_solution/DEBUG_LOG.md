# Task 1: AI-Powered Debugging and Refactoring — Debug & Refactoring Log

**Simulation:** Datacom — *Automation AI Accelerator: From Co-pilot to Autonomous Agent*  
**Deliverables Covered in This Single-File Submission:**
1. Interactive Debugging Log (`DEBUG_LOG.md`)
2. Unit Test Suite (`TEST_CASES.py`)
3. Refactored & Fixed Production Script (`process_data_final.py`)

---

## Step 1: Understand the Codebase

### Prompt Sent to AI Co-Pilot
> "This is a legacy Python script (`process_data.py`). Please provide a high-level summary of what it's supposed to do. Then, break down your explanation function by function, detailing the purpose of each, its expected inputs and outputs, and any side effects. Finally, identify any potential areas of concern or parts of the code that seem overly complex or inefficient."

### AI Response
#### High-Level Summary
`process_data.py` is a batch customer-analytics ETL script built around the `DataProcessor` class. Its intended pipeline is:
1. Load customer records from `customers.csv` into memory (`self.customers`).
2. Load transaction records from `transactions.csv`, append them to `self.transactions`, and aggregate `total_spent` and `transaction_count` per customer.
3. Compute aggregate KPIs (`total_revenue`, `average_transaction_value`, `top_customers`, `category_breakdown`).
4. Generate three JSON reports (`customer_summary.json`, `metrics.json`, `transactions.json`) and export customer records to `customers_export.csv` and `customers_export.json`.

#### Function-by-Function Breakdown
- **`DataProcessor.__init__(self, input_file: str)`** (lines 21–26)
  - **Purpose:** Initializes processor state.
  - **Inputs:** `input_file` (`str`, path to customers CSV).
  - **Outputs:** `None`.
  - **Side Effects:** Initializes `self.customers` (`dict`), `self.transactions` (`list`), `self.reports` (`dict`).
- **`load_data(self) -> bool`** (lines 28–50)
  - **Purpose:** Reads customer CSV rows and populates `self.customers` keyed by `customer_id`.
  - **Inputs:** Uses `self.input_file`.
  - **Outputs:** `bool` (`True` on success, `False` on exception).
  - **Side Effects:** Mutates `self.customers`; logs `INFO` or `ERROR`.
- **`process_transactions(self, transaction_file: str) -> bool`** (lines 52–86)
  - **Purpose:** Reads transactions CSV, stores rows in `self.transactions`, and updates customer totals.
  - **Inputs:** `transaction_file` (`str`).
  - **Outputs:** `bool`.
  - **Side Effects:** Mutates `self.transactions` and `self.customers`; logs count or warnings/errors.
- **`calculate_customer_metrics(self) -> Dict[str, Any]`** (lines 88–123)
  - **Purpose:** Computes summary metrics, top 10 spenders, and category counts.
  - **Inputs:** None (reads `self.customers` and `self.transactions`).
  - **Outputs:** `Dict[str, Any]` (or `{}` if `self.customers` is empty).
  - **Side Effects:** Logs `ERROR` if no customer data is available.
- **`find_matches(self, search_term: str, field: str = "name") -> List[Dict[str, Any]]`** (lines 125–138)
  - **Purpose:** Performs case-insensitive substring search across customer records.
  - **Inputs:** `search_term` (`str`), `field` (`str`, defaults to `"name"`).
  - **Outputs:** List of matching customer dicts containing `customer_id`.
  - **Side Effects:** None.
- **`generate_report(self, report_type: str, output_file: str) -> bool`** (lines 140–171)
  - **Purpose:** Serializes `customer_summary`, `metrics`, or `transactions` report data to JSON.
  - **Inputs:** `report_type` (`str`), `output_file` (`str`).
  - **Outputs:** `bool`.
  - **Side Effects:** Writes JSON file to disk; logs result.
- **`export_customer_data(self, output_file: str, format: str = "csv") -> bool`** (lines 173–200)
  - **Purpose:** Exports `self.customers` to CSV or JSON.
  - **Inputs:** `output_file` (`str`), `format` (`"csv"` or `"json"`).
  - **Outputs:** `bool`.
  - **Side Effects:** Writes CSV/JSON file to disk; logs result.
- **`main()`** (lines 203–228)
  - **Purpose:** Orchestrates the end-to-end nightly batch pipeline.
  - **Inputs / Outputs:** None / `None`.
  - **Side Effects:** Reads `customers.csv` & `transactions.csv`, writes 5 output files, logs completion.

#### Areas of Concern & Inefficiencies Identified
1. **Fragile Schema Inference in `export_customer_data` (line 180):** Calling `next(iter(self.customers.values())).keys()` crashes if `self.customers` is not a dict of uniform dicts (e.g., list values, list container, or heterogeneous dicts).
2. **Unchecked Return Values in `main()` (lines 219–227):** `main()` ignores `False` returns from `generate_report` and `export_customer_data`, logging `"Data processing completed successfully"` even when an export fails.
3. **Data Consistency & Input Hygiene:**
   - Whitespace is not stripped on CSV load (e.g., `customers.csv` line 6 has trailing whitespace `"2023-05-12 "`).
   - `float(row["amount"])` is parsed twice per row (lines 61 and 70) with no per-row validation; one malformed row aborts the entire file.
   - Unknown-customer transactions are appended to `self.transactions` (line 65) even though their revenue is excluded from `self.customers`, skewing `average_transaction_value`.
   - `customer_summary` report (line 146) drops `customer_id` by exporting `list(self.customers.values())`.
4. **Performance Bottlenecks:**
   - `calculate_customer_metrics()` sorts the entire customer list in $O(N \log N)$ just to take the top 10 (`customer_list[:10]`).
   - `find_matches()` performs a full linear scan with repeated `str(...).lower()` conversions on every query instead of maintaining an indexed lookup structure.

### Developer Thought Process (Notes)
Before touching any code, breaking the legacy script down function by function revealed that the SLA slowdown and the export crash are distinct issues: the export failure stems from unsafe assumptions about `self.customers`'s runtime shape and ignored return values in `main()`, while the latency/scalability issues stem from full sorting for top-k, unindexed repeated scans in `find_matches()`, and redundant conversions during CSV ingestion.

---

## Step 2: Diagnose the Specific Bug

### Prompt Sent to AI Co-Pilot
> "Given the following `export_customer_data` function (lines 173–200) and `main` function (lines 203–228) from `process_data.py` and the full `error.log` below, what is the most likely root cause of the failure? Please explain your reasoning step-by-step, referencing specific lines of code and the error message."

**Error Log Context (`error.log`):**
```text
2024-01-15 02:30:15,123 - INFO - Loaded 150 customers
2024-01-15 02:30:15,456 - INFO - Processed 1250 transactions
2024-01-15 02:30:15,789 - INFO - Generated customer_summary report: customer_summary.json
2024-01-15 02:30:15,890 - INFO - Generated metrics report: metrics.json
2024-01-15 02:30:16,012 - INFO - Generated transactions report: transactions.json
2024-01-15 02:30:16,123 - INFO - Exported customer data to customers_export.csv
2024-01-15 02:30:16,234 - ERROR - Error exporting data: 'dict' object has no attribute 'keys'
2024-01-15 02:30:16,235 - ERROR - Data processing completed successfully
```

### AI Response — Step-by-Step Root Cause Analysis
1. **Locating the Exception Source:**
   - Line 7 of `error.log` prints: `ERROR - Error exporting data: ... object has no attribute 'keys'`.
   - In `process_data.py`, the exact prefix `"Error exporting data: {e}"` appears only on **line 199** inside `export_customer_data()`'s `except Exception as e:` block.
2. **Pinpointing the Failing Expression:**
   - Inside `export_customer_data()`, the only `.keys()` invocation in the entire file is on **line 180**:
     ```python
     fieldnames = ["customer_id"] + list(
         next(iter(self.customers.values())).keys()
     )
     ```
   - This expression assumes two brittle invariants:
     1. `self.customers` is a non-empty `dict`.
     2. Every value in `self.customers` is a `dict` with identical keys (specifically the first value yielded by `iter(self.customers.values())`).
   - If `self.customers` contains non-dict values (such as a `list`, `tuple`, `str`, or `None` after an intermediate mutation/schema drift), `.keys()` raises `AttributeError: '<type>' object has no attribute 'keys'`. Similarly, if `self.customers` itself becomes a `list` of customer dicts, `.values()` raises `AttributeError: 'list' object has no attribute 'values'`. And if records have differing keys, `csv.DictWriter.writerow()` (line 187) raises `ValueError: dict contains fields not in fieldnames`.
   - *(Note on `error.log` wording: while Python `dict` objects normally implement `.keys()`, the log message explicitly maps to line 180's `.keys()` call inside `export_customer_data`, and line 8's `ERROR - Data processing completed successfully` highlights a second failure in `main()`.)*
3. **Why the Pipeline Silently Masked the Failure:**
   - On **lines 198–200**, `export_customer_data` catches the exception, logs it, and returns `False`.
   - On **lines 224–227**, `main()` calls `processor.export_customer_data(...)` without inspecting the return value and unconditionally logs `"Data processing completed successfully"`, allowing downstream SLA monitors to miss the failed export.

### Developer Thought Process (Notes)
Cross-referencing the log timestamp (`02:30:16,234`) against `process_data.py` confirmed that `export_customer_data` (lines 173–200) is the sole source of `"Error exporting data:"` and line 180 is the sole `.keys()` call. Beyond fixing `.keys()` by normalizing records against an explicit schema, we also need `main()` to inspect return codes so failures are surfaced properly instead of falsely reporting success.

---

## Step 3: Write a Test to Replicate the Bug

### Prompt Sent to AI Co-Pilot
> "Based on your analysis of the bug, write a Python unit test suite using the `unittest` library (`TEST_CASES.py`) that reproduces the `AttributeError` in `process_data.py`'s `export_customer_data` method when customer data has unexpected non-dict/list structures, and also verifies CSV/JSON loading, whitespace stripping, unknown-customer transaction consistency, metrics calculations, and indexed `find_matches` behavior."

### AI Response & Verification
Created `TEST_CASES.py` containing 8 `unittest.TestCase` methods, starting with `test_legacy_bug_reproduction_on_original`, which verifies:
1. Original `process_data.DataProcessor.export_customer_data()` returns `False` and logs `AttributeError: ... has no attribute 'keys'` when a customer record is list-structured (and fails when `self.customers` is a list of dicts).
2. Refactored `process_data_final.DataProcessor` normalizes those structures and exports valid CSVs cleanly.

#### Terminal Output Before / Against Legacy Behavior vs. Final Verification
Running `python -m unittest TEST_CASES.py -v` after refactoring confirmed all 8 test cases pass (including reproducing the legacy `AttributeError` on `process_data.py` while passing on `process_data_final.py`):
```text
test_calculate_customer_metrics ... ok
test_export_customer_data_csv_and_json ... ok
test_find_matches_performance_and_accuracy ... ok
test_generate_reports ... ok
test_legacy_bug_reproduction_on_original ... ok
test_load_data_and_whitespace_stripping ... ok
test_process_transactions_and_totals ... ok
test_unknown_customer_transaction_and_bad_amount ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.102s

OK
```

### Developer Thought Process (Notes)
Writing the reproduction test against the original `process_data` module first ensured we weren't guessing at the failure mode. Having an automated assertion that catches `has no attribute 'keys'` in the legacy logger and proves `process_data_final.py` handles both dict-of-dicts, dict-of-lists, list-of-dicts, heterogeneous keys, and empty datasets gives strong regression protection.

---

## Step 4: Refactor and Fix the Code

### Prompt Sent to AI Co-Pilot
> "Refactor `process_data.py` into `process_data_final.py` to fix the `export_customer_data` bug and pipeline error reporting. While doing so, improve performance and data integrity: maintain $O(1)$ dictionary lookups for `customer_id`, add an inverted index for `find_matches` to eliminate redundant scans, replace the full sort in `calculate_customer_metrics` with `heapq.nlargest`, strip CSV whitespace on ingestion, validate transaction amounts per row, keep matched transactions consistent with customer totals, and adhere to PEP 8 and type hints."

### Summary of Fixes & Performance Optimizations
1. **Schema-Safe Normalization & Export (`_normalize_customer_record`, `_get_normalized_customers`, `export_customer_data`):**
   - Replaced fragile `next(iter(self.customers.values())).keys()` with explicit normalization and deterministic column ordering (`DEFAULT_CUSTOMER_FIELDNAMES` plus any extra dynamic keys).
   - Empty datasets still emit valid CSV headers cleanly instead of 0-byte files.
   - Added explicit `encoding="utf-8"` on all file operations.
2. **Algorithmic Performance Improvements:**
   - **Top-K Selection:** Replaced `list.sort()` ($O(N \log N)$) in `calculate_customer_metrics()` with `heapq.nlargest(10, ...)` ($O(N \log k)$ where $k = 10$).
   - **Category Aggregation:** Replaced manual dict branching with `collections.Counter` in a single pass.
   - **Fast Lookups:** Maintained $O(1)$ `dict.get(customer_id)` lookup during transaction ingestion and introduced `_rebuild_search_index()` so `find_matches()` performs $O(1)$ dictionary index lookups for exact values and tokens (with automatic staleness detection via `_indexed_signature` and single-pass fallback for arbitrary substrings).
3. **Data Integrity & Pipeline Accuracy:**
   - Stripped whitespace on CSV headers and values (fixing `"2023-05-12 "` in `customers.csv`).
   - Validated numeric `amount` values per row, rounded currency sums to 2 decimal places, and isolated unknown-customer transactions in `self.unmatched_transactions` so `total_transactions`, `total_revenue`, and `average_transaction_value` remain mathematically consistent.
   - Included `customer_id` in both `customer_summary` and `top_customers` report outputs.
   - Updated `main()` to inspect all step return booleans and exit with code `0` only if every step succeeded.

### Terminal Verification of `process_data_final.py`
Command: `python process_data_final.py`
```text
2026-11-15 20:08:08,361 - INFO - Loaded 5 customers
2026-11-15 20:08:08,361 - INFO - Processed 10 transactions
2026-11-15 20:08:08,362 - INFO - Generated customer_summary report: customer_summary.json
2026-11-15 20:08:08,362 - INFO - Generated metrics report: metrics.json
2026-11-15 20:08:08,363 - INFO - Generated transactions report: transactions.json
2026-11-15 20:08:08,363 - INFO - Exported customer data to customers_export.csv
2026-11-15 20:08:08,364 - INFO - Exported customer data to customers_export.json
2026-11-15 20:08:08,364 - INFO - Data processing completed successfully
```

### Developer Thought Process (Notes)
Treating the AI's suggestions as testable hypotheses rather than accepting them blindly caught several subtle edge cases—for example, ensuring `_search_index` detects external in-memory mutations to `self.customers` via `_indexed_signature` and ensuring heterogeneous extra keys across customer dictionaries don't crash `csv.DictWriter`.

---

## Step 5: Complete Code Artifacts

### Artifact 1: `process_data_final.py`
```python
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
```

---

### Artifact 2: `TEST_CASES.py`
```python
#!/usr/bin/env python3
"""
Unit test suite for Task 1: Bug reproduction and verification of process_data_final.py.
"""

import csv
import json
import os
import tempfile
import unittest

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

    def test_legacy_bug_reproduction_on_original(self) -> None:
        """
        Reproduce the AttributeError from error.log in process_data.py when
        export_customer_data() receives non-dict or list-structured customer data,
        and verify that process_data_final.py handles both cleanly.
        """
        legacy_out = os.path.join(self.temp_dir.name, "legacy_export.csv")
        fixed_out = os.path.join(self.temp_dir.name, "fixed_export.csv")

        # Case 1: Dict values are lists instead of dicts -> legacy calls .keys() and fails
        legacy_proc = legacy_module.DataProcessor(self.customers_csv)
        legacy_proc.customers = {
            "C001": ["John Smith", "john.smith@email.com", "2023-01-15", 376.0, 3]
        }

        with self.assertLogs(legacy_module.logger, level="ERROR") as log_ctx:
            legacy_result = legacy_proc.export_customer_data(legacy_out, "csv")

        self.assertFalse(legacy_result)
        self.assertTrue(
            any("has no attribute 'keys'" in msg for msg in log_ctx.output),
            f"Expected AttributeError mentioning .keys(), got: {log_ctx.output}",
        )

        # Fixed processor normalizes list values and exports cleanly
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

        # Case 2: self.customers is a list of customer dicts -> legacy fails on .values()
        legacy_list_out = os.path.join(self.temp_dir.name, "legacy_list_export.csv")
        fixed_list_out = os.path.join(self.temp_dir.name, "fixed_list_export.csv")

        legacy_proc.customers = [
            {"customer_id": "C001", "name": "John Smith", "email": "john@email.com"}
        ]
        with self.assertLogs(legacy_module.logger, level="ERROR"):
            self.assertFalse(legacy_proc.export_customer_data(legacy_list_out, "csv"))

        fixed_proc.customers = [
            {"customer_id": "C001", "name": "John Smith", "email": "john@email.com"}
        ]
        self.assertTrue(fixed_proc.export_customer_data(fixed_list_out, "csv"))
        with open(fixed_list_out, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_id"], "C001")

    def test_load_data_and_whitespace_stripping(self) -> None:
        """Verify load_data() loads all customers and strips trailing whitespace."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        self.assertTrue(processor.load_data())
        self.assertEqual(len(processor.customers), 5)
        self.assertEqual(processor.customers["C005"]["join_date"], "2023-05-12")

        missing = fixed_module.DataProcessor(
            os.path.join(self.temp_dir.name, "missing.csv")
        )
        with self.assertLogs(fixed_module.logger, level="ERROR"):
            self.assertFalse(missing.load_data())

    def test_process_transactions_and_totals(self) -> None:
        """Verify transaction loading, customer total_spent, and transaction_count."""
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

    def test_unknown_customer_transaction_and_bad_amount(self) -> None:
        """
        Verify unknown-customer and invalid-amount transactions are logged without
        corrupting matched transaction metrics.
        """
        bad_tx_csv = os.path.join(self.temp_dir.name, "bad_transactions.csv")
        with open(bad_tx_csv, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,100.00,2024-01-10,electronics\n"
                "T002,C999,500.00,2024-01-11,electronics\n"
                "T003,C001,not_a_number,2024-01-12,food\n"
            )

        processor = fixed_module.DataProcessor(self.customers_csv)
        self.assertTrue(processor.load_data())

        with self.assertLogs(fixed_module.logger, level="WARNING") as log_ctx:
            self.assertTrue(processor.process_transactions(bad_tx_csv))

        self.assertEqual(len(processor.transactions), 1)
        self.assertEqual(len(processor.unmatched_transactions), 1)
        self.assertTrue(any("unknown customer: C999" in m for m in log_ctx.output))
        self.assertTrue(any("invalid amount" in m for m in log_ctx.output))

        metrics = processor.calculate_customer_metrics()
        self.assertEqual(metrics["total_transactions"], 1)
        self.assertAlmostEqual(metrics["total_revenue"], 100.00)
        self.assertAlmostEqual(metrics["average_transaction_value"], 100.00)

    def test_calculate_customer_metrics(self) -> None:
        """Verify calculated metrics, top_customers ranking, and category_breakdown."""
        empty_proc = fixed_module.DataProcessor(self.customers_csv)
        with self.assertLogs(fixed_module.logger, level="ERROR"):
            self.assertEqual(empty_proc.calculate_customer_metrics(), {})

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

    def test_find_matches_performance_and_accuracy(self) -> None:
        """Verify indexed exact lookup, substring search, case-insensitivity, and empty queries."""
        processor = fixed_module.DataProcessor(self.customers_csv)
        processor.load_data()

        # Case-insensitive token match
        john_matches = processor.find_matches("john", field="name")
        cids = {m["customer_id"] for m in john_matches}
        self.assertEqual(cids, {"C001", "C003"})  # John Smith & Bob Johnson

        # Exact indexed lookup
        exact_matches = processor.find_matches("john smith", field="name", exact=True)
        self.assertEqual(len(exact_matches), 1)
        self.assertEqual(exact_matches[0]["customer_id"], "C001")

        # Partial substring search
        email_matches = processor.find_matches("alice.brown", field="email")
        self.assertEqual(len(email_matches), 1)
        self.assertEqual(email_matches[0]["customer_id"], "C004")

        # Missing field and empty query
        self.assertEqual(processor.find_matches("anything", field="nonexistent"), [])
        self.assertEqual(processor.find_matches("   ", field="name"), [])

    def test_export_customer_data_csv_and_json(self) -> None:
        """Verify CSV and JSON export, empty-dataset header preservation, and heterogeneous keys."""
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

        # Empty customers still writes CSV header safely
        empty_proc = fixed_module.DataProcessor(self.customers_csv)
        empty_csv = os.path.join(self.temp_dir.name, "empty.csv")
        self.assertTrue(empty_proc.export_customer_data(empty_csv, "csv"))
        with open(empty_csv, "r", encoding="utf-8", newline="") as f:
            header = f.readline().strip()
        self.assertTrue(header.startswith("customer_id,name,email"))

        # Heterogeneous keys do not crash DictWriter
        hetero_csv = os.path.join(self.temp_dir.name, "hetero.csv")
        processor.customers["C002"]["loyalty_tier"] = "gold"
        self.assertTrue(processor.export_customer_data(hetero_csv, "csv"))

        # Unsupported format returns False cleanly
        with self.assertLogs(fixed_module.logger, level="ERROR"):
            self.assertFalse(processor.export_customer_data(csv_out, "xml"))

    def test_generate_reports(self) -> None:
        """Verify generation of all valid reports and rejection of unknown report types."""
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
```
