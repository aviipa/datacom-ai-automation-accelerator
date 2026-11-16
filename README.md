# Datacom — Automation AI Accelerator: From Co-pilot to Autonomous Agent

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Task 1 Tests](https://img.shields.io/badge/Task%201%20unittest-15%20passed-brightgreen.svg)](./task1/our_solution/TEST_CASES.py)
[![Task 2 Tests](https://img.shields.io/badge/Task%202%20unittest-7%20passed-brightgreen.svg)](./task2/our_solution/test_kudos.py)
[![Standalone Task 2 Repo](https://img.shields.io/badge/Standalone%20Repo-datacom--kudos--system-orange.svg)](https://github.com/aviipa/datacom-kudos-system)

Consolidated engineering portfolio for the **Datacom: Automation AI Accelerator** simulation, tracing the progression from AI-assisted code debugging (**Co-pilot**) to specification-first full-stack engineering (**Spec-Driven Architect**) and autonomous workflow orchestration (**Autonomous Agent Design**).

---

## Simulation Progression Overview

| Phase | AI Paradigm & Role | Key Engineering Deliverables | Verification |
| :--- | :--- | :--- | :--- |
| **Task 1** | **Co-Pilot** — Debugging & Algorithmic Refactoring | `process_data_final.py`, `TEST_CASES.py`, `DEBUG_LOG.md` | **15 unit tests passed** (`unittest`) |
| **Task 2** | **Architect** — Spec-Driven Full-Stack Development | `SPECIFICATION.md`, `kudos_app.py`, `index.html`, `test_kudos.py` | **7 unit/HTTP tests passed** (`unittest`) |
| **Task 3** | **Autonomous Agent** — Strategic AI System Design | `ORDERBOT_PROPOSAL.md`, `OrderBot_Presentation.{pdf,pptx}`, `presentation.html` | Executive Architecture & Rollout Plan |

---

## Task 1 — AI Co-Pilot Refactoring & $O(1)$ Data Pipeline (`task1/our_solution/`)

Diagnosed an intermittent nightly export failure (`AttributeError: ... has no attribute 'keys'`) and scalability bottlenecks in legacy ETL script [`process_data.py`](./task1/process_data.py), delivering a hardened implementation in [`process_data_final.py`](./task1/our_solution/process_data_final.py):

* **Root-Cause & Failure Control Fix:** Replaced brittle `next(iter(self.customers.values())).keys()` schema inference with explicit normalization (`_normalize_customer_record`, `_get_normalized_customers`) supporting non-dict entries, heterogeneous keys, and empty datasets, while enforcing pipeline exit-code propagation in `main()`.
* **Algorithmic & Lookup Optimization:** Replaced repeated $O(N)$ linear substring scans in `find_matches()` with an $O(1)$ inverted index (`_rebuild_search_index`) with exact/token matching and automatic invalidation, replaced full $O(N \log N)$ sorting with $O(N \log k)$ selection (`heapq.nlargest`), and switched category counts to single-pass `collections.Counter`.
* **Data Hygiene & Integrity:** Stripped CSV key/value whitespace (`_clean_row`), validated per-row numeric amounts gracefully without dropping whole files, and isolated unknown-customer transactions (`self.unmatched_transactions`) so `average_transaction_value` stays accurate.
* **Artifacts:**
  * [`task1/our_solution/process_data_final.py`](./task1/our_solution/process_data_final.py)
  * [`task1/our_solution/TEST_CASES.py`](./task1/our_solution/TEST_CASES.py) (**15 unit tests**)
  * [`task1/our_solution/DEBUG_LOG.md`](./task1/our_solution/DEBUG_LOG.md)

---

## Task 2 — Spec-Driven Full-Stack Kudos System (`task2/our_solution/`)

> **Dedicated Standalone Repository:** **[https://github.com/aviipa/datacom-kudos-system](https://github.com/aviipa/datacom-kudos-system)**

Engineered an internal peer-to-peer recognition feature following strict **Spec-Driven Development** (Initial Prompt $\rightarrow$ Architect Review & Governance Refinements $\rightarrow$ Approved Blueprint $\rightarrow$ Implementation & Verification):

* **Specification First ([`SPECIFICATION.md`](./task2/our_solution/SPECIFICATION.md)):** Defined functional requirements (`US-01` through `US-05`), SQLite schema with moderation audit columns (`is_visible`, `moderated_by`, `moderated_at`, `reason_for_moderation`) and composite feed index, REST API contracts, and UI component hierarchy before coding.
* **Zero-Dependency Backend & Guardrails ([`kudos_app.py`](./task2/our_solution/kudos_app.py)):** Built on Python standard library (`http.server`, `sqlite3`) with server-side validation (`1–500` chars, anti-self-kudos), stored XSS escaping, duplicate submission cooldown (`409 Conflict`), per-user rate limiting (`429 Too Many Requests`), and RBAC admin moderation (`hide` / `restore` / `delete`).
* **Responsive Dashboard UI ([`index.html`](./task2/our_solution/index.html)):** Clean single-page client (`KudosForm`, `KudosPublicFeed`, `AdminModerationModal`) with character counter and role-gated moderation actions.
* **Verification ([`test_kudos.py`](./task2/our_solution/test_kudos.py)):** **7 unit & end-to-end HTTP integration tests** covering all 5 user stories, schema audit columns, rate limits, and RBAC authorization.

---

## Task 3 — `OrderBot` Autonomous Agent Architecture (`task3/our_solution/`)

Architected `OrderBot`, an autonomous hardware order-processing AI agent transforming a `4–24+ hour` manual workflow across **Email $\leftrightarrow$ PDF $\leftrightarrow$ Salesforce $\leftrightarrow$ Google Sheets** into an automated sub-5-minute pipeline:

* **5-Component Agent Anatomy:** Explicitly defined **Goal** (`< 5 min` SLA, `>= 99.5%` validation accuracy), **Perception Tools** (Email Reader, OCR/Schema PDF Parser, read-only Salesforce & Google Sheets APIs), **Planning Loop**, **Action Tools** (atomic stock reservation, CRM logging, customer/warehouse notifications, Slack/Teams escalation), and **Memory / Learning** feedback tracking.
* **Safety Guardrails & Rollout Governance:** Confidence thresholds (`< 95%` triggers targeted sales-rep clarification rather than guessing), mandatory **Human-in-the-Loop** escalation for credit holds or high-value orders (`> $25,000`), dead-letter handling on API outages, and a low-risk **3-Phase Rollout** (Read-Only Shadow Mode PoC $\rightarrow$ Human-Approved Co-Pilot $\rightarrow$ Guardrailed Autonomy).
* **Artifacts:**
  * [`task3/our_solution/ORDERBOT_PROPOSAL.md`](./task3/our_solution/ORDERBOT_PROPOSAL.md)
  * [`task3/our_solution/OrderBot_Presentation.pdf`](./task3/our_solution/OrderBot_Presentation.pdf)
  * [`task3/our_solution/OrderBot_Presentation.pptx`](./task3/our_solution/OrderBot_Presentation.pptx)
  * [`task3/our_solution/presentation.html`](./task3/our_solution/presentation.html)

---

## Repository Structure

```text
datacom-ai-automation-accelerator/
├── task1/
│   ├── customers.csv                      # Input fixture for ETL pipeline
│   ├── transactions.csv                   # Input fixture for ETL pipeline
│   ├── error.log                          # Legacy production failure log
│   ├── process_data.py                    # Legacy baseline script
│   └── our_solution/
│       ├── process_data_final.py          # Refactored O(1) indexed ETL processor
│       ├── TEST_CASES.py                  # 15 unit tests (legacy repro + fixes)
│       └── DEBUG_LOG.md                   # Structured co-pilot root-cause trace
├── task2/
│   └── our_solution/                      # Mirrors https://github.com/aviipa/datacom-kudos-system
│       ├── SPECIFICATION.md               # Approved spec, schema & RBAC design
│       ├── kudos_app.py                   # Stdlib HTTP server + SQLite backend
│       ├── index.html                     # Responsive employee portal UI
│       ├── test_kudos.py                  # 7 unit & HTTP integration tests
│       └── README.md
├── task3/
│   └── our_solution/
│       ├── ORDERBOT_PROPOSAL.md           # Full As-Is / To-Be & agentic spec
│       ├── OrderBot_Presentation.pdf      # 3-slide executive deck (PDF)
│       ├── OrderBot_Presentation.pptx     # 3-slide executive deck (PowerPoint)
│       └── presentation.html              # Interactive HTML slide deck
└── README.md
```

---

## Running Tests Locally

```bash
# Task 1 — Data Pipeline & Refactoring (15 tests)
cd task1/our_solution
python -m unittest TEST_CASES.py -v

# Task 2 — Kudos System & HTTP/RBAC Integration (7 tests)
cd ../../task2/our_solution
python -m unittest test_kudos.py -v
```

---

## Disclaimer
Educational engineering portfolio artifacts developed for the **Datacom: Automation AI Accelerator** simulation on Forage.
