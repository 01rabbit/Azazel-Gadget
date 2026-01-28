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
    // Header
    updateElement('headerSSID', state.header?.ssid || '-');
    updateElement('headerClock', state.header?.clock || '--:--:--');
    updateElement('headerTemp', `${state.header?.temp_c || '--'}°C`);
    updateElement('headerCPU', `${state.header?.cpu_pct || '--'}%`);
    
    // Risk
    const risk = state.risk || {};
    updateElement('riskScore', risk.score || 0);
    updateElement('riskStatusValue', risk.status || 'SAFE');
    updateElement('riskThreatLevel', risk.threat_level || 'LOW');
    updateElement('riskRecommendation', risk.recommendation || '-');
    updateElement('riskReason', risk.reason || '-');
    
    // Update risk score color
    const scoreEl = document.getElementById('riskScore');
    const statusEl = document.getElementById('riskStatus');
    const cardEl = document.getElementById('cardRisk');
    const status = (risk.status || 'SAFE').toLowerCase();
    
    scoreEl.className = `score-value ${status}`;
    statusEl.className = `risk-status ${status}`;
    statusEl.textContent = risk.status || 'SAFE';
    cardEl.className = `card card-risk ${status}`;
    
    // Connection
    const conn = state.connection || {};
    updateElement('connBSSID', conn.bssid || '-');
    updateElement('connChannel', conn.channel || '-');
    updateElement('connSignal', `${conn.signal_dbm || '-'} dBm`);
    updateElement('connGateway', conn.gateway_ip || '-');
    updateElement('connCongestion', conn.congestion || '-');
    updateElement('connAPCount', conn.ap_count || '-');
    
    // Control
    const ctrl = state.control || {};
    updateBadge('ctrlQUIC', ctrl.quic_443 || 'ALLOWED');
    updateBadge('ctrlDoH', ctrl.doh_443 || 'BLOCKED');
    updateBadge('ctrlDegrade', ctrl.degrade || 'OFF');
    updateElement('ctrlDownMbps', `${ctrl.traffic_down_mbps || '-'} Mbps`);
    updateElement('ctrlUpMbps', `${ctrl.traffic_up_mbps || '-'} Mbps`);
    updateElement('ctrlProbe', ctrl.probe || '-');
    updateElement('ctrlDNS', ctrl.stats_dns || '-');
    updateElement('ctrlIDS', ctrl.ids || '-');
    
    // Evidence
    const evid = state.evidence || {};
    updateBadge('evidState', evid.state || 'NORMAL');
    updateElement('evidSuspicion', evid.suspicion || 0);
    updateElement('evidWindow', `${evid.window_sec || '-'} sec`);
    updateElement('evidScan', evid.scan || '-');
    updateElement('evidDecision', evid.decision || '-');
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
