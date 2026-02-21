# Azazel-Zero

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
  - Textual mode is also available with `--textual` (keeps the same action keys).
  
- **tmux console**  
  - `py/azazel_menu.py` is a curses menu for Wi-Fi selection, OpenCanary start/stop/log tail, and E-Paper test actions.  
  - `py/azazel_status.py` is a telemetry panel showing SSID/BSSID, USB gadget IP, RSSI, captive-portal indicators, etc.
  - Textual mode:
    - `python3 py/azazel_menu.py --textual`
    - `python3 py/ssid_list.py --textual [iface]`

---

## Runtime Components

| Component | Entry Point | Notes |
|-----------|-------------|-------|
| Unified installer | `install.sh`, `installer/stages/*.sh` | Single installation flow with Stage 00/10/20/30/40/99 |
| First-Minute controller | `py/azazel-first-minute.py` | Core state machine (`PROBE/NORMAL/DEGRADED/CONTAIN/DECEPTION`) |
| Status API | `py/azazel_zero/first_minute/controller.py` | JSON + actions on `10.55.0.10:8082` |
| Control daemon | `py/azazel_control/daemon.py` | Unix socket `/run/azazel/control.sock`, executes action scripts and Wi-Fi scan/connect |
| Web UI (optional) | `azazel_web/app.py` | HTTPS dashboard via Caddy (`https://10.55.0.10`) + Flask backend (`127.0.0.1:8084`) |
| Captive Portal Viewer (optional) | `scripts/azazel-portal-viewer.sh` | Chromium on virtual display + noVNC via `azazel-portal-viewer.service` (`:6080/vnc.html`) |
| TUI monitor | `py/azazel_zero/cli_unified.py` | Manual-refresh terminal monitor |
| E-Paper tools | `py/azazel_epd.py`, `py/boot_splash_epd.py` | Status/alert rendering and boot/shutdown splash |

---

## Captive Probe Roles

`first_minute.yaml` now separates route role and captive-probe role:

```yaml
interfaces:
  upstream: auto
  captive_probe: auto
  downstream: usb0

captive_probe_policy: wifi_prefer  # wifi_prefer | upstream_same | any
suppress_auto_wifi: true
```

- `upstream`: NAT/routing interface.
- `captive_probe`: interface bound with `curl --interface` for captive check.
- `wifi_state=DISCONNECTED` clears stale `ssid/ip_wlan/gateway_ip/bssid`.

---

## How to Read the TUI (Integrated Monitoring)

### Launch

```bash
sudo python3 py/azazel_zero/cli_unified.py
```

Textual mode:

```bash
sudo python3 py/azazel_zero/cli_unified.py --textual
```

Note:
- In Textual mode, EPD updates are disabled by default for stability.
- Enable them explicitly only when needed: `--enable-epd`

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

## Installation

**Complete setup with the unified installer.** See [installer/README.md](installer/README.md) for details.

### Prerequisites

- **Raspberry Pi Zero 2 W** running Raspberry Pi OS Lite 64-bit
- **USB gadget mode** configured:
  - Add `dtoverlay=dwc2` to `/boot/config.txt`
  - Add `modules-load=dwc2,g_ether` to `/boot/cmdline.txt`
  - After reboot, `usb0` is available
- Repository deployed to `/home/azazel/Azazel-Zero`

### Quick Start (Recommended)

```bash
cd ~/Azazel-Zero
sudo ./install.sh
```

**That's it.** The following is automatically executed:

✅ **Stage 00**: Prerequisites check (root, OS, disk, interfaces)  
✅ **Stage 10**: Dependency installation (nftables, dnsmasq, Python venv, etc.)  
✅ **Stage 20**: Network configuration (usb0, NAT, iptables)  
  - **Auto-detect network changes** → prompt reboot → resumable with `--resume`  
✅ **Stage 30**: Deploy configs to `/etc/azazel-zero/`  
✅ **Stage 40**: Register and enable systemd units  
✅ **Stage 99**: Validate all services and complete

### Network Change Handling

If wlan0 IP changes during installation (e.g., DHCP reassignment):

1. **Stage 20** detects the network change
2. Displays a reboot prompt message
3. Saves state and exits safely
4. After reboot, run:
   ```bash
   sudo ./install.sh --resume
   ```
5. Continues from **Stage 30**

### Enable Optional Features

```bash
# Include Web UI + OpenCanary + ntfy + Portal Viewer
# (E-Paper is enabled by default in the installer)
sudo ./install.sh --with-webui --with-canary --with-ntfy --with-portal-viewer

# Enable all optional features
sudo ./install.sh --all

# Preview only (no changes)
sudo ./install.sh --dry-run
```

**Available Options:**

| Option | Description |
|--------|-------------|
| `--with-webui` | Enable Web UI with HTTPS (Caddy) and Flask backend |
| `--with-canary` | Enable OpenCanary honeypot |
| `--with-epd` | Install Waveshare E-Paper driver (enabled by default) |
| `--with-ntfy` | Enable ntfy notifications |
| `--with-portal-viewer` | Enable noVNC portal assist viewer (port 6080) |
| `--all` | Enable all options |
| `--dry-run` | Print actions only (no changes) |
| `--resume` | Resume from interrupted installation |
| `--auto-reboot` | Auto-reboot when Stage 20 detects network changes |
| `--debug` | Enable debug logging for installer stages |

### ntfy Channels in Operation

When `--with-ntfy` is enabled, Azazel-Zero uses these two ntfy topics for runtime notifications:

- `azg-alert-critical` (critical alerts)
- `azg-info-status` (status/info updates)

Quick verification on the device:

```bash
sudo ntfy access
```

### After Installation

Once complete:

1. **Access Web UI** (from MacBook via usb0):
   ```
   https://10.55.0.10
   ```
2. **Open Captive Portal Viewer** (if installed):
   ```
   http://10.55.0.10:6080/vnc.html
   ```

3. **Verify systemd services**:
   ```bash
   systemctl status azazel-first-minute.service
   systemctl status azazel-control-daemon.service
   systemctl status usb0-static.service
   ```

4. **Check APIs**:
   ```bash
   curl http://10.55.0.10:8082/
   curl -k https://10.55.0.10/health
   ```

5. **Monitor logs** (real-time):
   ```bash
   journalctl -u azazel-first-minute.service -f
   ```

For advanced configuration changes and troubleshooting, see [installer/README.md](installer/README.md).

---
