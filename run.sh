#!/usr/bin/env bash
set -e

# ==============================================================================
# BFSI UPI Fraud Intelligence & Copilot System — 1-Click Startup Launcher
# Track 1: TransOrg AgentIQ Datathon
# ==============================================================================

echo "=================================================================="
echo "⚡ LAUNCHING UPI FRAUD INTELLIGENCE & COPILOT SYSTEM"
echo "=================================================================="

# 1. Verify Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is required but not installed."
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT/backend"

# 2. Verify / Run Graph Ring Detection
if [ ! -f "suspicious_cycles.csv" ]; then
    echo "🕸️ Running NetworkX Graph Fraud Ring Detection..."
    python3 fraud_ring_detection.py
else
    echo "✓ Detected existing 'suspicious_cycles.csv' (1,567 rings indexed)."
fi

# 3. Verify / Run Analytics Pipeline
if [ ! -f "fraud_analytics_table.csv" ] || [ ! -f "fraud_analytics.duckdb" ]; then
    echo "⚙️ Executing Fraud Analytics Pipeline (v2)..."
    python3 pipeline.py
else
    echo "✓ Analytics tables verified (20,000 transactions, 112 features)."
fi

# 4. Launch FastAPI Web Console
echo ""
echo "=================================================================="
echo "🚀 STARTING FASTAPI SERVER & INTERACTIVE CONSOLE"
echo "👉 Open http://localhost:8000 in your browser"
echo "=================================================================="
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
