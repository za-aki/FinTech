# FinTech - UPI Fraud Intelligence: Code & Methodology

Here is a simple breakdown of how our team built the data pipeline, the graph analysis, and the AI chatbot for this project.

## 1. Cleaning the Data (Pandas)
We used `pandas` in our backend to clean up the messy data without losing important transactions.

*   **Cleaning IDs:** The user and merchant IDs were messy (like `USR-123` or `usr 123`). We used regex to strip out special characters so we could properly link the tables together later.
*   **Fixing Currency:** The amount column had commas and strange symbols. We stripped everything except the numbers and turned them into clean floats.
*   **Parsing Dates:** The timestamps were all over the place. We used Pandas to standardize them so we could track trends over time.
*   **Duplicates:** We found exactly 400 identical duplicate rows in the raw file. We dropped them so we wouldn't fake the total network volume, but we preserved 100% of the actual 20,000 unique transactions.

## 2. Finding Fraud Rings (NetworkX)
Just looking at a spreadsheet isn't enough to find organized fraud. We used a Python library called `NetworkX` to build graphs and find connections between accounts.

*   **Merchant Rings:** We grouped merchants by their bank settlement accounts. If multiple different merchants route their money to the exact same bank account, it's a huge red flag. We found 203 of these rings.
*   **Fake Users:** We grouped users by their PAN card. If multiple user accounts share the exact same PAN, they are likely fake "mule" accounts. We found 1,340 of these.
*   **Dispute Networks:** We found 24 specific networks where the exact same group of users keep disputing transactions with the exact same group of merchants.

## 3. Joining the Data
In `backend/pipeline.py`, we join all the tables together (Transactions + KYC + Merchants + Chargebacks + Fraud Rings).
While joining, we calculate over 100 different risk features for every transaction. For example:
*   **Ticket Size Mismatch:** We check if the transaction amount is way higher than what the merchant usually sells.
*   **Income to Spend Ratio:** We check if a user is spending 5x more than their declared annual income.
*   **Ghost Users:** We flag transactions where the user isn't even in the KYC database.

Every transaction gets a fraud risk score from 0.0 to 1.0 based on these flags. We save this clean dataset and load it into DuckDB so our dashboard can query it instantly.

## 4. The AI Chatbot (For the Bonus Prize)
We wanted to hit the 30-point AI bonus, so we built an AI chatbot that actually writes SQL code instead of just guessing answers.

*   **How it understands:** It uses Groq (with the Qwen 27B model) to understand English questions and figure out what data the user is asking for.
*   **How it gets data:** It translates the English question into DuckDB SQL, runs the query on our clean dataset, and then uses Matplotlib to draw a chart (Bar, Line, Pie, or Scatter).
*   **Why we made it transparent:** AI can sometimes hallucinate, which is bad for a bank. So we added a "View SQL Query" button in the chat. This lets anyone click and see the exact SQL code the AI wrote to make sure the math is right.
