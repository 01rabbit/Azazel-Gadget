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
    // Map ui_snapshot.json fields to UI elements
    
    // Header
    updateElement('headerSSID', state.ssid || '-');
    updateElement('headerClock', state.now_time || '--:--:--');
    updateElement('headerTemp', `${state.temp_c || '--'}°C`);
    updateElement('headerCPU', `${state.cpu_percent || '--'}%`);
    
    // Risk Assessment (based on internal state)
    const internal = state.internal || {};
    const suspicion = internal.suspicion || 0;
    const stateVal = (internal.state_name || 'NORMAL').toUpperCase();
    
    updateElement('riskScore', suspicion);
    updateElement('riskStatusValue', mapState(stateVal));
    updateElement('riskReason', (state.reasons || [])[0] || state.recommendation || '-');
    
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
    statusEl.textContent = mapState(stateVal);
    cardEl.className = `card card-risk ${statusClass}`;
    
    // Connection Info
    updateElement('connBSSID', state.ssid || '-');
    updateElement('connGateway', state.gateway_ip || '-');
    updateElement('connChannel', state.channel || '-');
    updateElement('connSignal', `${state.signal_dbm || '-'} dBm`);
    
    // Control & Safety
    const degrade = state.degrade || {};
    updateBadge('ctrlDegrade', degrade.on ? 'ON' : 'OFF');
    updateBadge('ctrlQUIC', state.quic || 'ALLOWED');
    updateBadge('ctrlDoH', state.doh || 'BLOCKED');
    updateElement('ctrlDownMbps', `${degrade.rate_mbps || 0} Mbps`);
    updateElement('ctrlUpMbps', `-`);
    
    // Evidence
    updateBadge('evidState', mapState(stateVal));
    updateElement('evidSuspicion', suspicion);
    
    // System Health Card
    updateElement('sysCPUTemp', `${state.temp_c || '--'}°C`);
    updateElement('sysCPUUsage', `${state.cpu_percent || '--'}%`);
    updateElement('sysMemUsage', `${state.mem_percent || '--'}%`);
}

// Map state names between different systems
function mapState(state) {
    const map = {
        'NORMAL': 'SAFE',
        'PROBE': 'CHECKING',
        'DEGRADED': 'LIMITED',
        'CONTAIN': 'CONTAINED',
        'DECEPTION': 'DECEPTION',
        'INIT': 'CHECKING'
    };
    return map[state] || state;
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
