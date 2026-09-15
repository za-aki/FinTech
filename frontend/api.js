/**
 * api.js — Backend connection & data transformation utilities
 */

// Auto-detect backend host
const API_URL = (window.location.origin && window.location.origin.includes(":8000"))
  ? ""
  : (window.API_URL || "http://localhost:8000");

const DEFAULT_THREAD_ID = "datathon-session";

/**
 * Send natural language question to Fraud Copilot
 */
async function askAgent(question, threadId = DEFAULT_THREAD_ID) {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, thread_id: threadId }),
  });
  if (!res.ok) throw new Error(`Agent error (${res.status})`);
  return res.json();
}

/**
 * Fetch complete dashboard analytics payload (Instant, pure SQL, zero LLM lag)
 */
async function fetchDashboardSummary() {
  const res = await fetch(`${API_URL}/dashboard-summary`);
  if (!res.ok) throw new Error(`Dashboard summary error (${res.status})`);
  return res.json();
}

/**
 * Fetch Gate 2 audit evidence and referential integrity summary
 */
async function fetchAuditSummary() {
  const res = await fetch(`${API_URL}/audit-summary`);
  if (!res.ok) throw new Error(`Audit summary error (${res.status})`);
  return res.json();
}

/**
 * Format raw numbers to Indian currency notation (₹, L, Cr)
 */
function formatINR(val) {
  if (val == null || isNaN(val)) return "N/A";
  const num = Number(val);
  if (Math.abs(num) >= 10000000) return `₹${(num / 10000000).toFixed(2)} Cr`;
  if (Math.abs(num) >= 100000) return `₹${(num / 100000).toFixed(2)} L`;
  return `₹${num.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
