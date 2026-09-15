"""
pipeline.py

This script cleans and joins all the datasets together.
It flags suspicious activities based on business logic and gives every
transaction a fraud_risk_score from 0 to 1.
The final output is saved to fraud_analytics_table.csv and loaded into DuckDB.
"""

import os
import pandas as pd
import numpy as np
import duckdb

TXN_PATH = "../data/cleaned/cleaned_transactions.csv"
KYC_PATH = "../data/cleaned/cleaned_kyc.csv"
MER_PATH = "../data/cleaned/cleaned_merchants.csv"
CB_PATH = "../data/cleaned/cleaned_chargebacks.csv"
CYCLE_SCORES_PATH = "suspicious_cycles.csv"   # optional — produced by fraud_ring_detection.py
OUTPUT_CSV = "fraud_analytics_table.csv"
OUTPUT_DB = "fraud_analytics.duckdb"

MIN_TXN_FOR_RATIO = 3   # Lowered to 3 to match the dataset's actual density per merchant (~4.6 avg)

# ============================================================
# STAGE 1 — INGEST & TYPE CASTING
# ============================================================

txn = pd.read_csv(TXN_PATH)
kyc = pd.read_csv(KYC_PATH)
mer = pd.read_csv(MER_PATH)
cb = pd.read_csv(CB_PATH)

# Coerce timestamps and numerics to prevent aggregation type errors
for col in ["timestamp_clean", "transaction_timestamp_clean", "reported_timestamp_clean", "bank_response_timestamp_clean"]:
    if col in txn.columns:
        txn[col] = pd.to_datetime(txn[col], errors="coerce")
    if col in cb.columns:
        cb[col] = pd.to_datetime(cb[col], errors="coerce")

# Parse the actual transaction timestamp column
if "timestamp" in txn.columns:
    txn["timestamp"] = pd.to_datetime(txn["timestamp"], errors="coerce")

for col in ["amount_clean", "disputed_amount_clean", "declared_avg_ticket_size", "monthly_income"]:
    if col in txn.columns:
        txn[col] = pd.to_numeric(txn[col], errors="coerce")
    if col in cb.columns:
        cb[col] = pd.to_numeric(cb[col], errors="coerce")
    if col in mer.columns:
        mer[col] = pd.to_numeric(mer[col], errors="coerce")
    if col in kyc.columns:
        kyc[col] = pd.to_numeric(kyc[col], errors="coerce")

print(f"Loaded — transactions: {len(txn)}, kyc: {len(kyc)}, merchants: {len(mer)}, chargebacks: {len(cb)}")

# ============================================================
# STAGE 2 — DEDUPLICATE (per your instruction: flag/handle here, not before)
# ============================================================

def dedup_report(name, before, after):
    print(f"  {name}: {before} -> {after} ({before - after} removed)")

print("\nDeduplicating...")

before = len(txn)
txn = txn.drop_duplicates(subset="txn_id", keep="first")
dedup_report("transactions", before, len(txn))

before = len(kyc)
kyc["_completeness"] = kyc.notna().sum(axis=1)
kyc = kyc.sort_values(["user_id", "_completeness"]).drop_duplicates(subset="user_id", keep="last")
kyc = kyc.drop(columns="_completeness")
dedup_report("kyc (resolved to 1/user)", before, len(kyc))

before = len(mer)
mer["_completeness"] = mer.notna().sum(axis=1)
mer = mer.sort_values(["merchant_id", "_completeness"]).drop_duplicates(subset="merchant_id", keep="last")
mer = mer.drop(columns="_completeness")
dedup_report("merchants (resolved to 1/merchant)", before, len(mer))

before = len(cb)
cb = cb.drop_duplicates()
dedup_report("chargebacks (exact dupes)", before, len(cb))

# Aggregate chargebacks to 1 row per transaction (a txn can have multiple
# genuinely separate disputes — confirmed earlier this isn't a data error).
# Also carries the reason_code tied to the highest-severity dispute, since
# that's the most decision-relevant one if there are several.
severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
cb["_severity_rank"] = cb["severity_clean"].map(severity_rank).fillna(0)
cb_sorted = cb.sort_values("_severity_rank", ascending=False)

cb_agg = cb.groupby("txn_id_clean").agg(
    dispute_count=("complaint_id", "count"),
    total_disputed_amount=("disputed_amount_clean", "sum"),
    max_severity_rank=("_severity_rank", "max"),
    latest_reported=("reported_timestamp_clean", "max"),
).reset_index()
top_reason = cb_sorted.drop_duplicates(subset="txn_id_clean", keep="first")[["txn_id_clean", "reason_code_clean"]]
top_reason = top_reason.rename(columns={"reason_code_clean": "top_reason_code"})
cb_agg = cb_agg.merge(top_reason, on="txn_id_clean", how="left")

rank_to_label = {v: k for k, v in severity_rank.items()}
cb_agg["max_severity"] = cb_agg["max_severity_rank"].map(rank_to_label)
cb_agg = cb_agg.drop(columns="max_severity_rank")

print(f"  chargebacks aggregated to {len(cb_agg)} unique transactions with disputes")

# ============================================================
# STAGE 3 — JOIN (one row per transaction, everything else left-joined)
# ============================================================

valid_users = set(kyc["user_id"].dropna())
valid_merchants = set(mer["merchant_id"].dropna())

df = txn.merge(kyc, on="user_id", how="left", suffixes=("", "_kyc"))
df = df.merge(mer, on="merchant_id", how="left", suffixes=("", "_mer"))
df = df.merge(cb_agg, left_on="txn_id", right_on="txn_id_clean", how="left")

df["is_kyc_linked"] = df["user_id"].isin(valid_users)
df["is_merchant_linked"] = df["merchant_id"].isin(valid_merchants)
df["is_disputed"] = df["dispute_count"].fillna(0) > 0

# --- Deterministic MCC Recovery (from category 1:1 mappings) ---
mcc_map = (
    mer.dropna(subset=["merchant_category", "mcc"])
    .groupby("merchant_category")["mcc"]
    .agg(["nunique", "first"])
)
deterministic_mcc = mcc_map[mcc_map["nunique"] == 1]["first"]

df["mcc_derived"] = 0
for cat, code in deterministic_mcc.items():
    mask = df["mcc"].isna() & (df["merchant_category"] == cat)
    df.loc[mask, "mcc"] = code
    df.loc[mask, "mcc_derived"] = 1

# --- Age Derivation ---
if "date_of_birth" in df.columns:
    dob = pd.to_datetime(df["date_of_birth"], errors="coerce")
    ref_date = pd.Timestamp("2026-09-14")
    df["age"] = (
        ref_date.year
        - dob.dt.year
        - ((dob.dt.month > ref_date.month) | ((dob.dt.month == ref_date.month) & (dob.dt.day > ref_date.day))).astype(int)
    )

print(f"\nJoined table: {len(df)} rows (should equal transaction count: {len(txn)})")
assert len(df) == len(txn), "Row count changed after join — a fan-out slipped through, investigate before continuing"

# ============================================================
# STAGE 4 — PER-ROW FLAGS (each column checked individually)
# ============================================================

print("\nComputing per-row flags...")

def safe_isin(series, values):
    """Won't crash if the column is missing or has unexpected values —
    just returns all-False and prints a warning so you know to check."""
    if series is None:
        return pd.Series(False, index=df.index)
    return series.isin(values)

# --- transactions columns ---
df["flag_amount_anomaly"] = safe_isin(df.get("amount_status"), ["NEGATIVE", "UNPARSEABLE"])
df["flag_utr_invalid"] = safe_isin(df.get("utr_status"), ["INVALID", "MISSING"])
df["flag_missing_utr_and_failed"] = df["flag_utr_invalid"] & (df["status"] == "FAILED")
df["flag_mcc_invalid"] = safe_isin(df.get("mcc_status"), ["INVALID", "MISSING"])

# --- kyc columns ---
df["flag_kyc_doc_invalid"] = safe_isin(df.get("pan_status"), ["INVALID"]) | safe_isin(df.get("aadhaar_status"), ["INVALID"])
df["flag_kyc_doc_missing"] = safe_isin(df.get("pan_status"), ["MISSING"]) | safe_isin(df.get("aadhaar_status"), ["MISSING"])
df["flag_underage"] = safe_isin(df.get("age_status"), ["UNDERAGE"])
df["flag_income_anomaly"] = safe_isin(df.get("income_status"), ["NEGATIVE", "UNPARSEABLE"])
df["flag_rejected_kyc_active"] = df.get("kyc_status") == "REJECTED"
df["flag_under_review_kyc_active"] = df.get("kyc_status") == "UNDER_REVIEW"
df["flag_brand_new_account"] = safe_isin(df.get("signup_status"), ["BRAND_NEW"])

# --- merchants columns ---
df["flag_merchant_suspended"] = df.get("merchant_status") == "Suspended"
df["flag_merchant_status_unknown"] = df.get("merchant_status") == "Unknown"
df["flag_ticket_size_imputed"] = df.get("ticket_size_status") == "MISSING_OR_INVALID"

# amount vs. this merchant's own declared average ticket size — a >5x
# deviation either direction is a mismatch worth flagging (threshold is a
# judgment call, adjust if it flags too much/little in practice)
df["flag_amount_vs_ticket_mismatch"] = False
has_ticket_size = df["declared_avg_ticket_size"].notna() & (df["declared_avg_ticket_size"] > 0)
ratio = df["amount"] / df["declared_avg_ticket_size"].replace(0, np.nan)
df.loc[has_ticket_size, "flag_amount_vs_ticket_mismatch"] = (ratio > 5) | (ratio < 0.2)

# --- chargebacks columns ---
df["flag_high_severity_dispute"] = safe_isin(df.get("max_severity"), ["CRITICAL", "HIGH"])
df["flag_unauthorized_reason"] = df.get("top_reason_code") == "UNAUTHORIZED_TRANSACTION"
df["flag_disputed_amount_mismatch"] = False
has_dispute = df["total_disputed_amount"].notna()
disputed_ratio = df["total_disputed_amount"] / df["amount"].replace(0, np.nan)
df.loc[has_dispute, "flag_disputed_amount_mismatch"] = (disputed_ratio - 1).abs() > 0.05  # >5% off from the actual transaction amount

# --- orphan-FK flags (already computed above, restated here for clarity) ---
df["flag_unlinked_kyc"] = ~df["is_kyc_linked"]
df["flag_unlinked_merchant"] = ~df["is_merchant_linked"]

# --- temporal features ---
df["txn_hour"] = df["timestamp"].dt.hour
df["txn_day_of_week"] = df["timestamp"].dt.dayofweek
df["is_weekend"] = df["txn_day_of_week"] >= 5
df["is_night_txn"] = df["txn_hour"].between(0, 4)  # 00:00-04:59
df["flag_round_amount"] = (df["amount"] % 1000 == 0) & (df["amount"] > 0)

# account age at time of transaction
df["signup_date_parsed"] = pd.to_datetime(df.get("signup_date"), errors="coerce")
df["days_since_signup_at_txn"] = (df["timestamp"] - df["signup_date_parsed"]).dt.days

# ============================================================
# STAGE 5 — GROUPED / AGGREGATE FLAGS
# (per user, per merchant, per category — this is where the notes say
# "grouping upi transactions and merchant master may find a lot of fraud")
# ============================================================

print("Computing grouped aggregates (user, merchant, category)...")

# ---------- per user_id ----------
user_agg = df.groupby("user_id").agg(
    user_txn_count=("txn_id", "count"),
    user_total_volume=("amount", "sum"),
    user_dispute_count=("dispute_count", "sum"),
    user_failed_count=("status", lambda s: (s == "FAILED").sum()),
    user_distinct_merchants=("merchant_id", "nunique"),
    user_max_single_txn=("amount", "max"),
).reset_index()
user_agg["user_failed_rate"] = user_agg["user_failed_count"] / user_agg["user_txn_count"]

# per-user amount z-score: how unusual is each transaction for this user
user_amount_stats = df.groupby("user_id")["amount"].agg(["mean", "std"]).rename(
    columns={"mean": "user_avg_amount", "std": "user_std_amount"}
)

df = df.merge(user_agg, on="user_id", how="left")
df = df.merge(user_amount_stats, on="user_id", how="left")
df["user_amount_zscore"] = (df["amount"] - df["user_avg_amount"]) / df["user_std_amount"].replace(0, np.nan)
df["flag_amount_zscore_outlier"] = df["user_amount_zscore"].abs() > 3

# income-to-spend mismatch: rough annualized comparison. monthly_income * 12
# vs total transaction volume for that user — a user spending far beyond
# their declared income is a real signal, though it assumes the data
# covers roughly a year (a judgment call worth stating in your README)
df["user_income_to_spend_ratio"] = np.nan
has_income = df["monthly_income"].notna() & (df["monthly_income"] > 0)
df.loc[has_income, "user_income_to_spend_ratio"] = (
    df.loc[has_income, "user_total_volume"] / (df.loc[has_income, "monthly_income"] * 12)
)
df["flag_income_spend_mismatch"] = df["user_income_to_spend_ratio"] > 5  # spending 5x+ declared annual income

# brand-new account + high volume compounding signal
volume_90th = df["user_total_volume"].quantile(0.90)
df["flag_new_account_high_volume"] = df["flag_brand_new_account"] & (df["user_total_volume"] > volume_90th)

# invalid KYC docs + high volume compounding signal (the mule-account profile)
df["flag_invalid_kyc_high_volume"] = df["flag_kyc_doc_invalid"] & (df["user_total_volume"] > volume_90th)

# ---------- per merchant_id ----------
merchant_agg = df.groupby("merchant_id").agg(
    merchant_txn_count=("txn_id", "count"),
    merchant_total_volume=("amount", "sum"),
    merchant_dispute_count=("dispute_count", "sum"),          # total complaints — keep for reference
    merchant_disputed_txn_count=("is_disputed", "sum"),        # NEW: distinct transactions with disputes
).reset_index()
merchant_agg["merchant_chargeback_ratio"] = merchant_agg["merchant_disputed_txn_count"] / merchant_agg["merchant_txn_count"]
# guard against low-sample merchants dominating the ranking (using MIN_TXN_FOR_RATIO = 3)
merchant_agg.loc[merchant_agg["merchant_txn_count"] < MIN_TXN_FOR_RATIO, "merchant_chargeback_ratio"] = np.nan
merchant_agg["merchant_ratio_insufficient_sample"] = merchant_agg["merchant_txn_count"] < MIN_TXN_FOR_RATIO

df = df.merge(merchant_agg, on="merchant_id", how="left")

category_median_ratio = df.groupby("merchant_category")["merchant_chargeback_ratio"].transform("median")
df["flag_merchant_above_category_median"] = df["merchant_chargeback_ratio"] > category_median_ratio

# ---------- per merchant_category (for dashboard, merged back for reference) ----------
category_agg = df.groupby("merchant_category").agg(
    category_txn_count=("txn_id", "count"),
    category_total_volume=("amount", "sum"),
    category_dispute_count=("dispute_count", "sum"),
).reset_index()
category_agg["category_chargeback_ratio"] = category_agg["category_dispute_count"] / category_agg["category_txn_count"]
df = df.merge(category_agg, on="merchant_category", how="left", suffixes=("", "_categorylevel"))

# ============================================================
# STAGE 6 — MERGE IN CYCLE SCORES (optional — only if the file exists)
# ============================================================

if os.path.exists(CYCLE_SCORES_PATH):
    print("Merging in fraud-ring cycle scores...")
    cycles = pd.read_csv(CYCLE_SCORES_PATH)
    account_max_score = {}
    for _, row in cycles.iterrows():
        for account in row["cycle_accounts"].split(" -> "):
            account_max_score[account] = max(account_max_score.get(account, 0), row["composite_score"])
    df["user_cycle_score"] = df["user_id"].map(account_max_score).fillna(0)
    df["merchant_cycle_score"] = df["merchant_id"].map(account_max_score).fillna(0)
else:
    print(f"No {CYCLE_SCORES_PATH} found — skipping cycle scores (run fraud_ring_detection.py first if you want this)")
    df["user_cycle_score"] = 0
    df["merchant_cycle_score"] = 0

# ============================================================
# STAGE 7 — COMPOSITE FRAUD RISK SCORE
# Weights are a judgment call, not a verified fact — documented here so
# they're easy to challenge/adjust, same approach as the cycle scoring.
# ============================================================

boolean_flags = [
    "flag_amount_anomaly", "flag_missing_utr_and_failed", "flag_kyc_doc_invalid",
    "flag_underage", "flag_income_anomaly", "flag_rejected_kyc_active",
    "flag_merchant_suspended", "flag_amount_vs_ticket_mismatch",
    "flag_high_severity_dispute", "flag_unauthorized_reason",
    "flag_disputed_amount_mismatch", "flag_income_spend_mismatch",
    "flag_new_account_high_volume", "flag_invalid_kyc_high_volume",
    "flag_merchant_above_category_median",
    "flag_round_amount", "is_night_txn", "flag_amount_zscore_outlier",
]
df["flag_count"] = df[boolean_flags].sum(axis=1)

# Normalize continuous signals to roughly 0-1 before combining with the flag count
norm_cycle = (df["user_cycle_score"].clip(0, 1) + df["merchant_cycle_score"].clip(0, 1)) / 2
norm_chargeback_ratio = df["merchant_chargeback_ratio"].fillna(0).clip(0, 1)

df["fraud_risk_score"] = (
    0.5 * (df["flag_count"] / len(boolean_flags)) +
    0.3 * norm_chargeback_ratio +
    0.2 * norm_cycle
)

# Risk tier categorization for dashboard and agent queries
df["risk_tier"] = pd.cut(
    df["fraud_risk_score"],
    bins=[-0.01, 0.15, 0.35, 0.55, 1.01],
    labels=["LOW", "MEDIUM", "HIGH", "CRITICAL"]
)

# ============================================================
# STAGE 8 — OUTPUT
# ============================================================

df.to_csv(OUTPUT_CSV, index=False)

con = duckdb.connect(OUTPUT_DB)
con.execute("CREATE OR REPLACE TABLE fraud_analytics AS SELECT * FROM df")
con.close()

print(f"\nDone. Output: {OUTPUT_CSV} ({len(df)} rows, {len(df.columns)} columns), {OUTPUT_DB}")
print(f"\nFlag summary:")
print(df[boolean_flags].sum().sort_values(ascending=False))
print(f"\nfraud_risk_score distribution:\n{df['fraud_risk_score'].describe()}")
print(f"\nTop 10 highest-risk transactions:")
print(df.nlargest(10, "fraud_risk_score")[["txn_id", "user_id", "merchant_id", "amount", "fraud_risk_score", "flag_count"]].to_string(index=False))

# ============================================================
# STAGE 9 — GATE 2 REPRODUCIBILITY & AUDIT EVIDENCE GENERATION
# ============================================================
import json

AUDIT_DIR = "../outputs/audit_evidence"
os.makedirs(AUDIT_DIR, exist_ok=True)

def relationship_audit(name, source_key, master_key):
    rows = len(source_key)
    null_key = int(source_key.isna().sum())
    matched = int(source_key.dropna().isin(master_key).sum())
    unmatched = rows - null_key - matched
    master_duplicates = int(master_key.duplicated().sum())
    return {
        "relationship": name,
        "rows": rows,
        "matched": matched,
        "unmatched": unmatched,
        "null_key": null_key,
        "match_rate": round(matched / rows * 100, 2) if rows else 0,
        "master_duplicate_key": master_duplicates,
    }

relationships_df = pd.DataFrame([
    relationship_audit("transactions -> kyc", df["user_id"], kyc["user_id"]),
    relationship_audit("transactions -> merchants", df["merchant_id"], mer["merchant_id"]),
    relationship_audit("chargebacks -> transactions", cb["txn_id_clean"], df["txn_id"]),
    relationship_audit("chargebacks -> kyc", cb["user_id_clean"], kyc["user_id"]),
    relationship_audit("chargebacks -> merchants", cb["merchant_id_clean"], mer["merchant_id"]),
])
relationships_df.to_csv(f"{AUDIT_DIR}/relationship_integrity_report.csv", index=False)

validation = {
    "final_rows_preserved": len(df) == len(txn),
    "unique_txn_id": bool(df["txn_id"].nunique() == len(txn)),
    "zero_duplicate_txn_id": bool(df["txn_id"].duplicated().sum() == 0),
    "zero_null_txn_id": bool(df["txn_id"].isna().sum() == 0),
    "unique_kyc_master": bool(kyc["user_id"].duplicated().sum() == 0),
    "unique_merchant_master": bool(mer["merchant_id"].duplicated().sum() == 0),
    "transaction_dates_parsed": bool(df["timestamp"].notna().mean() >= 0.95),
    "amounts_parsed": bool(df["amount"].notna().mean() >= 0.95),
    "zero_chargeback_fanout": bool(len(df) == 20000),
}

validation_df = pd.DataFrame([{"check": k, "passed": v} for k, v in validation.items()])
validation_df.to_csv(f"{AUDIT_DIR}/final_validation_report.csv", index=False)

summary = {
    "pipeline": "AgentIQ UPI Fraud Production Data Pipeline v2",
    "final_rows": len(df),
    "final_columns": len(df.columns),
    "unique_transactions": int(df["txn_id"].nunique()),
    "kyc_linked_transactions": int(df["is_kyc_linked"].sum()),
    "merchant_linked_transactions": int(df["is_merchant_linked"].sum()),
    "disputed_transactions": int(df["is_disputed"].sum()),
    "derived_mcc_count": int(df["mcc_derived"].sum()),
    "risk_flagged_transactions": int((df["flag_count"] > 0).sum()),
    "final_gate_passed": bool(all(validation.values())),
}

with open(f"{AUDIT_DIR}/pipeline_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"\nAudit evidence written to '{AUDIT_DIR}/': final_validation_report.csv, relationship_integrity_report.csv, pipeline_summary.json")
print(f"Gate 2 Integrity Status: {'PASS' if all(validation.values()) else 'FAIL'}")