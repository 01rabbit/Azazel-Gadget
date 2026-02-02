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
    updateElement('headerClock', state.now_time || '--:--:--');
    
    // Risk Assessment (based on internal state)
    const internal = state.internal || {};
    const suspicion = internal.suspicion || 0;
    const stateVal = (internal.state_name || 'NORMAL').toUpperCase();
    
    // Update score circle
    const scoreCircle = document.getElementById('scoreCircle');
    scoreCircle.textContent = suspicion;
    
    const statusEl = document.getElementById('riskStatus');
    const cardEl = document.getElementById('cardRisk');
    const statusClass = getStatusClass(stateVal);
    
    scoreCircle.className = `score-circle ${statusClass}`;
    statusEl.className = `risk-status ${statusClass}`;
    statusEl.textContent = mapState(stateVal);
    cardEl.className = `card card-risk ${statusClass}`;
    
    // Threat level based on suspicion
    let threatLevel = 'LOW';
    if (suspicion >= 50) threatLevel = 'CRITICAL';
    else if (suspicion >= 30) threatLevel = 'HIGH';
    else if (suspicion >= 15) threatLevel = 'MEDIUM';
    updateElement('riskThreatLevel', threatLevel);
    
    updateElement('riskRecommendation', state.recommendation || '-');
    updateElement('riskReason', (state.reasons || [])[0] || '-');
    
    // Connection Info
    updateElement('connSSID', state.ssid || '-');
    updateElement('connBSSID', state.bssid || '-');
    updateElement('connGateway', state.gateway_ip || '-');
    updateElement('connSignal', `${state.signal_dbm || '-'} dBm`);
    
    // Wi-Fi Connection State
    const connection = state.connection || {};
    updateBadge('wifiState', connection.wifi_state || 'DISCONNECTED');
    updateBadge('usbNat', connection.usb_nat || 'OFF');
    updateBadge('internetCheck', connection.internet_check || 'UNKNOWN');
    
    // Captive Portal Warning
    const captivePortal = connection.captive_portal || 'NO';
    const captiveWarning = document.getElementById('captivePortalWarning');
    if (captivePortal === 'SUSPECTED' || captivePortal === 'YES') {
        captiveWarning.style.display = 'block';
    } else {
        captiveWarning.style.display = 'none';
    }
    
    // Control & Safety
    const degrade = state.degrade || {};
    updateBadge('ctrlDegrade', degrade.on ? 'ON' : 'OFF');
    updateBadge('ctrlQUIC', state.quic || 'ALLOWED');
    updateBadge('ctrlDoH', state.doh || 'BLOCKED');
    const downMbps = degrade.rate_mbps || 0;
    const upMbps = degrade.rate_mbps || 0;
    updateElement('ctrlSpeed', `${downMbps} / ${upMbps}`);
    
    // Security - Probe results
    const probe = state.probe || {};
    const probeStatus = probe.tls_total > 0 
        ? `${probe.tls_ok}/${probe.tls_total} ✓` + (probe.blocked > 0 ? ` (${probe.blocked} blocked)` : '')
        : '-';
    updateElement('ctrlProbe', probeStatus);
    
    // Security - IDS (Suricata alerts)
    const suricataCritical = state.suricata_critical || 0;
    const suricataWarning = state.suricata_warning || 0;
    let idsStatus = '-';
    if (suricataCritical > 0 || suricataWarning > 0) {
        const parts = [];
        if (suricataCritical > 0) parts.push(`${suricataCritical} critical`);
        if (suricataWarning > 0) parts.push(`${suricataWarning} warning`);
        idsStatus = parts.join(', ');
    }
    updateElement('ctrlIDS', idsStatus);
    
    // Evidence
    updateBadge('evidState', mapState(stateVal));
    updateElement('evidSuspicion', suspicion);
    
    // Scan Results - Channel congestion and AP count
    const channelCongestion = state.channel_congestion || 'unknown';
    const apCount = state.channel_ap_count || 0;
    const scanStatus = apCount > 0 
        ? `${apCount} APs (${channelCongestion})` 
        : '-';
    updateElement('evidScan', scanStatus);
    
    // Decision - State + Suspicion
    const decisionText = `State: ${mapState(stateVal)}, Suspicion: ${suspicion}`;
    updateElement('evidDecision', decisionText);
    
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
    const scoreCircle = document.getElementById('scoreCircle');
    if (scoreCircle) scoreCircle.textContent = '?';
    
    const statusEl = document.getElementById('riskStatus');
    if (statusEl) statusEl.textContent = 'ERROR';
    
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

// ========== Wi-Fi Control Functions ==========

let selectedSSID = '';
let selectedSecurity = 'UNKNOWN';

// Scan Wi-Fi networks
async function scanWiFi() {
    try {
        showToast('🔍 Scanning Wi-Fi networks...', 'info');
        
        const res = await fetch('/api/wifi/scan', {
            method: 'GET'
        });
        
        const data = await res.json();
        
        if (data.ok && data.aps) {
            displayWiFiResults(data.aps);
            showToast(`✅ Found ${data.aps.length} networks`, 'success');
        } else {
            showToast(`❌ Scan failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (e) {
        console.error('Wi-Fi scan failed:', e);
        showToast(`❌ Scan failed: ${e.message}`, 'error');
    }
}

// Display Wi-Fi scan results
function displayWiFiResults(aps) {
    const resultsDiv = document.getElementById('wifiScanResults');
    const apList = document.getElementById('wifiAPList');
    
    // Clear existing results
    apList.innerHTML = '';
    
    // Populate AP list
    aps.forEach(ap => {
        const row = document.createElement('tr');
        row.style.borderBottom = '1px solid #333';
        row.style.cursor = 'pointer';
        
        const ssidCell = document.createElement('td');
        ssidCell.textContent = ap.ssid;
        if (ap.saved) {
            ssidCell.textContent += ' ★';
            ssidCell.style.color = '#4CAF50';
        }
        
        const signalCell = document.createElement('td');
        signalCell.textContent = `${ap.signal_dbm} dBm`;
        signalCell.style.textAlign = 'center';
        
        // Color code signal strength
        if (ap.signal_dbm >= -50) {
            signalCell.style.color = '#4CAF50';
        } else if (ap.signal_dbm >= -70) {
            signalCell.style.color = '#FFC107';
        } else {
            signalCell.style.color = '#F44336';
        }
        
        const securityCell = document.createElement('td');
        securityCell.textContent = ap.security;
        securityCell.style.textAlign = 'center';
        
        if (ap.security === 'OPEN') {
            securityCell.style.color = '#ff6b35';
        }
        
        const actionCell = document.createElement('td');
        actionCell.style.textAlign = 'center';
        
        const selectBtn = document.createElement('button');
        selectBtn.textContent = 'Select';
        selectBtn.className = 'btn-small';
        selectBtn.onclick = () => selectAP(ap.ssid, ap.security);
        
        actionCell.appendChild(selectBtn);
        
        row.appendChild(ssidCell);
        row.appendChild(signalCell);
        row.appendChild(securityCell);
        row.appendChild(actionCell);
        
        apList.appendChild(row);
    });
    
    // Show results section
    resultsDiv.style.display = 'block';
}

// Select AP from list
function selectAP(ssid, security) {
    selectedSSID = ssid;
    selectedSecurity = security;
    
    // Populate manual SSID field
    document.getElementById('manualSSID').value = ssid;
    
    // Show/hide passphrase section based on security
    const passphraseSection = document.getElementById('passphraseSection');
    if (security === 'OPEN') {
        passphraseSection.style.display = 'none';
        document.getElementById('wifiPassphrase').value = '';
    } else {
        passphraseSection.style.display = 'block';
    }
    
    showToast(`✅ Selected: ${ssid} (${security})`, 'info');
}

// Connect to Wi-Fi
async function connectWiFi() {
    const manualSSID = document.getElementById('manualSSID').value.trim();
    const passphrase = document.getElementById('wifiPassphrase').value;
    
    // Use manual SSID if provided, else selected SSID
    const ssid = manualSSID || selectedSSID;
    
    if (!ssid) {
        showToast('❌ Please select or enter an SSID', 'error');
        return;
    }
    
    // Determine security if manually entered
    let security = selectedSecurity;
    if (manualSSID && manualSSID !== selectedSSID) {
        security = passphrase ? 'WPA2' : 'OPEN';
    }
    
    // Validate passphrase for protected networks
    if (security !== 'OPEN' && !passphrase) {
        showToast('❌ Passphrase required for protected network', 'error');
        return;
    }
    
    try {
        showToast(`🔗 Connecting to ${ssid}...`, 'info');
        
        const body = {
            ssid: ssid,
            security: security,
            persist: true
        };
        
        // Add passphrase only for protected networks
        if (security !== 'OPEN' && passphrase) {
            body.passphrase = passphrase;
        }
        
        const res = await fetch('/api/wifi/connect', {
            method: 'POST',
            headers: {
                'X-AZAZEL-TOKEN': AUTH_TOKEN,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });
        
        const data = await res.json();
        
        if (data.ok) {
            showToast(`✅ Connected to ${ssid}!`, 'success');
            
            // Clear passphrase field
            document.getElementById('wifiPassphrase').value = '';
            
            // Refresh state immediately
            setTimeout(fetchState, 1000);
        } else {
            showToast(`❌ Connection failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (e) {
        console.error('Wi-Fi connect failed:', e);
        showToast(`❌ Connection failed: ${e.message}`, 'error');
    }
}
