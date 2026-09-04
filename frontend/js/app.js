/**
 * NSE Swing Trading Bot - Frontend JavaScript Client
 * Manages Auth, Screener Data, Trade Approvals, and System Status.
 */

// Determine API base URL dynamically (allows deployment on Cloudflare Pages or custom backend)
const API_BASE_URL = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
  ? "" 
  : (window.APP_CONFIG?.API_BASE_URL || "");

let currentToken = localStorage.getItem("nse_bot_token") || null;
let currentUsername = localStorage.getItem("nse_bot_user") || "admin";
let pendingApprovalSignal = null;
let pollTimer = null;

// ─────────────────────────────────────────────────────────────
// INITIALIZATION
// ─────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  setupAuthEventListeners();
  setupTabNavigation();
  setupModalEventListeners();
  setupActionButtons();
  startLiveClock();

  if (currentToken) {
    verifySessionAndLoad();
  } else {
    showLogin();
  }
});

function getHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (currentToken) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }
  return headers;
}

// ─────────────────────────────────────────────────────────────
// AUTHENTICATION
// ─────────────────────────────────────────────────────────────

function setupAuthEventListeners() {
  const loginForm = document.getElementById("loginForm");
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value.trim();
    const errorEl = document.getElementById("loginError");
    const submitBtn = document.getElementById("loginSubmitBtn");

    errorEl.style.display = "none";
    submitBtn.disabled = true;
    submitBtn.textContent = "Authenticating...";

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Authentication failed");
      }

      currentToken = data.token;
      currentUsername = data.user.username;
      localStorage.setItem("nse_bot_token", currentToken);
      localStorage.setItem("nse_bot_user", currentUsername);

      showDashboard();
      loadAllDashboardData();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.style.display = "block";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Authenticate & Enter";
    }
  });

  document.getElementById("logoutBtn").addEventListener("click", () => {
    currentToken = null;
    localStorage.removeItem("nse_bot_token");
    localStorage.removeItem("nse_bot_user");
    if (pollTimer) clearInterval(pollTimer);
    showLogin();
  });
}

async function verifySessionAndLoad() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, { headers: getHeaders() });
    if (res.ok) {
      showDashboard();
      loadAllDashboardData();
      // Start auto-poll (default 60s when idle, 5s when scanning)
      scheduleDynamicPoll(60000);
    } else {
      showLogin();
    }
  } catch (err) {
    showLogin();
  }
}

function showLogin() {
  document.getElementById("loginSection").style.display = "flex";
  document.getElementById("dashboardSection").style.display = "none";
}

function showDashboard() {
  document.getElementById("loginSection").style.display = "none";
  document.getElementById("dashboardSection").style.display = "block";
  document.getElementById("userNameDisplay").textContent = currentUsername;
}

// ─────────────────────────────────────────────────────────────
// NAVIGATION TABS
// ─────────────────────────────────────────────────────────────

function setupTabNavigation() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add("active");
    });
  });
}

// ─────────────────────────────────────────────────────────────
// DATA LOADING & RENDERING
// ─────────────────────────────────────────────────────────────

async function loadAllDashboardData() {
  if (!currentToken) return;
  await Promise.all([
    fetchSignals(),
    fetchActiveTrades(),
    fetchTradeHistory(),
    fetchSystemStatus(),
    fetchSystemLogs(),
  ]);
}

// Helper Functions for UI formatting
function getStarRating(score) {
  const numScore = Number(score) || 0;
  const fullStars = Math.min(5, Math.max(1, Math.round(numScore / 2)));
  return "★".repeat(fullStars) + "☆".repeat(5 - fullStars);
}

function getRsiBadge(rsi) {
  if (rsi == null || isNaN(rsi)) {
    return '<span class="rsi-tag rsi-neutral">--</span>';
  }
  const val = Number(rsi);
  if (val < 30) {
    return `<span class="rsi-tag rsi-oversold-deep" title="Deep Oversold (<30)">${val.toFixed(1)} (Deep OS)</span>`;
  } else if (val <= 40) {
    return `<span class="rsi-tag rsi-oversold-mild" title="Oversold Zone (30-40)">${val.toFixed(1)} (Oversold)</span>`;
  } else {
    return `<span class="rsi-tag rsi-neutral">${val.toFixed(1)}</span>`;
  }
}

function getExchangeBadge(exchange, isDualListed) {
  const ex = (exchange || "NSE").toUpperCase();
  const cls = ex === "BSE" ? "badge-bse" : "badge-nse";
  let html = `<span class="exchange-badge ${cls}">${ex}</span>`;
  if (isDualListed) {
    html += ` <span class="exchange-badge badge-dual" title="Dual Listed on NSE and BSE">Dual Listed</span>`;
  }
  return html;
}

function formatLastScanTime(timeStr) {
  if (!timeStr) return "Today 03:32 PM IST";
  try {
    const parts = timeStr.split(" ");
    if (parts.length >= 2) {
      const timePart = parts[1];
      const [h, m] = timePart.split(":");
      const hourNum = parseInt(h, 10);
      const ampm = hourNum >= 12 ? "PM" : "AM";
      const displayHour = hourNum % 12 || 12;
      return `Today ${String(displayHour).padStart(2, "0")}:${m} ${ampm} IST`;
    }
    return `Today ${timeStr} IST`;
  } catch (e) {
    return `Today ${timeStr} IST`;
  }
}

window.switchSignalsView = function (mode) {
  const cardsContainer = document.getElementById("signalsCardsContainer");
  const tableContainer = document.getElementById("signalsTableContainer");
  const cardsBtn = document.getElementById("viewCardsBtn");
  const tableBtn = document.getElementById("viewTableBtn");

  if (mode === "cards") {
    if (cardsContainer) cardsContainer.style.display = "grid";
    if (tableContainer) tableContainer.style.display = "none";
    if (cardsBtn) cardsBtn.classList.add("active");
    if (tableBtn) tableBtn.classList.remove("active");
  } else {
    if (cardsContainer) cardsContainer.style.display = "none";
    if (tableContainer) tableContainer.style.display = "block";
    if (tableBtn) tableBtn.classList.add("active");
    if (cardsBtn) cardsBtn.classList.remove("active");
  }
};

let currentPollInterval = 60000;
function scheduleDynamicPoll(intervalMs) {
  if (intervalMs === currentPollInterval && pollTimer) return;
  currentPollInterval = intervalMs;
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(loadAllDashboardData, intervalMs);
}

// 1. Screener Signals
async function fetchSignals() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/screener/latest`, { headers: getHeaders() });
    if (res.status === 401) { showLogin(); return; }
    const data = await res.json();

    const tbody = document.getElementById("signalsTableBody");
    const cardsContainer = document.getElementById("signalsCardsContainer");
    const countEl = document.getElementById("statSignalsCount");
    const badgeEl = document.getElementById("signalsBadgeCount");
    const summaryPill = document.getElementById("stockCountSummary");
    const summaryChip = document.getElementById("signalsCountChip");

    const nseCount = data.nse_count != null ? data.nse_count : (data.signals || []).filter(s => (s.exchange || "NSE").toUpperCase() === "NSE").length;
    const bseCount = data.bse_count != null ? data.bse_count : (data.signals || []).filter(s => (s.exchange || "").toUpperCase() === "BSE").length;
    const totalSignals = (data.signals || []).length;

    const summaryText = `Found ${totalSignals} signals — NSE: ${nseCount} | BSE: ${bseCount}`;
    if (summaryPill) summaryPill.textContent = summaryText;
    if (summaryChip) summaryChip.textContent = summaryText;

    if (!data.signals || data.signals.length === 0) {
      if (tbody) {
        tbody.innerHTML = `
          <tr>
            <td colspan="12">
              <div class="empty-state">
                <div class="empty-icon">📊</div>
                <div>No signals generated yet.</div>
                <div style="font-size: 12px; margin-top: 6px;">Click <strong>"Run Screener Now"</strong> above or wait for the 3:30 PM IST daily run.</div>
              </div>
            </td>
          </tr>
        `;
      }
      if (cardsContainer) {
        cardsContainer.innerHTML = `
          <div class="empty-state" style="grid-column: 1 / -1;">
            <div class="empty-icon">📊</div>
            <div>No signals generated yet.</div>
            <div style="font-size: 12px; margin-top: 6px;">Click <strong>"Run Screener Now"</strong> above or wait for the 3:30 PM IST daily run.</div>
          </div>
        `;
      }
      countEl.textContent = "0";
      badgeEl.textContent = "0";
      return;
    }

    const pendingSignals = data.signals.filter((s) => s.status === "PENDING");
    countEl.textContent = pendingSignals.length;
    badgeEl.textContent = pendingSignals.length;

    // Render Cards View
    if (cardsContainer) {
      cardsContainer.innerHTML = data.signals.map((sig) => {
        const scoreClass = sig.score >= 8 ? "score-high" : (sig.score >= 5 ? "score-med" : "score-low");
        const isPending = sig.status === "PENDING";
        const isApproved = sig.status === "APPROVED";
        const stars = getStarRating(sig.score);
        const exBadges = getExchangeBadge(sig.exchange, sig.dual_listed);
        const rsiBadge = getRsiBadge(sig.rsi_value);

        return `
          <div class="signal-card" data-signal-id="${sig.id}">
            <div class="card-header-row">
              <div class="card-title-group">
                <div class="card-symbol-line">
                  <span class="card-symbol">${sig.symbol}</span>
                  ${exBadges}
                </div>
                <div class="card-company" title="${sig.company_name}">${sig.company_name}</div>
              </div>
              <div class="card-score-box">
                <div class="score-badge ${scoreClass}">${sig.score}/10</div>
                <div class="star-rating" title="Signal Score: ${sig.score}/10">${stars}</div>
              </div>
            </div>

            <div class="card-price-row">
              <div class="card-price-cell">
                <span class="price-lbl">Current</span>
                <span class="price-val">₹${sig.current_price.toFixed(2)}</span>
              </div>
              <div class="card-price-cell">
                <span class="price-lbl">Entry</span>
                <span class="price-val text-accent">₹${sig.suggested_entry.toFixed(2)}</span>
              </div>
              <div class="card-price-cell">
                <span class="price-lbl">Target (+15%)</span>
                <span class="price-val text-success">₹${sig.target_price.toFixed(2)}</span>
              </div>
              <div class="card-price-cell">
                <span class="price-lbl">SL (-0.5%)</span>
                <span class="price-val text-danger">₹${sig.stop_loss.toFixed(2)}</span>
              </div>
            </div>

            <div class="card-technicals-box">
              <div class="tech-level-line">
                <span>Trad S1/S2: ₹${sig.traditional_s1} / ₹${sig.traditional_s2}</span>
                <span>Fib S1/S2: ₹${sig.fibonacci_s1} / ₹${sig.fibonacci_s2}</span>
              </div>
              <div class="tech-level-line" style="align-items: center;">
                <div>RSI: ${rsiBadge}</div>
                <span class="tag-badge tag-success">Bullish Div ✓</span>
              </div>
            </div>

            <div class="card-action-bar">
              <div>
                <span class="rr-pill">R:R ${sig.risk_reward_ratio ? sig.risk_reward_ratio.toFixed(1) + ":1" : "--"}</span>
                <span style="font-size: 11px; color: var(--text-muted); margin-left: 6px;">₹${Number(sig.market_cap_cr).toLocaleString()} Cr</span>
              </div>
              <div>
                ${
                  isPending
                    ? `
                      <button class="btn btn-success btn-sm approve-btn" onclick="openApprovalModal(${sig.id})">Approve</button>
                      <button class="btn btn-ghost btn-sm reject-btn" onclick="rejectSignal(${sig.id})" style="margin-left: 6px;">Reject</button>
                    `
                    : isApproved
                    ? `<span class="tag-badge tag-success">Approved ✓</span>`
                    : `<span class="tag-badge tag-danger">Rejected ✗</span>`
                }
              </div>
            </div>
          </div>
        `;
      }).join("");
    }

    // Render Table View
    if (tbody) {
      tbody.innerHTML = data.signals.map((sig) => {
        const scoreClass = sig.score >= 8 ? "score-high" : (sig.score >= 5 ? "score-med" : "score-low");
        const isPending = sig.status === "PENDING";
        const isApproved = sig.status === "APPROVED";
        const stars = getStarRating(sig.score);
        const exBadges = getExchangeBadge(sig.exchange, sig.dual_listed);
        const rsiBadge = getRsiBadge(sig.rsi_value);

        return `
          <tr data-signal-id="${sig.id}">
            <td>
              <div style="display: flex; flex-direction: column; align-items: flex-start; gap: 2px;">
                <div class="score-badge ${scoreClass}">${sig.score}/10</div>
                <div class="star-rating" style="font-size: 11px;">${stars}</div>
              </div>
            </td>
            <td>
              <div class="stock-symbol">${sig.symbol}</div>
              <div class="company-name" title="${sig.company_name}">${sig.company_name}</div>
            </td>
            <td>
              ${exBadges}
            </td>
            <td><strong>₹${sig.current_price.toFixed(2)}</strong></td>
            <td>
              <div style="font-size: 12px;">
                <span style="color: var(--text-muted);">Trad:</span> S1 ₹${sig.traditional_s1} | S2 ₹${sig.traditional_s2}<br>
                <span style="color: var(--text-muted);">Fib:</span> S1 ₹${sig.fibonacci_s1} | S2 ₹${sig.fibonacci_s2}
              </div>
            </td>
            <td>
              <div style="font-size: 12px;">
                ${rsiBadge}<br>
                <span class="tag-badge tag-success" style="margin-top: 3px;">Bullish Div ✓</span>
              </div>
            </td>
            <td><strong class="text-accent">₹${sig.suggested_entry.toFixed(2)}</strong></td>
            <td><strong class="text-success">₹${sig.target_price.toFixed(2)}</strong></td>
            <td><strong class="text-danger">₹${sig.stop_loss.toFixed(2)}</strong></td>
            <td>${sig.risk_reward_ratio ? sig.risk_reward_ratio.toFixed(1) + ":1" : "--"}</td>
            <td>₹${Number(sig.market_cap_cr).toLocaleString()} Cr</td>
            <td style="text-align: right; white-space: nowrap;">
              ${
                isPending
                  ? `
                    <button class="btn btn-success btn-sm approve-btn" onclick="openApprovalModal(${sig.id})">Approve</button>
                    <button class="btn btn-ghost btn-sm reject-btn" onclick="rejectSignal(${sig.id})" style="margin-left: 6px;">Reject</button>
                  `
                  : isApproved
                  ? `<span class="tag-badge tag-success">Approved ✓</span>`
                  : `<span class="tag-badge tag-danger">Rejected ✗</span>`
              }
            </td>
          </tr>
        `;
      }).join("");
    }
  } catch (err) {
    console.error("Error fetching signals:", err);
  }
}

// 2. Active Trades
async function fetchActiveTrades() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/trades/active`, { headers: getHeaders() });
    if (res.status === 401) { showLogin(); return; }
    const data = await res.json();

    const tbody = document.getElementById("activeTradesTableBody");
    const countEl = document.getElementById("statActiveTradesCount");
    const badgeEl = document.getElementById("activeTradesBadgeCount");
    const deployedEl = document.getElementById("statCapitalDeployed");

    countEl.textContent = data.count || 0;
    badgeEl.textContent = data.count || 0;

    if (!data.trades || data.trades.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="10">
            <div class="empty-state">
              <div class="empty-icon">💼</div>
              <div>No active trades open.</div>
              <div style="font-size: 12px; margin-top: 6px;">Approve a screener signal to dispatch order to broker.</div>
            </div>
          </td>
        </tr>
      `;
      deployedEl.textContent = "Deployed: ₹0";
      return;
    }

    let totalDeployed = 0;

    tbody.innerHTML = data.trades.map((t) => {
      const invested = t.entry_price * t.quantity;
      totalDeployed += invested;
      const isPositive = (t.pnl || 0) >= 0;
      const pnlColor = isPositive ? "text-success" : "text-danger";

      // Calculate progress toward target vs stop loss
      const totalRange = t.target_price - t.stop_loss;
      const progress = totalRange > 0 ? Math.min(100, Math.max(0, ((t.current_price - t.stop_loss) / totalRange) * 100)) : 50;

      return `
        <tr>
          <td>#${t.id}</td>
          <td><strong class="stock-symbol">${t.symbol}</strong></td>
          <td>${t.quantity}</td>
          <td>₹${t.entry_price.toFixed(2)}</td>
          <td><strong>₹${(t.current_price || t.entry_price).toFixed(2)}</strong></td>
          <td><strong class="text-success">₹${t.target_price.toFixed(2)}</strong></td>
          <td><strong class="text-danger">₹${t.stop_loss.toFixed(2)}</strong></td>
          <td class="${pnlColor}">
            <strong>${isPositive ? "+" : ""}₹${(t.pnl || 0).toFixed(2)}</strong> (${isPositive ? "+" : ""}${(t.pnl_pct || 0).toFixed(2)}%)
          </td>
          <td style="min-width: 140px;">
            <div style="background: rgba(255,255,255,0.06); border-radius: 4px; height: 6px; overflow: hidden; margin-bottom: 4px;">
              <div style="background: var(--accent-gradient); width: ${progress}%; height: 100%;"></div>
            </div>
            <div style="font-size: 10px; color: var(--text-muted); display: flex; justify-content: space-between;">
              <span>SL</span>
              <span>Target (+15%)</span>
            </div>
          </td>
          <td><span class="tag-badge tag-accent">${t.status}</span></td>
        </tr>
      `;
    }).join("");

    deployedEl.textContent = `Deployed: ₹${totalDeployed.toLocaleString()}`;
  } catch (err) {
    console.error("Error fetching active trades:", err);
  }
}

// 3. Trade History
async function fetchTradeHistory() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/trades/history`, { headers: getHeaders() });
    if (res.status === 401) { showLogin(); return; }
    const data = await res.json();

    const tbody = document.getElementById("historyTableBody");
    const pnlEl = document.getElementById("statRealizedPnl");
    const winRateEl = document.getElementById("statWinRate");

    const totalPnl = data.total_realized_pnl || 0;
    pnlEl.textContent = (totalPnl >= 0 ? "+" : "") + `₹${totalPnl.toFixed(2)}`;
    pnlEl.className = `metric-value ${totalPnl >= 0 ? "text-success" : "text-danger"}`;
    winRateEl.textContent = `Win Rate: ${data.win_rate_pct || 0}% (${data.closed_trades || 0} closed)`;

    if (!data.trades || data.trades.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="11">
            <div class="empty-state">
              <div class="empty-icon">📜</div>
              <div>No trade history available yet.</div>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = data.trades.map((t) => {
      const isPositive = (t.pnl || 0) >= 0;
      const pnlColor = isPositive ? "text-success" : "text-danger";

      return `
        <tr>
          <td>#${t.id}</td>
          <td><strong>${t.symbol}</strong></td>
          <td>${t.entry_date ? t.entry_date.split(" ")[0] : "--"}</td>
          <td>${t.exit_date ? t.exit_date.split(" ")[0] : "--"}</td>
          <td>${t.quantity}</td>
          <td>₹${t.entry_price.toFixed(2)}</td>
          <td>${t.exit_price ? `₹${t.exit_price.toFixed(2)}` : "--"}</td>
          <td class="${pnlColor}"><strong>${isPositive ? "+" : ""}₹${(t.pnl || 0).toFixed(2)}</strong></td>
          <td class="${pnlColor}">${isPositive ? "+" : ""}${(t.pnl_pct || 0).toFixed(2)}%</td>
          <td><span class="tag-badge ${t.status === 'TARGET_HIT' ? 'tag-success' : (t.status === 'SL_HIT' ? 'tag-danger' : 'tag-accent')}">${t.status}</span></td>
          <td style="font-size: 11px; color: var(--text-muted);">${t.notes || "--"}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error fetching trade history:", err);
  }
}

// 4. System & Scheduler Status
async function fetchSystemStatus() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/system/status`, { headers: getHeaders() });
    if (!res.ok) return;
    const data = await res.json();

    const brokerTag = document.getElementById("brokerModeTag");
    if (brokerTag) brokerTag.textContent = data.broker_mode || "MOCK";

    const sched = data.scheduler || {};
    const nextRunEl = document.getElementById("schedNextRun");
    if (nextRunEl) nextRunEl.textContent = sched.next_run_time || "Scheduled at 3:30 PM IST";

    const lastStatusEl = document.getElementById("schedLastStatus");
    if (lastStatusEl) lastStatusEl.textContent = sched.last_run_status || "Ready";

    // 1. Update Last Scan Time Display
    const lastScanFormatted = formatLastScanTime(sched.last_run_time);
    const lastScanEl = document.getElementById("lastScannedDisplay");
    if (lastScanEl) lastScanEl.textContent = lastScanFormatted;

    // 2. Update Screener Status Bar & Progress
    const statusTextEl = document.getElementById("screenerStatusText");
    const progressStatsEl = document.getElementById("screenerProgressStats");
    const progressBarEl = document.getElementById("screenerProgressBar");
    const dotEl = document.getElementById("screenerDot");
    const progress = sched.progress || {};

    const isScanning = sched.is_scanning;
    const scanSpinner = document.getElementById("scanSpinner");
    const triggerBtn = document.getElementById("triggerScanBtn");

    if (isScanning) {
      if (scanSpinner) scanSpinner.style.display = "inline-block";
      if (triggerBtn) triggerBtn.disabled = true;

      const processed = progress.processed || 0;
      const total = progress.total || 0;
      const percent = progress.percent || (total > 0 ? Math.round((processed / total) * 100) : 20);

      if (statusTextEl) statusTextEl.textContent = progress.status_text || `Scanning... ${processed}/${total} stocks processed`;
      if (progressStatsEl) progressStatsEl.textContent = `${processed}/${total} stocks processed`;
      if (progressBarEl) progressBarEl.style.width = `${percent}%`;

      if (dotEl) {
        dotEl.style.background = "var(--warning)";
        dotEl.style.boxShadow = "0 0 10px var(--warning)";
      }

      // Fast poll while scanning
      scheduleDynamicPoll(4000);
    } else {
      if (scanSpinner) scanSpinner.style.display = "none";
      if (triggerBtn) triggerBtn.disabled = false;

      if (statusTextEl) statusTextEl.textContent = "Scan Complete";
      if (progressStatsEl) progressStatsEl.textContent = sched.last_run_status || "Ready";
      if (progressBarEl) progressBarEl.style.width = "100%";

      if (dotEl) {
        dotEl.style.background = "var(--success)";
        dotEl.style.boxShadow = "0 0 10px var(--success)";
      }

      // Auto refresh every 60 seconds when idle
      scheduleDynamicPoll(60000);
    }
  } catch (err) {
    console.error("Error fetching system status:", err);
  }
}

// 5. System Logs
async function fetchSystemLogs() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/system/logs`, { headers: getHeaders() });
    if (!res.ok) return;
    const data = await res.json();

    const container = document.getElementById("systemLogsContainer");
    if (!data.logs || data.logs.length === 0) {
      container.textContent = "No log records found.";
      return;
    }

    container.innerHTML = data.logs.map((log) => {
      const color = log.level === "ERROR" ? "var(--danger)" : (log.level === "WARNING" ? "var(--warning)" : "var(--info)");
      return `<div style="margin-bottom: 4px;">
        <span style="color: var(--text-muted);">${log.timestamp}</span>
        <span style="color: ${color}; font-weight: bold; margin: 0 4px;">[${log.level}]</span>
        <span style="color: #a5b4fc; margin-right: 6px;">[${log.source}]</span>
        <span>${log.message}</span>
      </div>`;
    }).join("");
  } catch (err) {
    console.error("Error fetching logs:", err);
  }
}

// ─────────────────────────────────────────────────────────────
// ACTIONS: SCREENER SCAN & APPROVAL MODAL
// ─────────────────────────────────────────────────────────────

function setupActionButtons() {
  const triggerBtn = document.getElementById("triggerScanBtn");
  triggerBtn.addEventListener("click", async () => {
    const limit = document.getElementById("scanLimitSelector").value;
    triggerBtn.disabled = true;
    document.getElementById("scanSpinner").style.display = "inline-block";

    try {
      const res = await fetch(`${API_BASE_URL}/api/screener/run`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ limit_universe: limit || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || "Failed to trigger scan");
      alert("Screener scan started in background. New signals will appear here automatically.");
    } catch (err) {
      alert(`Error starting scan: ${err.message}`);
      triggerBtn.disabled = false;
      document.getElementById("scanSpinner").style.display = "none";
    }
  });

  document.getElementById("refreshLogsBtn").addEventListener("click", fetchSystemLogs);
}

// Modal
function setupModalEventListeners() {
  const modal = document.getElementById("approvalModal");
  const closeBtn = document.getElementById("closeModalBtn");
  const cancelBtn = document.getElementById("cancelModalBtn");
  const confirmBtn = document.getElementById("confirmApproveBtn");

  const closeModal = () => {
    modal.classList.remove("active");
    pendingApprovalSignal = null;
  };

  closeBtn.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  confirmBtn.addEventListener("click", async () => {
    if (!pendingApprovalSignal) return;

    confirmBtn.disabled = true;
    document.getElementById("modalBtnSpinner").style.display = "inline-block";

    try {
      const res = await fetch(`${API_BASE_URL}/api/trades/approve/${pendingApprovalSignal.id}`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ quantity: pendingApprovalSignal.quantity }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Approval failed");

      closeModal();
      await loadAllDashboardData();
      alert(`Order successfully executed for ${pendingApprovalSignal.symbol}! (Trade ID: ${data.trade_id})`);
    } catch (err) {
      alert(`Trade approval failed: ${err.message}`);
    } finally {
      confirmBtn.disabled = false;
      document.getElementById("modalBtnSpinner").style.display = "none";
    }
  });
}

// Global hook for Approve button click in table
window.openApprovalModal = async function (signalId) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/screener/latest`, { headers: getHeaders() });
    const data = await res.json();
    const signal = (data.signals || []).find((s) => s.id === signalId);
    if (!signal) return;

    pendingApprovalSignal = signal;
    document.getElementById("modalSymbol").textContent = signal.symbol;
    document.getElementById("modalCompany").textContent = signal.company_name;
    document.getElementById("modalEntry").textContent = `₹${signal.suggested_entry.toFixed(2)}`;
    document.getElementById("modalQuantity").textContent = `${signal.quantity} Shares`;
    document.getElementById("modalInvestment").textContent = `₹${(signal.quantity * signal.suggested_entry).toFixed(2)}`;
    document.getElementById("modalTarget").textContent = `₹${signal.target_price.toFixed(2)} (+15%)`;
    document.getElementById("modalStopLoss").textContent = `₹${signal.stop_loss.toFixed(2)} (-0.5% below S2)`;

    document.getElementById("approvalModal").classList.add("active");
  } catch (err) {
    console.error("Error opening modal:", err);
  }
};

// Global hook for Reject button click in table
window.rejectSignal = async function (signalId) {
  if (!confirm("Are you sure you want to reject this signal?")) return;

  try {
    const res = await fetch(`${API_BASE_URL}/api/trades/reject/${signalId}`, {
      method: "POST",
      headers: getHeaders(),
    });
    if (res.ok) {
      await fetchSignals();
    }
  } catch (err) {
    console.error("Error rejecting signal:", err);
  }
};

// ─────────────────────────────────────────────────────────────
// LIVE IST CLOCK & MARKET STATUS
// ─────────────────────────────────────────────────────────────

function startLiveClock() {
  function update() {
    const now = new Date();
    // Format to Asia/Kolkata
    const istString = now.toLocaleTimeString("en-IN", {
      timeZone: "Asia/Kolkata",
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    const clockEl = document.getElementById("liveIstClock");
    if (clockEl) clockEl.textContent = `${istString} IST`;

    // Check market session (Mon-Fri 09:15 to 15:30)
    const day = now.getDay();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const currentMins = hours * 60 + minutes;
    const marketOpen = 9 * 60 + 15;
    const marketClose = 15 * 60 + 30;

    const statusEl = document.getElementById("marketStatusText");
    const dotEl = document.getElementById("marketDot");

    if (day >= 1 && day <= 5 && currentMins >= marketOpen && currentMins <= marketClose) {
      statusEl.textContent = "NSE Market LIVE (09:15 - 15:30 IST)";
      dotEl.style.background = "var(--success)";
      dotEl.style.boxShadow = "0 0 10px var(--success)";
    } else {
      statusEl.textContent = "NSE Closed (Next Scan 3:30 PM IST)";
      dotEl.style.background = "var(--warning)";
      dotEl.style.boxShadow = "0 0 10px var(--warning)";
    }
  }
  update();
  setInterval(update, 1000);
}
