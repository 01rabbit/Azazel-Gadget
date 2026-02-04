# Azazel-Zero (English translation of README_ja.md)

English | [日本語](/README_ja.md)

## Concept

**Azazel-Zero** is a prototype of a **“Substitute Barrier”** running on Raspberry Pi Zero 2 W.  
It brings the Azazel System’s **delaying action** into a practical form while returning to the roots of the **Substitute Barrier** and **Barrier Maze**.

### Compared to Azazel-Pi

- **Azazel-Pi**  
  - A **Portable Security Gateway (Cyber Scapegoat Gateway)** based on Raspberry Pi 5  
  - A **concept model** to cheaply protect **small temporary networks**  
  - Heavily experimental for trying multiple technical elements

- **Azazel-Zero**  
  - A **trimmed, lightweight edition** with narrowed scope, designed for real operation  
  - A physical barrier focused on portability and practicality  
  - Unlike the concept-model Azazel-Pi, this is a **deployable, practical model**

---

## Design Principles

- **Portability**: fits in a shirt pocket  
- **Inevitability**: forcibly interposes between device and external network  
- **Simplicity**: plug USB and the firewall is in place  
- **Delaying defense**: waste the attacker’s time (core of the Azazel System)

---

## Implementation

### Base

- **Raspberry Pi Zero 2 W**

### Network

- **USB OTG gadget mode**  
  - Single USB cable supplies power and virtual networking  
  - Plug into a laptop and it boots immediately

### Lightweight Protection

- Blocking/latency via **iptables/nftables**  
- Delay/jitter injection with **tc (Traffic Control)**  
- **Custom Python scripts** for dynamic control and notifications  
- **Wi-Fi Safety Sensor** (Python + `iw` + `tcpdump`) detects Evil AP / MITM / DNS & DHCP spoofing, issues danger tags, and auto-disconnects

### Status Display

- **E-Paper**  
  - 2.13" monochrome (250×122)  
  - Compact view of threat level/action/RTT/queue state/captive-portal detection

---

## Threat Evaluation Pipeline

Uses a deterministic two-layer engine that runs even on Pi Zero 2 W.

- **Layer 1: Wi-Fi Safety Sensor**  
  - `py/azazel_zero/sensors/wifi_safety.py` inspects `iw dev … link` and short `tcpdump` captures to detect ARP/DHCP/DNS anomalies.  
  - Emits tags and metadata such as `evil_ap`, `mitm`, `arp_spoof`, `dhcp_spoof`, `dns_spoof`, `tls_downgrade`, `captive_portal`, `phish`.

- **Layer 2: Mock-LLM Core**  
  - `py/azazel_zero/core/mock_llm_core.py` maps inputs to legacy categories (`scan`, `bruteforce`, `exploit`, `malware`, `sqli`, `dos`, `unknown`).  
  - Modernized from regex + randomness to hash-based deterministic replies, outputting risk (1–5) and rationale consistently.  
  - Profile `"zero"` raises risk when Evil AP / MITM tags exist, ensuring Danger/Disconnect decisions.

- **Threat Judge wrapper**  
  - `py/azazel_zero/app/threat_judge.py` bundles tags and final decisions into JSON that UI/automation can consume (e.g., immediate disconnect for `risk >= 4` or `evil_ap`).

Heavyweight ML remains a future research theme; the current deterministic stack alone provides the automation needed for a portable shield.

---

## Operator Console & Automation

- **TUI (terminal UI)**  
  - `py/azazel_zero/cli_unified.py` is the unified monitoring TUI showing Wi-Fi state, threat level, channel congestion, control rules in real time.
  - Colorful icons and color-coding for intuitive situational awareness.
  - Manual refresh mode ([U] key).
  
- **tmux console**  
  - `py/azazel_menu.py` is a curses menu with Wi-Fi selector, Portal/Shield/Lockdown scripts, OpenCanary control, and E-Paper tests.  
  - `py/azazel_status.py` is a telemetry panel showing SSID/BSSID, USB gadget IP, RSSI, captive-portal indicators, etc.
  
- **Bootstrap tools**  
  - `tools/bootstrap_zero.sh` installs dependencies, systemd units, minimal Suricata rules, and smoke tests in one shot.  
  - Flags `--no-epd`, `--no-enable`, `--no-suricata`, `--dry-run` tailor for lab/production.

---

## How to Read the TUI (Integrated Monitoring)

### Launch

```bash
sudo python3 py/azazel_zero/cli_unified.py
```

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Azazel-Zero | 📶 SSID: MyWiFi | ⬇️ usb0 | ⬆️ wlan0 | 🕐 12:34:56 │  ← Status bar
│ View: SNAPSHOT (manual)  Age: 🟢 00:00:15                   │  ← Data freshness
├─────────────────────────────────────────────────────────────┤
│ ✅ SAFE        Recommendation: keep as-is                   │  ← State badge (inverted)
│ Reason: probe ok / DNS ok                                  │
│ Threat: [🟢🟢⚪⚪⚪] Low                                     │  ← Threat level
│ Next: waiting for re-eval                                  │
├──────────────────────┬──────────────────────────────────────┤
│ Connection           │ Control / Safety                     │
│ BSSID: aa:bb:cc:...  │ QUIC(UDP/443): ⛔ BLOCKED           │
│ Channel: 🟢 Ch124    │ DoH(TCP/443): ⛔ BLOCKED            │
│    - Low (31 APs)    │ Degrade: ✓ OFF                      │
│ Signal: 🟩🟩🟩 -55dBm │ Probe: ✓ 5/5 ALL OK                │
│ Gateway: 🏠 192.168… │ Stats: DNS: ✅ 45 ⚠️ 3 🔴 2         │
├──────────────────────┴──────────────────────────────────────┤
│ Evidence (last 90s)                                         │
│ 🟢 Normal probe completed                                   │
│ 🟡 DNS query to suspicious domain                          │
│ 💠 action: reprobe command sent                             │
│ ↳ decision: state=NORMAL suspicion=5 decay=0.9             │
├─────────────────────────────────────────────────────────────┤
│ Flow: PROBE → DEGRADED → NORMAL → ✅ SAFE                   │
│ [U] Refresh  [A] Stage-Open  [R] Re-Probe  [C] Contain  [L] Details  [Q] Quit │
│ Hint: This screen does not auto-refresh. Press [U] when needed.             │
└─────────────────────────────────────────────────────────────┘
```

### Icons and Colors

#### 🎯 State badge (main status)

| Icon | State | Color | Meaning |
|------|-------|-------|---------|
| ⟳ | Checking | Cyan (inverted) | Initial scan |
| ✅ | **Safe** | **Green (inverted, bold)** | Network is safe |
| ⚠️ | Limited | Yellow (inverted) | Restrictions like bandwidth limits |
| ⛔ | Contained | Red (inverted) | Danger detected, containment mode |
| 👁 | Deception | Purple (inverted) | Decoy mode |

#### 🎯 Threat level indicator

```
Threat: [🟢🟢⚪⚪⚪] Low      ← Safe
Threat: [🟡🟡🟡⚪⚪] Med      ← Caution
Threat: [🔴🔴🔴🔴🔴] Critical ← Dangerous
```

#### 🎯 Age (freshness)

- 🟢 **0–30s**: freshest, trustworthy
- 🟡 **30s–2m**: slightly old, verify
- 🔴 **2m+**: stale, press [U] to refresh

#### 🎯 Signal strength

| Display | Strength | Meaning |
|---------|----------|---------|
| 🟩🟩🟩🟩 | >= -50dBm | Excellent |
| 🟩🟩🟩 | -50 to -60dBm | Good |
| 🟨🟨 | -60 to -70dBm | Fair |
| 🟧 | -70 to -80dBm | Weak |
| 🟥 | <= -80dBm | Very weak |

#### 🎯 Channel congestion (measured)

| Display | Congestion | APs | Meaning |
|---------|------------|-----|---------|
| 🟢 Clear/Low | Low | 0–2 | Open (comfortable) |
| 🟡 Medium | Medium | 3–5 | Normal |
| 🟧 High | High | 6–10 | Crowded |
| 🔴 Critical | Very high | 11+ | Extremely crowded |

※ APs around you are scanned when you press [U].

#### 🎯 Gateway IP

- 🏠 **Green**: private IP (normal)
- ⚠️ **Yellow**: public IP (check)

#### 🎯 Control rules

| Item | Icon | Color | Meaning |
|------|------|-------|---------|
| QUIC | ⛔ | Red | Blocked |
| QUIC | ✓ | Green | Allowed |
| Degrade | ⚡ | Yellow | Bandwidth limited |
| Degrade | ✓ | Green | No limit |
| Probe | ⚠ | Red | Probe detected problems |
| Probe | ✓ | Green | All good |

#### 🎯 DNS stats

- ✅ Normal queries
- ⚠️ Suspicious queries
- 🔴 Blocked queries

#### 🎯 Evidence log

| Icon | Color | Meaning |
|------|-------|---------|
| 🔴 | Red (bold) | Anomaly / error (blocked, fail, hijack, etc.) |
| 🟡 | Yellow | Warning / caution (portal, dns, probe, etc.) |
| 🟢 | Green | Normal / success (ok, safe, normal, etc.) |
| 💠 | Cyan | Action (command, transition, etc.) |
| ⚪ | White | Other |

### Key bindings

| Key | Function | Description |
|-----|----------|-------------|
| **[U]** | Refresh | Manually update data (runs Wi-Fi scan) |
| **[A]** | Stage-Open | Move from restricted to normal mode |
| **[R]** | Re-Probe | Run probe test again |
| **[C]** | Contain | Enter containment mode |
| **[L]** | Details | Detail view (30 evidence entries, internal state) |
| **[Q]** | Quit | Exit |

### Details screen (via [L])

- **Evidence history**: last 30 evidence entries
- **Internal state**:
  - `State`: current state machine status (PROBE/NORMAL/DEGRADED/CONTAIN/DECEPTION)
  - `Suspicion`: suspicion score (0–100)
  - `Decay`: decay value
  - `Rules`: control rule details
- Press **[B]** to return to main screen

### Color rules

| Color | Meaning | Where used |
|-------|---------|-----------|
| 🟢 Green | Good / normal / safe | SAFE, strong signal, clear channel, normal logs |
| 🟡 Yellow | Caution / warning / medium | LIMITED, weak signal, congestion, warning logs |
| 🔴 Red | Danger / error / abnormal | CONTAINED, very weak signal, severe congestion, error logs |
| 🟣 Purple | Special | DECEPTION |
| 🔵 Cyan | Info / technical | CHECKING, action logs, technical info |
| ⚪ White | Neutral / unknown | Other logs, unknown states |

---

## Setup (overview)

See [docs/setup-zero.md](docs/setup-zero.md) for details.

### Quick start

Use the automated setup script for reproducible installs.

```bash
sudo chmod +x tools/bootstrap_zero.sh
sudo tools/bootstrap_zero.sh
```

Options:

- `--no-epd`: skip E-Paper dependencies  
- `--no-enable`: do not enable systemd services  
- `--no-suricata`: skip lightweight Suricata rules  
- `--no-webui`: skip Web UI (monitor/control)  
- `--no-ntfy`: skip ntfy (notification backend)  
- `--no-canary`: skip OpenCanary  
- `--no-gadget`: skip USB gadget boot config (dwc2/g_ether)  
- `--dry-run`: print actions only

Note:
- Wi-Fi connect/save is done via **Azazel tools (Web UI / Control Daemon)**. The installer does not hardcode SSID/PSK.

1. Install **Raspberry Pi OS Lite (64bit)**  
2. Configure **USB gadget mode**  
   - Add `dtoverlay=dwc2` to `/boot/config.txt`  
   - Add `modules-load=dwc2,g_ether` to `/boot/cmdline.txt`  
3. Install **E-Paper control library** (e.g., Waveshare Python)  
4. Deploy **UI scripts** to display threat level and delay state  
5. Enable **systemd services** to autostart shield/UI

## Boot-time E-Paper splash (~/Azazel-Zero)

See [Boot_E-Paper_Splash_ja.md](/docs/Boot_E-Paper_Splash_ja.md) for details.

At boot, display **SSID** and **IPv4** on the Waveshare E-Paper.  
Script: `py/boot_splash_epd.py`

**Setup**

1. Install dependencies together: `sudo bash bin/install_dependencies.sh --with-epd`  
2. Test: `sudo python3 ~/Azazel-Zero/py/boot_splash_epd.py`  
3. Enable service `azazel-epd.service` (path managed in `/etc/default/azazel-zero`)

If your panel driver is not `epd2in13_V4`, change to `V3` or `V2`.

### Install Waveshare libraries (Raspberry Pi Zero 2 W)

`bin/install_waveshare_epd.sh` automates the official steps so Waveshare demos run immediately:

```bash
sudo bash bin/install_waveshare_epd.sh
```

Script contents (can run manually):

```bash
# Dependencies
sudo apt-get update
sudo apt-get install python3-pip
sudo apt-get install python3-pil
sudo apt-get install python3-numpy
sudo python3 -m pip install spidev

# gpiozero (only if missing)
sudo apt-get update
sudo apt install python3-gpiozero
sudo apt install python-gpiozero

# Fetch Waveshare demos
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/
wget https://files.waveshare.com/upload/7/71/E-Paper_code.zip
unzip E-Paper_code.zip -d e-Paper
# Alternative: use 7zip
sudo apt-get install p7zip-full
7z x E-Paper_code.zip -O./e-Paper

# Run demo (2.13in mono V4)
cd e-Paper/RaspberryPi_JetsonNano/python/examples/
python3 epd_2in13b_V4_test.py
```

`install_waveshare_epd.sh` installs the library under `/opt/waveshare-epd` and fetches `E-Paper_code.zip`. Add `--run-demo` to automatically execute the demo at the end.
---

## Web UI

### Overview

A responsive Flask-based Web UI accessible from MacBook via USB gadget network. Provides real-time security status, system metrics, and control actions.

### Architecture

- **Backend**: Python Flask (port 8084)
  - Reads shared state from `/run/azazel-zero/ui_snapshot.json` (first-minute controller)
  - Unix socket control daemon for action execution
  - JSON API endpoints: `/api/state`, `/api/action/*`, `/health`

- **Frontend**: HTML5 + CSS3 + JavaScript
  - Responsive 2-column layout (PC) / stacked (mobile)
  - 2-second polling interval for real-time updates
  - Risk Assessment, Connection Info, Control & Safety panels
  - System Health metrics (CPU temp, usage; memory usage)

### Access

**MacBook via USB gadget:**
```bash
# Network configuration
usb0 (ラズパイ): 10.55.0.10/24
en17 (MacBook):  10.55.0.114/24 (DHCP assigned)

# Web UI
http://10.55.0.10:8084
```

### State Information

All data flows through single source: `/run/azazel-zero/ui_snapshot.json`

```json
{
  "ssid": "JCOM_NYRY",
  "temp_c": 30.7,
  "cpu_percent": 2.2,
  "mem_percent": 25.7,
  "internal": {
    "state_name": "NORMAL",
    "suspicion": 0.0
  }
}
```

Shared between:
- **Web UI (Flask)** - Remote access via HTTP
- **TUI (Terminal UI)** - Local text-based interface
- **Control Daemon** - Action execution (refresh, reprobe, contain, etc.)

### Firewall Rules

Port whitelisting on `usb0` (downstream):

| Port | Purpose |
|------|---------|
| 22   | SSH management |
| 80   | HTTP probes, redirects |
| 443  | HTTPS/TLS probes |
| 8081 | Status API |
| 8084 | **Web UI** |

ICMP (ping) and IGMP fully supported for network diagnostics.

---
