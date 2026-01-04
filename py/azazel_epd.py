#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Azazel EPD Controller for Waveshare 2.13inch e-Paper HAT (B) V4
3-color display (Black/White/Red) - 250x122 pixels

Dependencies:
  - Python 3.7+
  - Pillow (PIL)
  - waveshare_epd (for hardware control)

Usage:
  # NORMAL state
  python3 py/azazel_epd.py --state normal --ssid "AzazelNet" --ip "172.16.0.1" --signal 72
  
  # WARNING state
  python3 py/azazel_epd.py --state warning --msg "CHECK WEB"
  
  # DANGER state
  python3 py/azazel_epd.py --state danger --msg "REMOVE DEVICE"
  
  # STALE state
  python3 py/azazel_epd.py --state stale --msg "NO UPDATE"
  
  # Dry-run mode (preview only)
  python3 py/azazel_epd.py --state danger --msg "TEST" --dry-run

Icon files in icons/epd/:
  - wifi_3.png / wifi_2.png / wifi_1.png (signal strength)
  - wifi_notconnected.png (not connected)
  - warning.png (for WARNING state)
  - danger.png (for DANGER state)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple, Optional

try:
    from PIL import Image, ImageDraw, ImageFont, ImageChops
except ImportError:
    print("ERROR: Pillow is required. Install with: pip3 install pillow")
    sys.exit(1)

# Waveshare EPD library paths
WS_ROOT = "/opt/waveshare-epd/RaspberryPi_JetsonNano/python"
WS_LIB = "/opt/waveshare-epd/RaspberryPi_JetsonNano/python/lib"

# Display specifications
EPD_WIDTH = 250
EPD_HEIGHT = 122

# Icon file names (user-replaceable in icons/epd/)
ICON_WIFI_STRONG = "wifi_3.png"      # Signal >= 70
ICON_WIFI_MEDIUM = "wifi_2.png"      # Signal >= 50
ICON_WIFI_WEAK = "wifi_1.png"        # Signal >= 0
ICON_WIFI_DISCONNECTED = "wifi_notconnected.png"  # No connection
ICON_WARNING = "warning.png"
ICON_DANGER = "danger.png"


def check_icon_files(icon_dir: Path) -> None:
    """
    Check if required icon files exist.
    Exit with clear error message if any are missing.
    """
    required_icons = [
        ICON_WIFI_STRONG, ICON_WIFI_MEDIUM, ICON_WIFI_WEAK, ICON_WIFI_DISCONNECTED,
        ICON_WARNING, ICON_DANGER
    ]
    missing = []
    
    for icon_name in required_icons:
        icon_path = icon_dir / icon_name
        if not icon_path.exists():
            missing.append(str(icon_path))
    
    if missing:
        print("ERROR: Required icon files are missing:")
        for path in missing:
            print(f"  - {path}")
        print("\nPlease place the following PNG files in icons/epd/ directory:")
        print(f"  - {ICON_WIFI_STRONG} (Wi-Fi icon - strong signal)")
        print(f"  - {ICON_WIFI_MEDIUM} (Wi-Fi icon - medium signal)")
        print(f"  - {ICON_WIFI_WEAK} (Wi-Fi icon - weak signal)")
        print(f"  - {ICON_WIFI_DISCONNECTED} (Wi-Fi icon - not connected)")
        print(f"  - {ICON_WARNING} (Warning icon for WARNING state)")
        print(f"  - {ICON_DANGER} (Danger icon for DANGER state)")
        sys.exit(1)


def load_font(size: int, font_name: str = "stardos") -> ImageFont.FreeTypeFont:
    """Load font. Use 'icbm' for icbmss20.ttf or 'stardos' for StardosStencilBold-9mzn.ttf."""
    # Get project root (parent of py/)
    script_dir = Path(__file__).parent
    asset_root = script_dir.parent
    
    if font_name == "icbm":
        font_path = asset_root / "fonts" / "icbmss20.ttf"
    else:  # stardos
        font_path = asset_root / "fonts" / "StardosStencilBold-9mzn.ttf"
    
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception as e:
            print(f"ERROR: Failed to load font {font_path}: {e}")
            sys.exit(1)
    else:
        print(f"ERROR: Font file not found: {font_path}")
        sys.exit(1)


def load_icon_with_transparency(icon_path: Path, max_size: int = 48) -> Image.Image:
    """
    Load PNG icon and resize while preserving transparency.
    Returns RGBA image.
    """
    try:
        icon = Image.open(icon_path).convert("RGBA")
        
        # Resize if needed
        width, height = icon.size
        if max(width, height) > max_size:
            if width > height:
                new_width = max_size
                new_height = int(height * max_size / width)
            else:
                new_height = max_size
                new_width = int(width * max_size / height)
            
            icon = icon.resize((new_width, new_height), Image.LANCZOS)
        
        return icon
    except Exception as e:
        print(f"ERROR: Failed to load icon {icon_path}: {e}")
        sys.exit(1)


def convert_to_1bit(img: Image.Image, invert: bool = False) -> Image.Image:
    """
    Convert image to 1-bit mode.
    In 1-bit mode: 0=black pixel, 255=white pixel
    For icons: dark parts of icon should be black (0), light/transparent should be white (255)
    """
    # Convert RGBA to grayscale, considering both color and alpha
    if img.mode == 'RGBA':
        # Create white background
        bg = Image.new('RGB', img.size, (255, 255, 255))
        # Composite RGBA over white background
        bg.paste(img, mask=img.split()[3])  # Use alpha as mask
        gray = bg.convert('L')
    else:
        gray = img.convert('L')
    
    # Threshold to 1-bit: dark becomes 0 (black), light becomes 255 (white)
    if invert:
        # Invert: dark becomes 255 (white), light becomes 0 (black)
        return gray.point(lambda p: 255 if p < 128 else 0, mode='1')
    else:
        # Normal: dark becomes 0 (black), light becomes 255 (white)
        return gray.point(lambda p: 0 if p < 128 else 255, mode='1')


def render_normal(ssid: str, ip: str, icon_dir: Path, signal: Optional[int] = None) -> Tuple[Image.Image, Image.Image]:
    """
    Render NORMAL state:
    - White background
    - Wi-Fi icon (top-left, black) - changes based on signal strength
    - IP address (center, large, black)
    - SSID (bottom, small, black)
    
    Args:
        ssid: Wi-Fi SSID ("Not Connected" if unavailable)
        ip: IP address ("0.0.0.0" if unavailable)
        icon_dir: Path to icon directory
        signal: Signal strength (0-100) or None for disconnected
    """
    # Create 1-bit images: 0=black, 255=white for display; 0=no red, 255=red for red layer
    black_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 255)  # White background
    red_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 255)    # No red
    
    draw_black = ImageDraw.Draw(black_img)
    
    # Load fonts - StardosStencilBold for NORMAL state
    font_ip = load_font(23, "stardos")  # IP address - 23pt
    font_ssid = load_font(20, "stardos")  # SSID - 20pt
    
    # Select Wi-Fi icon based on signal strength
    if signal is None or signal < 0:
        wifi_icon_name = ICON_WIFI_DISCONNECTED
    elif signal >= 70:
        wifi_icon_name = ICON_WIFI_STRONG
    elif signal >= 50:
        wifi_icon_name = ICON_WIFI_MEDIUM
    else:
        wifi_icon_name = ICON_WIFI_WEAK
    
    # Load and paste Wi-Fi icon (left side, black)
    wifi_icon_path = icon_dir / wifi_icon_name
    wifi_icon = load_icon_with_transparency(wifi_icon_path, max_size=45)
    wifi_icon_1bit = convert_to_1bit(wifi_icon, invert=False)
    icon_x = 10
    icon_y = 8
    black_img.paste(wifi_icon_1bit, (icon_x, icon_y))
    
    # Draw IP address next to icon (20pt, black)
    ip_x = icon_x + 55  # Icon width + small gap
    ip_y = 20
    draw_black.text((ip_x, ip_y), ip, fill=0, font=font_ip)  # 0=black
    
    # Draw horizontal line
    line_y = 65
    line_margin = 10
    draw_black.line([(line_margin, line_y), (EPD_WIDTH - line_margin, line_y)], fill=0, width=2)
    
    # Draw SSID (bottom center, 30pt)
    ssid_bbox = draw_black.textbbox((0, 0), ssid, font=font_ssid)
    ssid_width = ssid_bbox[2] - ssid_bbox[0]
    ssid_x = (EPD_WIDTH - ssid_width) // 2
    ssid_y = 80
    draw_black.text((ssid_x, ssid_y), ssid, fill=0, font=font_ssid)  # 0=black
    
    return black_img, red_img


def render_warning(msg: str, icon_dir: Path) -> Tuple[Image.Image, Image.Image]:
    """
    Render WARNING state:
    - White background
    - Warning icons on left and right (BLACK, 30pt size)
    - "WARNING" text (center, 30pt, black)
    - Horizontal line dividing screen in half
    - Message (bottom half, 30pt, black)
    """
    # Create layers
    black_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 255)  # White background
    red_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 255)    # No red
    
    draw_black = ImageDraw.Draw(black_img)
    
    # Load fonts - icbmss20 for WARNING state
    font_warning = load_font(35, "icbm")  # WARNING
    font_message = load_font(28, "icbm")  # Message
    
    # Load warning icon and convert to 1-bit for BLACK layer (35pt size)
    warning_icon_path = icon_dir / ICON_WARNING
    warning_icon = load_icon_with_transparency(warning_icon_path, max_size=35)
    warning_icon_1bit = convert_to_1bit(warning_icon, invert=False)
    
    # Place warning icons in BLACK on left and right
    icon_left_x = 10
    icon_right_x = EPD_WIDTH - 45  # 10px margin + 35px icon
    icon_y = 15
    black_img.paste(warning_icon_1bit, (icon_left_x, icon_y))
    black_img.paste(warning_icon_1bit, (icon_right_x, icon_y))
    
    # Draw "WARNING" text in black (center, top half)
    warning_bbox = draw_black.textbbox((0, 0), "WARNING", font=font_warning)
    warning_width = warning_bbox[2] - warning_bbox[0]
    warning_x = (EPD_WIDTH - warning_width) // 2
    warning_y = 15
    draw_black.text((warning_x, warning_y), "WARNING", fill=0, font=font_warning)  # 0=black
    
    # Draw horizontal line dividing screen in half (y=61 for 122px height)
    line_y = EPD_HEIGHT // 2
    line_margin = 10
    draw_black.line([(line_margin, line_y), (EPD_WIDTH - line_margin, line_y)], fill=0, width=2)
    
    # Draw message (bottom half, centered, 30pt, black)
    msg_bbox = draw_black.textbbox((0, 0), msg, font=font_message)
    msg_width = msg_bbox[2] - msg_bbox[0]
    msg_x = (EPD_WIDTH - msg_width) // 2
    msg_y = line_y + 15
    draw_black.text((msg_x, msg_y), msg, fill=0, font=font_message)  # 0=black
    
    return black_img, red_img


def render_danger(msg: str, icon_dir: Path) -> Tuple[Image.Image, Image.Image]:
    """
    Render DANGER state:
    - Red background
    - Warning icons on left and right (BLACK, 35pt size)
    - "DANGER" text (center, 35pt, white)
    - Horizontal line dividing screen in half
    - Message (bottom half, 25pt, white)
    """
    # Create layers
    black_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 255)  # White background
    red_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 0)      # All red background
    
    draw_black = ImageDraw.Draw(black_img)
    
    # Create white mask for text (where red should be knocked out to white)
    white_mask = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 0)   # Black background
    draw_white = ImageDraw.Draw(white_mask)
    
    # Load fonts - icbmss20 for DANGER state
    font_danger = load_font(35, "icbm")
    font_message = load_font(25, "icbm")
    
    # Load warning icon and convert to white (40pt size)
    warning_icon_path = icon_dir / ICON_WARNING
    warning_icon = load_icon_with_transparency(warning_icon_path, max_size=40)
    warning_icon_white = convert_to_1bit(warning_icon, invert=True)  # White mask for knockout
    
    # Place warning icons in WHITE on white mask (knockout from red)
    icon_left_x = 10
    icon_right_x = EPD_WIDTH - 50  # 10px margin + 40px icon
    icon_y = 15
    white_mask.paste(warning_icon_white, (icon_left_x, icon_y))
    white_mask.paste(warning_icon_white, (icon_right_x, icon_y))
    
    # Draw "DANGER" text in white on white mask (center, top half, 35pt)
    danger_bbox = draw_white.textbbox((0, 0), "DANGER", font=font_danger)
    danger_width = danger_bbox[2] - danger_bbox[0]
    danger_x = (EPD_WIDTH - danger_width) // 2
    danger_y = 15
    draw_white.text((danger_x, danger_y), "DANGER", fill=255, font=font_danger)  # 255=white
    
    # Draw horizontal line dividing screen in half (y=61 for 122px height)
    line_y = EPD_HEIGHT // 2
    line_margin = 10
    draw_white.line([(line_margin, line_y), (EPD_WIDTH - line_margin, line_y)], fill=255, width=2)
    
    # Draw message (bottom half, centered, 25pt, white)
    msg_bbox = draw_white.textbbox((0, 0), msg, font=font_message)
    msg_width = msg_bbox[2] - msg_bbox[0]
    msg_x = (EPD_WIDTH - msg_width) // 2
    msg_y = line_y + 15
    draw_white.text((msg_x, msg_y), msg, fill=255, font=font_message)  # 255=white
    
    # Apply white knockout: use ImageChops.lighter to OR the white parts onto red
    red_img = ImageChops.lighter(red_img, white_mask)
    
    return black_img, red_img


def render_stale(msg: str, icon_dir: Path) -> Tuple[Image.Image, Image.Image]:
    """
    Render STALE state:
    - White background
    - "STALE" text in upper half (black, icbmss20, 35pt)
    - Horizontal line dividing screen in half
    - "NO UPDATE" and "CHECK WEB PORTAL" in lower half (black, icbmss20, 20pt, 2 lines)
    """
    # Create layers
    black_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 255)  # White background
    red_img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 255)    # No red
    
    draw_black = ImageDraw.Draw(black_img)
    
    # Load fonts - icbmss20 for STALE state
    font_stale = load_font(35, "icbm")    # STALE
    font_message = load_font(20, "icbm")  # Messages
    
    # Draw "STALE" text in upper half (black, centered)
    stale_bbox = draw_black.textbbox((0, 0), "STALE", font=font_stale)
    stale_width = stale_bbox[2] - stale_bbox[0]
    stale_x = (EPD_WIDTH - stale_width) // 2
    stale_y = 15
    draw_black.text((stale_x, stale_y), "STALE", fill=0, font=font_stale)  # 0=black
    
    # Draw horizontal line dividing screen in half (y=61 for 122px height)
    line_y = EPD_HEIGHT // 2
    line_margin = 10
    draw_black.line([(line_margin, line_y), (EPD_WIDTH - line_margin, line_y)], fill=0, width=2)
    
    # Draw "NO UPDATE" in lower half, first line (black, centered)
    msg1_text = "NO UPDATE"
    msg1_bbox = draw_black.textbbox((0, 0), msg1_text, font=font_message)
    msg1_width = msg1_bbox[2] - msg1_bbox[0]
    msg1_x = (EPD_WIDTH - msg1_width) // 2
    msg1_y = line_y + 10
    draw_black.text((msg1_x, msg1_y), msg1_text, fill=0, font=font_message)  # 0=black
    
    # Draw "CHECK WEB PORTAL" in lower half, second line (black, centered)
    msg2_text = "CHECK WEB PORTAL"
    msg2_bbox = draw_black.textbbox((0, 0), msg2_text, font=font_message)
    msg2_width = msg2_bbox[2] - msg2_bbox[0]
    msg2_x = (EPD_WIDTH - msg2_width) // 2
    msg2_y = msg1_y + 25
    draw_black.text((msg2_x, msg2_y), msg2_text, fill=0, font=font_message)  # 0=black
    
    return black_img, red_img


def save_preview(black_img: Image.Image, red_img: Image.Image, state: str) -> None:
    """
    Save preview images for debugging.
    Generates:
    - Black layer preview
    - Red layer preview
    - Composite preview (visual representation)
    """
    base = f"/tmp/azazel_epd_preview_{state}"
    
    # Save black layer
    black_img.save(f"{base}_black.png")
    
    # Save red layer
    red_img.save(f"{base}_red.png")
    
    # Create composite RGB image for visual preview
    composite = Image.new('RGB', (EPD_WIDTH, EPD_HEIGHT), (255, 255, 255))  # White bg
    
    # Convert 1-bit to RGB arrays
    black_pixels = black_img.load()
    red_pixels = red_img.load()
    composite_pixels = composite.load()
    
    for y in range(EPD_HEIGHT):
        for x in range(EPD_WIDTH):
            # In 1-bit mode: 0=black/red, 255=white/off
            is_black = black_pixels[x, y] == 0
            is_red = red_pixels[x, y] == 0
            
            if is_black:
                composite_pixels[x, y] = (0, 0, 0)  # Black
            elif is_red:
                composite_pixels[x, y] = (255, 0, 0)  # Red
            else:
                composite_pixels[x, y] = (255, 255, 255)  # White
    
    composite.save(f"{base}_composite.png")
    
    print("✓ Preview saved:")
    print(f"  Black layer: {base}_black.png")
    print(f"  Red layer:   {base}_red.png")
    print(f"  Composite:   {base}_composite.png")


def display_to_epd(black_img: Image.Image, red_img: Image.Image) -> None:
    """
    Display images to actual EPD hardware.
    Uses Waveshare epd2in13b_V4 driver.
    """
    # Add Waveshare library to path
    for p in (WS_ROOT, WS_LIB):
        if p not in sys.path:
            sys.path.append(p)
    
    epd = None
    try:
        from waveshare_epd import epd2in13b_V4
        epd = epd2in13b_V4.EPD()
    except ImportError as e:
        print("ERROR: Waveshare EPD library not found.")
        print(f"Details: {e}")
        print("\nMake sure the library is installed at:")
        print(f"  {WS_LIB}")
        print("\nOr use --dry-run to test without hardware.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to initialize EPD: {e}")
        sys.exit(1)
    
    try:
        print("Initializing EPD...")
        epd.init()
        
        print("Sending image data...")
        # Convert 1-bit images to buffers
        black_buffer = epd.getbuffer(black_img)
        red_buffer = epd.getbuffer(red_img)
        
        # Display both layers (skip Clear() to save time)
        epd.display(black_buffer, red_buffer)
        
        print("Putting EPD to sleep...")
        epd.sleep()
        
        print("✓ Display updated successfully")
        
    except Exception as e:
        print(f"ERROR: EPD operation failed: {e}")
        import traceback
        traceback.print_exc()
        if epd:
            try:
                epd.sleep()
            except:
                pass
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Azazel EPD Controller for Waveshare 2.13" e-Paper HAT (B) V4',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --state normal --ssid "AzazelNet" --ip "172.16.0.1"
  %(prog)s --state warning --msg "CHECK WEB"
  %(prog)s --state danger --msg "REMOVE DEVICE"
  %(prog)s --state stale --msg "NO UPDATE"
  %(prog)s --state danger --msg "TEST" --dry-run
        """
    )
    
    parser.add_argument('--state', required=True, 
                       choices=['normal', 'warning', 'danger', 'stale'],
                       help='Display state')
    parser.add_argument('--ssid', help='Wi-Fi SSID (for normal state)')
    parser.add_argument('--ip', help='IP address (for normal state)')
    parser.add_argument('--signal', type=int, help='Wi-Fi signal strength 0-100 (for normal state)')
    parser.add_argument('--msg', help='Message (for warning/danger/stale states)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Generate preview only, do not update EPD')
    
    args = parser.parse_args()
    
    # Get icon directory: icons/epd/ relative to project root
    script_dir = Path(__file__).parent
    icon_dir = script_dir.parent / "icons" / "epd"
    
    # Check icon files exist
    check_icon_files(icon_dir)
    
    # Validate arguments
    if args.state == 'normal':
        if not args.ssid or not args.ip:
            parser.error("--ssid and --ip are required for normal state")
    else:
        if not args.msg:
            parser.error(f"--msg is required for {args.state} state")
    
    # Render appropriate state
    print(f"Rendering {args.state.upper()} state...")
    
    if args.state == 'normal':
        black_img, red_img = render_normal(args.ssid, args.ip, icon_dir, args.signal)
    elif args.state == 'warning':
        black_img, red_img = render_warning(args.msg, icon_dir)
    elif args.state == 'danger':
        black_img, red_img = render_danger(args.msg, icon_dir)
    elif args.state == 'stale':
        black_img, red_img = render_stale(args.msg, icon_dir)
    
    # Output
    if args.dry_run:
        save_preview(black_img, red_img, args.state)
    else:
        display_to_epd(black_img, red_img)


if __name__ == '__main__':
    main()
