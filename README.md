# ⚡ BFSI UPI Fraud Ring & Merchant Risk Intelligence System
### Track 1: FinTech & BFSI — UPI Fraud Ring & Merchant Analytics | TransOrg AgentIQ Datathon

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-v1.0+-yellow.svg)](https://duckdb.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-2.0.0-emerald.svg)](https://fastapi.tiangolo.com/)
[![NetworkX](https://img.shields.io/badge/NetworkX-Graph--First-orange.svg)](https://networkx.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Autonomous--Copilot-purple.svg)](https://www.langchain.com/)

An end-to-end, institutional-grade fraud intelligence suite that detects organized UPI transaction-laundering rings, merchant settlement collusion networks, and synthetic identity clusters. Powered by a **NetworkX graph topology engine**, **DuckDB columnar OLAP**, and an **autonomous LangGraph AI copilot** that translates natural language inquiries into deterministic SQL.

---

## 🎯 Executive Summary & Key Findings

Across **20,000 verified transactions** totaling **₹23.92 Crore** in monitored digital payment volume:
- **12.26% Network Dispute Rate**: 2,567 transactions incurred chargebacks, driven overwhelmingly by `UNAUTHORIZED_TRANSACTION` (37.0%) and `SERVICE_NOT_PROVIDED` (25.3%).
- **203 Merchant Settlement Collusion Rings**: Graph topology revealed 203 clusters where seemingly independent merchant storefronts funneled UPI revenue into the **exact same shadow bank account**.
- **1,340 Synthetic Identity Mule Clusters**: Discovered 1,340 clusters of user profiles sharing identical government PAN credentials, executing coordinated high-value transactions.
- **Critical Outlier Merchants**: Entities like `MCH3549` (Khalsa And Sons) and `MCH1744` exhibited a **100.0% chargeback rate** across all processed volume, tied directly to shadow settlement accounts.
- **Zero Data Loss Ingestion**: Maintained **exactly 20,000 transactions** across all joins with zero join fan-out and rigorous foreign key validation.

---

## 🏗️ System Architecture

```
[ RAW UNSTRUCTURED DATA ]
├── track1_upi_transactions.csv  (20,400 raw txns, currency symbols, mixed timestamps)
├── track1_kyc_records.csv       (36,400 customer records, duplicate IDs, OCR noise)
├── track1_merchants_master.csv  (6,210 merchant masters, inconsistent MCCs)
└── track1_chargebacks.json      (2,800 JSON dispute claims, unix/string dates)
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1 & 2: INGESTION, SANITIZATION & DEDUPLICATION        │
│ • Drop 400 exact dupes -> Exactly 20,000 transactions       │
│ • Resolve KYC (28,920 unique) & Merchants (4,343 unique)   │
│ • Date parsing with dual-ambiguity resolution               │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: STAR-SCHEMA JOINS & FOREIGN-KEY FRAUD SIGNALS      │
│ • Detect Orphaned Customers (67.5% Ghost User Signal)       │
│ • Detect Unregistered Merchant Gateways (51.9% Shadow Flag) │
│ • Disparity Checks: Amount vs Declared Ticket Size (>5x)    │
│ • Chargeback Join: Amount vs Disputed Amount Mismatch (>5%) │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 4: NETWORKX GRAPH FRAUD RING DETECTION ENGINE         │
│ • Merchant Collusion: Shared settlement account clustering  │
│ • Synthetic Identity: Shared PAN/Aadhaar identity networks  │
│ • Bipartite Dispute Subgraphs: Multi-node coordinated loops │
│ ↳ Output: suspicious_cycles.csv (1,567 indexed rings)       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 5: 112-FEATURE COMPOSITE RISK SCORING ENGINE          │
│ Score = 50% Rule Flags + 30% CB Ratio + 20% Graph Topology │
│ Categorized into: LOW, MEDIUM, HIGH, CRITICAL Tiers         │
│ ↳ Outputs: fraud_analytics_table.csv & DuckDB database     │
└──────────────────────────────┬──────────────────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│ AUTONOMOUS LANGGRAPH COPILOT│ │ LIVE INTERACTIVE CONSOLE     │
│ • Auto-discovers 112 schema │ │ • Zero static image hacks   │
│ • Generates safe DuckDB SQL │ │ • Plotly dual-axis velocity │
│ • Collapsible SQL execution │ │ • Live Flagged Merchant audit│
│ • 5 dynamic chart engines   │ │ • Live Graph Ring ledger    │
└─────────────────────────────┘ └─────────────────────────────┘
```

---

## 🔎 How the Pipeline Joins Detect Fraud

A key evaluation criterion is whether joins actively surface fraud:
1. **Ghost Users / Unregistered Account Laundering (`flag_unlinked_kyc`)**:
   Transactions initiated by `user_id`s that have no registration in the KYC master. Flagged when transacting in the top 90th percentile without identity vetting.
2. **Shadow Gateways / Unvetted Merchants (`flag_unlinked_merchant`)**:
   Transactions routing to merchant IDs that do not exist in the official Merchant Master.
3. **Ticket Size Inversion (`flag_amount_vs_ticket_mismatch`)**:
   During the merchant join, the transaction amount is dynamically compared against the merchant's `declared_avg_ticket_size`. A >5x spike or <0.2x deviation flags terminal compromise or ticket stuffing.
4. **Dispute Amount Disparity (`flag_disputed_amount_mismatch`)**:
   Joining chargeback complaints against transaction logs to compare `disputed_amount` vs original `amount`. A discrepancy >5% reveals fee inflation or unauthorized partial debit claims.
5. **Income-to-Spend Multiplier (`flag_income_spend_mismatch`)**:
   Annualized total spend compared against KYC `monthly_income * 12`. Spending >5x declared income isolates mule accounts and tax bypass vectors.

---

## 📁 Repository Structure

```
fraud-agent/
├── data/
│   ├── raw/                      # Original uncleaned datathon files
│   │   ├── track1_upi_transactions.csv
│   │   ├── track1_kyc_records.csv
│   │   ├── track1_merchants_master.csv
│   │   ├── track1_chargebacks.json
│   │   └── track1_dataset_notes.txt
│   └── cleaned/                  # Cleaned assets from Phase 1
│       ├── cleaned_transactions.csv
│       ├── cleaned_kyc.csv
│       ├── cleaned_merchants.csv
│       └── cleaned_chargebacks.csv
├── backend/
│   ├── Assets/                   # Active runtime data directory
│   ├── fraud_ring_detection.py   # NetworkX graph collusion ring detection
│   ├── pipeline_v2_fraud_scoring.py # 112-feature pipeline & composite scoring
│   ├── agent.py                  # LangGraph StateGraph autonomous copilot
│   ├── main.py                   # FastAPI application & static router
│   ├── requirements.txt          # Python dependencies
│   ├── suspicious_cycles.csv     # 1,567 detected graph rings
│   ├── fraud_analytics_table.csv # Single source of truth (20,000 x 112)
│   └── fraud_analytics.duckdb    # High-performance columnar DuckDB
├── frontend/
│   ├── index.html                # Clean, minimal institutional HTML (<150 lines)
│   ├── style.css                 # Dark fintech theme (obsidian #080C14, tabular nums)
│   ├── api.js                    # Modular API client & auto-port detection
│   ├── dashboard.js              # Plotly charts & live risk audit tables
│   └── chat.js                   # AI copilot drawer with SQL transparency trace
├── docs/
│   └── Problem Statements - TransOrg AgentIQ Datathon.pdf
├── dashboard.py                  # Standalone high-res Matplotlib graphic exporter
├── run.sh                        # 1-Click automated startup launcher
└── README.md                     # This documentation
```

---

## 🚀 Quickstart & 1-Click Launch

### Prerequisites
- Python 3.10+
- Free Groq API Key (for the autonomous copilot)

### 1. Setup Environment
```bash
git clone https://github.com/your-username/fraud-agent.git
cd fraud-agent

# Set your Groq API key (used by agent.py)
export GROQ_API_KEY="your-groq-api-key"
```

### 2. Run with One Command
```bash
./run.sh
```
*`run.sh` will automatically verify your graph cycle indexes, build the DuckDB tables if missing, and launch the FastAPI server at `http://localhost:8000`.*

### Manual Step-by-Step
```bash
cd backend
pip install -r requirements.txt

# 1. Run Graph Ring Detection
python3 fraud_ring_detection.py

# 2. Run Analytics Pipeline (outputs 20,000 x 112 table & DuckDB)
python3 pipeline_v2_fraud_scoring.py

# 3. Start the Web Console
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Open **`http://localhost:8000`** in any browser.

---

## 📊 Core Business Metrics (Verified Against Rubric)

| Metric | Measured Value | Methodology |
|---|---|---|
| **Total Monitored Transactions** | **20,000** | Deduplicated from 20,400 raw; 0 join fan-out |
| **Total Monitored Volume** | **₹23.92 Crore** | Currency-stripped, floating-point parsed |
| **Network Dispute Rate** | **12.26%** | 2,567 transactions with active disputes |
| **Network Failure Rate** | **9.78%** | 1,956 failed attempts normalized from 14 variants |
| **Multi-Flagged High-Risk Txns** | **2,163 txns** | Triggering $\ge 3$ simultaneous fraud flags |
| **Detected Merchant Collusion Rings** | **203 clusters** | Distinct merchants sharing identical settlement accounts |
| **Synthetic Identity Mule Networks** | **1,340 clusters** | Disparate user accounts registered under identical PAN |
| **Coordinated Dispute Subgraphs** | **24 clusters** | Multi-node connected components in dispute bipartite graph |
| **Critical Outlier Merchant** | **MCH3549** | 100.0% chargeback ratio across all processed volume |

---

## 🎤 3-Minute Live Presentation Pitch Script

1. **The Context (0:00 - 0:45)**:
   > *"We monitored ₹23.92 Crore across 20,000 UPI transactions. While the average network dispute rate is 12.26%, our multi-layer intelligence engine revealed that fraud is not uniformly distributed — it is concentrated in organized merchant collusion rings and synthetic identity networks."*
2. **The Graph Discovery (0:45 - 1:45)**:
   > *"Notice merchant MCH3549 (Khalsa And Sons) and MCH1744. They display a 100% chargeback rate across all processed volume. When we executed our NetworkX graph engine across settlement accounts, we uncovered 203 merchant collusion clusters — distinct storefronts routing illicit proceeds into shared bank accounts."*
3. **The Autonomous Copilot (1:45 - 3:00)**:
   > *"Rather than relying on pre-baked charts, our LangGraph AI copilot queries our 112-column DuckDB database dynamically. Notice that every response includes a transparent, inspectable SQL trace so risk officers can verify the exact deterministic logic behind every insight."*
