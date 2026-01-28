# Azazel-Gadget Web UI

Flask-based Web UI implementation following the AI Coding Spec v1.

## Architecture

```
Browser → Flask Web UI → Unix Socket → Control Daemon → Scripts → System
                ↓
         /run/azazel/state.json
```

### Components

1. **Flask Web UI** (`azazel_web/`)
   - Display dashboard
   - REST API
   - Token authentication
   - NO direct system operations

2. **Control Daemon** (`azazel_control/`)
   - Unix socket listener (`/run/azazel/control.sock`)
   - Policy enforcement
   - Script execution
   - State update

3. **State Store** (`/run/azazel/state.json`)
   - Single source of truth
   - Updated by daemon
   - Read by Flask

## Quick Start

### 1. Install Dependencies

```bash
pip3 install flask
```

### 2. Generate State (Bridge to Existing Controller)

```bash
# Terminal 1: Generate state.json from legacy API
sudo python3 azazel_control/state_generator.py
```

### 3. Start Control Daemon

```bash
# Terminal 2: Start Unix socket daemon
sudo python3 azazel_control/daemon.py
```

### 4. Start Flask Web UI

```bash
# Terminal 3: Start Web UI
python3 azazel_web/app.py
```

### 5. Access Dashboard

```
http://localhost:8080/
```

## API Endpoints

### `GET /api/state`
Returns current state.json

Response:
```json
{
  "ok": true,
  "ts": "2026-01-28T...",
  "header": { ... },
  "risk": { ... },
  "connection": { ... },
  "control": { ... },
  "evidence": { ... }
}
```

### `POST /api/action/<action>`
Execute control action

Header:
```
X-AZAZEL-TOKEN: <token>
```

Actions:
- `refresh` - Refresh state
- `reprobe` - Re-run probes
- `contain` - Activate contain mode
- `details` - Dump details
- `stage_open` - Open stage
- `disconnect` - Disconnect

Response:
```json
{
  "ok": true,
  "action": "contain",
  "message": "contain executed",
  "ts": "2026-01-28T..."
}
```

## UI Layout

### PC Layout
```
┌─────────────────────────────────────────┐
│ Header (SSID, Clock, Temp, CPU)        │
├──────────────────┬──────────────────────┤
│ Risk             │ Control & Safety     │
│ Assessment       │ - QUIC/DoH           │
│                  │ - Traffic Shaping    │
│                  │ - Security Services  │
├──────────────────┼──────────────────────┤
│ Connection       │                      │
│ Info             │                      │
└──────────────────┴──────────────────────┘
┌─────────────────────────────────────────┐
│ Evidence & State (Full Width)          │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ [Refresh] [Re-Probe] [Contain] [Disc.] │ ← Fixed bottom
└─────────────────────────────────────────┘
```

### Mobile Layout
```
┌─────────────────┐
│ Header          │
├─────────────────┤
│ Risk            │
├─────────────────┤
│ Connection      │
├─────────────────┤
│ Control/Safety  │
├─────────────────┤
│ Evidence        │
└─────────────────┘
┌─────────────────┐
│ [4 Actions]     │ ← Fixed bottom
│ [⋮ More]        │
└─────────────────┘
```

## Color Rules

- **SAFE** → Green
- **CAUTION** → Yellow/Orange
- **DANGER** → Red
- **ALLOWED** → Green
- **BLOCKED** → Red
- **NORMAL** → Green
- **DEGRADED** → Yellow
- **CONTAINED** → Orange
- **LOCKDOWN** → Red

## Security

### Token Authentication
Set token via environment:
```bash
export AZAZEL_TOKEN="your-secret-token"
python3 azazel_web/app.py
```

Store in browser localStorage:
```javascript
localStorage.setItem('azazel_token', 'your-secret-token');
```

### Policy Constraints

Enforced by Control Daemon:

1. **LOCKDOWN state** → `stage_open` rejected
2. **DANGER status** → `stage_open` rejected
3. **Rate limit** → Same action within 1s rejected

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AZAZEL_TOKEN` | `azazel-default-token-change-me` | Auth token |
| `AZAZEL_WEB_HOST` | `0.0.0.0` | Bind address |
| `AZAZEL_WEB_PORT` | `8080` | Bind port |

### File Paths

| Path | Purpose |
|------|---------|
| `/run/azazel/state.json` | State store |
| `/run/azazel/control.sock` | Unix socket |
| `azazel_control/scripts/` | Action scripts |

## Production Deployment

### systemd Services

Create `/etc/systemd/system/azazel-web.service`:
```ini
[Unit]
Description=Azazel-Gadget Web UI
After=network.target

[Service]
Type=simple
User=azazel
WorkingDirectory=/home/azazel/Azazel-Zero/azazel_web
Environment="AZAZEL_TOKEN=your-production-token"
ExecStart=/usr/bin/python3 app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/azazel-control.service`:
```ini
[Unit]
Description=Azazel Control Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/azazel/Azazel-Zero/azazel_control
ExecStart=/usr/bin/python3 daemon.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/azazel-state-gen.service`:
```ini
[Unit]
Description=Azazel State Generator
After=azazel-first-minute.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /home/azazel/Azazel-Zero/azazel_control/state_generator.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now azazel-control azazel-state-gen azazel-web
```

## Development

### Test State Generation
```bash
# View generated state
python3 azazel_control/state_generator.py &
sleep 3
cat /run/azazel/state.json | jq
```

### Test Control Daemon
```bash
# Terminal 1
sudo python3 azazel_control/daemon.py

# Terminal 2
echo '{"action":"refresh"}' | nc -U /run/azazel/control.sock
```

### Test Flask API
```bash
curl http://localhost:8080/api/state | jq

curl -X POST http://localhost:8080/api/action/refresh \
  -H "X-AZAZEL-TOKEN: azazel-default-token-change-me"
```

## Troubleshooting

### State not updating
```bash
# Check state generator
sudo systemctl status azazel-state-gen
journalctl -u azazel-state-gen -n 20
```

### Actions failing
```bash
# Check control daemon
sudo systemctl status azazel-control
journalctl -u azazel-control -n 20

# Check socket permissions
ls -la /run/azazel/control.sock
```

### Web UI not loading
```bash
# Check Flask
systemctl status azazel-web
journalctl -u azazel-web -n 20

# Check bind address
ss -tulpn | grep 8080
```

## Future Extensions (Not in v1)

- [ ] TLS / reverse proxy integration
- [ ] WebSocket for real-time updates
- [ ] DecisionExplanation visualization
- [ ] Action history timeline
- [ ] Dedicated mode switching UI
- [ ] Network traffic graphs

## License
Same as Azazel-Zero project
