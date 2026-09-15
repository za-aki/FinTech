# 📖 Comprehensive Code & Architecture Guide
### Track 1: FinTech & BFSI — UPI Fraud Ring & Merchant Analytics | TransOrg AgentIQ Datathon

This document provides a thorough, code-level explanation of every module, function, mathematical formulation, and architectural decision in this repository. It is designed to prepare you for technical evaluation, code review, and judge Q&A.

---

## 📑 Table of Contents
1. [End-to-End System Architecture](#1-end-to-end-system-architecture)
2. [Graph Fraud Ring Engine (`backend/fraud_ring_detection.py`)](#2-graph-fraud-ring-engine)
3. [114-Feature Analytics Pipeline (`backend/pipeline_v2_fraud_scoring.py`)](#3-analytics-pipeline)
4. [Autonomous AI Copilot (`backend/agent.py`)](#4-autonomous-ai-copilot)
5. [API Server & Asset Router (`backend/main.py`)](#5-api-server--asset-router)
6. [Frontend Console Architecture (`frontend/`)](#6-frontend-console-architecture)
7. [Matplotlib Report Exporter (`dashboard.py`)](#7-matplotlib-report-exporter)
8. [Auditing & Gate 2 Compliance Evidence](#8-auditing--gate-2-compliance-evidence)
9. [Judge Q&A Defense Strategy](#9-judge-qa-defense-strategy)

---

## 1. End-to-End System Architecture

```
[ RAW DATASETS ]
  ├── track1_upi_transactions.csv (20,400 rows)
  ├── track1_kyc_records.csv (36,400 rows)
  ├── track1_merchants_master.csv (6,210 rows)
  └── track1_chargebacks.json (2,800 records)
           │
           ▼
[ STAGE 1: GRAPH FRAUD RING DETECTION (fraud_ring_detection.py) ]
  ├── 1. Merchant Settlement Collusion Detection (203 rings via shared bank accounts)
  ├── 2. Synthetic Identity Mule Detection (1,340 clusters via duplicate PANs)
  └── 3. Bipartite Coordinated Dispute Subgraphs (24 clusters via NetworkX)
  ↳ Outputs: suspicious_cycles.csv
           │
           ▼
[ STAGE 2: PRODUCTION SCORING PIPELINE (pipeline_v2_fraud_scoring.py) ]
  ├── Deduplication & Master Key Resolution (20,000 transactions protected)
  ├── Star-Schema Left Joins (Zero fan-out assertion)
  ├── Deterministic MCC Recovery (1,173 missing MCCs recovered from category 1:1 maps)
  ├── 20+ Per-Row & Grouped Behavioral Flags
  ├── Statistical User Z-Score Outlier Modeling
  ├── 3-Factor Composite Fraud Scoring (Rules 50% + CB Rate 30% + Graph Ring 20%)
  └── Gate 2 Audit Evidence Export (outputs/audit_evidence/)
  ↳ Outputs: fraud_analytics_table.csv & fraud_analytics.duckdb
           │
           ▼
[ STAGE 3: INTERFACES & INTELLIGENCE ]
  ├── Fast Columnar Queries ──► FastAPI (main.py) ──► Plotly Web Console (index.html)
  └── LangGraph Copilot (agent.py) ──► Qwen-27B LLM ──► Deterministic SQL + Business Insights
```

---

## 2. Graph Fraud Ring Engine (`backend/fraud_ring_detection.py`)

### Problem Context
The datathon track is named **"UPI Fraud Ring & Merchant Analytics"**. Standard SQL queries (`GROUP BY merchant_id`) can only analyze entities in isolation. Fraud rings operate across **relational linkages**:
1. Multiple merchants routing revenue to a single shared bank account (merchant collusion).
2. Multiple customer accounts registered under the same stolen identity (synthetic mule clusters).
3. Dense groups of customers repeatedly filing chargebacks against specific merchants.

### Key Logic & Methods

#### A. Merchant Settlement Collusion Rings
```python
shared_acct = mer[mer['settlement_account'].notna()].groupby('settlement_account').agg(...)
```
- **Mechanism**: Groups merchants by `settlement_account`. Where more than one merchant ID shares the same account number, a collusion cluster is flagged.
- **Scoring Formula**:
  $$\text{Score} = \min(1.0, 0.4 + 0.15 \times N_{\text{merchants}} + 0.2 \times \mathbb{I}(\text{failed\_txns} > 2))$$
- **Finding**: **203 distinct collusion clusters** were identified. Example: `RING-MERCH-0101` links 4 distinct storefronts (including *Gokhale Plc*) sharing bank account `XXXX1304` with ₹1.09 Lakhs in volume.

#### B. Synthetic Identity & Mule Clusters
```python
shared_pan = kyc[kyc['pan'].notna()].groupby('pan').agg(...)
```
- **Mechanism**: Groups KYC records by government PAN credentials. Multiple `user_id`s registered under the identical PAN represent identity theft or synthetic mule accounts.
- **Finding**: **1,340 clusters** sharing identical PAN credentials.

#### C. Bipartite Coordinated Dispute Networks
```python
G = nx.Graph()
for _, r in disp_df.iterrows():
    G.add_edge(r['user_id'], r['merchant_id'], amount=r['amount'])
components = [c for c in nx.connected_components(G) if len(c) >= 4]
```
- **Mechanism**: Builds a NetworkX bipartite graph where edges exist between users and merchants who experienced chargeback disputes.
- **Finding**: Discovered **24 interconnected subgraphs** with $\ge 4$ nodes where dispute activity was coordinated across multiple entities.

---

## 3. Analytics Pipeline (`backend/pipeline_v2_fraud_scoring.py`)

This script is the **single source of truth** producing `fraud_analytics_table.csv` and `fraud_analytics.duckdb`. It executes across 9 deterministic stages:

### Stage 1: Ingestion & Type Coercion
- Loads CSVs and parses numerical amounts (stripping `₹`, `$`, `,`).
- Coerces timestamps (`pd.to_datetime(..., errors='coerce')`).
- Critical fix applied: The transaction timestamp column is named `timestamp` (not `timestamp_clean`).

### Stage 2: Deduplication Without Data Loss
- **Transactions**: 20,400 raw rows contained 400 exact duplicates. Dropped to exactly **20,000 unique transactions**.
- **KYC Master Resolution**: Resolves 36,400 raw KYC rows to exactly 28,920 unique `user_id` records using deterministic sorting:
  ```python
  kyc['_completeness'] = kyc.notna().sum(axis=1)
  kyc = kyc.sort_values(['user_id', '_completeness', 'signup_date']).drop_duplicates('user_id', keep='last')
  ```
- **Merchant Master Resolution**: Resolves 6,210 rows to 4,343 unique `merchant_id` records.
- **Chargeback Aggregation**: A single transaction can experience multiple complaints. Aggregates to transaction grain (`txn_id_clean`) taking `dispute_count = count()`, `total_disputed_amount = sum()`, `max_severity = first()`, and `top_reason_code = first()`. This **prevents join fan-out**.

### Stage 3: Star-Schema Joins & Integrity
- Left-joins `transactions` $\to$ `kyc`, `merchants`, and aggregated `chargebacks`.
- **Integrity Assertion**:
  ```python
  assert len(df) == len(txn) # Must strictly equal 20,000
  ```
- **Deterministic MCC Recovery**: Where `mcc` is missing, checks if `merchant_category` has an unambiguous 1:1 mapping in the merchant master (e.g. `Apparel` $\to$ `5699`). Imputes the MCC and sets `mcc_derived = 1` (**1,173 missing MCCs recovered**).
- **Customer Age Derivation**: Calculates `age` relative to benchmark date `2026-09-14`.

### Stage 4: Per-Row Rule Flags
Evaluates 20 independent binary flags:
- `flag_amount_anomaly`: Negative or unparseable amounts.
- `flag_amount_vs_ticket_mismatch`: Transaction amount deviates >5x or <0.2x from merchant's declared average ticket size.
- `flag_disputed_amount_mismatch`: Disputed amount differs by >5% from original transaction amount.
- `flag_kyc_doc_invalid`: PAN or Aadhaar failed regex validation.
- `flag_merchant_suspended`: Merchant marked as Suspended.
- `flag_unauthorized_reason`: Dispute code is `UNAUTHORIZED_TRANSACTION`.
- `flag_unlinked_kyc` & `flag_unlinked_merchant`: Orphan foreign key indicators.

### Stage 5: Grouped Behavioral & Velocity Flags
- **User Aggregates**: Computes `user_txn_count`, `user_total_volume`, `user_failed_rate`, and `user_distinct_merchants`.
- **Statistical Z-Score Modeling**:
  ```python
  df["user_amount_zscore"] = (df["amount"] - df["user_avg_amount"]) / df["user_std_amount"].replace(0, np.nan)
  df["flag_amount_zscore_outlier"] = df["user_amount_zscore"].abs() > 3
  ```
  Measures whether a specific transaction is a statistical outlier (>3 standard deviations) compared to that user's historical spend.

### Stage 6: Graph Fraud Ring Score Merge
- Maps `suspicious_cycles.csv` into `user_cycle_score` and `merchant_cycle_score`. Accounts identified in collusion rings receive scores up to 1.0.

### Stage 7: Composite Multi-Factor Fraud Score
Combines rules, chargeback velocity, and graph topology into a unified metric:
$$\text{fraud\_risk\_score} = 0.5 \times \left(\frac{\text{flag\_count}}{18}\right) + 0.3 \times \text{chargeback\_ratio} + 0.2 \times \text{cycle\_score}$$
Binned into actionable risk tiers:
- `LOW`: $0.00 - 0.15$
- `MEDIUM`: $0.15 - 0.35$
- `HIGH`: $0.35 - 0.55$
- `CRITICAL`: $0.55 - 1.00$

### Stage 8 & 9: Exports & Gate 2 Audit Evidence
- Exports `fraud_analytics_table.csv` (20,000 rows, 114 columns) and `fraud_analytics.duckdb`.
- Automatically outputs `outputs/audit_evidence/`:
  - `final_validation_report.csv` (100% pass on 9 integrity checks)
  - `relationship_integrity_report.csv` (foreign-key match rate audit)
  - `pipeline_summary.json` (machine-readable summary)

---

## 4. Autonomous AI Copilot (`backend/agent.py`)

### Architecture: LangGraph StateGraph
Unlike fragile regex or rigid keyword-metric registries, the copilot executes as a 5-node directed acyclic graph:

```
[START] ──► decompose_intent ──► generate_sql ──► execute_sql ──► render_chart ──► synthesize_response ──► [END]
```

### The 5 Graph Nodes:
1. **`node_decompose_intent`**:
   - Analyzes the user's natural language question.
   - Extracts: `needs_chart`, `chart_type` (`bar`, `hbar`, `line`, `pie`, `scatter`), `is_currency_metric`, and `is_rate_metric`.
   - Includes a **heuristic fallback** (`_heuristic_intent`) ensuring the copilot never crashes even if structured output fails.
2. **`node_generate_sql`**:
   - Injects the **full 114-column schema context** + categorical distinct values + `fraud_rings` table into the system prompt.
   - Generates read-only DuckDB SQL.
   - Strips Qwen thinking tags (`<think>...</think>`) and markdown fences.
   - **Safety Guardrail (`_validate_sql`)**: Rejects any query containing blocked keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `PRAGMA`).
3. **`node_execute_sql`**:
   - Executes the query inside DuckDB in memory.
   - Enforces `MAX_RESULT_ROWS = 500` to prevent memory blowouts.
4. **`node_render_chart`**:
   - If `needs_chart = True`, renders the appropriate chart using Matplotlib with a dark obsidian theme (`#0A0E14`, amber `#E8A33D` accents, currency formatting).
   - Generates unique timestamped artifacts (`chart_{ts}.png`).
5. **`node_synthesize_response`**:
   - Synthesizes findings into concise risk-officer prose.
   - Formats numbers into Indian numbering (₹, Lakhs, Crores).
   - Flags anomaly patterns automatically.

---

## 5. API Server & Asset Router (`backend/main.py`)

FastAPI application providing endpoints for the web console:
- `GET /`: Serves `frontend/index.html`.
- `GET /{filename}.js` & `GET /{filename}.css`: Multi-path asset router that resolves files from `../frontend` or `./frontend` automatically.
- `GET /stats`: Instant SQL-computed KPIs (<20ms response, zero LLM lag).
- `GET /dashboard-summary`: Complete aggregated telemetry for Plotly charts, top merchants, flagged txns, and fraud rings.
- `POST /ask`: Main agent entrypoint; returns `answer`, `chart_generated`, and `sql`.
- `GET /chart`: Serves the latest generated chart with `Cache-Control: no-cache`.
- `GET /health`: Liveness probe.

---

## 6. Frontend Console Architecture (`frontend/`)

Built as a lightweight, modular single-page application without bloated frameworks:
- **`index.html`**: Clean semantic markup (<180 lines). Zero inline scripts or inline styles.
- **`style.css`**: Institutional dark fintech design (`#080C14` background, monospace tabular figures, glowing risk badges).
- **`api.js`**: Auto-detects whether the app is running on `:8000`, `:5500` (Live Server), or a cloud URL, and provides data transformation helpers.
- **`dashboard.js`**:
  - Initializes the 5 KPI telemetry cards.
  - Renders 3 interactive Plotly visualizations:
    1. *Daily Volume & Dispute Velocity* (dual-axis area + line).
    2. *Merchant Category Volume Exposure* (horizontal bar).
    3. *Dispute Reason Code Anatomy* (donut chart).
  - Renders 2 live data tables:
    1. *Flagged High-Risk Merchants Audit* (with live text search filter).
    2. *Critical Transactions Ledger*.
    3. *NetworkX Fraud Rings & Collusion Clusters*.
- **`chat.js`**:
  - Controls the floating AI Copilot drawer.
  - Implements **collapsible SQL inspection traces** (`<details class="sql-trace">`) so evaluators can inspect the exact SQL query generated by the LLM.
  - Quick Diagnostic chips for 1-click query execution.

---

## 7. Matplotlib Report Exporter (`dashboard.py`)

A standalone script that produces `fraud_dashboard_overview.png` (300-DPI high-resolution static graphic).
- **Why it exists**: Satisfies Gate 4 requirements for static presentation slide assets.
- **Dynamic Path Resolution**: Safely detects whether it is executed from the repository root or inside `backend/`.

---

## 8. Auditing & Gate 2 Compliance Evidence

The pipeline automatically compiles evidence into `outputs/audit_evidence/`:

1. **`final_validation_report.csv`**:
   - `final_rows_preserved`: `True` (exactly 20,000)
   - `unique_txn_id`: `True` (20,000 unique IDs)
   - `zero_duplicate_txn_id`: `True`
   - `zero_null_txn_id`: `True`
   - `unique_kyc_master`: `True` (0 duplicate users)
   - `unique_merchant_master`: `True` (0 duplicate merchants)
   - `transaction_dates_parsed`: `True` (>95% parsed)
   - `amounts_parsed`: `True` (>95% parsed)
   - `zero_chargeback_fanout`: `True` (row count unchanged)
2. **`relationship_integrity_report.csv`**:
   - Detailed audit of foreign key match rates between transactions, KYC, merchants, and chargebacks.
3. **`pipeline_summary.json`**:
   - Machine-readable run configuration and verified metrics.

---

## 9. Judge Q&A Defense Strategy

### Question 1: "Why did you drop 400 transactions in Stage 2?"
> **Answer**: *"We analyzed the raw 20,400 rows and identified exactly 400 identical duplicate records where every field (timestamp, UTR, user, merchant, amount) was duplicate. Keeping them would have artificially inflated network volume by ₹48 Lakhs. We preserved 100% of distinct transactions (exactly 20,000) and did not drop any transaction for missing KYC or chargeback data."*

### Question 2: "How did your pipeline detect fraud during the joins?"
> **Answer**: *"Our joins surfaced five critical fraud signals: First, orphan foreign keys revealed 13,783 transactions initiated by unvetted users and shadow merchants. Second, we joined merchant declared ticket sizes against transaction amounts to detect >5x spikes, which flagged terminal compromise. Third, joining chargebacks revealed dispute amount mismatches exceeding 5%. Fourth, joining user income identified accounts spending >5x their declared annual income."*

### Question 3: "How did you detect fraud rings if transactions are strictly user-to-merchant?"
> **Answer**: *"Because the transaction log is bipartite, directed transaction cycles do not exist between users. Therefore, we used NetworkX to model entity infrastructure: we clustered merchants by shared bank settlement accounts, uncovering 203 collusion rings where multiple storefronts funnel money to the same account. We also clustered users by duplicate PAN credentials to find 1,340 synthetic identity mule clusters."*

### Question 4: "Why did you build an AI Copilot instead of just using PowerBI?"
> **Answer**: *"PowerBI is static and pre-aggregated. Risk investigations require dynamic exploratory SQL. Our LangGraph copilot inspects all 114 columns in DuckDB and compiles deterministic, read-only SQL in real time. We also provide a transparent SQL trace so risk officers can verify the query logic rather than blindly trusting LLM output."*
