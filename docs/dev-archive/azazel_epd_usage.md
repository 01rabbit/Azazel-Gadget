# Azazel EPD Controller - Usage Guide

## Overview

`azazel_epd.py` is a controller for the Waveshare 2.13" e-Paper HAT (B) V4 three-color display (Black/White/Red, 250x122 pixels). It provides four distinct display states for monitoring network security status.

## Hardware Requirements

- Raspberry Pi (tested on Zero 2 W)
- Waveshare 2.13" e-Paper HAT (B) V4
- Proper SPI connection and permissions

## Software Dependencies

```bash
# Python requirements
- Python 3.7+
- Pillow (PIL)
- waveshare_epd library

# Install Pillow
pip3 install pillow

# Waveshare EPD library path
/opt/waveshare-epd/RaspberryPi_JetsonNano/python/lib
```

## Display States

### 1. NORMAL State
**Purpose**: Display current network status  
**Layout**:
- Wi-Fi icon (45x45px, top-left) that reflects signal strength
- IP address (23pt StardosStencil, beside icon)
- Horizontal line separator
- SSID (20pt StardosStencil, bottom center)

**Usage**:
```bash
sudo python3 py/azazel_epd.py --state normal --ssid "AzazelNet" --ip "172.16.0.1" --signal 72
```

**Font**: StardosStencilBold-9mzn.ttf  
**Colors**: Black text on white background
**Signal thresholds**: `>=70` strong, `>=50` medium, `<50` weak, `None`/missing = not connected

---

### 2. WARNING State
**Purpose**: Alert user to check web portal  
**Layout**:
- Warning icons (35x35px, black) on left and right
- "WARNING" text (30pt icbmss20, center)
- Horizontal line at screen midpoint
- Custom message (28pt icbmss20, bottom)

**Usage**:
```bash
sudo python3 py/azazel_epd.py --state warning --msg "Check Web Portal"
```

**Font**: icbmss20.ttf  
**Colors**: Black text/icons on white background

---

### 3. DANGER State
**Purpose**: Critical alert requiring immediate action  
**Layout**:
- Red background (full screen)
- Warning icons (40x40px, white) on left and right
- "DANGER" text (35pt icbmss20, white, center)
- Horizontal line at screen midpoint
- Custom message (25pt icbmss20, white, bottom)

**Usage**:
```bash
sudo python3 py/azazel_epd.py --state danger --msg "REMOVE DEVICE!"
```

**Font**: icbmss20.ttf  
**Colors**: White text/icons on red background

---

### 4. STALE State
**Purpose**: Indicate data staleness or no updates  
**Layout**:
- "STALE" text (35pt icbmss20, top)
- Horizontal line at screen midpoint
- "NO UPDATE" (20pt icbmss20, first line)
- "CHECK WEB PORTAL" (20pt icbmss20, second line)

**Usage**:
```bash
sudo python3 py/azazel_epd.py --state stale --msg "dummy"
```

**Note**: The `--msg` parameter is required but not used (hardcoded messages)  
**Font**: icbmss20.ttf  
**Colors**: Black text on white background

---

## Dry-Run Mode

Test display rendering without updating hardware. Generates preview images in `/tmp/`.

**Usage**:
```bash
python3 py/azazel_epd.py --state danger --msg "TEST" --dry-run
```

**Output files**:
- `/tmp/azazel_epd_preview_{state}_black.png` - Black layer
- `/tmp/azazel_epd_preview_{state}_red.png` - Red layer
- `/tmp/azazel_epd_preview_{state}_composite.png` - Visual preview (RGB)

---

## Command-Line Arguments

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `--state` | Yes | Display state: `normal`, `warning`, `danger`, `stale` | `--state normal` |
| `--ssid` | For NORMAL | Wi-Fi SSID | `--ssid "AzazelNet"` |
| `--ip` | For NORMAL | IP address | `--ip "172.16.0.1"` |
| `--signal` | Optional for NORMAL | Wi-Fi signal strength (0-100). If omitted, shows disconnected icon | `--signal 65` |
| `--msg` | For WARNING/DANGER/STALE | Custom message | `--msg "Check Web"` |
| `--dry-run` | No | Preview mode (no hardware update) | `--dry-run` |

---

## Asset Files

### Fonts (in `fonts/`)
- **icbmss20.ttf** - Used for WARNING, DANGER, STALE states
- **StardosStencilBold-9mzn.ttf** - Used for NORMAL state

### Icons (in `icons/epd/`)
- **wifi_3.png** - Strong signal (>=70)
- **wifi_2.png** - Medium signal (>=50)
- **wifi_1.png** - Weak signal (<50)
- **wifi_notconnected.png** - Not connected
- **warning.png** - Warning icon for WARNING/DANGER states
- **danger.png** - (Reserved for future use)

**Icon format**: PNG with transparency (RGBA)  
**Icon size**: Automatically resized to specified dimensions

---

## Display Specifications

| Property | Value |
|----------|-------|
| Model | Waveshare 2.13" e-Paper HAT (B) V4 |
| Resolution | 250 x 122 pixels |
| Colors | Black, White, Red (3-color) |
| Driver | `epd2in13b_V4` |
| Update time | ~25 seconds (optimized) |
| 1-bit mode | 0=black/red, 255=white |

---

## Performance Optimization

- **Removed `epd.Clear()` call** - Reduces update time from 30s to ~25s
- **Direct buffer display** - No intermediate refresh
- **Efficient image conversion** - Pre-processes 1-bit images

---

## Troubleshooting

### Error: "Waveshare EPD library not found"
**Solution**: Install Waveshare library to `/opt/waveshare-epd/`

### Error: "Font file not found"
**Solution**: Ensure fonts exist in `fonts/` directory:
```bash
ls -l fonts/icbmss20.ttf fonts/StardosStencilBold-9mzn.ttf
```

### Error: "Icon files are missing"
**Solution**: Place required PNG files in `icons/epd/`:
```bash
ls -l icons/epd/wifi_*.png icons/epd/wifi_notconnected.png icons/epd/warning.png
```

### Permission denied
**Solution**: Run with sudo for hardware access:
```bash
sudo python3 py/azazel_epd.py --state normal --ssid "Test" --ip "192.168.1.1"
```

### Display shows inverted colors
**Issue**: This was a known bug (fixed in current version)  
**Cause**: 1-bit mode interpretation (0=black, not 0=white)  
**Fix**: Updated `convert_to_1bit()` function

---

## Integration Examples

### From TUI (cli_unified.py)
```python
import subprocess

def update_epd_display(state: str, **kwargs):
    """Update EPD with current system state."""
    cmd = ["sudo", "python3", "py/azazel_epd.py", "--state", state]
    
    if state == "normal":
        cmd.extend(["--ssid", kwargs.get("ssid", "Unknown")])
        cmd.extend(["--ip", kwargs.get("ip", "0.0.0.0")])
        # Optional: pass Wi-Fi signal strength if available
        signal = kwargs.get("signal")
        if signal is not None:
            cmd.extend(["--signal", str(signal)])
    else:
        cmd.extend(["--msg", kwargs.get("msg", "Status Update")])
    
    subprocess.run(cmd, check=True)
```

### From systemd service
```ini
[Unit]
Description=Azazel EPD Status Display
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/azazel/azazel/py/azazel_epd.py --state normal --ssid "AzazelNet" --ip "172.16.0.1"
User=root

[Install]
WantedBy=multi-user.target
```

### Periodic updates with cron
```bash
# Update every 5 minutes
*/5 * * * * /usr/bin/python3 /home/azazel/azazel/py/azazel_epd.py --state normal --ssid "AzazelNet" --ip "172.16.0.1" 2>&1 | logger -t azazel-epd
```

---

## Color Rendering Details

### Black Layer (1-bit mode)
- `0` = black pixel
- `255` = white pixel
- Used for: text, icons, lines on NORMAL/WARNING/STALE

### Red Layer (1-bit mode)
- `0` = red pixel (display red)
- `255` = no red (leave white/black)
- Used for: DANGER state background

### White Knockout Technique (DANGER state)
```python
# Create white mask with text/icons
white_mask = Image.new('1', (250, 122), 0)  # Black background
draw.text((x, y), "DANGER", fill=255)       # White text

# Apply to red layer (makes text appear white)
red_img = ImageChops.lighter(red_img, white_mask)
```

---

## Version History

- **v2.1** (2026-01-06): Wi-Fi signal-aware NORMAL state
  - Added `--signal` CLI argument and dynamic icon selection
  - New Wi-Fi icon set (strong/medium/weak/disconnected)
  - Updated usage examples and integration snippet

- **v2** (2026-01-04): Complete rewrite with four states
  - Added icbmss20 font support
  - Implemented WARNING/DANGER/STALE states
  - Fixed icon color inversion bug
  - Optimized display refresh time
  - Added dry-run preview mode

- **v1**: Initial implementation (boot splash only)

---

## Future Enhancements

- [ ] Automatic state detection from system status
- [ ] Animation support for state transitions
- [ ] Partial refresh for faster updates
- [ ] QR code display for web portal access
- [ ] Battery level indicator
- [ ] Multi-language support
- [ ] Integration with First Minute detection

---

## License

Part of Azazel-Gadget project  
Repository: https://github.com/01rabbit/Azazel-Zero
