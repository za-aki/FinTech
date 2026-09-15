# UPI Fraud Intelligence & Copilot System
TransOrg AgentIQ Datathon — Track 1: FinTech & BFSI

This repository contains our submission for Track 1 of the Datathon. We built a data pipeline, a fraud detection engine using graphs, and an interactive dashboard to analyze the provided UPI transactions, KYC records, merchants, and chargebacks.

Live Demo
[https://fintech-dk9k.onrender.com](https://fintech-dk9k.onrender.com)

## What We Built

### 1. Data Cleaning
Instead of just dropping messy rows, we used Pandas and Regex to clean the data. We fixed user and merchant IDs, cleaned up the currency amounts, parsed the dates, and removed duplicate rows. After cleaning everything, we safely joined all the tables together.

### 2. Fraud Ring Detection
Fraud doesn't happen in isolation. We used NetworkX to find connections between accounts. This helped us find:
* Merchant Collusion: 203 merchants routing money to the same bank accounts.
* Synthetic Identities: 1,340 accounts using the exact same PAN card.
* Dispute Loops: 24 networks of users repeatedly disputing transactions with the same merchants.

### 3. Dashboard and Simulator
All our cleaned data was compiled into a single table with 112 features and loaded into DuckDB for really fast querying.
We also built a Risk Policy Simulator on the dashboard. This lets you play with risk thresholds to see how blocking fraud affects normal customers.

## Best AI Agent Submission (Bonus Category)
We built an AI Copilot to target the 30-point AI bonus. It handles text-to-SQL and text-to-chart generation.
* The Brain: We used LangChain and LangGraph to manage the logic.
* The LLM: Powered by Groq using the Qwen 2.5 27B model.
* How it works: You type a question in plain English. The AI writes DuckDB SQL in real-time, runs it, and uses Matplotlib to draw the right chart (Bar, Line, Pie, or Scatter). It also writes a short summary next to the chart.

## Tech Stack
* Backend: Python 3, FastAPI, Pandas, NetworkX, DuckDB
* Frontend: Vanilla JS, HTML, CSS, Plotly.js
* AI: LangChain, LangGraph, Groq

## Repository Structure
* data/ - The raw files and our cleaned outputs.
* notebooks/ - Our data exploration and cleaning scripts.
* backend/ - The FastAPI server, graph engine, and AI copilot code.
* frontend/ - The dashboard UI files.
* docs/CODE_EXPLAINED.md - Detailed breakdown of how our code actually works.
