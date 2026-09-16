/**
 * dashboard.js — Fraud Analytics Dashboard Engine
 * Renders Plotly charts, KPIs, tables, Cytoscape graphs, and guided tour.
 */

// Plotly Light Theme Configuration
const PLOT_THEME = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "#ffffff",
  font: {
    color: "#374151",
    family: "-apple-system, BlinkMacSystemFont, Inter, Segoe UI, sans-serif",
    size: 11
  },
  margin: { t: 30, l: 50, r: 30, b: 50 },
  hoverlabel: {
    bgcolor: "#ffffff",
    bordercolor: "#e2e5ea",
    font: { color: "#111827", size: 12 }
  }
};

// Tab Navigation Switching
function switchTab(tabId) {
  document.querySelectorAll(".tab-btn, .nav-link").forEach(btn => {
    if (btn.dataset.tab === tabId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const target = document.getElementById("panel-" + tabId);
  if (target) target.classList.add("active");

  // Auto-resize Plotly charts upon tab activation
  if (tabId === "overview") {
    setTimeout(() => {
      ["plot-daily-trend", "plot-reasons", "plot-category-volume"].forEach(id => {
        const el = document.getElementById(id);
        if (el) Plotly.Plots.resize(el);
      });
    }, 50);
  }

  // Cytoscape resize/fit upon rings tab activation
  if (tabId === "rings") {
    setTimeout(() => {
      if (!window.cyInstance) {
        loadRingGraph("RING-MERCH-0101");
      } else {
        window.cyInstance.resize();
        window.cyInstance.fit(30);
      }
    }, 80);
  }

  // Simulator recalculation on ledger tab
  if (tabId === "ledger") {
    updateSimulator();
  }
}

document.querySelectorAll(".tab-btn, .nav-link").forEach(link => {
  link.addEventListener("click", () => {
    if (link.dataset.tab) switchTab(link.dataset.tab);
  });
});

// Auto-resize charts on window resize
window.addEventListener("resize", () => {
  ["plot-daily-trend", "plot-reasons", "plot-category-volume"].forEach(id => {
    const el = document.getElementById(id);
    if (el) Plotly.Plots.resize(el);
  });
  if (window.cyInstance) {
    window.cyInstance.resize();
    window.cyInstance.fit(30);
  }
});

// Sidebar collapse toggle
function toggleCopilot() {
  const sidebar = document.getElementById("copilot-sidebar");
  if (!sidebar) return;
  sidebar.classList.toggle("minimized");
  setTimeout(() => {
    ["plot-daily-trend", "plot-reasons", "plot-category-volume"].forEach(id => {
      const el = document.getElementById(id);
      if (el) Plotly.Plots.resize(el);
    });
    if (window.cyInstance) {
      window.cyInstance.resize();
      window.cyInstance.fit(30);
    }
  }, 220);
}

/**
 * Load dashboard data from /dashboard-summary
 */
async function initDashboard() {
  try {
    const data = await fetchDashboardSummary();
    if (data.error) throw new Error(data.error);

    renderKPIs(data.kpis);
    renderRingKPIs(data.kpis);
    renderDailyTrendChart(data.daily_trend);
    renderCategoryChart(data.categories);
    renderReasonDonut(data.reasons);
    renderMerchantTable(data.top_merchants);
    renderTransactionTable(data.flagged_transactions);
    renderFraudRingsTable(data.fraud_rings);
    loadRingGraph("RING-MERCH-0101");
    updateSimulator();
  } catch (err) {
    console.error("Dashboard initialization failed:", err);
  }
}

/**
 * Populate Overview KPI Cards
 */
function renderKPIs(kpis) {
  if (!kpis) return;

  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setVal("kpi-volume", formatINR(kpis.total_volume));
  setVal("kpi-volume-sub", `${(kpis.total_transactions || 0).toLocaleString()} transactions`);

  setVal("kpi-risk", kpis.avg_risk_score != null ? kpis.avg_risk_score.toFixed(4) : "—");
  setVal("kpi-risk-sub", "Composite benchmark: 0.00 – 1.00");

  setVal("kpi-highrisk", (kpis.high_risk_count || 0).toLocaleString());
  setVal("kpi-highrisk-sub", "Flagged with >= 3 risk indicators");

  setVal("kpi-disputes", `${kpis.dispute_rate ?? 0}%`);
  setVal("kpi-disputes-sub", `${(kpis.dispute_count || 0).toLocaleString()} disputed claims`);

  setVal("kpi-merchant", kpis.top_chargeback_merchant || "—");
  setVal("kpi-merchant-sub", `CB Rate: ${kpis.top_chargeback_ratio || 0}%`);
}

/**
 * Populate Fraud Rings KPI Cards (dynamically from API)
 */
function renderRingKPIs(kpis) {
  if (!kpis) return;
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val != null ? val.toLocaleString() : "—";
  };
  setVal("kpi-total-rings", kpis.total_rings);
  setVal("kpi-merch-rings", kpis.collusion_rings);
  setVal("kpi-synth-rings", kpis.mule_rings);
  setVal("kpi-dispute-rings", kpis.dispute_loops);
}

/**
 * Chart 1: Daily Transaction Volume & Dispute Trend
 */
function renderDailyTrendChart(dailyData) {
  const container = document.getElementById("plot-daily-trend");
  if (!container || !dailyData || !dailyData.length) return;

  const dates = dailyData.map(d => d.date);
  const volumes = dailyData.map(d => (d.volume / 100000)); // in Lakhs
  const disputes = dailyData.map(d => d.disputes);

  const traceVolume = {
    x: dates,
    y: volumes,
    name: "Volume (₹ Lakhs)",
    type: "scatter",
    mode: "lines",
    fill: "tozeroy",
    fillcolor: "rgba(37, 99, 235, 0.06)",
    line: { color: "#2563eb", width: 2 },
    yaxis: "y"
  };

  const traceDisputes = {
    x: dates,
    y: disputes,
    name: "Disputed Claims",
    type: "scatter",
    mode: "lines",
    line: { color: "#dc2626", width: 2, dash: "dot" },
    yaxis: "y2"
  };

  const layout = {
    ...PLOT_THEME,
    height: 310,
    showlegend: true,
    legend: { orientation: "h", y: 1.15, x: 0.05 },
    xaxis: {
      gridcolor: "#f1f3f5",
      tickangle: -20,
      showline: false
    },
    yaxis: {
      title: "Volume (₹ Lakhs)",
      gridcolor: "#f1f3f5",
      showline: false
    },
    yaxis2: {
      title: "Dispute Count",
      overlaying: "y",
      side: "right",
      gridcolor: "transparent",
      showline: false
    }
  };

  Plotly.newPlot("plot-daily-trend", [traceVolume, traceDisputes], layout, {
    displayModeBar: false,
    responsive: true
  });
}

/**
 * Chart 2: Merchant Category Volume Breakdown
 */
function renderCategoryChart(categories) {
  const container = document.getElementById("plot-category-volume");
  if (!container || !categories || !categories.length) return;

  const sorted = [...categories].sort((a, b) => a.volume - b.volume);
  const labels = sorted.map(c => c.category);
  const values = sorted.map(c => (c.volume / 100000)); // in Lakhs

  const trace = {
    x: values,
    y: labels,
    type: "bar",
    orientation: "h",
    marker: {
      color: "#2563eb",
      line: { color: "#e2e5ea", width: 1 }
    },
    hoverinfo: "x+y"
  };

  const layout = {
    ...PLOT_THEME,
    height: 310,
    margin: { t: 20, l: 140, r: 30, b: 40 },
    xaxis: {
      title: "Volume (₹ Lakhs)",
      gridcolor: "#f1f3f5"
    },
    yaxis: {
      gridcolor: "#f1f3f5"
    }
  };

  Plotly.newPlot("plot-category-volume", [trace], layout, {
    displayModeBar: false,
    responsive: true
  });
}

/**
 * Chart 3: Dispute Reason Code Donut Chart
 */
function renderReasonDonut(reasons) {
  const container = document.getElementById("plot-reasons");
  if (!container || !reasons || !reasons.length) return;

  const labels = reasons.map(r => r.reason.replace(/_/g, " "));
  const values = reasons.map(r => r.count);
  const colors = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed"];

  const trace = {
    labels: labels,
    values: values,
    type: "pie",
    hole: 0.65,
    marker: { colors: colors },
    textinfo: "percent",
    hoverinfo: "label+value+percent",
    textfont: { size: 10, color: "#374151" }
  };

  const layout = {
    ...PLOT_THEME,
    height: 310,
    margin: { t: 20, l: 20, r: 20, b: 20 },
    showlegend: true,
    legend: { orientation: "h", y: -0.1, font: { size: 10 } }
  };

  Plotly.newPlot("plot-reasons", [trace], layout, {
    displayModeBar: false,
    responsive: true
  });
}

/**
 * Table 1: High Risk Merchants
 */
function renderMerchantTable(merchants) {
  const tbody = document.getElementById("merchant-table-body");
  if (!tbody || !merchants) return;

  tbody.innerHTML = merchants.map(m => {
    const isCritical = m.cb_ratio >= 80;
    const badgeClass = isCritical ? "critical" : (m.cb_ratio >= 40 ? "high" : "active");
    const statusClass = m.status === "Active" ? "active" : (m.status === "Suspended" ? "critical" : "inactive");

    return `
      <tr>
        <td style="font-weight:700;color:var(--primary)">${m.merchant_id}</td>
        <td>${m.name}</td>
        <td style="color:var(--text-muted)">${m.category}</td>
        <td>${m.txns}</td>
        <td style="color:var(--danger)">${m.disputes}</td>
        <td><span class="badge-status ${badgeClass}">${m.cb_ratio}%</span></td>
        <td><span class="badge-status ${statusClass}">${m.status}</span></td>
      </tr>
    `;
  }).join("");
}

/**
 * Table 2: High Risk Transactions
 */
function renderTransactionTable(txns) {
  const tbody = document.getElementById("transaction-table-body");
  if (!tbody || !txns) return;

  tbody.innerHTML = txns.map(t => {
    const riskBadge = t.risk_tier === "HIGH" || t.risk_tier === "CRITICAL" ? "critical" : "high";
    return `
      <tr>
        <td style="font-weight:700;color:var(--primary)">${t.txn_id}</td>
        <td style="color:var(--text-muted)">${t.user_id}</td>
        <td style="color:var(--text-muted)">${t.merchant_id}</td>
        <td style="font-weight:700">${Number(t.amount).toLocaleString("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 0})}</td>
        <td><span style="color:var(--amber)">${t.flag_count} flags</span></td>
        <td><span class="badge-status ${riskBadge}">${t.risk_score}</span></td>
        <td style="color:var(--text-dim);font-size:11px;">${t.reason}</td>
      </tr>
    `;
  }).join("");
}

/**
 * Table 3: Detected Fraud Rings
 */
function renderFraudRingsTable(rings) {
  const tbody = document.getElementById("rings-table-body");
  if (!tbody || !rings || !rings.length) return;

  tbody.innerHTML = rings.map(r => {
    const typeBadge = r.ring_type === "MERCHANT_SETTLEMENT_COLLUSION"
      ? "critical"
      : (r.ring_type === "SYNTHETIC_IDENTITY_MULE_RING" ? "high" : "active");
    const cleanType = r.ring_type.replace(/_/g, " ");

    return `
      <tr onclick="selectRingAndScroll('${r.ring_id}')" style="cursor:pointer;" title="Click to view on graph">
        <td style="font-weight:700;color:var(--primary)">${r.ring_id}</td>
        <td><span class="badge-status ${typeBadge}">${cleanType}</span></td>
        <td style="text-align:center">${r.entity_count}</td>
        <td style="font-weight:700;color:var(--safe)">${Number(r.cluster_volume).toLocaleString("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 0})}</td>
        <td><span class="badge-status ${r.composite_score >= 0.9 ? 'critical' : 'high'}">${r.composite_score}</span></td>
        <td style="color:var(--text-muted);font-size:11px;">${r.description}</td>
      </tr>
    `;
  }).join("");
}

// Search filter for merchant table
function filterMerchants() {
  const query = (document.getElementById("merchant-search")?.value || "").toLowerCase();
  const rows = document.querySelectorAll("#merchant-table-body tr");
  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    r.style.display = text.includes(query) ? "" : "none";
  });
}

// ── Cytoscape Interactive Graph Visualizer ────────────────────
let cyInstance = null;

async function loadRingGraph(ringId = "RING-MERCH-0101") {
  const container = document.getElementById("cy-container");
  if (!container || typeof cytoscape === "undefined") return;

  const select = document.getElementById("ring-select");
  if (select && select.value !== ringId) select.value = ringId;

  const infoEl = document.getElementById("cy-selected-node");
  const typeTag = document.getElementById("cy-cluster-type");

  try {
    const res = await fetch(`${API_URL}/graph-topology?ring_id=${encodeURIComponent(ringId)}`);
    if (!res.ok) throw new Error("Failed to load graph data");
    const data = await res.json();

    if (typeTag) typeTag.textContent = (data.ring_type || "FRAUD CLUSTER").replace(/_/g, " ");

    if (cyInstance) {
      cyInstance.destroy();
      cyInstance = null;
    }

    cyInstance = cytoscape({
      container: container,
      elements: data.elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "label": "data(label)",
            "color": "#111827",
            "font-size": "9.5px",
            "font-family": "-apple-system, BlinkMacSystemFont, sans-serif",
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "wrap",
            "text-max-width": "120px",
            "padding": "12px",
            "shape": "round-rectangle",
            "border-width": 2,
            "border-color": "#d1d5db",
            "text-outline-color": "#ffffff",
            "text-outline-width": 2
          }
        },
        {
          selector: "node[type='hub']",
          style: {
            "shape": "diamond",
            "border-color": "#0891b2",
            "border-width": 3,
            "font-weight": "bold",
            "padding": "16px"
          }
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#2563eb",
            "border-width": 4
          }
        },
        {
          selector: "edge",
          style: {
            "width": 2,
            "line-color": "#d1d5db",
            "target-arrow-color": "#6b7280",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "label": "data(label)",
            "font-size": "8.5px",
            "color": "#6b7280",
            "font-family": "-apple-system, BlinkMacSystemFont, sans-serif",
            "text-background-color": "#f1f3f5",
            "text-background-opacity": 0.9,
            "text-background-padding": "2px"
          }
        }
      ],
      layout: {
        name: "cose",
        animate: true,
        animationDuration: 400,
        nodeDimensionsIncludeLabels: true,
        padding: 40,
        componentSpacing: 60,
        nodeRepulsion: 450000,
        idealEdgeLength: 100
      }
    });

    window.cyInstance = cyInstance;

    cyInstance.on("tap", "node", evt => {
      const node = evt.target;
      const d = node.data();
      if (infoEl) {
        infoEl.innerHTML = `<strong>${d.id}</strong>: ${d.subtext || d.label} | Volume: ${Number(data.cluster_volume).toLocaleString('en-IN', {style: 'currency', currency: 'INR', maximumFractionDigits: 0})}`;
      }
    });

    cyInstance.on("tap", "edge", evt => {
      const edge = evt.target;
      const d = edge.data();
      if (infoEl) {
        infoEl.innerHTML = `<strong>${d.source}</strong> → <strong>${d.target}</strong> (${d.label})`;
      }
    });

    if (infoEl) {
      infoEl.textContent = `${data.ring_id} (${data.entity_count} entities, Score: ${data.composite_score}) — Click nodes to inspect.`;
    }

  } catch (err) {
    console.error("Failed to render graph:", err);
  }
}

function selectRingAndScroll(ringId) {
  loadRingGraph(ringId);
  const card = document.getElementById("graph-canvas-card");
  if (card) card.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Risk Policy Simulator ─────────────────────────────
function updateSimulator() {
  const scoreSlider = document.getElementById("sim-score-slider");
  const flagSlider = document.getElementById("sim-flag-slider");
  if (!scoreSlider || !flagSlider) return;

  const scoreVal = parseFloat(scoreSlider.value);
  const flagVal = parseInt(flagSlider.value, 10);

  const scoreLabel = document.getElementById("sim-score-val");
  const flagLabel = document.getElementById("sim-flag-val");
  if (scoreLabel) scoreLabel.textContent = scoreVal.toFixed(2);
  if (flagLabel) flagLabel.textContent = `>= ${flagVal} flags`;

  const baseRate = Math.exp(-scoreVal * 4.5);
  const flagFactor = Math.pow(0.68, flagVal - 1);
  const simDeclines = Math.max(3, Math.round(20000 * 0.12 * baseRate * flagFactor));
  const avgDeclinedAmount = 14200 + (scoreVal * 8500);
  const simVolume = simDeclines * avgDeclinedAmount;

  const fpr = Math.max(0.04, (1.8 * Math.exp(-scoreVal * 3.8) * Math.pow(0.7, flagVal - 1))).toFixed(2);
  const cleanApproval = (100 - (simDeclines / 20000 * 100)).toFixed(2);

  const setEl = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  setEl("sim-declines", `${simDeclines.toLocaleString()} txns`);
  setEl("sim-protected", formatINR(simVolume));
  setEl("sim-fpr", `${fpr}%`);
  setEl("sim-approval", `${cleanApproval}%`);
}

function resetSimulator() {
  const scoreSlider = document.getElementById("sim-score-slider");
  const flagSlider = document.getElementById("sim-flag-slider");
  if (scoreSlider) scoreSlider.value = 0.35;
  if (flagSlider) flagSlider.value = 3;
  updateSimulator();
}

// ── Interactive Guided Tour Controller ────────────────────────
const TOUR_STEPS = [
  {
    target: "#kpi-section",
    tab: "overview",
    badge: "STEP 1 OF 6 — KPI OVERVIEW",
    title: "Key Performance Indicators",
    content: "Live metrics computed from the full transaction dataset: total volume, average risk score, high-risk count, dispute ratio, and the merchant with highest chargeback rate.",
    placement: "bottom"
  },
  {
    target: "#chart-section",
    tab: "overview",
    badge: "STEP 2 OF 6 — TREND ANALYSIS",
    title: "Daily Volume & Dispute Trends",
    content: "Interactive Plotly charts showing transaction volume over time alongside dispute counts, plus a breakdown of dispute reason codes by frequency.",
    placement: "bottom"
  },
  {
    target: "#graph-canvas-card",
    tab: "rings",
    badge: "STEP 3 OF 6 — GRAPH ANALYSIS",
    title: "Fraud Ring Graph Inspector",
    content: "Cytoscape.js graph visualization. Nodes represent merchants, settlement hubs, and users. Select a ring from the dropdown or drag nodes to explore connections.",
    placement: "bottom"
  },
  {
    target: "#rings-table-card",
    tab: "rings",
    badge: "STEP 4 OF 6 — DETECTED RINGS",
    title: "Fraud Rings Table",
    content: "All detected fraud rings from NetworkX graph analysis — merchant collusion, synthetic identity clusters, and coordinated dispute networks. Click any row to view it on the graph.",
    placement: "top"
  },
  {
    target: "#simulator-card",
    tab: "ledger",
    badge: "STEP 5 OF 6 — POLICY SIMULATOR",
    title: "Risk Policy Simulator",
    content: "Adjust the risk score cutoff and flag threshold to see how different policies affect decline rates, protected volume, false positive friction, and approval rates.",
    placement: "bottom"
  },
  {
    target: "#copilot-sidebar",
    tab: "overview",
    badge: "STEP 6 OF 6 — COPILOT",
    title: "Fraud Analysis Copilot",
    content: "The copilot is always available on the right side. It uses DuckDB to query the transaction data and can generate charts on the fly. Try asking a question or use a quick chip! Also, make sure to try clicking on a lot of things throughout the dashboard—the charts and graphs are highly interactive.",
    placement: "left"
  }
];

let currentTourIndex = 0;

function startTour() {
  currentTourIndex = 0;
  const backdrop = document.getElementById("tour-backdrop");
  const modal = document.getElementById("tour-modal");
  if (backdrop) backdrop.classList.add("active");
  if (modal) modal.classList.add("active");
  renderTourStep();
}

function exitTour() {
  document.querySelectorAll(".tour-highlight").forEach(el => el.classList.remove("tour-highlight"));
  const backdrop = document.getElementById("tour-backdrop");
  const modal = document.getElementById("tour-modal");
  if (backdrop) backdrop.classList.remove("active");
  if (modal) modal.classList.remove("active");
}

function nextTourStep() {
  if (currentTourIndex < TOUR_STEPS.length - 1) {
    currentTourIndex++;
    renderTourStep();
  } else {
    exitTour();
  }
}

function renderTourStep() {
  const step = TOUR_STEPS[currentTourIndex];
  if (!step) return;

  // Clear previous highlights
  document.querySelectorAll(".tour-highlight").forEach(el => el.classList.remove("tour-highlight"));

  // Switch to target tab
  switchTab(step.tab);

  // Update modal contents
  const badgeEl = document.getElementById("tour-step-badge");
  const titleEl = document.getElementById("tour-title");
  const contentEl = document.getElementById("tour-content");
  const nextBtn = document.getElementById("tour-next-btn");
  const dotsEl = document.getElementById("tour-dots");

  if (badgeEl) badgeEl.textContent = step.badge;
  if (titleEl) titleEl.textContent = step.title;
  if (contentEl) contentEl.textContent = step.content;
  if (nextBtn) nextBtn.textContent = (currentTourIndex === TOUR_STEPS.length - 1) ? "Finish" : "Next";

  if (dotsEl) {
    dotsEl.innerHTML = TOUR_STEPS.map((_, i) =>
      `<span class="tour-dot ${i === currentTourIndex ? 'active' : ''}"></span>`
    ).join("");
  }

  // Highlight and position after DOM render
  setTimeout(() => {
    const targetEl = document.querySelector(step.target);
    const modal = document.getElementById("tour-modal");
    if (targetEl) {
      targetEl.classList.add("tour-highlight");
      targetEl.scrollIntoView({ behavior: "smooth", block: "center" });

      if (modal) {
        const rect = targetEl.getBoundingClientRect();
        const modalWidth = 380;
        const modalHeight = 220;

        let top, left;
        if (step.placement === "left") {
          top = Math.max(70, rect.top + 50);
          left = Math.max(20, rect.left - modalWidth - 20);
        } else if (step.placement === "top") {
          top = Math.max(70, rect.top - modalHeight - 16);
          left = Math.max(20, Math.min(window.innerWidth - modalWidth - 380, rect.left + 20));
        } else if (step.placement === "bottom") {
          top = Math.min(window.innerHeight - modalHeight - 30, rect.bottom + 16);
          left = Math.max(20, Math.min(window.innerWidth - modalWidth - 380, rect.left + 20));
        } else {
          // Center screen
          top = Math.max(80, (window.innerHeight - modalHeight) / 2);
          left = Math.max(20, (window.innerWidth - modalWidth - 360) / 2);
        }

        modal.style.top = `${top}px`;
        modal.style.left = `${left}px`;
      }
    }
  }, 120);
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initDashboard();
  if (!localStorage.getItem("fraudAgentTourSeen")) {
    setTimeout(() => {
      startTour();
      localStorage.setItem("fraudAgentTourSeen", "true");
    }, 1000);
  }
});
