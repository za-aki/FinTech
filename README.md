# FinTech - UPI Fraud Intelligence
TransOrg AgentIQ Datathon — Track 1: FinTech & BFSI

This repository contains our final submission for Track 1. While a lot of dashboards just show basic SQL aggregations, we wanted to build something that actually finds organized crime. Our three-person team combined mathematical graph theory, an interactive risk simulator, and an AI agent that writes real SQL to detect fraud rings.

**Live Deployed Application:** [https://fintech-dk9k.onrender.com](https://fintech-dk9k.onrender.com)

## The Architecture: Why We Built It This Way

### 1. Data Integrity & Automated Audits
Most data pipelines just drop rows when the data gets messy. Instead, Bhavya and I collaborated to build a robust Pandas pipeline using regex to clean the raw data, fix mismatched IDs, and format currencies. We preserved **100% of the 20,000 unique transactions** through a massive 5-way join. 
*To prove that we didn't accidentally lose or duplicate any transactions during the joins, our pipeline automatically generates an `outputs/audit_evidence/` folder. This proves our math is totally solid.*

### 2. NetworkX Graph Theory (The Secret Weapon)
UPI transactions just go from user to merchant, which hides direct peer-to-peer fraud. Basic SQL queries can't catch organized rings. We used NetworkX to model shared connections and instantly discovered:
* **Merchant Collusion:** 203 distinct merchants funneling funds into the exact same bank settlement accounts.
* **Synthetic Identities:** 1,340 clusters of mule accounts registered under the exact same PAN credentials.

### 3. Risk Simulator & Power BI
Static charts don't really solve business problems. We built a custom HTML/JS **Risk Policy Simulator**. By adjusting the sliders on the dashboard, you can simulate the trade-off between blocking fraudulent transactions and annoying real customers. Additionally, Aiswarya embedded a deep-dive **Power BI** dashboard directly into the UI for further analysis.

## Security & LLM Guardrails
Since AI can be unpredictable, we hardcoded strict guardrails into our Python backend:
* **Anti-SQL Injection:** The LangGraph agent is completely blocked from running DML/DDL commands. If the AI ever tries to run a `DROP`, `DELETE`, or `UPDATE` statement, our backend kills the query before it hits the database.
* **API Protection:** To prevent people from spamming our public Render demo and draining the API limits, the chat interface restricts users to 10 queries per session.
* **File Security:** The FastAPI server strictly enforces file extensions, so attackers can't read our backend Python files or environment secrets.

## The AI Agent (Targeting the 30-Point Bonus)
We didn't just plug a basic LLM API into a chatbox. We built a Text-to-SQL engine targeting the AI bonus rubric.
* **The Pipeline:** We used LangChain and LangGraph to route the logic.
* **The Database:** The clean data is loaded into an in-memory DuckDB database so queries run instantly.
* **The Execution:** Powered by Groq (Qwen 27B), the agent translates English into secure SQL in real-time, runs it, and uses Matplotlib to draw the correct chart (Bar, Line, Pie, or Scatter).
* **Transparency:** You can click "View SQL Query" in the chat to see exactly what code the AI wrote, so there are no black boxes.

## Repository Structure
* `video.mp4` - Our 3-minute pitch video demonstration.
* `FinTech_Fraud_Intelligence_Pitch.pdf` - Our presentation deck mapping out the architecture.
* `frontend/` & `backend/` - The complete source code for our deployed application.
* `outputs/audit_evidence/` - Auto-generated proof of 100% data integrity.
* `docs/CODE_EXPLAINED.md` - A simple breakdown of our code and logic.
