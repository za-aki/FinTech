"""
backend/main.py — FastAPI server for the Fraud Analytics Copilot.

Endpoints
─────────
  GET   /        → serve frontend index.html
  POST  /ask     → ask the agent a question → answer + optional chart
  GET   /chart   → latest generated chart image
  GET   /stats   → pre-computed KPIs (instant, no LLM)
  GET   /schema  → table schema for debugging
  GET   /health  → liveness check
"""

import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from agent import agent, get_chart_path, get_stats, get_dashboard_summary, get_schema, get_ring_graph_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fraud Analytics Copilot API",
    description="Natural-language interface over the fraud analytics table.",
    version="2.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5500",
    os.environ.get("FRONTEND_URL", ""),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ALLOWED_ORIGINS if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response schemas ─────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    thread_id: str = "default-session"


class AskResponse(BaseModel):
    answer: str
    chart_generated: bool
    sql: str = ""


# ── Endpoints ──────────────────────────────────────────────────────────

def _find_frontend_file(filename: str):
    candidates = [
        os.path.join(os.path.dirname(__file__), "../frontend", filename),
        os.path.join(os.path.dirname(__file__), "frontend", filename),
        os.path.join(os.path.dirname(__file__), filename),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

@app.get("/")
def serve_index():
    path = _find_frontend_file("index.html")
    if path:
        with open(path, "r") as f:
            return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-cache"})
    return HTMLResponse(
        content="<h3>Fraud Analytics API is running.</h3>"
                "<p>Place index.html in ../frontend/ to serve the dashboard.</p>",
        status_code=200,
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/{filename}.js")
def serve_js(filename: str):
    path = _find_frontend_file(f"{filename}.js")
    if path:
        return FileResponse(path, media_type="application/javascript", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail=f"{filename}.js not found")

@app.get("/{filename}.css")
def serve_css(filename: str):
    path = _find_frontend_file(f"{filename}.css")
    if path:
        return FileResponse(path, media_type="text/css", headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail=f"{filename}.css not found")


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest):
    """Send a natural-language question to the fraud copilot."""
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    logger.info("Question: %s", question[:120])
    
    # Fast-path for conversational greetings to bypass the SQL engine
    clean_q = question.lower().strip(" .?!")
    greet_words = {"hi", "hello", "hey", "help", "who are you", "what can you do", "greetings"}
    if clean_q in greet_words:
        return AskResponse(
            answer="Hello! I am the FinTech AI Copilot. I can analyze the database in real-time and generate actionable charts. Try asking me:\n\n- *'Show me top 5 merchants by dispute count'*\n- *'Plot a pie chart of transactions by risk tier'*\n- *'Show me a bar chart of volume by merchant category'*",
            chart_generated=False,
            sql=""
        )

    try:
        result = agent.invoke(
            {"question": question},
            config={"configurable": {"thread_id": payload.thread_id}},
        )
        return AskResponse(
            answer=result.get("answer", "No answer generated."),
            chart_generated=bool(result.get("chart_generated", False)),
            sql=result.get("sql", ""),
        )
    except Exception as exc:
        logger.exception("Agent invocation failed")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")


@app.get("/chart")
def chart():
    """Return the most recently generated chart image."""
    path = get_chart_path()
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No chart generated yet.")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/stats")
def stats():
    """Pre-computed KPIs — no LLM call, instant response."""
    data = get_stats()
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data


@app.get("/dashboard-summary")
def dashboard_summary():
    """Complete aggregated analytics package for high-performance interactive dashboard."""
    data = get_dashboard_summary()
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data


@app.get("/audit-summary")
def audit_summary():
    """Return Gate 2 referential integrity and validation audit reports."""
    try:
        audit_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../outputs/audit_evidence"))
        result = {}
        summary_path = os.path.join(audit_dir, "pipeline_summary.json")
        if os.path.exists(summary_path):
            import json
            with open(summary_path) as f:
                result["summary"] = json.load(f)

        val_path = os.path.join(audit_dir, "final_validation_report.csv")
        if os.path.exists(val_path):
            import pandas as pd
            result["validation"] = pd.read_csv(val_path).fillna("").to_dict(orient="records")

        rel_path = os.path.join(audit_dir, "relationship_integrity_report.csv")
        if os.path.exists(rel_path):
            import pandas as pd
            result["relationships"] = pd.read_csv(rel_path).fillna("").to_dict(orient="records")

        return result
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/schema")
def schema():
    """Return the auto-discovered table schema (useful for debugging)."""
    return JSONResponse(content={"schema": get_schema()})


@app.get("/graph-topology")
def graph_topology(ring_id: str = "RING-MERCH-0101"):
    """Return Cytoscape.js compatible graph topology for a specific fraud ring cluster."""
    data = get_ring_graph_data(ring_id)
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data


# ── Entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
    )