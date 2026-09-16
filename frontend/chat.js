/**
 * chat.js
 * Handles the chatbot UI, message bubbles, and sending questions to the API.
 */

const copilotInput = document.getElementById("copilot-input");
const copilotBody = document.getElementById("copilot-body");

/**
 * Append message bubble to copilot chat feed
 */
function appendMessage(role, text, imageUrl = null, sql = null) {
  if (!copilotBody) return;

  const div = document.createElement("div");
  div.className = `chat-bubble ${role}`;

  if (role === "bot") {
    // Render markdown bold and bullets cleanly
    let formattedText = text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/^-\s+(.*)$/gm, "• $1");

    let sqlBlock = "";
    if (sql) {
      sqlBlock = `
        <details class="sql-trace-box">
          <summary style="cursor:pointer;font-size:10px;color:var(--amber)">VIEW SQL QUERY</summary>
          <pre style="margin-top:6px;white-space:pre-wrap;font-size:10px;color:var(--cyan);">${sql}</pre>
        </details>
      `;
    }

    let chartBlock = "";
    if (imageUrl) {
      chartBlock = `
        <div class="chart-card-wrap">
          <div style="padding:6px 10px;font-size:10px;font-family:var(--mono);color:var(--text-dim);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;background:var(--surface)">
            <span>GENERATED CHART</span>
            <span style="color:var(--amber)">OPEN</span>
          </div>
          <img src="${imageUrl}" alt="Telemetry Chart" onclick="window.open('${imageUrl}', '_blank')" />
        </div>
      `;
    }

    div.innerHTML = `
      <div class="tag">
        <span>COPILOT</span>
        <span>${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
      </div>
      <div>${formattedText}</div>
      ${sqlBlock}
      ${chartBlock}
    `;
  } else {
    div.textContent = text;
  }

  copilotBody.appendChild(div);
  copilotBody.scrollTop = copilotBody.scrollHeight;
}

let questionCount = 0;
const MAX_QUESTIONS = 10;

/**
 * Send user prompt to Copilot
 */
async function sendCopilotQuery(customPrompt = null) {
  const query = (customPrompt || (copilotInput ? copilotInput.value : "")).trim();
  if (!query) return;

  if (questionCount >= MAX_QUESTIONS) {
    appendMessage("bot", "🚨 **Demo Limit Reached:** To protect backend cloud resources, this interactive demo is restricted to 10 AI queries per session. Please refresh the page to start a new session.");
    if (copilotInput) {
      copilotInput.disabled = true;
      copilotInput.placeholder = "Session limit reached. Refresh page.";
    }
    return;
  }

  questionCount++;
  if (copilotInput) copilotInput.value = "";

  appendMessage("user", query);
  appendMessage("bot", "Generating SQL query...");

  try {
    const data = await askAgent(query);
    // Remove "Generating..." bubble
    if (copilotBody && copilotBody.lastChild) {
      copilotBody.lastChild.remove();
    }

    const chartUrl = data.chart_generated ? `${API_URL}/chart?ts=${Date.now()}` : null;
    appendMessage("bot", data.answer, chartUrl, data.sql);
  } catch (err) {
    if (copilotBody && copilotBody.lastChild) {
      copilotBody.lastChild.remove();
    }
    appendMessage("bot", `Query failed: ${err.message}`);
  }
}

// Preset chips handler
document.querySelectorAll(".copilot-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    const prompt = chip.getAttribute("data-prompt") || chip.textContent;
    sendCopilotQuery(prompt);
  });
});
