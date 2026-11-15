// Global State
let chart = null;
let candleSeries = null;
let swingHighLine = null;
let swingLowLine = null;
let entryLine = null;
let slLine = null;
let tpLine = null;

let soundEnabled = true;
let lastKnownSignalType = null;
let audioContext = null;

// Zoom Management (Normal / Large / Extra Large)
const ZOOM_LEVELS = ["zoom-normal", "zoom-large", "zoom-xlarge"];
let currentZoomIdx = 0;

function applyZoom(idx) {
    currentZoomIdx = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, idx));
    document.body.className = ZOOM_LEVELS[currentZoomIdx];
    localStorage.setItem("gold_app_zoom", currentZoomIdx);

    const labels = ["100%", "125%", "150%"];
    const resetBtn = document.getElementById("btnZoomReset");
    if (resetBtn) {
        resetBtn.innerText = labels[currentZoomIdx];
        resetBtn.className = currentZoomIdx === 0 ? "btn-zoom active" : "btn-zoom";
    }

    // Trigger chart resize
    if (chart) {
        const container = document.getElementById("tvChartContainer");
        chart.applyOptions({
            width: container.clientWidth,
            height: container.clientHeight
        });
        chart.timeScale().fitContent();
    }
}

function changeZoom(delta) {
    applyZoom(currentZoomIdx + delta);
}

function resetZoom() {
    applyZoom(0);
}

// Initialize when DOM loads
document.addEventListener("DOMContentLoaded", () => {
    const savedZoom = localStorage.getItem("gold_app_zoom");
    if (savedZoom !== null) {
        applyZoom(parseInt(savedZoom, 10));
    } else {
        // Default to Large on screens wider than 1600px
        if (window.innerWidth >= 1600) {
            applyZoom(1); // 125%
        } else {
            applyZoom(0);
        }
    }

    initChart();
    requestNotificationPermission();
    fetchStatus();

    // Auto-polling every 30 seconds
    setInterval(fetchStatus, 30000);
});

// 1. Initialize TradingView Lightweight Charts
function initChart() {
    const container = document.getElementById("tvChartContainer");
    
    chart = LightweightCharts.createChart(container, {
        layout: {
            background: { color: "#131822" },
            textColor: "#cbd5e1",
            fontSize: 14,
            fontFamily: "'JetBrains Mono', monospace",
        },
        grid: {
            vertLines: { color: "#1c2434" },
            horzLines: { color: "#1c2434" },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: "#2a374d",
            scaleMargins: { top: 0.1, bottom: 0.2 },
        },
        timeScale: {
            borderColor: "#2a374d",
            timeVisible: true,
            secondsVisible: false,
        },
    });

    candleSeries = chart.addCandlestickSeries({
        upColor: "#10b981",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#10b981",
        wickDownColor: "#ef4444",
    });

    // Handle responsive resize
    window.addEventListener("resize", () => {
        chart.applyOptions({
            width: container.clientWidth,
            height: container.clientHeight
        });
    });
}

// 2. Fetch Latest Strategy Status from Python Server
async function fetchStatus() {
    try {
        const resp = await fetch("/api/status");
        const json = await resp.json();
        if (json.status === "success" && json.data) {
            updateUI(json.data, json.config);
        }
    } catch (err) {
        console.error("Error fetching status:", err);
    }
}

// 3. Manual Scan Trigger
async function triggerManualScan() {
    const icon = document.getElementById("scanIcon");
    const statusText = document.getElementById("scanStatusText");
    
    icon.classList.add("fa-spin");
    statusText.innerText = "Analyzing XAU/USD...";

    try {
        const resp = await fetch("/api/scan_now", { method: "POST" });
        const json = await resp.json();
        if (json.status === "success" && json.data) {
            updateUI(json.data);
        }
    } catch (err) {
        console.error("Scan error:", err);
    } finally {
        setTimeout(() => {
            icon.classList.remove("fa-spin");
            statusText.innerText = "Auto-Scanning Active";
        }, 800);
    }
}

// 4. Update the Entire Dashboard UI
function updateUI(data, config) {
    if (!data) return;

    // A. Update Live Price
    if (data.current_price) {
        document.getElementById("livePrice").innerText = `$${data.current_price.toFixed(2)}`;
    }

    // B. Update Chart Candles
    if (data.chart_data && data.chart_data.length > 0) {
        candleSeries.setData(data.chart_data);
        if (!window.hasFittedChart) {
            chart.timeScale().fitContent();
            window.hasFittedChart = true;
        }
    }

    // C. Update Liquidity Lines on Chart
    if (data.recent_swing_high) {
        document.getElementById("valHighLiquidity").innerText = `$${data.recent_swing_high.toFixed(2)}`;
        if (swingHighLine) candleSeries.removePriceLine(swingHighLine);
        swingHighLine = candleSeries.createPriceLine({
            price: data.recent_swing_high,
            color: "#f97316",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: "Buy-side Liq (15M High)",
        });
    }

    if (data.recent_swing_low) {
        document.getElementById("valLowLiquidity").innerText = `$${data.recent_swing_low.toFixed(2)}`;
        if (swingLowLine) candleSeries.removePriceLine(swingLowLine);
        swingLowLine = candleSeries.createPriceLine({
            price: data.recent_swing_low,
            color: "#06b6d4",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: "Sell-side Liq (15M Low)",
        });
    }

    // D. Step 1: Timeframe Badges
    const b1H = document.getElementById("badge1H");
    const b15M = document.getElementById("badge15M");
    const sStep1 = document.getElementById("statusStep1");

    const htfText = data.htf_bias === "BULLISH" ? "1-Hour: Bullish (Up) 🟢" : (data.htf_bias === "BEARISH" ? "1-Hour: Bearish (Down) 🔴" : "1-Hour: Neutral / Choppy ⚪");
    const ltfText = data.ltf_bias === "BULLISH" ? "15-Min: Bullish (Up) 🟢" : (data.ltf_bias === "BEARISH" ? "15-Min: Bearish (Down) 🔴" : "15-Min: Neutral / Choppy ⚪");

    b1H.className = `badge ${data.htf_bias.toLowerCase()}`;
    b1H.innerText = htfText;

    b15M.className = `badge ${data.ltf_bias.toLowerCase()}`;
    b15M.innerText = ltfText;

    if (data.alignment_status === "ALIGNED_BULLISH") {
        sStep1.innerHTML = `<i class="fa-solid fa-circle-check text-success" title="Both aligned Bullish!"></i>`;
    } else if (data.alignment_status === "ALIGNED_BEARISH") {
        sStep1.innerHTML = `<i class="fa-solid fa-circle-check text-danger" title="Both aligned Bearish!"></i>`;
    } else {
        sStep1.innerHTML = `<i class="fa-solid fa-hourglass-start text-warning" style="color: #f59e0b;" title="Waiting for alignment"></i>`;
    }

    // E. Steps 3 & 4: Sweep Status
    const sweepTxt = document.getElementById("sweepStatusDetail");
    const sStep3 = document.getElementById("statusStep3");
    if (data.swept_bullish) {
        sweepTxt.innerHTML = `<span class="text-success">🔥 Smart money swept sell-side stops at ${data.sweep_time || "recent candle"}! Rejected and closed back up.</span>`;
        sStep3.innerHTML = `<i class="fa-solid fa-circle-check text-success"></i>`;
    } else if (data.swept_bearish) {
        sweepTxt.innerHTML = `<span class="text-danger">🔥 Smart money swept buy-side stops at ${data.sweep_time || "recent candle"}! Rejected and closed back down.</span>`;
        sStep3.innerHTML = `<i class="fa-solid fa-circle-check text-danger"></i>`;
    } else {
        sweepTxt.innerText = "No sweep detected yet. Price is inside the range (Be patient, wait for liquidity grab).";
        sStep3.innerHTML = `<i class="fa-solid fa-circle-question status-waiting"></i>`;
    }

    // F. Active Signal Box & Targets
    const card = document.getElementById("signalHeroCard");
    const emptyState = document.getElementById("signalEmptyState");
    const activeState = document.getElementById("signalActiveState");
    const badge = document.getElementById("signalBadge");

    if (data.signal) {
        const sig = data.signal;
        emptyState.style.display = "none";
        activeState.style.display = "block";

        card.className = `card signal-card ${sig.type.toLowerCase()}`;
        badge.className = `signal-badge ${sig.type.toLowerCase()}`;
        badge.innerText = `${sig.type} SIGNAL (CONFIRMED)`;

        document.getElementById("sigEntry").innerText = `$${sig.entry.toFixed(2)}`;
        document.getElementById("sigSL").innerText = `$${sig.sl.toFixed(2)}`;
        document.getElementById("sigTP").innerText = `$${sig.tp.toFixed(2)}`;
        document.getElementById("sigRR").innerText = sig.rr;
        document.getElementById("sigReason").innerText = sig.reason;

        // Draw SL & TP lines on chart
        if (entryLine) candleSeries.removePriceLine(entryLine);
        if (slLine) candleSeries.removePriceLine(slLine);
        if (tpLine) candleSeries.removePriceLine(tpLine);

        entryLine = candleSeries.createPriceLine({
            price: sig.entry,
            color: "#3b82f6",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            title: `ENTRY ($${sig.entry})`,
        });

        slLine = candleSeries.createPriceLine({
            price: sig.sl,
            color: "#ef4444",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            title: `STOP LOSS ($${sig.sl})`,
        });

        tpLine = candleSeries.createPriceLine({
            price: sig.tp,
            color: "#10b981",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            title: `TAKE PROFIT ($${sig.tp})`,
        });

        // Trigger Audio Chime & Browser Notification on fresh signal
        if (lastKnownSignalType !== sig.type) {
            playAlertSound();
            showBrowserNotification(sig);
            lastKnownSignalType = sig.type;
        }

    } else {
        emptyState.style.display = "block";
        activeState.style.display = "none";
        card.className = "card signal-card waiting";

        if (entryLine) { candleSeries.removePriceLine(entryLine); entryLine = null; }
        if (slLine) { candleSeries.removePriceLine(slLine); slLine = null; }
        if (tpLine) { candleSeries.removePriceLine(tpLine); tpLine = null; }
        lastKnownSignalType = null;
    }

    // Populate Settings Modal form if config provided
    if (config) {
        if (document.getElementById("cfgEntryMode")) {
            document.getElementById("cfgEntryMode").value = config.entry_mode || "Conservative (MSS Confirmation)";
            document.getElementById("cfgRR").value = config.risk_reward || 2.5;
            document.getElementById("cfgTgToken").value = config.telegram_token || "";
            document.getElementById("cfgTgChatId").value = config.telegram_chat_id || "";
        }
    }
}

// 5. Sound Alerts using Web Audio API (Zero dependencies / free)
function playAlertSound() {
    if (!soundEnabled) return;
    try {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();

        osc.type = "sine";
        // Nice pleasant ascending double chime
        osc.frequency.setValueAtTime(587.33, audioContext.currentTime); // D5
        osc.frequency.setValueAtTime(880.00, audioContext.currentTime + 0.15); // A5

        gain.gain.setValueAtTime(0.2, audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.6);

        osc.connect(gain);
        gain.connect(audioContext.destination);

        osc.start();
        osc.stop(audioContext.currentTime + 0.6);
    } catch (e) {
        console.log("Audio play error:", e);
    }
}

function toggleAudioAlert() {
    soundEnabled = !soundEnabled;
    const btn = document.getElementById("btnSoundToggle");
    const icon = document.getElementById("soundIcon");
    if (soundEnabled) {
        btn.innerHTML = `<i class="fa-solid fa-volume-high" id="soundIcon"></i> Sound ON`;
        btn.className = "btn btn-secondary";
        playAlertSound();
    } else {
        btn.innerHTML = `<i class="fa-solid fa-volume-xmark" id="soundIcon"></i> Sound OFF`;
        btn.className = "btn btn-outline";
    }
}

// 6. Browser Push Notifications
function requestNotificationPermission() {
    if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
    }
}

function showBrowserNotification(sig) {
    if ("Notification" in window && Notification.permission === "granted") {
        new Notification(`🚨 Gold ${sig.type} Signal Detected!`, {
            body: `Entry: $${sig.entry} | SL: $${sig.sl} | TP: $${sig.tp}\nSetup: ${sig.reason}`,
            icon: "https://cdn-icons-png.flaticon.com/512/2534/2534183.png"
        });
    }
}

// 7. Config & Telegram Modal
function openConfigModal() {
    document.getElementById("configModal").style.display = "flex";
}

function closeConfigModal() {
    document.getElementById("configModal").style.display = "none";
    document.getElementById("tgTestMsg").innerText = "";
}

async function saveConfiguration() {
    const payload = {
        entry_mode: document.getElementById("cfgEntryMode").value,
        risk_reward: parseFloat(document.getElementById("cfgRR").value) || 2.5,
        telegram_token: document.getElementById("cfgTgToken").value.trim(),
        telegram_chat_id: document.getElementById("cfgTgChatId").value.trim()
    };

    try {
        await fetch("/api/save_config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        closeConfigModal();
        triggerManualScan();
    } catch (err) {
        console.error("Save config error:", err);
    }
}

async function testTelegram() {
    const token = document.getElementById("cfgTgToken").value.trim();
    const chatId = document.getElementById("cfgTgChatId").value.trim();
    const feedback = document.getElementById("tgTestMsg");

    feedback.innerText = "Sending test message...";
    feedback.style.color = "#94a3b8";

    try {
        const resp = await fetch("/api/test_telegram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: token, chat_id: chatId })
        });
        const res = await resp.json();
        if (res.status === "success") {
            feedback.innerText = "✅ Test message sent! Check your Telegram.";
            feedback.style.color = "#10b981";
        } else {
            feedback.innerText = `❌ Error: ${res.message}`;
            feedback.style.color = "#ef4444";
        }
    } catch (e) {
        feedback.innerText = "❌ Network connection error.";
        feedback.style.color = "#ef4444";
    }
}
