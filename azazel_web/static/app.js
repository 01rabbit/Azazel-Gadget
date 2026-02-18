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
        const res = await fetch('/api/state', {
            headers: {
                'X-Auth-Token': AUTH_TOKEN
            }
        });
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

    // Toggle Contain/Release buttons based on state
    const containBtn = document.getElementById('containBtn');
    const releaseBtn = document.getElementById('releaseBtn');
    if (containBtn && releaseBtn) {
        if (stateVal === 'CONTAIN') {
            containBtn.style.display = 'none';
            releaseBtn.style.display = 'inline-flex';
        } else {
            containBtn.style.display = 'inline-flex';
            releaseBtn.style.display = 'none';
        }
    }
    
    // Threat level based on suspicion
    let threatLevel = 'LOW';
    if (suspicion >= 50) threatLevel = 'CRITICAL';
    else if (suspicion >= 30) threatLevel = 'HIGH';
    else if (suspicion >= 15) threatLevel = 'MEDIUM';
    updateElement('riskThreatLevel', threatLevel);
    
    updateElement('riskRecommendation', state.recommendation || '-');
    updateElement('riskReason', (state.reasons || [])[0] || '-');

    // Monitoring status
    const monitoring = state.monitoring || {};
    updateBadge('riskSuricata', monitoring.suricata || 'UNKNOWN');
    updateBadge('riskOpenCanary', monitoring.opencanary || 'UNKNOWN');
    updateBadge('riskNtfy', monitoring.ntfy || 'UNKNOWN');
    
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

    const portalViewer = state.portal_viewer || {};
    const portalViewerRow = document.getElementById('portalViewerRow');
    const portalViewerBtn = document.getElementById('portalViewerBtn');
    const shouldShowPortalButton = (
        (captivePortal === 'SUSPECTED' || captivePortal === 'YES') &&
        portalViewer.active &&
        portalViewer.url
    );
    if (portalViewerRow && portalViewerBtn) {
        if (shouldShowPortalButton) {
            portalViewerRow.style.display = 'flex';
            portalViewerBtn.dataset.url = portalViewer.url;
        } else {
            portalViewerRow.style.display = 'none';
            delete portalViewerBtn.dataset.url;
        }
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

function openPortalViewer() {
    const btn = document.getElementById('portalViewerBtn');
    if (!btn || !btn.dataset.url) {
        showToast('Portal viewer is not ready', 'error');
        return;
    }
    window.open(btn.dataset.url, '_blank', 'noopener,noreferrer');
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
        if (action === 'release') {
            showToast('⏳ Releasing...', 'info');
        }

        const data = await postAction(action);
        
        if (data.ok) {
            // Special handling for details action
            if (action === 'details') {
                showDetailsModal(data);
                return;
            }
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

// POST /api/action/<action>
async function postAction(action) {
    const res = await fetch(`/api/action/${action}`, {
        method: 'POST',
        headers: {
            'X-Auth-Token': AUTH_TOKEN,
            'Content-Type': 'application/json'
        }
    });
    
    return res.json();
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

// Show Details Modal
function showDetailsModal(data) {
    const modal = document.getElementById('detailsModal');
    const body = document.getElementById('detailsBody');
    
    let html = '<div class="details-section">';
    
    // Current State
    html += '<h4>Current State</h4>';
    html += `<p><strong>Stage:</strong> ${data.state || 'UNKNOWN'}</p>`;
    html += `<p><strong>Suspicion Score:</strong> ${data.suspicion || 0}</p>`;
    html += `<p><strong>Reason:</strong> ${data.reason || '-'}</p>`;
    
    // Probe Details
    if (data.details) {
        html += '<h4>Probe Results</h4>';
        
        // TLS checks
        if (data.details.tls && Array.isArray(data.details.tls)) {
            html += '<p><strong>TLS Verification:</strong></p><ul>';
            data.details.tls.forEach(item => {
                const status = item.ok ? '✅' : '❌';
                html += `<li>${status} ${item.site || 'Unknown'}</li>`;
            });
            html += '</ul>';
        }
        
        // DNS checks
        if (data.details.dns !== undefined) {
            const dnsStatus = data.details.dns ? '❌ Mismatch detected' : '✅ OK';
            html += `<p><strong>DNS:</strong> ${dnsStatus}</p>`;
        }
        
        // Captive Portal
        if (data.details.captive_portal !== undefined) {
            const cpStatus = data.details.captive_portal ? '⚠️ Detected' : '✅ None';
            html += `<p><strong>Captive Portal:</strong> ${cpStatus}</p>`;
        }
        
        // Route Anomaly
        if (data.details.route_anomaly !== undefined) {
            const routeStatus = data.details.route_anomaly ? '⚠️ Anomaly detected' : '✅ OK';
            html += `<p><strong>Route:</strong> ${routeStatus}</p>`;
        }
    } else {
        html += '<p>No probe details available</p>';
    }
    
    html += '</div>';
    
    body.innerHTML = html;
    modal.style.display = 'flex';
}

// Close Details Modal
function closeDetailsModal() {
    const modal = document.getElementById('detailsModal');
    modal.style.display = 'none';
}

// ========== Wi-Fi Control Functions ==========

let selectedSSID = '';
let selectedSecurity = 'UNKNOWN';
let selectedSaved = false;

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
        selectBtn.onclick = () => selectAP(ap.ssid, ap.security, ap.saved);
        
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
function selectAP(ssid, security, saved) {
    selectedSSID = ssid;
    selectedSecurity = security;
    selectedSaved = !!saved;
    
    // Populate manual SSID field
    document.getElementById('manualSSID').value = ssid;
    
    // Show/hide passphrase section based on security
    const passphraseSection = document.getElementById('passphraseSection');
    if (security === 'OPEN' || selectedSaved) {
        passphraseSection.style.display = 'none';
        document.getElementById('wifiPassphrase').value = '';
    } else {
        passphraseSection.style.display = 'block';
    }
    
    const savedLabel = selectedSaved ? ' (saved)' : '';
    showToast(`✅ Selected: ${ssid} (${security})${savedLabel}`, 'info');
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

    const isSavedSelection = !!(selectedSaved && ssid === selectedSSID);
    
    // Validate passphrase for protected networks
    if (security !== 'OPEN' && !passphrase && !isSavedSelection) {
        showToast('❌ Passphrase required for protected network', 'error');
        return;
    }
    
    try {
        showToast(`🔗 Connecting to ${ssid}...`, 'info');
        
        const body = {
            ssid: ssid,
            security: security,
            persist: true,
            saved: isSavedSelection
        };
        
        // Add passphrase only for protected networks
        if (security !== 'OPEN' && passphrase) {
            body.passphrase = passphrase;
        }
        
        const res = await fetch('/api/wifi/connect', {
            method: 'POST',
            headers: {
                'X-Auth-Token': AUTH_TOKEN,
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
