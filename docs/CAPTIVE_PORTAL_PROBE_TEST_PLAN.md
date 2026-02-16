# Captive Portal Probe Test Plan

## Scope

- Deterministic `captive_probe_iface` resolution
- `curl --interface` bound captive probe
- `NO|YES|SUSPECTED|NA` state updates
- `azazel-epd-portal.service` health

## Pre-check

```bash
sudo systemctl daemon-reload
sudo systemctl restart azazel-first-minute.service
sudo systemctl restart azazel-epd-portal.timer
sudo systemctl status azazel-epd-portal.service azazel-epd-portal.timer --no-pager
```

Expected:
- `azazel-epd-portal.service` is `active (exited)`
- no `203/EXEC` in journal

## Test Cases

### T1: WLAN normal AP

Expected:
- `connection.captive_probe_iface` resolves to wireless interface
- probe to `generate_204` returns `HTTP_204`
- `connection.captive_portal=NO`

### T2: WLAN captive AP

Expected:
- HTTP `30x` => `YES` (`HTTP_30X`)
- HTTP `200` with body / other non-204 => `SUSPECTED`

### T3: ETH only

With `captive_probe_policy: wifi_prefer`:
- no wireless candidate -> fallback to wired interface
- reason contains `fallback_to_<iface>`

### T4: No usable interface

Expected:
- `connection.captive_portal=NA`
- reason `NO_IP` or `LINK_DOWN` or `NOT_FOUND`
- probe skipped (no unbound curl)

### T5: Service periodic execution

```bash
sudo systemctl list-timers azazel-epd-portal.timer --no-pager
journalctl -u azazel-epd-portal.service -n 100 --no-pager
```

Expected log examples:

```text
captive_probe_iface resolved: wlan0 (policy=wifi_prefer, src=auto)
skip captive probe: reason=NO_IP
Portal status=YES reason=HTTP_30X iface=wlan0
```
