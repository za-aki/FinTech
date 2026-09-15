# UPI Fraud Intelligence & Copilot System
**TransOrg AgentIQ Datathon — Track 1: FinTech & BFSI**

This repository contains our submission for Track 1 of the TransOrg AgentIQ Datathon. We built a complete end-to-end data pipeline, a NetworkX fraud detection engine, and an interactive FastAPI dashboard to analyze the provided synthetic UPI transactions, KYC records, merchant masters, and chargeback datasets.

## 🚀 Live Demo
**[https://fintech-dk9k.onrender.com](https://fintech-dk9k.onrender.com)**

## 🧠 Approach & Architecture

### 1. Data Cleaning & Normalization (`notebooks/` & `pipeline.py`)
Rather than dropping messy rows, we preserved data integrity by heavily utilizing Pandas and Regex to parse the raw datasets. We standardized `user_id` and `merchant_id` formats, normalized currency values, fixed timestamp mismatches, and resolved duplicate entries before executing a strict 5-way join across all datasets.

### 2. Graph-Based Fraud Ring Detection (`fraud_ring_detection.py`)
We went beyond standard SQL analytics by implementing a bipartite graph engine using **NetworkX**. This allowed us to automatically detect:
*   **Merchant Settlement Collusion:** 203 distinct merchants routing funds into shared bank accounts.
*   **Synthetic Identity Clusters:** 1,340 profiles registered under identical PAN/Aadhaar credentials.
*   **Coordinated Dispute Loops:** 24 dense networks of users repeatedly disputing transactions with the exact same merchants.

### 3. Analytics Engine & Dashboard (`agent.py` & `frontend/`)
*   **DuckDB:** All cleaned data is compiled into a high-performance, 112-feature analytical table loaded into in-memory DuckDB for zero-latency queries.
*   **Risk Policy Simulator:** An interactive dashboard widget allowing risk officers to instantly see the trade-off between blocking fraudulent transactions and increasing false-positive customer friction.

## 🏆 Best AI Agent Submission (Bonus Category)
We built our AI Copilot specifically to target the 30-point Agentic AI Bonus and the ₹3,000 special prize. 
Instead of relying on basic API calls, we engineered a fully autonomous **Text-to-SQL & Text-to-Chart Agent**:
*   **The Brain:** We used **LangChain** and **LangGraph** to build a directed acyclic graph (DAG) reasoning engine.
*   **The LLM:** Powered by **Groq** (running the incredibly fast **Qwen 2.5 27B** model).
*   **The Execution:** It writes read-only **DuckDB SQL** in real-time based on natural language questions, executes it securely in memory, and uses **Matplotlib** to dynamically render the exact requested chart type (Bar, Line, Pie, or Scatter) alongside a synthesized text summary.

## 💻 Tech Stack
*   **Backend:** Python 3, FastAPI, Pandas, NetworkX, DuckDB
*   **Frontend:** Vanilla JS, HTML, CSS (Light SaaS Theme), Plotly.js
*   **AI Engine:** LangChain, LangGraph, Groq (Qwen 27B)

## 📁 Repository Structure
*   `data/` - Contains the raw datathon files and our cleaned CSV outputs.
*   `notebooks/` - Jupyter notebooks showing our data exploration and cleaning rationale.
*   `backend/` - The FastAPI server, NetworkX engine, and LangChain Copilot.
*   `frontend/` - The dashboard UI files (HTML/CSS/JS).
*   `docs/CODE_EXPLAINED.md` - Extremely detailed documentation of our cleaning steps, graph logic, and AI prompt engineering.

## ⚙️ How to Run Locally

1. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
2. Set your free Groq API key:
   ```bash
   export GROQ_API_KEY="your_api_key_here"
   ```
3. Run the automated startup script (this runs the data pipelines and starts the server):
   ```bash
   ./run.sh
   ```
4. Open `http://localhost:8000` in your browser.
