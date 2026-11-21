// Constants & Globals
const STATUS_POLL_INTERVAL = 500; // Poll backend every 500ms
let currentView = "alerts";       // "alerts", "live-command", "workstations", "volunteers"
let currentSystemState = "resting";
const MOCK_VOLUNTEERS = [
    { id: "vol-2", name: "Volunteer Jane Doe", model: "HQ-PI-ZERO-02", distance: 120, x: 80, y: -60, status: "available" },
    { id: "vol-3", name: "Volunteer John Smith", model: "HQ-PI-ZERO-03", distance: 280, x: -180, y: 150, status: "available" },
    { id: "vol-4", name: "Volunteer Alice Wang", model: "HQ-PI-ZERO-04", distance: 410, x: 120, y: 320, status: "available" }
];

let statusHistory = {
    bpm: Array(30).fill(72),
    micAmp: Array(30).fill(0.01)
};
let isAudioPlaying = false;

// Web Audio API Globals
let audioCtx = null;
let analyser = null;
let audioSource = null;
let audioDataArray = null;
let animationFrameId = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    // Start clock display
    startClock();
    
    // Start active backend polling
    pollStatus();
    setInterval(pollStatus, STATUS_POLL_INTERVAL);
    
    // Start drawing canvas charts
    startTelemetryCharts();
    
    // Start radar map visualization loop
    startVolunteersMap();
});

// 1. DYNAMIC SYSTEM CLOCK
function startClock() {
    const clockEl = document.getElementById("clock");
    function updateClock() {
        const now = new Date();
        clockEl.textContent = now.toTimeString().split(" ")[0];
    }
    updateClock();
    setInterval(updateClock, 1000);
}

// 2. COHESIVE ROUTING SYSTEM (SWITCH VIEWS)
function switchView(viewId) {
    if (viewId === currentView) return;
    
    // Toggle active classes on primary navigation tabs
    const navTabs = document.getElementById("main-nav-tabs");
    navTabs.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
    
    // If navigating inside views, light up correct primary nav tab
    if (viewId === "alerts" || viewId === "live-command") {
        document.getElementById("tab-btn-alerts").classList.add("active");
    } else if (viewId === "workstations" || viewId === "volunteers") {
        document.getElementById("tab-btn-workstations").classList.add("active");
    }
    
    // Toggle active view layouts
    document.querySelectorAll(".tab-content").forEach(view => view.classList.remove("active"));
    document.getElementById(`view-${viewId}`).classList.add("active");
    
    currentView = viewId;
}

// 3. SCROLLING LINE TELEMETRY CHARTS
function startTelemetryCharts() {
    const micCanvas = document.getElementById("canvas-mic-chart");
    const pulseCanvas = document.getElementById("canvas-pulse-chart");
    
    function drawChart(canvas, data, minVal, maxVal, color) {
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const width = canvas.width = canvas.clientWidth;
        const height = canvas.height = canvas.clientHeight;
        
        ctx.clearRect(0, 0, width, height);
        
        // Draw layout grid lines
        ctx.strokeStyle = "rgba(255, 255, 255, 0.02)";
        ctx.lineWidth = 1;
        for (let i = 1; i < 4; i++) {
            let y = (height / 4) * i;
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
        }

        if (data.length === 0) return;
        
        // Plot line graph
        ctx.beginPath();
        ctx.lineWidth = 2;
        ctx.strokeStyle = color;
        
        const step = width / (data.length - 1);
        for (let i = 0; i < data.length; i++) {
            const normalized = (data[i] - minVal) / (maxVal - minVal || 1);
            const capped = Math.min(Math.max(normalized, 0), 1);
            const x = i * step;
            const y = height - (capped * height * 0.8) - (height * 0.1);
            
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
        
        // Glowing fills below graph
        ctx.lineTo(width, height);
        ctx.lineTo(0, height);
        ctx.closePath();
        
        let grad = ctx.createLinearGradient(0, 0, 0, height);
        grad.addColorStop(0, color.replace("1)", "0.15)"));
        grad.addColorStop(1, color.replace("1)", "0)"));
        ctx.fillStyle = grad;
        ctx.fill();
    }

    function animate() {
        const isTriggered = document.body.classList.contains("state-triggered");
        const pulseColor = isTriggered ? "rgba(255, 51, 102, 1)" : "rgba(0, 230, 118, 1)";
        const micColor = "rgba(0, 229, 255, 1)";
        
        drawChart(pulseCanvas, statusHistory.bpm, 40, 180, pulseColor);
        drawChart(micCanvas, statusHistory.micAmp, 0.0, 0.4, micColor);
        
        setTimeout(() => requestAnimationFrame(animate), 66);
    }
    
    animate();
}

// 4. REST POLING API CALLBACK ROUTINE
async function pollStatus() {
    try {
        const res = await fetch("/api/status");
        if (!res.ok) throw new Error("Server communication issue");
        const data = await res.json();
        
        // Update general body CSS status
        updateSystemStateView(data.state);
        
        // Update Dashboard Summary Stats Row (Glance values)
        const stateText = data.state === "triggered" ? "TRIGGERED" : "RESTING";
        document.getElementById("val-state").textContent = stateText;
        
        const hrText = data.heart_rate > 0 ? `${data.heart_rate} BPM` : "-- BPM";
        document.getElementById("val-heart").textContent = hrText;
        document.getElementById("val-freq").textContent = `${data.mic_frequency} Hz`;
        document.getElementById("val-faces").textContent = data.captured_faces_count;
        
        // Update view containers based on alarm presence
        const noAlertsPanel = document.getElementById("panel-no-alerts");
        const activeAlertCard = document.getElementById("panel-active-alert");
        const cardThumb = document.getElementById("alert-static-thumb");
        
        if (data.state === "triggered") {
            // Hide empty state, reveal emergency card
            noAlertsPanel.style.display = "none";
            activeAlertCard.style.display = "block";
            
            // Append cache-buster timestamp to starting thumbnail image to prevent caching issues!
            const t = new Date().getTime();
            cardThumb.src = `/static/screenshots/alert_start.jpg?t=${t}`;
            
            // Update emergency specs on card
            document.getElementById("alert-card-val-source").textContent = (data.last_trigger_source || "AUDIO").toUpperCase();
            document.getElementById("alert-card-val-duration").textContent = `${data.duration_seconds}s`;
            document.getElementById("alert-card-val-pulse").textContent = hrText;
            
            // Update live view badge
            document.getElementById("live-feed-badge-text").textContent = "ALARM ACTIVE - LIVE FEED";
            
            // Update Workstations card info (heart rate removed as requested)
            const wStatus = document.getElementById("workstation-card-status");
            wStatus.textContent = "TRIGGERED";
            wStatus.style.color = "var(--neon-red)";
        } else {
            // Return back to resting empty states
            noAlertsPanel.style.display = "flex";
            activeAlertCard.style.display = "none";
            
            document.getElementById("live-feed-badge-text").textContent = "RESTING - CAMERA OFFLINE";
            
            const wStatus = document.getElementById("workstation-card-status");
            wStatus.textContent = "RESTING";
            wStatus.style.color = "var(--neon-green)";
            
            // If the alert was cleared and we were inside the live-command panel,
            // let's not force boot the user out, but let their live audio player mute cleanly
        }
        
        currentSystemState = data.state;

        // Update Volunteering Dashboard status row inside workstation card
        const volStatus = document.getElementById("device-volunteer-status");
        const volResetBtn = document.getElementById("btn-device-reset");
        if (volStatus && volResetBtn) {
            if (data.state === "triggered") {
                volStatus.textContent = "ALERTED";
                volStatus.style.color = "var(--neon-red)";
                volResetBtn.disabled = false;
            } else {
                volStatus.textContent = "AVAILABLE";
                volStatus.style.color = "var(--neon-green)";
                volResetBtn.disabled = true;
            }
        }

        // Render dynamic list if current view is volunteers
        if (currentView === "volunteers") {
            renderVolunteersList();
        }

        // Store telemetry history
        statusHistory.bpm.push(data.heart_rate > 0 ? data.heart_rate : 72);
        statusHistory.bpm.shift();
        
        statusHistory.micAmp.push(data.mic_amplitude);
        statusHistory.micAmp.shift();
        
        // Populate screenshots gallery
        renderGallery(data.screenshots);
        
    } catch (err) {
        console.error("Error polling system status:", err);
    }
}

// Toggles visual alarm colors on global stats row
function updateSystemStateView(state) {
    const body = document.body;
    const cardState = document.getElementById("card-state");
    
    if (state === "triggered") {
        if (!body.classList.contains("state-triggered")) {
            body.className = "state-triggered";
            cardState.className = "stat-card glass-panel state-triggered-alert";
        }
    } else {
        if (body.classList.contains("state-triggered")) {
            body.className = "state-resting";
            cardState.className = "stat-card glass-panel state-resting";
        }
    }
}

// Renders the chronological face snapshot gallery
function renderGallery(screenshots) {
    const gallery = document.getElementById("screenshots-gallery");
    
    if (!screenshots || screenshots.length === 0) {
        gallery.innerHTML = `
            <div class="no-screenshots">
                <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <polyline points="21 15 16 10 5 21" />
                </svg>
                <span>No captures recorded yet. Faces are captured during active emergency alerts.</span>
            </div>
        `;
        document.getElementById("snapshots-count").textContent = "0 snapshots saved";
        return;
    }
    
    // Check if files are identical to avoid flickering redrawing
    const displayedFiles = Array.from(gallery.querySelectorAll(".gallery-item")).map(el => el.dataset.filename);
    const listsMatch = displayedFiles.length === screenshots.length && 
                       displayedFiles.every((val, index) => val === screenshots[index]);
                       
    if (listsMatch) return;
    
    gallery.innerHTML = "";
    document.getElementById("snapshots-count").textContent = `${screenshots.length} snapshots saved`;
    
    screenshots.forEach(file => {
        const parts = file.split("_");
        let displayTime = "Unknown";
        if (parts.length >= 3) {
            const timePart = parts[2];
            if (timePart.length === 6) {
                displayTime = `${timePart.slice(0, 2)}:${timePart.slice(2, 4)}:${timePart.slice(4, 6)}`;
            }
        }
        
        const card = document.createElement("div");
        card.className = "gallery-item";
        card.dataset.filename = file;
        card.onclick = () => openLightbox(`/static/screenshots/${file}`);
        
        card.innerHTML = `
            <img src="/static/screenshots/${file}" alt="Captured Target Face">
            <div class="gallery-item-overlay">
                <span>Captured</span>
                <strong>${displayTime}</strong>
            </div>
        `;
        
        gallery.appendChild(card);
    });
}

// 5. RESPONDER ACTIONS COMMANDS
async function triggerAlert() {
    try {
        const res = await fetch("/api/trigger", { method: "POST" });
        const data = await res.json();
        console.log("Forced Trigger active:", data.message);
        pollStatus();
        switchView("live-command"); // Automatically open livecommand view on forced trigger!
    } catch (err) {
        console.error("Trigger Failed:", err);
    }
}

async function resetAlert() {
    try {
        const res = await fetch("/api/reset", { method: "POST" });
        const data = await res.json();
        console.log("System Reset completed:", data.message);
        pollStatus();
        switchView("alerts"); // Automatically jump back to Alerts Dashboard empty state
    } catch (err) {
        console.error("Reset Failed:", err);
    }
}

async function deleteHistory() {
    if (!confirm("Are you sure you want to permanently delete all captured face screenshots from the archive?")) {
        return;
    }
    try {
        const res = await fetch("/api/delete_screenshots", { method: "POST" });
        const data = await res.json();
        console.log("History Purged:", data.message);
        pollStatus(); // Instantly update gallery display
    } catch (err) {
        console.error("History Purge failed:", err);
    }
}

// 6. LIVE WAV AUDIO PLAYBACK & WAVEFORM CANVAS VISUALIZER
function toggleAudio() {
    const audio = document.getElementById("live-audio");
    const playSvg = document.getElementById("play-svg-path");
    const pauseSvg = document.getElementById("pause-svg-path");
    const audioBtn = document.getElementById("audio-toggle-btn");
    const audioStatus = document.getElementById("audio-feed-status");
    
    if (!isAudioPlaying) {
        audioStatus.textContent = "Connecting live stream...";
        
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        
        audio.play()
            .then(() => {
                isAudioPlaying = true;
                audioBtn.classList.add("playing");
                playSvg.style.display = "none";
                pauseSvg.style.display = "block";
                audioStatus.textContent = "Live microphone audio stream active";
                
                setupAudioVisualizer(audio);
            })
            .catch(err => {
                console.error("Audio stream playback failed:", err);
                audioStatus.textContent = "Connection failed. Please try again.";
            });
    } else {
        audio.pause();
        isAudioPlaying = false;
        audioBtn.classList.remove("playing");
        playSvg.style.display = "block";
        pauseSvg.style.display = "none";
        audioStatus.textContent = "Audio stream muted";
    }
}

function setupAudioVisualizer(audioElement) {
    if (audioCtx) return;
    
    try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;
        
        audioSource = audioCtx.createMediaElementSource(audioElement);
        audioSource.connect(analyser);
        analyser.connect(audioCtx.destination);
        
        const bufferLength = analyser.frequencyBinCount;
        audioDataArray = new Uint8Array(bufferLength);
        
        animateAudioWaveform();
    } catch (e) {
        console.error("Audio context initialization blocked/failed:", e);
    }
}

function animateAudioWaveform() {
    const canvas = document.getElementById("audio-waveform");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    
    function draw() {
        if (!isAudioPlaying) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }
        
        animationFrameId = requestAnimationFrame(draw);
        
        const width = canvas.width = canvas.clientWidth;
        const height = canvas.height = canvas.clientHeight;
        
        analyser.getByteFrequencyData(audioDataArray);
        
        ctx.clearRect(0, 0, width, height);
        
        const barCount = audioDataArray.length;
        const barWidth = (width / barCount) * 1.5;
        let barHeight;
        let x = 0;
        
        for (let i = 0; i < barCount; i++) {
            barHeight = (audioDataArray[i] / 255) * height * 0.85;
            
            ctx.beginPath();
            let grad = ctx.createLinearGradient(0, height, 0, height - barHeight);
            grad.addColorStop(0, "rgba(0, 229, 255, 0.08)");
            grad.addColorStop(1, "rgba(0, 229, 255, 0.85)");
            
            ctx.fillStyle = grad;
            ctx.fillRect(x, height - barHeight, barWidth - 3, barHeight);
            
            x += barWidth;
        }
    }
    
    draw();
}

// 7. LIGHTBOX CONTROLS
function openLightbox(src) {
    const lightbox = document.getElementById("lightbox");
    const lightboxImg = document.getElementById("lightbox-img");
    lightboxImg.src = src;
    lightbox.classList.add("active");
}

function closeLightbox() {
    const lightbox = document.getElementById("lightbox");
    lightbox.classList.remove("active");
}

// 8. VOLUNTEERING DASHBOARD CONTROLS & RADAR MAP
async function markAlertAsFalse(event) {
    if (event) event.stopPropagation();
    try {
        const res = await fetch("/api/reset", { method: "POST" });
        const data = await res.json();
        console.log("System Reset completed from volunteering dashboard:", data.message);
        pollStatus();
    } catch (err) {
        console.error("Reset Failed:", err);
    }
}

function renderVolunteersList() {
    const listContainer = document.getElementById("volunteers-list-container");
    if (!listContainer) return;
    
    const isTriggered = (currentSystemState === "triggered");
    
    // Clear list
    listContainer.innerHTML = "";
    
    // Add primary node
    const mainNodeDiv = document.createElement("div");
    mainNodeDiv.className = "volunteer-node-item";
    
    const mainNodeInfo = `
        <div class="volunteer-node-info">
            <div class="volunteer-node-name">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" style="color: var(--neon-cyan)">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                    <line x1="8" y1="21" x2="16" y2="21"/>
                    <line x1="12" y1="17" x2="12" y2="21"/>
                </svg>
                HQ-PI-ZERO-01 <span style="font-size:0.75rem; color:var(--text-muted); font-weight:normal;">(This Device)</span>
            </div>
            <div class="volunteer-node-dist">Active Monitoring Node | 0 meters away</div>
        </div>
        <div class="volunteer-node-status">
            ${isTriggered ? `
                <span class="v-badge v-badge-alerted">ALERTED</span>
                <button class="v-node-reset-btn" onclick="markAlertAsFalse(event)">🛡️ Mark Safe</button>
            ` : `
                <span class="v-badge v-badge-available">AVAILABLE</span>
            `}
        </div>
    `;
    mainNodeDiv.innerHTML = mainNodeInfo;
    listContainer.appendChild(mainNodeDiv);
    
    // Add mock nodes
    MOCK_VOLUNTEERS.forEach(vol => {
        const nodeDiv = document.createElement("div");
        nodeDiv.className = "volunteer-node-item";
        
        const nodeInfo = `
            <div class="volunteer-node-info">
                <div class="volunteer-node-name">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" style="color: var(--text-muted)">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                        <circle cx="12" cy="7" r="4"/>
                    </svg>
                    ${vol.name}
                </div>
                <div class="volunteer-node-dist">${vol.model} | ${vol.distance} meters away</div>
            </div>
            <div class="volunteer-node-status">
                ${isTriggered ? `
                    <span class="v-badge v-badge-alerted">ALERTED</span>
                ` : `
                    <span class="v-badge v-badge-available">AVAILABLE</span>
                `}
            </div>
        `;
        nodeDiv.innerHTML = nodeInfo;
        listContainer.appendChild(nodeDiv);
    });
    
    // Update count badge
    const countBadge = document.getElementById("volunteers-active-count");
    if (countBadge) {
        countBadge.textContent = isTriggered ? `${MOCK_VOLUNTEERS.length + 1} Nodes Alerted` : "0 Nodes Alerted";
    }
}

let volunteersMapCanvas = null;
let volunteersMapCtx = null;
let radarAngle = 0;

function startVolunteersMap() {
    volunteersMapCanvas = document.getElementById("canvas-volunteers-map");
    if (!volunteersMapCanvas) return;
    volunteersMapCtx = volunteersMapCanvas.getContext("2d");
    
    function draw() {
        if (!volunteersMapCanvas) return;
        
        // Only consume cycles drawing if we are actively viewing the volunteers tab
        if (currentView !== "volunteers") {
            requestAnimationFrame(draw);
            return;
        }
        
        const canvas = volunteersMapCanvas;
        const ctx = volunteersMapCtx;
        const width = canvas.width = canvas.clientWidth;
        const height = canvas.height = canvas.clientHeight;
        
        ctx.clearRect(0, 0, width, height);
        
        const centerX = width / 2;
        const centerY = height / 2;
        const maxRadius = Math.min(width, height) * 0.45;
        
        // 1. Draw radar sweep grid background
        ctx.strokeStyle = "rgba(0, 229, 255, 0.05)";
        ctx.lineWidth = 1;
        
        // Concentric circles
        for (let r = 1; r <= 4; r++) {
            const radius = (maxRadius / 4) * r;
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
            ctx.stroke();
            
            // Draw range label
            ctx.fillStyle = "rgba(255, 255, 255, 0.25)";
            ctx.font = "9px Inter";
            ctx.fillText(`${r * 100}m`, centerX + radius + 4, centerY + 3);
        }
        
        // Crosshairs
        ctx.beginPath();
        ctx.moveTo(centerX - maxRadius, centerY);
        ctx.lineTo(centerX + maxRadius, centerY);
        ctx.moveTo(centerX, centerY - maxRadius);
        ctx.lineTo(centerX, centerY + maxRadius);
        ctx.stroke();
        
        // 2. Draw radar sweeping beam
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(radarAngle);
        
        let gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, maxRadius);
        gradient.addColorStop(0, "rgba(0, 229, 255, 0.12)");
        gradient.addColorStop(1, "rgba(0, 229, 255, 0)");
        
        // Draw wedge
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.arc(0, 0, maxRadius, -0.25, 0.25);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
        
        // Update angle for sweeping motion
        radarAngle += 0.015;
        if (radarAngle >= Math.PI * 2) radarAngle = 0;
        
        // 3. Draw Nodes (Center node first, then mock nodes)
        const isTriggered = (currentSystemState === "triggered");
        
        // Center node coordinates (0, 0)
        drawNode(ctx, centerX, centerY, "HQ-PI-ZERO-01 (This Node)", isTriggered ? "alerted" : "available", true);
        
        // Mock nodes relative to center
        // Scale coordinate space: map 400m to maxRadius
        const scale = maxRadius / 400;
        
        MOCK_VOLUNTEERS.forEach(vol => {
            const nodeX = centerX + vol.x * scale;
            const nodeY = centerY + vol.y * scale;
            drawNode(ctx, nodeX, nodeY, `${vol.name} (${vol.distance}m)`, isTriggered ? "alerted" : vol.status, false);
        });
        
        requestAnimationFrame(draw);
    }
    
    draw();
}

function drawNode(ctx, x, y, label, status, isCenter) {
    const isAlerted = (status === "alerted");
    const color = isAlerted ? "rgba(255, 51, 102, 1)" : "rgba(0, 230, 118, 1)";
    const colorLight = isAlerted ? "rgba(255, 51, 102, 0.25)" : "rgba(0, 230, 118, 0.15)";
    
    // Draw pulsing ring around node
    const time = Date.now() / 1000;
    const pulseRadius = 5 + (isCenter ? 8 : 4) * (0.5 + 0.5 * Math.sin(time * 6));
    
    ctx.strokeStyle = colorLight;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(x, y, pulseRadius, 0, Math.PI * 2);
    ctx.stroke();
    
    // Draw solid center dot
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, isCenter ? 6 : 4, 0, Math.PI * 2);
    ctx.fill();
    
    // Draw target marker brackets around center node if alerted
    if (isAlerted && isCenter) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        const size = 12;
        
        // Bracket top-left
        ctx.beginPath();
        ctx.moveTo(x - size, y - size + 4);
        ctx.lineTo(x - size, y - size);
        ctx.lineTo(x - size + 4, y - size);
        ctx.stroke();
        
        // Bracket top-right
        ctx.beginPath();
        ctx.moveTo(x + size, y - size + 4);
        ctx.lineTo(x + size, y - size);
        ctx.lineTo(x + size - 4, y - size);
        ctx.stroke();
        
        // Bracket bottom-left
        ctx.beginPath();
        ctx.moveTo(x - size, y + size - 4);
        ctx.lineTo(x - size, y + size);
        ctx.lineTo(x - size + 4, y + size);
        ctx.stroke();
        
        // Bracket bottom-right
        ctx.beginPath();
        ctx.moveTo(x + size, y + size - 4);
        ctx.lineTo(x + size, y + size);
        ctx.lineTo(x + size - 4, y + size);
        ctx.stroke();
    }
    
    // Draw label text
    ctx.fillStyle = "#fff";
    ctx.font = isCenter ? "bold 10px Inter" : "10px Inter";
    ctx.textAlign = "center";
    ctx.shadowColor = "rgba(0, 0, 0, 0.8)";
    ctx.shadowBlur = 4;
    ctx.fillText(label, x, y - (isCenter ? 14 : 10));
    ctx.shadowBlur = 0; // Reset shadow
}
