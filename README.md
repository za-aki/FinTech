# FinTech - UPI Fraud Intelligence
TransOrg AgentIQ Datathon — Track 1: FinTech & BFSI

This repository contains our final submission for Track 1. While standard dashboards focus on basic SQL aggregations, we engineered an enterprise-grade intelligence system. We combined mathematical graph theory, an interactive risk simulator, and a deterministic text-to-SQL AI agent to detect organized fraud at the architectural level.

**Live Deployed Application:** [https://fintech-dk9k.onrender.com](https://fintech-dk9k.onrender.com)

## The Architecture: Why We Built It This Way

### 1. Data Integrity & Automated Audit Evidence
Most pipelines blindly use `dropna()` on messy datasets. Instead, we built a robust Pandas and Regex pipeline to clean the raw data, fix mismatched IDs, and normalize currencies. We preserved **100% of the 20,000 unique transactions** through a strict 5-way schema join. 
*To prove zero data loss occurred during the joins, our pipeline automatically generates a cryptographic-style `outputs/audit_evidence/` folder containing validation reports, guaranteeing our math is production-ready.*

### 2. NetworkX Graph Theory (The Secret Weapon)
UPI transactions are bipartite (user-to-merchant), meaning direct peer-to-peer fraud is hidden. Basic SQL queries cannot catch organized rings. We used NetworkX to model shared infrastructure, instantly discovering:
* **Merchant Collusion:** 203 distinct merchants funneling funds into identical bank settlement accounts.
* **Synthetic Identities:** 1,340 clusters of mule accounts registered under the exact same PAN credentials.

### 3. Actionable Business Logic (Risk Simulator) & Power BI
Static charts don't solve business problems. We built a custom HTML/JS **Risk Policy Simulator**. By adjusting risk thresholds on the dashboard, executives can instantly simulate the trade-off between blocking fraudulent transactions and increasing false-positive customer friction. We also integrated a deep-dive **Power BI** dashboard directly into the UI for enterprise analysts.

## Best AI Agent Submission (Targeting the 30-Point Bonus)
We didn't just plug a basic LLM API into a chatbox that hallucinates answers. We built a deterministic Text-to-SQL engine targeting the AI bonus rubric.
* **The Pipeline:** A LangChain and LangGraph reasoning engine.
* **The Database:** Clean data loaded into an in-memory DuckDB for zero-latency analytical querying.
* **The Execution:** Powered by Groq (Qwen 27B), the agent translates English into secure DuckDB SQL in real-time, executes it, and uses Matplotlib to draw the correct chart type (Bar, Line, Pie, or Scatter) alongside a synthesized text summary.
* **Transparency:** Risk officers can view the exact SQL trace in the UI to verify the logic.

## Repository Structure
* `video.mp4` - Our 3-minute pitch video demonstration.
* `FinTech_Fraud_Intelligence_Pitch.pdf` - Our architectural presentation deck.
* `frontend/` & `backend/` - The complete source code for our deployed application.
* `outputs/audit_evidence/` - Auto-generated proof of 100% data integrity post-joins.
* `docs/CODE_EXPLAINED.md` - A deep dive into the code, logic, 
