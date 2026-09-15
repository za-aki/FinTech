# FinTech - UPI Fraud Intelligence: Code & Methodology
TransOrg AgentIQ Datathon

This document explains exactly how our data pipeline, graph engine, and AI copilot work under the hood. We engineered this system to go far beyond standard SQL aggregations by focusing on data integrity, mathematical graph theory, and deterministic AI execution.

---

## 1. Data Cleaning (Pandas)
We used the `pandas` library heavily in `backend/pipeline.py` and our Jupyter notebooks to fix the messy data without recklessly dropping rows. 

*   Cleaning IDs: `user_id` and `merchant_id` were messy (e.g., `USR-123`, `usr 123`). We used regex `.str.replace(r'[^A-Z0-9]', '', regex=True)` to standardize everything so our SQL joins would actually work.
*   Fixing Currency: The `amount` column had strange symbols and commas. We stripped everything except numbers and decimals, and cast it to a `float`.
*   Parsing Dates: The timestamps were in completely different formats. We used `pd.to_datetime(..., errors='coerce')` to standardize them so we could do time-series analysis.
*   Deduplication: We found exactly 400 identical duplicate rows in the raw transaction file. We dropped them so we wouldn't artificially inflate the total network volume. We successfully preserved 100% of the 20,000 unique transactions.

## 2. Fraud Ring Detection (NetworkX)
We didn't just run SQL queries. Because UPI transactions are bipartite, direct peer-to-peer fraud is hidden. We used `NetworkX` in `backend/fraud_ring_detection.py` to build graphs and expose shared infrastructure:

*   Merchant Collusion: We grouped merchants by their `settlement_account`. If multiple storefronts route money to the exact same bank account, it's a collusion ring. We found 203 of these.
*   Synthetic Identities: We grouped users by their `pan` card. If multiple user IDs share the exact same PAN, they are likely mule accounts. We found 1,340 of these clusters.
*   Coordinated Disputes: We built a bipartite graph connecting users to merchants. Using `nx.connected_components()`, we found 24 dense networks where the same group of users are constantly disputing transactions with the same group of merchants.

## 3. The 112-Feature Pipeline & DuckDB
In `backend/pipeline.py`, we do a massive 5-way join (Transactions + KYC + Merchants + Chargebacks + Fraud Rings).
While joining, we calculate 112 different features for every single transaction. 

How our joins detect fraud:
*   Ticket Size Mismatch: We check if the transaction amount is >5x higher than the merchant's `declared_avg_ticket_size`.
*   Income to Spend Ratio: We check if a user is spending 5x more than their declared annual income.
*   Ghost Users: We flag transactions where the `user_id` literally doesn't exist in the KYC database.

Every transaction gets a `fraud_risk_score` from 0.0 to 1.0 based on these flags, the merchant's chargeback ratio, and their graph cycle score. This is all saved to `fraud_analytics_table.csv` and loaded into DuckDB for fast querying.

## 4. The AI Copilot (Targeting the Bonus Prize)
We built a LangGraph engine to hit the 30-point AI bonus rubric, completely avoiding the hallucination risks of basic chat APIs:
*   NLP Understanding (10 pts): Powered by Groq (using the Qwen 27B model), it understands natural language and maps it to our exact 112-column DuckDB schema.
*   Dynamic Charting (10 pts): It writes secure DuckDB SQL in real-time, executes it, and uses Matplotlib to draw the correct chart type (Bar, Line, Pie, Scatter) on the fly.
*   Text Summaries (10 pts): The LangChain pipeline synthesizes the exact numbers from the SQL execution into a clean, human-readable summary that displays next to the chart.

## 5. Judge Q&A Defense Strategy

If the judges ask us these questions during the pitch, here is exactly how we answer:

Question: "Why did you drop 400 transactions from the raw file?"
Answer: "We analyzed the raw 20,400 rows and found exactly 400 identical duplicates where every single field (timestamp, UTR, user, amount) was an exact copy. If we kept them, it would have artificially inflated the revenue by Rs. 48 Lakhs. We kept 100% of the distinct transactions and didn't drop anything just because it was missing KYC data."

Question: "How did your pipeline detect fraud during the joins?"
Answer: "Our joins actually created fraud signals. For example, when we joined transactions to merchants, we compared the transaction amount to the merchant's declared average ticket size. If there was a massive 5x spike, we flagged it as a compromised terminal. When we joined users, we flagged anyone spending way more than their declared annual income."

Question: "How did you detect fraud rings?"
Answer: "Because transactions are just user-to-merchant, direct user-to-user cycles don't exist. So we used NetworkX to look at shared infrastructure. We found 203 merchant rings where different storefronts route money to the same bank account, and 1,340 synthetic user rings sharing the exact same PAN card."

Question: "Why did you build an AI Copilot instead of just a dashboard?"
Answer: "Standard dashboards are static. Real fraud investigation requires exploratory SQL. Our AI looks at our 112 columns in DuckDB and writes deterministic SQL in real time. We also built a 'View SQL' toggle in the chat so risk officers can verify the exact query logic instead of blindly trusting the AI."
