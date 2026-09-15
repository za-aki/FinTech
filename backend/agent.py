"""
agent.py

This handles the AI chatbot and dashboard APIs.
It uses LangGraph to turn user questions into SQL, runs it against DuckDB,
and returns the answers and charts.
Reads from fraud_analytics_table.csv.
"""

import os
import re
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from typing import Optional, Literal, TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Configuration & Path Resolution ────────────────────────────────────
def _resolve_data_file(env_var: str, default_filename: str) -> str:
    env_val = os.environ.get(env_var)
    if env_val and os.path.exists(env_val):
        return os.path.abspath(env_val)
    candidates = [
        default_filename,
        os.path.join(os.path.dirname(__file__), default_filename),
        os.path.join(os.path.dirname(__file__), "..", default_filename),
        os.path.join(os.path.dirname(__file__), "../outputs/audit_evidence", default_filename),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return default_filename

DATA_PATH  = _resolve_data_file("FRAUD_DATA_PATH", "fraud_analytics_table.csv")
CHART_DIR  = os.environ.get("CHART_OUTPUT_DIR", os.path.dirname(__file__))
MODEL_NAME = os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b")

# ── LLM ────────────────────────────────────────────────────────────────
groq_api_key = os.environ.get("GROQ_API_KEY") or "gsk_placeholder_telemetry_key"
llm = ChatGroq(
    model=MODEL_NAME,
    api_key=groq_api_key,
    temperature=0.0,
    max_tokens=800,
)

# ── Database ───────────────────────────────────────────────────────────
con = duckdb.connect(database=":memory:")
con.execute(f"CREATE TABLE fraud_data AS SELECT * FROM '{DATA_PATH}'")
CYCLES_PATH = _resolve_data_file("CYCLES_PATH", "suspicious_cycles.csv")
if os.path.exists(CYCLES_PATH):
    con.execute(f"CREATE TABLE fraud_rings AS SELECT * FROM '{CYCLES_PATH}'")

# ── Schema Context (auto-discovered at startup) ───────────────────────

_COL_DESCRIPTIONS = {
    "txn_id":                       "unique transaction ID, e.g. TXN00011869",
    "timestamp":                    "transaction timestamp (text, cast to TIMESTAMP for date ops)",
    "user_id":                      "customer ID, e.g. USR45826",
    "merchant_id":                  "merchant ID, e.g. MCH7045",
    "amount":                       "transaction amount in INR",
    "status":                       "SUCCESS | FAILED | PENDING",
    "merchant_category":            "e.g. Apparel, Grocery, Electronics",
    "merchant_name":                "name of the merchant business",
    "merchant_status":              "Active | Suspended | Inactive | Unknown",
    "kyc_status":                   "APPROVED | REJECTED | UNDER_REVIEW | PENDING",
    "fraud_risk_score":             "composite fraud score 0.0–1.0",
    "risk_tier":                    "LOW | MEDIUM | HIGH | CRITICAL",
    "flag_count":                   "count of boolean fraud flags triggered (0–18)",
    "is_disputed":                  "true if this txn has a chargeback dispute",
    "dispute_count":                "number of disputes on this txn (NULL if none)",
    "total_disputed_amount":        "total disputed amount in INR",
    "top_reason_code":              "primary dispute reason: UNAUTHORIZED_TRANSACTION, SERVICE_NOT_PROVIDED, WRONG_AMOUNT, DUPLICATE_TRANSACTION, etc.",
    "max_severity":                 "highest dispute severity: CRITICAL | HIGH | MEDIUM | LOW",
    "latest_reported":              "timestamp when dispute was reported",
    "user_txn_count":               "total transactions by this user (aggregate)",
    "user_total_volume":            "total transaction volume by this user in INR",
    "user_failed_rate":             "fraction of this user's transactions that failed",
    "user_distinct_merchants":      "number of unique merchants the user transacted with",
    "user_max_single_txn":          "largest single transaction amount for this user",
    "user_amount_zscore":           "z-score of this txn amount vs user's own mean/std",
    "merchant_txn_count":           "total transactions for this merchant",
    "merchant_chargeback_ratio":    "fraction of this merchant's txns with disputes",
    "category_chargeback_ratio":    "dispute ratio for this merchant_category",
    "txn_hour":                     "hour of day (0–23)",
    "txn_day_of_week":              "day of week (0=Mon, 6=Sun)",
    "is_weekend":                   "true if Saturday or Sunday",
    "is_night_txn":                 "true if between 00:00 and 04:59",
    "flag_round_amount":            "true if amount is exact multiple of 1000",
    "monthly_income":               "user's declared monthly income",
    "user_income_to_spend_ratio":   "user total spend / (monthly_income × 12)",
    "risk_segment":                 "KYC risk segment: Low | Medium | High",
    "occupation":                   "user's declared occupation",
    "city":                         "user's city",
    "state":                        "user's state",
    "business_type":                "merchant business type",
    "flag_amount_anomaly":          "true if amount was negative or unparseable",
    "flag_kyc_doc_invalid":         "true if PAN or Aadhaar is invalid",
    "flag_merchant_suspended":      "true if merchant status is Suspended",
    "flag_high_severity_dispute":   "true if dispute severity is CRITICAL or HIGH",
    "flag_unauthorized_reason":     "true if dispute reason is UNAUTHORIZED_TRANSACTION",
    "flag_income_spend_mismatch":   "true if spending >5× declared annual income",
    "flag_new_account_high_volume": "true if brand-new account with top-10% volume",
    "flag_invalid_kyc_high_volume": "true if invalid KYC docs + top-10% volume",
    "flag_merchant_above_category_median": "true if merchant's CB ratio > category median",
    "flag_amount_zscore_outlier":   "true if |z-score| > 3 for this user",
    "user_cycle_score":             "fraud-ring cycle score for user (0–1)",
    "merchant_cycle_score":         "fraud-ring cycle score for merchant (0–1)",
    "days_since_signup_at_txn":     "days between account signup and this txn",
}


def _build_schema_context() -> str:
    """Auto-discover schema from DuckDB and enrich with descriptions."""
    cols = con.execute("DESCRIBE fraud_data").fetchall()
    row_count = con.execute("SELECT COUNT(*) FROM fraud_data").fetchone()[0]

    lines = [
        f"Table: fraud_data  ({row_count:,} rows, {len(cols)} columns)",
        "",
        "Columns:",
    ]
    for col_name, col_type, *_ in cols:
        desc = _COL_DESCRIPTIONS.get(col_name, "")
        suffix = f" — {desc}" if desc else ""
        lines.append(f"  {col_name}  {col_type}{suffix}")

    # Sample distinct values for key categorical columns
    for cat_col in [
        "status", "merchant_category", "kyc_status", "risk_tier",
        "top_reason_code", "max_severity", "merchant_status", "risk_segment",
    ]:
        try:
            vals = con.execute(
                f"SELECT DISTINCT {cat_col} FROM fraud_data "
                f"WHERE {cat_col} IS NOT NULL ORDER BY {cat_col} LIMIT 25"
            ).fetchall()
            if vals:
                lines.append(
                    f"  ↳ {cat_col} values: {', '.join(str(v[0]) for v in vals)}"
                )
        except Exception:
            pass

    # Auto-discover fraud_rings if available
    try:
        r_cols = con.execute("DESCRIBE fraud_rings").fetchall()
        r_count = con.execute("SELECT COUNT(*) FROM fraud_rings").fetchone()[0]
        lines.append(f"\nTable: fraud_rings  ({r_count:,} graph clusters detected by NetworkX)")
        lines.append("Columns:")
        for c_name, c_type, *_ in r_cols:
            lines.append(f"  {c_name}  {c_type}")
        lines.append("  ↳ ring_type values: MERCHANT_SETTLEMENT_COLLUSION, SYNTHETIC_IDENTITY_MULE_RING, COORDINATED_DISPUTE_NETWORK")
    except Exception:
        pass

    return "\n".join(lines)


SCHEMA_CONTEXT = _build_schema_context()

# ── SQL Safety ─────────────────────────────────────────────────────────
_BLOCKED_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|COPY|ATTACH|DETACH"
    r"|PRAGMA|EXPORT|IMPORT|EXECUTE)\b",
    re.IGNORECASE,
)
MAX_RESULT_ROWS = 500


def _validate_sql(sql: str) -> tuple[bool, str]:
    stripped = sql.strip().rstrip(";")
    if _BLOCKED_RE.search(stripped):
        return False, "Query contains a blocked keyword (DML/DDL)."
    if not stripped.upper().startswith(("SELECT", "WITH")):
        return False, "Query must begin with SELECT or WITH."
    return True, ""


# ── Structured Intent Schema ──────────────────────────────────────────
class AnalyticalIntent(BaseModel):
    """LLM-extracted intent from a user's natural-language question."""
    reasoning: str = Field(
        description="Step-by-step reasoning about what the user wants."
    )
    needs_chart: bool = Field(
        default=False,
        description="True if the answer benefits from a visual chart.",
    )
    chart_type: Literal["bar", "hbar", "line", "scatter", "pie"] = Field(
        default="bar",
        description="Best chart type for this data.",
    )
    chart_title: str = Field(
        default="",
        description="Clean, descriptive chart title (no jargon).",
    )
    is_currency_metric: bool = Field(
        default=False,
        description="True if the primary metric is a monetary value in INR.",
    )
    is_rate_metric: bool = Field(
        default=False,
        description="True if the primary metric is a rate / ratio / percentage.",
    )


_intent_llm = llm.with_structured_output(AnalyticalIntent)


# ── LangGraph State ───────────────────────────────────────────────────
class AgentState(TypedDict):
    question:   str
    intent:     Optional[AnalyticalIntent]
    sql:        str
    sql_error:  str
    results:    list
    columns:    list
    chart_path: str
    answer:     str
    error:      str


# ── Node 1 — Intent Decomposition ────────────────────────────────────

def _heuristic_intent(question: str) -> AnalyticalIntent:
    """Fast keyword-based fallback when structured LLM output fails."""
    q = question.lower()
    needs_chart = any(w in q for w in ("show", "chart", "plot", "trend", "compare", "top", "by ", "distribution"))
    is_currency = any(w in q for w in ("amount", "volume", "revenue", "spend", "income", "ticket"))
    is_rate = any(w in q for w in ("rate", "ratio", "percent", "fraction"))

    chart_type = "bar"
    if any(w in q for w in ("trend", "daily", "over time", "hourly")):
        chart_type = "line"
    elif any(w in q for w in ("distribution", "breakdown", "split", "proportion")):
        chart_type = "pie"
    elif any(w in q for w in ("category", "reason")):
        chart_type = "hbar"

    return AnalyticalIntent(
        reasoning=f"Heuristic fallback for: {question}",
        needs_chart=needs_chart,
        chart_type=chart_type,
        chart_title=question[:80],
        is_currency_metric=is_currency,
        is_rate_metric=is_rate,
    )


def node_decompose_intent(state: AgentState) -> dict:
    question = state["question"]
    try:
        intent = _intent_llm.invoke(
            "You are analysing a UPI fraud-analytics dataset for an Indian fintech. "
            "Given the user's question, determine the analytical intent.\n\n"
            "Guidelines:\n"
            "• 'bar'    → comparisons across categories (top merchants, users)\n"
            "• 'hbar'   → categories with long names (merchant categories, reason codes)\n"
            "• 'line'   → trends over time (daily, hourly)\n"
            "• 'pie'    → distributions / proportions (status split, reason codes)\n"
            "• 'scatter' → correlations between two numeric variables\n"
            "• Set needs_chart = true whenever the answer has grouped data (≥ 2 rows)\n"
            "• Set is_currency_metric = true for INR amounts\n"
            "• Set is_rate_metric = true for percentages / ratios\n\n"
            f"User question: {question}"
        )
        if intent is None:
            raise ValueError("structured output returned None")
        return {"intent": intent}
    except Exception:
        return {"intent": _heuristic_intent(question)}


# ── Node 2 — SQL Generation ──────────────────────────────────────────
_SQL_SYSTEM_PROMPT = (
    "You are a DuckDB SQL expert. Generate ONE valid DuckDB SELECT query "
    "that answers the user's question against the schema below.\n\n"
    "RULES:\n"
    "1. Use ONLY columns listed in the schema.\n"
    "2. Table name is `fraud_data`.\n"
    "3. For date/time grouping use:\n"
    "     DATE_TRUNC('day', CAST(timestamp AS TIMESTAMP))  for daily\n"
    "     EXTRACT(HOUR FROM CAST(timestamp AS TIMESTAMP))  for hourly\n"
    "4. Alias result columns clearly (e.g. AS category, AS total_amount).\n"
    "5. For rates, multiply by 100 and ROUND to 2 decimals.\n"
    "6. LIMIT to 20 unless the user asks for more.\n"
    "7. ORDER BY the metric DESC (ASC for time series).\n"
    "8. For 'distribution' questions use COUNT(*) with GROUP BY.\n"
    "9. Handle NULLs with COALESCE where appropriate.\n"
    "10. Use pre-computed aggregate columns (merchant_chargeback_ratio, "
    "user_total_volume, etc.) when available instead of re-aggregating.\n"
    "11. `is_disputed` is a BOOLEAN column — use it for dispute filtering.\n"
    "12. `dispute_count` is NULL when there are no disputes — COALESCE to 0.\n"
    "13. Return ONLY the SQL, no explanation, no markdown fences.\n"
)


def node_generate_sql(state: AgentState) -> dict:
    question = state["question"]
    intent = state.get("intent")
    reasoning = intent.reasoning if intent else ""

    prompt = (
        f"{_SQL_SYSTEM_PROMPT}\n"
        f"SCHEMA:\n{SCHEMA_CONTEXT}\n\n"
        f"QUESTION: {question}\n"
        f"REASONING: {reasoning}\n\n"
        "SQL:"
    )
    try:
        response = llm.invoke(prompt)
        sql = response.content.strip()
        # Strip Qwen-3 thinking tags if present
        sql = re.sub(r"<think>.*?</think>", "", sql, flags=re.DOTALL).strip()
        # Strip markdown fencing if present
        sql = re.sub(r"^```(?:sql)?\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.strip().rstrip(";")

        ok, err = _validate_sql(sql)
        if not ok:
            return {"sql": "", "sql_error": err}
        return {"sql": sql, "sql_error": ""}
    except Exception as exc:
        return {"sql": "", "sql_error": str(exc)}


# ── Node 3 — Execute SQL ─────────────────────────────────────────────
def node_execute_sql(state: AgentState) -> dict:
    sql = state.get("sql", "")
    if not sql:
        return {
            "results": [],
            "columns": [],
            "error": state.get("sql_error", "No SQL was generated."),
        }
    try:
        cursor = con.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchmany(MAX_RESULT_ROWS)
        return {
            "results": [list(r) for r in rows],
            "columns": columns,
            "error": "",
        }
    except Exception as exc:
        return {
            "results": [],
            "columns": [],
            "error": f"SQL execution error: {exc}\nGenerated SQL: {sql}",
        }


# ── Node 4 — Chart Rendering ─────────────────────────────────────────

# Theme palette (matches the frontend CSS variables)
_BG       = "#f8f9fb"
_SURFACE  = "#ffffff"
_BORDER   = "#e2e5ea"
_TEXT     = "#111827"
_TEXT_DIM = "#6b7280"
_AMBER    = "#d97706"
_DANGER   = "#dc2626"
_SAFE     = "#059669"
_BLUE     = "#2563eb"
_PALETTE  = [_BLUE, _DANGER, _SAFE, _AMBER, "#7c3aed", "#0891b2", "#fbbf24", "#34d399"]


def _fmt_inr_short(value: float) -> str:
    """Compact INR label for chart axes."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(value) >= 1_00_00_000:
        return f"₹{value / 1_00_00_000:.1f}Cr"
    if abs(value) >= 1_00_000:
        return f"₹{value / 1_00_000:.1f}L"
    if abs(value) >= 1_000:
        return f"₹{value / 1_000:.1f}K"
    return f"₹{value:,.0f}"


def _fmt_inr(value) -> str:
    """Full INR formatting (lakhs / crores) for text output."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(value) >= 1_00_00_000:
        return f"₹{value / 1_00_00_000:.2f} crore"
    if abs(value) >= 1_00_000:
        return f"₹{value / 1_00_000:.2f} lakh"
    return f"₹{value:,.2f}"


def _apply_theme(fig, ax, chart_type: str, intent: AnalyticalIntent):
    """Apply the dark-theme styling to any chart (except pie)."""
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_SURFACE)
    ax.tick_params(colors=_TEXT_DIM, labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(_BORDER)
    ax.grid(axis="y", linestyle="--", alpha=0.12, color=_TEXT_DIM)

    if intent.is_currency_metric and chart_type != "hbar":
        ax.yaxis.set_major_formatter(lambda x, _: _fmt_inr_short(x))
        ax.set_ylabel("Amount (₹)", color=_TEXT_DIM, fontsize=10)
    elif intent.is_rate_metric and chart_type != "hbar":
        ax.set_ylabel("Rate (%)", color=_TEXT_DIM, fontsize=10)

    title = intent.chart_title or "Analysis"
    ax.set_title(title, color=_TEXT, fontsize=12, fontweight="600", pad=14)


def node_render_chart(state: AgentState) -> dict:
    intent  = state.get("intent")
    results = state.get("results", [])
    columns = state.get("columns", [])

    if (
        not intent
        or not intent.needs_chart
        or not results
        or len(results) < 1
        or len(columns) < 2
    ):
        return {"chart_path": ""}

    chart_type = intent.chart_type or "bar"
    ts = int(datetime.now().timestamp())
    chart_path = os.path.join(CHART_DIR, f"chart_{ts}.png")

    labels = [str(r[0]) for r in results]

    # Find the first numeric column (index >= 1) for values
    value_idx = 1
    for idx in range(1, len(results[0])):
        try:
            float(results[0][idx])
            value_idx = idx
            break
        except (TypeError, ValueError):
            continue

    try:
        values = [float(r[value_idx]) if r[value_idx] is not None else 0.0 for r in results]
    except (TypeError, ValueError, IndexError):
        return {"chart_path": ""}

    try:
        fig, ax = plt.subplots(figsize=(10, 5.5))

        if chart_type == "bar":
            bars = ax.bar(labels, values, color=_AMBER, edgecolor=_BORDER,
                          linewidth=0.5, alpha=0.92)
            # Value labels
            peak = max(values) if values else 1
            for bar, val in zip(bars, values):
                if intent.is_currency_metric:
                    lbl = _fmt_inr_short(val)
                elif intent.is_rate_metric:
                    lbl = f"{val:.1f}%"
                else:
                    lbl = f"{val:,.0f}" if val == int(val) else f"{val:.2f}"
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + peak * 0.02,
                    lbl, ha="center", va="bottom",
                    fontsize=8, color=_TEXT_DIM,
                )
            plt.xticks(rotation=35, ha="right", fontsize=9)
            _apply_theme(fig, ax, chart_type, intent)

        elif chart_type == "hbar":
            y_pos = range(len(labels))
            ax.barh(y_pos, values, color=_AMBER, edgecolor=_BORDER,
                    linewidth=0.5, alpha=0.92)
            ax.set_yticks(list(y_pos))
            ax.set_yticklabels(labels, fontsize=9)
            ax.invert_yaxis()
            _apply_theme(fig, ax, chart_type, intent)
            # Value labels to the right
            peak = max(values) if values else 1
            for i, val in enumerate(values):
                if intent.is_currency_metric:
                    lbl = _fmt_inr_short(val)
                elif intent.is_rate_metric:
                    lbl = f"{val:.1f}%"
                else:
                    lbl = f"{val:,.0f}" if val == int(val) else f"{val:.2f}"
                ax.text(val + peak * 0.01, i, lbl,
                        va="center", fontsize=8, color=_TEXT_DIM)

        elif chart_type == "line":
            ax.plot(labels, values, marker="o", color=_AMBER,
                    linewidth=2, markersize=5)
            ax.fill_between(range(len(labels)), values, alpha=0.08, color=_AMBER)
            plt.xticks(rotation=35, ha="right", fontsize=9)
            _apply_theme(fig, ax, chart_type, intent)

        elif chart_type == "scatter":
            ax.scatter(labels, values, color=_AMBER, s=60,
                       edgecolors=_BORDER, linewidth=0.5)
            plt.xticks(rotation=35, ha="right", fontsize=9)
            _apply_theme(fig, ax, chart_type, intent)

        elif chart_type == "pie":
            # Pie gets its own layout
            fig.clear()
            ax = fig.add_subplot(111)
            fig.patch.set_facecolor(_BG)
            ax.set_facecolor(_BG)
            wedge_colors = (_PALETTE * ((len(labels) // len(_PALETTE)) + 1))[
                : len(labels)
            ]
            wedges, texts, autotexts = ax.pie(
                values,
                labels=labels,
                autopct="%1.1f%%",
                colors=wedge_colors,
                textprops={"color": _TEXT, "fontsize": 9},
                pctdistance=0.80,
                startangle=90,
            )
            for t in autotexts:
                t.set_fontsize(8)
                t.set_color(_TEXT_DIM)
            title = intent.chart_title or "Distribution"
            ax.set_title(title, color=_TEXT, fontsize=12, fontweight="600", pad=14)

        plt.tight_layout()
        plt.savefig(
            chart_path,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
            dpi=150,
            edgecolor="none",
        )
        plt.close()
        return {"chart_path": chart_path}

    except Exception:
        plt.close("all")
        return {"chart_path": ""}


# ── Node 5 — Response Synthesis ───────────────────────────────────────
def node_synthesize_response(state: AgentState) -> dict:
    question   = state["question"]
    results    = state.get("results", [])
    columns    = state.get("columns", [])
    error      = state.get("error", "")
    chart_path = state.get("chart_path", "")
    intent     = state.get("intent")

    if error:
        return {"answer": f"I couldn't process that query.\n\n**Error:** {error}"}

    if not results:
        return {
            "answer": "No data matched your query. "
                      "Try rephrasing or broadening your question."
        }

    # Build a compact result table for the LLM
    header = " | ".join(columns)
    body_lines = [" | ".join(str(v) for v in row) for row in results[:20]]
    result_table = header + "\n" + "\n".join(body_lines)
    if len(results) > 20:
        result_table += f"\n… and {len(results) - 20} more rows"

    prompt = (
        "You are a fraud-analytics expert presenting findings to a fintech risk team. "
        "Summarise the query results in 2–4 concise sentences with specific numbers.\n\n"
        "Formatting rules:\n"
        "• Use Indian Rupee formatting: ₹, lakhs, crores.\n"
        "• Bold (**) key numbers and entity names.\n"
        "• Lead with the most important finding.\n"
        "• If fraud / risk patterns are visible, call them out.\n"
        "• Be factual — only state what the data shows.\n"
        "• For grouped results, include a markdown bullet list of the top entries.\n\n"
        f"User question: {question}\n\n"
        f"Query results ({len(results)} rows):\n{result_table}"
    )

    try:
        response = llm.invoke(prompt)
        answer = response.content.strip()
        # Strip Qwen-3 thinking tags if present
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
    except Exception:
        answer = _fallback_format(results, columns, intent)

    if chart_path:
        answer += "\n\n📊 *Chart generated.*"
    return {"answer": answer}


def _fallback_format(results, columns, intent) -> str:
    """Deterministic formatting when the synthesis LLM call fails."""
    if not results:
        return "No results found."
    if len(columns) == 1:
        return f"**Result:** {results[0][0]}"

    lines = []
    for row in results[:12]:
        label = str(row[0])
        value = row[1]
        if intent and intent.is_currency_metric:
            fmt = _fmt_inr(value)
        elif isinstance(value, float):
            fmt = f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"
        else:
            fmt = str(value)
        lines.append(f"- **{label}**: `{fmt}`")
    return "\n".join(lines)


# ── Build Graph ───────────────────────────────────────────────────────
def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("decompose_intent",    node_decompose_intent)
    g.add_node("generate_sql",        node_generate_sql)
    g.add_node("execute_sql",         node_execute_sql)
    g.add_node("render_chart",        node_render_chart)
    g.add_node("synthesize_response", node_synthesize_response)

    g.add_edge(START,                 "decompose_intent")
    g.add_edge("decompose_intent",    "generate_sql")
    g.add_edge("generate_sql",        "execute_sql")
    g.add_edge("execute_sql",         "render_chart")
    g.add_edge("render_chart",        "synthesize_response")
    g.add_edge("synthesize_response", END)
    return g.compile()


_graph = _build_graph()


# ── Public API ────────────────────────────────────────────────────────
CHART_PATH = ""  # most-recently generated chart (used by main.py)


class FraudCopilot:
    """Thin wrapper that invokes the LangGraph pipeline."""

    def invoke(self, payload: dict, config: Optional[dict] = None) -> dict:
        global CHART_PATH
        question = payload.get("question", "")

        initial_state: AgentState = {
            "question":   question,
            "intent":     None,
            "sql":        "",
            "sql_error":  "",
            "results":    [],
            "columns":    [],
            "chart_path": "",
            "answer":     "",
            "error":      "",
        }

        try:
            final = _graph.invoke(initial_state)
        except Exception as exc:
            return {
                "answer": f"Agent pipeline error: {exc}",
                "chart_generated": False,
                "sql": "",
            }

        chart = final.get("chart_path", "")
        if chart:
            CHART_PATH = chart

        return {
            "answer":          final.get("answer", "No answer generated."),
            "chart_generated": bool(chart),
            "sql":             final.get("sql", ""),
        }


agent = FraudCopilot()


# ── Utility functions for main.py ─────────────────────────────────────

def get_chart_path() -> str:
    """Return the path to the most recently generated chart."""
    return CHART_PATH


def get_stats() -> dict:
    """Pre-computed KPIs for instant dashboard loading (no LLM needed)."""
    try:
        s: dict = {}
        s["total_transactions"] = con.execute(
            "SELECT COUNT(*) FROM fraud_data"
        ).fetchone()[0]
        s["total_volume"] = con.execute(
            "SELECT SUM(amount) FROM fraud_data"
        ).fetchone()[0]
        s["avg_risk_score"] = round(
            con.execute("SELECT AVG(fraud_risk_score) FROM fraud_data").fetchone()[0], 4
        )
        s["high_risk_count"] = con.execute(
            "SELECT COUNT(*) FROM fraud_data WHERE flag_count >= 3"
        ).fetchone()[0]
        s["dispute_count"] = con.execute(
            "SELECT SUM(COALESCE(dispute_count, 0)) FROM fraud_data"
        ).fetchone()[0]
        s["dispute_rate"] = round(
            con.execute(
                "SELECT AVG(CASE WHEN is_disputed THEN 100.0 ELSE 0.0 END) FROM fraud_data"
            ).fetchone()[0],
            2,
        )
        s["failed_rate"] = round(
            con.execute(
                "SELECT AVG(CASE WHEN status='FAILED' THEN 100.0 ELSE 0.0 END) FROM fraud_data"
            ).fetchone()[0],
            2,
        )

        # Top chargeback merchant
        top = con.execute(
            "SELECT merchant_id, ANY_VALUE(merchant_chargeback_ratio) AS ratio "
            "FROM fraud_data "
            "WHERE merchant_chargeback_ratio IS NOT NULL "
            "GROUP BY merchant_id ORDER BY ratio DESC LIMIT 1"
        ).fetchone()
        if top:
            s["top_chargeback_merchant"] = top[0]
            s["top_chargeback_ratio"] = round(float(top[1]) * 100, 2)

        # Risk-tier distribution
        tiers = con.execute(
            "SELECT risk_tier, COUNT(*) AS cnt FROM fraud_data "
            "WHERE risk_tier IS NOT NULL GROUP BY risk_tier ORDER BY cnt DESC"
        ).fetchall()
        s["risk_tiers"] = {str(r[0]): r[1] for r in tiers}

        try:
            total_rings = con.execute('SELECT COUNT(*) FROM fraud_rings').fetchone()[0]
            collusion_rings = con.execute("SELECT COUNT(*) FROM fraud_rings WHERE ring_type = 'MERCHANT_SETTLEMENT_COLLUSION'").fetchone()[0]
            mule_rings = con.execute("SELECT COUNT(*) FROM fraud_rings WHERE ring_type = 'SYNTHETIC_IDENTITY_MULE_RING'").fetchone()[0]
            dispute_loops = con.execute("SELECT COUNT(*) FROM fraud_rings WHERE ring_type = 'COORDINATED_DISPUTE_NETWORK'").fetchone()[0]
            
            s["total_rings"] = total_rings
            s["collusion_rings"] = collusion_rings
            s["mule_rings"] = mule_rings
            s["dispute_loops"] = dispute_loops
        except Exception:
            pass

        return s
    except Exception as exc:
        return {"error": str(exc)}


def get_dashboard_summary() -> dict:
    """Aggregated analytics package for real-time interactive dashboard telemetry."""
    try:
        data = {"kpis": get_stats()}

        # 1. Daily volume & dispute velocity
        daily_rows = con.execute("""
            SELECT 
                SUBSTR(timestamp::VARCHAR, 1, 10) as date,
                COUNT(*) as txns,
                ROUND(SUM(amount), 2) as volume,
                SUM(CASE WHEN is_disputed THEN 1 ELSE 0 END) as disputes
            FROM fraud_data 
            WHERE timestamp IS NOT NULL
            GROUP BY 1 
            ORDER BY 1 ASC
        """).fetchall()
        data["daily_trend"] = [
            {"date": r[0], "txns": r[1], "volume": r[2], "disputes": r[3]}
            for r in daily_rows
        ]

        # 2. Categories with volume, dispute count, and dispute rate
        cat_rows = con.execute("""
            SELECT 
                COALESCE(merchant_category, 'Uncategorized') as category,
                ROUND(SUM(amount), 2) as volume,
                SUM(CASE WHEN is_disputed THEN 1 ELSE 0 END) as disputes,
                ROUND(AVG(CASE WHEN is_disputed THEN 100.0 ELSE 0.0 END), 2) as dispute_rate
            FROM fraud_data 
            GROUP BY 1 
            ORDER BY volume DESC
            LIMIT 10
        """).fetchall()
        data["categories"] = [
            {"category": r[0], "volume": r[1], "disputes": r[2], "dispute_rate": r[3]}
            for r in cat_rows
        ]

        # 3. Dispute reason code breakdown
        reason_rows = con.execute("""
            SELECT 
                COALESCE(top_reason_code, 'OTHER') as reason,
                COUNT(*) as count,
                ROUND(SUM(COALESCE(total_disputed_amount, 0)), 2) as amount
            FROM fraud_data 
            WHERE is_disputed = TRUE 
            GROUP BY 1 
            ORDER BY count DESC
        """).fetchall()
        data["reasons"] = [
            {"reason": r[0], "count": r[1], "amount": r[2]}
            for r in reason_rows
        ]

        # 4. Top high-risk merchants
        merch_rows = con.execute("""
            SELECT 
                merchant_id,
                COALESCE(merchant_name, 'Unknown Entity') as name,
                COALESCE(merchant_category, 'General') as category,
                merchant_txn_count as txns,
                merchant_disputed_txn_count as disputes,
                ROUND(merchant_chargeback_ratio * 100, 1) as cb_ratio,
                COALESCE(merchant_status, 'Active') as status,
                ROUND(MAX(fraud_risk_score), 3) as max_risk
            FROM fraud_data
            WHERE merchant_chargeback_ratio IS NOT NULL
            GROUP BY 1,2,3,4,5,6,7
            ORDER BY cb_ratio DESC, disputes DESC
            LIMIT 10
        """).fetchall()
        data["top_merchants"] = [
            {
                "merchant_id": r[0], "name": r[1], "category": r[2],
                "txns": r[3], "disputes": r[4], "cb_ratio": r[5],
                "status": r[6], "max_risk": r[7]
            }
            for r in merch_rows
        ]

        # 5. Top flagged recent transactions
        flagged_txns = con.execute("""
            SELECT 
                txn_id,
                user_id,
                merchant_id,
                amount,
                status,
                flag_count,
                ROUND(fraud_risk_score, 3) as risk_score,
                COALESCE(risk_tier, 'LOW') as risk_tier,
                COALESCE(top_reason_code, '-') as reason
            FROM fraud_data
            ORDER BY fraud_risk_score DESC, flag_count DESC
            LIMIT 10
        """).fetchall()
        data["flagged_transactions"] = [
            {
                "txn_id": r[0], "user_id": r[1], "merchant_id": r[2],
                "amount": r[3], "status": r[4], "flag_count": r[5],
                "risk_score": r[6], "risk_tier": r[7], "reason": r[8]
            }
            for r in flagged_txns
        ]

        # 6. Top Graph Fraud Rings
        try:
            rings_rows = con.execute("""
                SELECT ring_id, ring_type, entity_count, composite_score, cluster_volume, description
                FROM fraud_rings
                ORDER BY composite_score DESC, cluster_volume DESC
                LIMIT 8
            """).fetchall()
            data["fraud_rings"] = [
                {
                    "ring_id": r[0], "ring_type": r[1], "entity_count": r[2],
                    "composite_score": r[3], "cluster_volume": r[4], "description": r[5]
                }
                for r in rings_rows
            ]
        except Exception:
            data["fraud_rings"] = []

        return data
    except Exception as exc:
        return {"error": str(exc)}


def get_ring_graph_data(ring_id: str = "RING-MERCH-0101") -> dict:
    """Generate Cytoscape.js compatible graph topology for a specific fraud ring cluster."""
    try:
        row = con.execute("""
            SELECT ring_id, ring_type, cycle_accounts, entity_count, composite_score, cluster_volume, description
            FROM fraud_rings
            WHERE ring_id = ?
        """, [ring_id]).fetchone()

        if not row:
            # Fallback to the top ring if requested ring not found
            row = con.execute("""
                SELECT ring_id, ring_type, cycle_accounts, entity_count, composite_score, cluster_volume, description
                FROM fraud_rings
                ORDER BY composite_score DESC, cluster_volume DESC
                LIMIT 1
            """).fetchone()

        if not row:
            return {"error": "No fraud rings available"}

        r_id, r_type, cycle_accs, entity_count, score, volume, desc = row
        raw_entities = [e.strip() for e in cycle_accs.split("->") if e.strip()]
        unique_entities = list(dict.fromkeys(raw_entities))

        elements = []
        hub_match = re.search(r'account\s+([A-Za-z0-9]+)', desc, re.IGNORECASE)
        hub_id = f"HUB_{hub_match.group(1)}" if hub_match else None

        if hub_id:
            elements.append({
                "data": {
                    "id": hub_id,
                    "label": f"Settlement Hub\n{hub_match.group(1)}",
                    "type": "hub",
                    "color": "#06b6d4",
                    "subtext": f"Shared Bank Settlement Account: {hub_match.group(1)}"
                }
            })

        for ent in unique_entities:
            is_merchant = ent.startswith("MCH")
            is_user = ent.startswith("USR")

            if is_merchant:
                m_info = con.execute("""
                    SELECT merchant_name, merchant_category, ROUND(AVG(merchant_chargeback_ratio)*100, 1)
                    FROM fraud_data
                    WHERE merchant_id = ?
                    GROUP BY merchant_name, merchant_category
                    LIMIT 1
                """, [ent]).fetchone()
                name = m_info[0] if m_info and m_info[0] else "Merchant Entity"
                cb_rate = m_info[2] if m_info and m_info[2] is not None else 0
                cb_label = f"\n{cb_rate}% CB" if cb_rate > 0 else ""
                label = f"{ent}\n{name[:16]}{cb_label}"
                color = "#ef4444" if cb_rate >= 50 else "#f59e0b"
                subtext = f"{name} // {m_info[1] if m_info else 'General'}"
            else:
                label = f"{ent}\nCustomer"
                color = "#a855f7"
                subtext = "UPI Customer Account"

            elements.append({
                "data": {
                    "id": ent,
                    "label": label,
                    "type": "merchant" if is_merchant else "user",
                    "color": color,
                    "subtext": subtext
                }
            })

            if hub_id:
                elements.append({
                    "data": {
                        "id": f"e_{ent}_{hub_id}",
                        "source": ent,
                        "target": hub_id,
                        "label": "Settles To"
                    }
                })

        # Direct sequence flow if no hub
        if not hub_id and len(raw_entities) > 1:
            for i in range(len(raw_entities) - 1):
                s = raw_entities[i]
                t = raw_entities[i+1]
                elements.append({
                    "data": {
                        "id": f"e_{s}_{t}_{i}",
                        "source": s,
                        "target": t,
                        "label": "Dispute Flow"
                    }
                })

        return {
            "ring_id": r_id,
            "ring_type": r_type,
            "entity_count": entity_count,
            "composite_score": score,
            "cluster_volume": volume,
            "description": desc,
            "elements": elements
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_schema() -> str:
    """Return the auto-discovered schema context string."""
    return SCHEMA_CONTEXT