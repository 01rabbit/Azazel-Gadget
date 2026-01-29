// Azazel-Gadget Web UI Frontend
// Polls /api/state every 2 seconds

const AUTH_TOKEN = localStorage.getItem('azazel_token') || 'azazel-default-token-change-me';
let updateInterval;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchState();
    updateInterval = setInterval(fetchState, 2000); // Poll every 2 seconds
});

// Fetch state from API
async function fetchState() {
    try {
        const res = await fetch('/api/state');
        const data = await res.json();
        
        if (!data.ok) {
            showToast(`Error: ${data.error}`, 'error');
            displayErrorState();
            return;
        }
        
        updateUI(data);
    } catch (e) {
        console.error('Failed to fetch state:', e);
        showToast('Connection error', 'error');
    }
}

// Update UI with state data
function updateUI(state) {
    // System metrics (from new API format)
    const system = state.system || {};
    const wifiInfo = system.wifi || {};
    const cpuInfo = system.cpu || {};
    const memInfo = system.memory || {};
    
    // Header
    updateElement('headerSSID', wifiInfo.ssid || '-');
    updateElement('headerClock', getCurrentTime());
    updateElement('headerTemp', `${cpuInfo.temp_c || '--'}°C`);
    updateElement('headerCPU', `${cpuInfo.usage_percent || '--'}%`);
    
    // Risk Assessment (from state machine)
    const suspicion = state.suspicion || 0;
    const stateVal = (state.state || 'INIT').toUpperCase();
    
    updateElement('riskScore', suspicion);
    updateElement('riskStatusValue', stateVal);
    updateElement('riskReason', state.reason || '-');
    
    // Threat level based on suspicion
    let threatLevel = 'LOW';
    if (suspicion >= 50) threatLevel = 'CRITICAL';
    else if (suspicion >= 30) threatLevel = 'HIGH';
    else if (suspicion >= 15) threatLevel = 'MEDIUM';
    updateElement('riskThreatLevel', threatLevel);
    
    // Update risk score color
    const scoreEl = document.getElementById('riskScore');
    const statusEl = document.getElementById('riskStatus');
    const cardEl = document.getElementById('cardRisk');
    const statusClass = getStatusClass(stateVal);
    
    scoreEl.className = `score-value ${statusClass}`;
    statusEl.className = `risk-status ${statusClass}`;
    statusEl.textContent = stateVal;
    cardEl.className = `card card-risk ${statusClass}`;
    
    // Connection Info (WiFi)
    updateElement('connBSSID', wifiInfo.ssid ? wifiInfo.ssid : 'Not connected');
    updateElement('connGateway', wifiInfo.ip || '-');
    
    // Control & Safety
    updateBadge('ctrlDegrade', stateVal === 'DEGRADED' ? 'ON' : 'OFF');
    
    // Evidence
    updateBadge('evidState', stateVal);
    updateElement('evidSuspicion', suspicion);
    
    // System Health
    if (!document.getElementById('sysHealth')) {
        addSystemHealthCard(system);
    } else {
        updateElement('sysCPUTemp', `${cpuInfo.temp_c || '--'}°C`);
        updateElement('sysCPUUsage', `${cpuInfo.usage_percent || '--'}%`);
        updateElement('sysMemUsage', `${memInfo.usage_percent || '--'}%`);
    }
}

// Get current time string
function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString('en-US', { 
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// Get CSS class for status
function getStatusClass(status) {
    const lower = (status || '').toLowerCase();
    if (lower === 'normal') return 'normal';
    if (lower === 'probe') return 'degraded';
    if (lower === 'degraded') return 'degraded';
    if (lower === 'contain') return 'contained';
    if (lower === 'deception') return 'lockdown';
    return 'normal';
}

// Add system health card if not exists
function addSystemHealthCard(system) {
    const evidCard = document.querySelector('.card-evidence');
    if (!evidCard) return;
    
    const cpuInfo = system.cpu || {};
    const memInfo = system.memory || {};
    
    const html = `
        <div class="metric" id="sysHealth">
            <span class="metric-label">CPU Temp</span>
            <span class="metric-value" id="sysCPUTemp">${cpuInfo.temp_c || '--'}°C</span>
        </div>
        <div class="metric">
            <span class="metric-label">CPU Usage</span>
            <span class="metric-value" id="sysCPUUsage">${cpuInfo.usage_percent || '--'}%</span>
        </div>
        <div class="metric">
            <span class="metric-label">Memory Usage</span>
            <span class="metric-value" id="sysMemUsage">${memInfo.usage_percent || '--'}%</span>
        </div>
    `;
    
    // Insert after state metric
    const stateMetric = evidCard.querySelector('.evidence-grid');
    if (stateMetric) {
        stateMetric.insertAdjacentHTML('beforeend', html);
    }
}

// Helper: Update element text
function updateElement(id, text) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
    }
}

// Helper: Update badge with color
function updateBadge(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    
    el.textContent = value;
    
    // Remove all possible classes
    el.classList.remove('allowed', 'blocked', 'on', 'off', 'normal', 'degraded', 'contained', 'lockdown');
    
    // Add appropriate class
    const valueLower = value.toLowerCase();
    if (valueLower === 'allowed') {
        el.classList.add('allowed');
    } else if (valueLower === 'blocked') {
        el.classList.add('blocked');
    } else if (valueLower === 'on') {
        el.classList.add('on');
    } else if (valueLower === 'off') {
        el.classList.add('off');
    } else if (valueLower === 'normal') {
        el.classList.add('normal');
    } else if (valueLower === 'degraded') {
        el.classList.add('degraded');
    } else if (valueLower === 'contained') {
        el.classList.add('contained');
    } else if (valueLower === 'lockdown') {
        el.classList.add('lockdown');
    }
}

// Display error state when API unavailable
function displayErrorState() {
    updateElement('riskScore', '?');
    updateElement('riskStatusValue', 'ERROR');
    updateElement('headerClock', '--:--:--');
}

// Execute action via API
async function executeAction(action) {
    try {
        const res = await fetch(`/api/action/${action}`, {
            method: 'POST',
            headers: {
                'X-AZAZEL-TOKEN': AUTH_TOKEN,
                'Content-Type': 'application/json'
            }
        });
        
        const data = await res.json();
        
        if (data.ok) {
            showToast(`✅ ${action} executed successfully`, 'success');
            // Immediately refresh state
            setTimeout(fetchState, 500);
        } else {
            showToast(`❌ ${action} failed: ${data.error}`, 'error');
        }
    } catch (e) {
        console.error(`Action ${action} failed:`, e);
        showToast(`❌ ${action} failed: ${e.message}`, 'error');
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast show ${type}`;
    
    setTimeout(() => {
        toast.className = 'toast';
    }, 3000);
}

// Show more menu (mobile)
function showMoreMenu() {
    const menu = document.getElementById('moreMenu');
    menu.style.display = 'flex';
}

// Hide more menu
function hideMoreMenu() {
    const menu = document.getElementById('moreMenu');
    menu.style.display = 'none';
}

// Close more menu when clicking outside
document.addEventListener('click', (e) => {
    const menu = document.getElementById('moreMenu');
    const moreBtn = document.querySelector('.mobile-more');
    
    if (menu && moreBtn && 
        !menu.contains(e.target) && 
        !moreBtn.contains(e.target)) {
        hideMoreMenu();
    }
});
