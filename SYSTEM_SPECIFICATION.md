# Azazel-Zero System Specification

**Version**: 2.0 (feature/web-ui branch)  
**Date**: 2026-01-29  
**Purpose**: Complete technical specification for AI-assisted development

---

## 1. System Overview

### 1.1 Architecture Type
- **Pattern**: State Machine-Driven Security Gateway
- **Platform**: Raspberry Pi Zero 2 W (ARMv8, 512MB RAM)
- **OS**: Raspberry Pi OS Lite 64-bit
- **Network Mode**: USB Gadget (g_ether) + Wi-Fi AP connection
- **Primary Language**: Python 3.9+
- **Secondary Tools**: bash, nftables, tc (traffic control), dnsmasq

### 1.2 Core Concept
5-stage finite state machine (INIT → PROBE → DEGRADED → NORMAL → CONTAIN) that dynamically applies firewall rules and traffic shaping based on threat signals from multiple sensors (Wi-Fi safety, DNS observer, TLS probes, Suricata IDS).

### 1.3 Network Topology
```
[Upstream Wi-Fi AP] ←--wlan0--→ [Raspberry Pi Zero 2 W] ←--usb0 (gadget)--→ [Client Device]
                                         ↓
                                   nftables + tc
                                         ↓
                              Stage-based filtering
```

**Interfaces:**
- `wlan0`: Upstream (connects to external Wi-Fi AP)
- `usb0`: Downstream (USB gadget mode, virtual Ethernet to client)
- Management IP: `10.55.0.10/24` on usb0
- Client receives DHCP (e.g., `10.55.0.114/24`)

---

## 2. Directory Structure

```
~/Azazel-Zero/
├── azazel_web/                      # Flask Web UI
│   ├── app.py                       # Flask application (port 8084)
│   ├── templates/
│   │   └── index.html               # Responsive dashboard
│   └── static/
│       ├── app.js                   # Frontend polling logic (2s interval)
│       └── style.css                # Dark theme, responsive design
│
├── py/
│   ├── azazel-first-minute.py       # Main entry point (controller lifecycle)
│   ├── azazel_zero/
│   │   ├── first_minute/
│   │   │   ├── config.py            # YAML config loader
│   │   │   ├── controller.py        # Main control loop (2s cycle)
│   │   │   ├── state_machine.py     # FSM logic (5 stages)
│   │   │   ├── nft.py               # nftables template renderer
│   │   │   ├── tc.py                # Traffic shaping (HTB qdisc)
│   │   │   ├── probes.py            # TLS/DNS/captive portal tests
│   │   │   ├── dns_observer.py      # dnsmasq log watcher
│   │   │   └── web_api.py           # HTTP API (port 8082, deprecated for Web UI)
│   │   ├── sensors/
│   │   │   ├── wifi_safety.py       # Evil AP/MITM/DNS spoofing detection
│   │   │   └── network_analysis.py  # Routing anomaly detection
│   │   ├── app/
│   │   │   └── threat_judge.py      # (Future) ML/LLM threat assessment
│   │   └── core/
│   │       └── mock_llm_core.py     # Mock LLM backend for testing
│   │
│   └── azazel_control/
│       ├── daemon.py                # Unix socket listener (/run/azazel/control.sock)
│       └── scripts/
│           ├── refresh.sh           # Action: force state refresh
│           ├── reprobe.sh           # Action: re-run probes
│           ├── contain.sh           # Action: enter CONTAIN stage
│           ├── stage_open.sh        # Action: move to NORMAL
│           ├── disconnect.sh        # Action: disconnect from AP
│           └── details.sh           # Action: dump detailed state
│
├── systemd/
│   ├── azazel-first-minute.service  # Core controller service
│   ├── azazel-control-daemon.service # Action executor service
│   ├── azazel-epd*.service          # E-Paper display services
│   ├── opencanary.service           # Honeypot integration
│   └── suri-epaper.service          # Suricata display service
│
├── nftables/
│   └── first_minute.nft             # Firewall template (Jinja2-like)
│
├── configs/
│   ├── first_minute.yaml            # Runtime configuration
│   ├── dnsmasq-first_minute.conf    # DNS proxy config
│   └── known_wifi.json              # Trusted Wi-Fi AP database
│
├── bin/
│   ├── install_webui.sh             # Web UI installer (standalone)
│   ├── install_dependencies.sh      # System packages
│   ├── install_systemd.sh           # Service installation
│   └── install_waveshare_epd.sh     # E-Paper library
│
├── tools/
│   └── bootstrap_zero.sh            # Full system installer (--with-webui)
│
├── docs/
│   ├── WEB_UI.md                    # Web UI documentation
│   ├── WEB_UI_INSTALL.md            # Installation guide
│   ├── setup-zero.md                # Hardware setup
│   └── Boot_E-Paper_Splash_ja.md    # E-Paper documentation
│
└── tests/
    └── test_redesign_verification.py # FSM unit tests
```

---

## 3. State Machine (FSM)

### 3.1 States (Stages)
Located in: `py/azazel_zero/first_minute/state_machine.py`

| Stage      | Suspicion Range | Traffic Control        | Description                          |
|------------|-----------------|------------------------|--------------------------------------|
| INIT       | 0               | None                   | Boot, initial scan                   |
| PROBE      | 8-19            | None (investigating)   | Minor anomaly, running verification |
| DEGRADED   | 20-49           | +180ms RTT, 2 Mbps cap | Moderate threat, bandwidth limited   |
| NORMAL     | 0-7             | None                   | Clean state, full speed              |
| CONTAIN    | 50+             | Block most egress      | High-confidence attack, quarantine   |
| DECEPTION  | Special trigger | Honeypot redirect      | (Rare) Active decoy mode             |

### 3.2 Suspicion Score
- **Range**: 0-100 (float)
- **Increments**: Signal-based (WiFi: +10, DNS mismatch: +5, Suricata: +15, etc.)
- **Decay**: -3 per second (passive, configurable)
- **Cooldowns**: Suricata alerts have 30s deduplication window

### 3.3 Transition Logic
```python
# Key thresholds (from configs/first_minute.yaml)
degrade_threshold: 20   # PROBE/NORMAL → DEGRADED
normal_threshold: 8     # PROBE → NORMAL, DEGRADED → NORMAL
contain_threshold: 50   # Any state → CONTAIN

# Special rules:
# - CONTAIN has minimum 20s duration
# - CONTAIN recovery requires suspicion < 30
# - Decay applies every controller loop (2s)
```

### 3.4 Signal Sources
Defined in `state_machine.py::_apply_signals()`:

```python
signal_weights = {
    'wifi_tags': +10,          # Evil AP, MITM, DNS/DHCP spoofing
    'probe_fail': +8,          # TLS/DNS/captive portal test failure
    'dns_mismatch': +5,        # DNS query mismatch
    'suricata_alert': +15,     # IDS alert (with cooldown)
    'cert_mismatch': +12,      # Certificate validation failure
    'route_anomaly': +7,       # Gateway/routing change
}
```

---

## 4. Core Components

### 4.1 Controller (`py/azazel_zero/first_minute/controller.py`)

**Main Loop (run_loop method):**
```python
while True:
    # 1. Gather signals
    signals = {
        'wifi_tags': wifi_safety.get_tags(),
        'probe_fail': probes.check(),
        'dns_mismatch': dns_observer.count_mismatches(),
        'suricata_alert': suricata.poll(),
        # ...
    }
    
    # 2. Step state machine
    new_stage, context = state_machine.step(signals)
    
    # 3. Apply firewall/tc rules
    if stage_changed:
        nft_manager.set_stage(new_stage)
        tc_manager.apply(new_stage)
    
    # 4. Update shared state
    write_ui_snapshot({
        'ssid': get_ssid(),
        'temp_c': get_cpu_temp(),
        'cpu_percent': get_cpu_usage(),
        'mem_percent': get_memory_usage(),
        'internal': {
            'state_name': new_stage.name,
            'suspicion': context['suspicion'],
            # ...
        }
    })
    
    # 5. Sleep 2s
    time.sleep(2)
```

**System Metrics Collection:**
```python
def _get_cpu_temp(self) -> float:
    # Read /sys/class/thermal/thermal_zone0/temp
    return temp_c

def _get_cpu_usage(self) -> float:
    # Run 'top -bn1' and parse CPU%
    return cpu_percent

def _get_memory_usage(self) -> float:
    # Run 'free' and parse Mem%
    return mem_percent
```

### 4.2 Firewall Manager (`py/azazel_zero/first_minute/nft.py`)

**Template Rendering:**
```python
# Template: nftables/first_minute.nft
# Tokens: @UPSTREAM@, @DOWNSTREAM@, @MGMT_IP@, @MGMT_SUBNET@

def apply_base(self):
    """Load base ruleset from template"""
    # 1. Delete old table (if exists)
    subprocess.run(['nft', 'delete', 'table', 'inet', 'azazel_fmc'], ...)
    
    # 2. Render template
    rendered = template.replace('@UPSTREAM@', 'wlan0')
                       .replace('@DOWNSTREAM@', 'usb0')
                       .replace('@MGMT_IP@', '10.55.0.10')
    
    # 3. Apply via nft -f
    subprocess.run(['nft', '-f', '-'], input=rendered, ...)

def set_stage(self, stage: Stage):
    """Set ct mark for stage-based routing"""
    # nft add rule inet azazel_fmc stage_switch mark set <stage_num>
```

**nftables Structure:**
```
table inet azazel_fmc {
    set mgmt_ports { type inet_service; elements = { 22, 80, 443, 8081, 8084 } }
    set mgmt_subnet { type ipv4_addr; elements = { 10.55.0.0/24 } }
    
    chain input {
        # Fast-path for management traffic
        iifname "usb0" tcp dport @mgmt_ports accept
        iifname "usb0" icmp type { echo-request, echo-reply } accept
        # ...
    }
    
    chain forward {
        # Stage-based routing (uses ct mark)
        ct mark 1 jump stage_probe       # PROBE
        ct mark 2 jump stage_degraded    # DEGRADED
        ct mark 3 jump stage_normal      # NORMAL
        ct mark 4 jump stage_contain     # CONTAIN
        ct mark 5 jump stage_deception   # DECEPTION
    }
    
    chain stage_normal {
        # Full forwarding
        accept
    }
    
    chain stage_contain {
        # Block most egress, allow management
        ip daddr @mgmt_subnet accept
        drop
    }
}
```

### 4.3 Traffic Shaping (`py/azazel_zero/first_minute/tc.py`)

**HTB (Hierarchical Token Bucket) Configuration:**
```python
def apply_degraded(self):
    """DEGRADED stage: +180ms RTT, 2 Mbps cap"""
    # 1. Create HTB root qdisc
    tc qdisc add dev usb0 root handle 1: htb default 10
    
    # 2. Add class with rate limit
    tc class add dev usb0 parent 1: classid 1:10 htb rate 2mbit
    
    # 3. Add netem for latency
    tc qdisc add dev usb0 parent 1:10 handle 10: netem delay 180ms

def apply_probe(self):
    """PROBE stage: +180ms RTT, 1 Mbps cap"""
    # Similar to DEGRADED but 1mbit rate

def clear(self):
    """Remove all tc rules (NORMAL/CONTAIN)"""
    tc qdisc del dev usb0 root
```

### 4.4 Probes (`py/azazel_zero/first_minute/probes.py`)

**Test Types:**
```python
def run_all_probes(config):
    results = {
        'tls_checks': [],   # HTTPS cert validation
        'dns_checks': [],   # DNS resolution consistency
        'captive_portal': None,  # Captive portal detection
    }
    
    # TLS test (example: github.com)
    for site in config['probes']['tls_sites']:
        try:
            ssl.create_connection((site, 443), timeout=5)
            results['tls_checks'].append({'host': site, 'ok': True})
        except:
            results['tls_checks'].append({'host': site, 'ok': False})
    
    # DNS test (compare upstream vs. direct query)
    for target in config['probes']['dns_targets']:
        upstream_ip = resolve_via_dnsmasq(target)
        direct_ip = resolve_via_public_dns(target)
        results['dns_checks'].append({
            'target': target,
            'match': upstream_ip == direct_ip
        })
    
    # Captive portal (check for HTTP redirect)
    results['captive_portal'] = check_captive_portal(
        config['probes']['captive_test_url']
    )
    
    return results
```

### 4.5 Wi-Fi Safety Sensor (`py/azazel_zero/sensors/wifi_safety.py`)

**Detection Methods:**
```python
def scan_threats():
    tags = []
    
    # 1. Evil Twin AP detection
    if detect_multiple_bssids_same_ssid():
        tags.append('evil_twin')
    
    # 2. MITM detection (gateway MAC mismatch)
    if gateway_mac_changed():
        tags.append('mitm_gateway')
    
    # 3. DNS spoofing (unexpected DNS server)
    if dns_server_suspicious():
        tags.append('dns_spoof')
    
    # 4. DHCP rogue server
    if multiple_dhcp_offers():
        tags.append('rogue_dhcp')
    
    return len(tags)  # Returns count for suspicion increment
```

---

## 5. Web UI Architecture

### 5.1 Flask Application (`azazel_web/app.py`)

**Server Configuration:**
```python
BIND_HOST = "0.0.0.0"  # Listen on all interfaces
BIND_PORT = 8084
STATE_PATH = Path("/run/azazel-zero/ui_snapshot.json")
CONTROL_SOCKET = Path("/run/azazel/control.sock")
```

**Routes:**
```python
@app.route('/')
def index():
    """Serve HTML dashboard"""
    return render_template('index.html')

@app.route('/api/state')
def get_state():
    """JSON state endpoint (polled by frontend every 2s)"""
    state = json.load(open(STATE_PATH))
    return jsonify(state)

@app.route('/api/action/<action_name>', methods=['POST'])
def execute_action(action_name):
    """Send command to control daemon via Unix socket"""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(CONTROL_SOCKET))
    sock.send(json.dumps({'action': action_name}).encode())
    result = json.loads(sock.recv(1024).decode())
    sock.close()
    return jsonify(result)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'service': 'azazel-web',
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })
```

### 5.2 Frontend (`azazel_web/static/app.js`)

**Polling Logic:**
```javascript
async function updateState() {
    try {
        const response = await fetch('/api/state');
        const state = await response.json();
        
        // Update DOM elements
        document.getElementById('stage').textContent = state.internal.state_name;
        document.getElementById('suspicion').textContent = state.suspicion || 0;
        document.getElementById('ssid').textContent = state.ssid || 'N/A';
        document.getElementById('cpu-temp').textContent = state.temp_c || '--';
        // ... (40+ DOM updates)
        
    } catch (error) {
        console.error('State update failed:', error);
    }
}

// Poll every 2 seconds
setInterval(updateState, 2000);
```

### 5.3 Control Daemon (`py/azazel_control/daemon.py`)

**Socket Server:**
```python
SOCKET_PATH = Path('/run/azazel/control.sock')

ACTION_SCRIPTS = {
    'refresh': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/refresh.sh',
    'reprobe': '/.../reprobe.sh',
    'contain': '/.../contain.sh',
    'stage_open': '/.../stage_open.sh',
    'disconnect': '/.../disconnect.sh',
    'details': '/.../details.sh',
}

def handle_client(conn, addr):
    data = conn.recv(1024).decode('utf-8')
    request = json.loads(data)
    action = request.get('action')
    
    # Execute corresponding shell script
    result = subprocess.run(
        ['/bin/bash', ACTION_SCRIPTS[action]],
        timeout=10,
        capture_output=True,
        text=True
    )
    
    response = {
        'ok': result.returncode == 0,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'ts': time.time()
    }
    
    conn.send(json.dumps(response).encode('utf-8'))
    conn.close()
```

---

## 6. Configuration (`configs/first_minute.yaml`)

```yaml
interfaces:
  upstream: wlan0
  downstream: usb0
  mgmt_ip: 10.55.0.10
  mgmt_subnet: 10.55.0.0/24

state_machine:
  degrade_threshold: 20
  normal_threshold: 8
  contain_threshold: 50
  decay_per_sec: 3
  suricata_cooldown_sec: 30

probes:
  tls_sites:
    - github.com
    - www.google.com
  dns_targets:
    - github.com
    - www.cloudflare.com
  captive_test_url: http://captive.apple.com/hotspot-detect.html
  interval_sec: 60

dnsmasq:
  upstream_dns:
    - 9.9.9.9       # Quad9
    - 1.1.1.1       # Cloudflare
  block_doh_sni:
    - cloudflare-dns.com
    - dns.google
  cache_size: 1000

status_api:
  host: 10.55.0.10     # Legacy API (deprecated)
  port: 8082
  web_host: 0.0.0.0    # Web UI (current)
  web_port: 8084
  enable_remote_access: true

suricata:
  enabled: false
  rules_path: /etc/suricata/rules
  eve_json: /var/log/suricata/eve.json
```

---

## 7. Shared State Format

**File**: `/run/azazel-zero/ui_snapshot.json`  
**Writer**: `controller.py` (every 2s)  
**Readers**: Flask Web UI, TUI, Control Daemon

```json
{
  "ssid": "JCOM_NYRY",
  "bssid": "AA:BB:CC:DD:EE:FF",
  "signal_dbm": -55,
  "upstream_if": "wlan0",
  "downstream_if": "usb0",
  "mgmt_ip": "10.55.0.10",
  "temp_c": 30.7,
  "cpu_percent": 2.2,
  "mem_percent": 25.7,
  "uptime_sec": 12345,
  "internal": {
    "state_name": "NORMAL",
    "suspicion": 0.0,
    "reason": "All checks passed",
    "last_signals": {
      "wifi_tags": 0,
      "probe_fail": 0,
      "dns_mismatch": 0,
      "suricata_alert": 0,
      "cert_mismatch": 0
    },
    "thresholds": {
      "degrade": 20,
      "normal": 8,
      "contain": 50
    },
    "traffic_control": {
      "rtt_ms": 0,
      "rate_mbps": 0
    },
    "transition_history": [
      {
        "from": "PROBE",
        "to": "NORMAL",
        "ts": 1706425200.5,
        "suspicion": 5,
        "reason": "Suspicion decayed below threshold"
      }
    ]
  }
}
```

---

## 8. Installation

### 8.1 Dependencies

**System Packages:**
```bash
apt-get install -y \
    python3 python3-pip \
    nftables dnsmasq tcpdump iw \
    suricata git tmux curl jq
```

**Python Packages:**
```bash
pip3 install Flask>=3.1.1 PyYAML
```

### 8.2 Installers

**Full System Setup:**
```bash
sudo tools/bootstrap_zero.sh --with-webui
```

**Web UI Only:**
```bash
sudo bin/install_webui.sh
```

**Flags:**
- `--dry-run`: Show steps without executing
- `--no-systemd`: Skip service installation
- `--no-epd`: Skip E-Paper dependencies

### 8.3 Service Management

```bash
# Enable and start
sudo systemctl enable --now azazel-first-minute
sudo systemctl enable --now azazel-control-daemon

# Status check
sudo systemctl status azazel-first-minute
journalctl -u azazel-first-minute -f

# Restart after config changes
sudo systemctl restart azazel-first-minute
```

---

## 9. Development Guidelines

### 9.1 Code Style

**Python:**
- PEP 8 compliant
- Type hints preferred: `def func(arg: str) -> Dict[str, Any]:`
- Docstrings: Google style
- Logging: Use `logging` module, not `print()`

**Logging Levels:**
```python
logger.info("State transition: {old} -> {new}")   # State changes only
logger.debug("Loop iteration: signals={signals}") # Every 2s loop
logger.warning("Probe failure: {reason}")
logger.error("Fatal error: {exception}")
```

### 9.2 Testing

**Unit Tests:**
```bash
python3 test_redesign_verification.py
```

**Integration Tests:**
```bash
# Check services
sudo systemctl is-active azazel-first-minute
sudo systemctl is-active azazel-control-daemon

# Check state file
jq . /run/azazel-zero/ui_snapshot.json

# Check firewall
sudo nft list table inet azazel_fmc | grep 8084

# Check Web UI
curl http://10.55.0.10:8084/health
```

### 9.3 Commit Messages

**Format:**
```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring
- `docs`: Documentation
- `test`: Tests
- `chore`: Maintenance

**Example:**
```
feat: Add TCP connection tracking to CONTAIN stage

- Track active connections before entering CONTAIN
- Gracefully close existing connections
- Add connection count to ui_snapshot.json

Fixes issue where long-lived connections bypass CONTAIN rules.
```

### 9.4 File Modification Checklist

**When modifying state machine:**
1. Update `state_machine.py`
2. Run `test_redesign_verification.py`
3. Update `configs/first_minute.yaml` (if thresholds change)
4. Update `SYSTEM_SPECIFICATION.md` (this file)
5. Test state transitions manually

**When modifying Web UI:**
1. Update `azazel_web/app.py` or `static/app.js`
2. Test with `curl http://10.55.0.10:8084/health`
3. Verify browser rendering
4. Check `/run/azazel-zero/ui_snapshot.json` format
5. Update `docs/WEB_UI.md` (if API changes)

**When modifying firewall:**
1. Update `nftables/first_minute.nft` template
2. Test with `nft -f nftables/first_minute.nft --check`
3. Apply via `sudo systemctl restart azazel-first-minute`
4. Verify with `sudo nft list table inet azazel_fmc`
5. Test connectivity from MacBook

---

## 10. Troubleshooting

### 10.1 Common Issues

**Issue**: Web UI not accessible on port 8084  
**Diagnosis**:
```bash
sudo nft list table inet azazel_fmc | grep 8084  # Check firewall
sudo ss -tlnp | grep 8084                         # Check if Flask is listening
journalctl -u azazel-first-minute -n 50           # Check logs
```
**Solution**: Restart first-minute to reload nftables template

**Issue**: State not updating in Web UI  
**Diagnosis**:
```bash
ls -la /run/azazel-zero/ui_snapshot.json         # Check if file exists
jq . /run/azazel-zero/ui_snapshot.json           # Check if valid JSON
journalctl -u azazel-first-minute | grep ERROR   # Check controller errors
```
**Solution**: Verify first-minute service is running

**Issue**: Control actions not executing  
**Diagnosis**:
```bash
ls -la /run/azazel/control.sock                  # Check socket
sudo systemctl status azazel-control-daemon      # Check daemon status
ls -la py/azazel_control/scripts/*.sh            # Check script permissions
```
**Solution**: Restart control-daemon or fix script permissions

### 10.2 Debug Mode

**Enable verbose logging:**
```bash
# Edit service file
sudo systemctl edit azazel-first-minute

# Add:
[Service]
Environment="AZAZEL_LOG_LEVEL=DEBUG"

# Restart
sudo systemctl daemon-reload
sudo systemctl restart azazel-first-minute

# View logs
journalctl -u azazel-first-minute -f --output=json | jq .
```

---

## 11. API Reference

### 11.1 Web UI API

**Base URL**: `http://10.55.0.10:8084`

**Endpoints:**

| Method | Path                 | Description                  | Response Type |
|--------|----------------------|------------------------------|---------------|
| GET    | `/`                  | HTML dashboard               | text/html     |
| GET    | `/health`            | Health check                 | application/json |
| GET    | `/api/state`         | Current system state         | application/json |
| POST   | `/api/action/refresh`| Force state refresh          | application/json |
| POST   | `/api/action/reprobe`| Re-run probes                | application/json |
| POST   | `/api/action/contain`| Enter CONTAIN stage          | application/json |
| POST   | `/api/action/stage_open` | Move to NORMAL           | application/json |
| POST   | `/api/action/disconnect` | Disconnect from Wi-Fi    | application/json |
| POST   | `/api/action/details`| Dump detailed state          | application/json |

**Response Format:**
```json
{
  "ok": true,
  "stdout": "Probe refresh initiated\n",
  "stderr": null,
  "ts": 1706425200.5
}
```

### 11.2 Control Daemon Protocol

**Socket**: `/run/azazel/control.sock` (Unix domain socket)  
**Protocol**: JSON over stream

**Request:**
```json
{
  "action": "reprobe",
  "params": {}
}
```

**Response:**
```json
{
  "ok": true,
  "stdout": "Probes completed: 5/5 passed\n",
  "stderr": null,
  "ts": 1706425200.5
}
```

---

## 12. Security Considerations

### 12.1 Authentication

**Web UI Token (Optional):**
```bash
# Generate token
TOKEN=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)
echo "$TOKEN" > ~/.azazel-zero/web_token.txt
chmod 600 ~/.azazel-zero/web_token.txt

# Access with token
curl -H "X-Auth-Token: $TOKEN" http://10.55.0.10:8084/api/state
```

### 12.2 Firewall Restrictions

**Management Network Only:**
```yaml
# configs/first_minute.yaml
status_api:
  web_host: 10.55.0.10  # Bind to usb0 only (not 0.0.0.0)
  enable_remote_access: false
```

### 12.3 Service Isolation

**systemd Hardening:**
```ini
[Service]
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/azazel /run/azazel-zero
```

---

## 13. Performance Metrics

**Controller Loop:**
- Interval: 2 seconds
- CPU usage: ~2-5% (idle), ~10-15% (active scanning)
- Memory: ~50-80 MB (Python process)

**Web UI:**
- Polling interval: 2 seconds (frontend)
- Response time: <10ms (local), <50ms (USB gadget)
- Concurrent connections: 1-5 typical

**Firewall:**
- nftables overhead: <1% CPU
- tc overhead: <2% CPU (DEGRADED stage)
- Latency added: 0ms (NORMAL), 180ms (PROBE/DEGRADED)

---

## 14. Future Enhancements

**Planned Features:**
1. **LLM Integration**: Real threat_judge.py implementation with local LLM
2. **Tactics Engine**: Automated response playbooks
3. **Persistent Storage**: SQLite for long-term event history
4. **TUI Improvements**: Real-time ncurses dashboard
5. **Multi-AP Support**: Automatic failover between known APs

**Technical Debt:**
1. Migrate tc to nftables native `limit` rules
2. Replace shell scripts in `azazel_control/scripts/` with Python
3. Add comprehensive error handling in probes.py
4. Implement proper certificate pinning for TLS checks

---

## 15. Glossary

**Terms:**
- **FSM**: Finite State Machine (5-stage threat response)
- **Suspicion**: Numeric score (0-100) representing threat level
- **Decay**: Passive reduction of suspicion over time
- **Probe**: Active test (TLS/DNS/captive portal) to verify network safety
- **Signal**: Input to FSM (wifi_tags, probe_fail, dns_mismatch, etc.)
- **Stage**: Current FSM state (INIT/PROBE/DEGRADED/NORMAL/CONTAIN/DECEPTION)
- **tc**: Linux Traffic Control (HTB qdisc for rate limiting)
- **nftables**: Linux kernel packet filter (successor to iptables)
- **USB Gadget**: Kernel module (g_ether) for virtual Ethernet over USB
- **Management Network**: usb0 subnet (10.55.0.0/24) for admin access

**File Paths:**
- `/run/azazel-zero/ui_snapshot.json`: Shared state (written by controller, read by Web UI)
- `/run/azazel/control.sock`: Unix socket for action commands
- `/etc/azazel-zero/`: System-wide config and templates (synced from repo)
- `~/.azazel-zero/`: User-specific config (fallback for non-root testing)

---

**End of Specification**

This document is version-controlled and should be updated with every significant architectural change. For AI-assisted development, provide this entire specification along with specific modification requests.
