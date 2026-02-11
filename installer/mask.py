#!/usr/bin/env python3
"""
mask.py - Secret Masking for Azazel-Gadget Snapshots
秘匿情報（SSID/PSK、ntfy token、API keys等）を ***MASKED*** に置換し、Git commit可能に
"""

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Any

# マスク対象パターン
MASK_PATTERNS = [
    # Wi-Fi PSK (NetworkManager connections, dhcpcd.conf)
    (r'(psk=)([^\s]+)', r'\1***MASKED***'),
    (r'(ssid=)([^\s]+)', r'\1***MASKED***'),
    
    # ntfy.sh tokens
    (r'(ntfy_token:?\s*["\']?)([a-zA-Z0-9_\-]+)(["\']?)', r'\1***MASKED***\3'),
    (r'(Authorization:\s*Bearer\s+)([a-zA-Z0-9_\-]+)', r'\1***MASKED***'),
    
    # API keys (generic)
    (r'(api_key:?\s*["\']?)([a-zA-Z0-9_\-]+)(["\']?)', r'\1***MASKED***\3'),
    (r'(API_KEY=)([^\s]+)', r'\1***MASKED***'),
    
    # Passwords (generic)
    (r'(password:?\s*["\']?)([^\s"\']+)(["\']?)', r'\1***MASKED***\3'),
    (r'(PASSWORD=)([^\s]+)', r'\1***MASKED***'),
    
    # OpenCanary API keys
    (r'("device.node_id":\s*")(.*?)(")', r'\1***MASKED***\3'),
    
    # Suricata HOME_NET (IPアドレスは保持、ただしプライベートIP以外はマスク)
    # 公開IPをマスク（10.x, 172.16-31.x, 192.168.x は残す）
]

def should_mask_ip(ip: str) -> bool:
    """公開IPかどうかを判定（公開IPの場合True=マスク対象）"""
    # プライベートIP範囲は保持
    private_patterns = [
        r'^10\.',
        r'^172\.(1[6-9]|2[0-9]|3[0-1])\.',
        r'^192\.168\.',
        r'^127\.',
        r'^169\.254\.',
    ]
    for pattern in private_patterns:
        if re.match(pattern, ip):
            return False
    return True

def mask_file(file_path: Path) -> bool:
    """
    ファイル内の秘匿情報をマスク
    Returns: True if file was modified
    """
    if not file_path.is_file():
        return False
    
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return False
    
    original_content = content
    
    # パターンマッチング
    for pattern, replacement in MASK_PATTERNS:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
    
    # IPアドレスマスク（公開IPのみ）
    def mask_public_ip(match):
        ip = match.group(0)
        if should_mask_ip(ip):
            return '***MASKED_IP***'
        return ip
    
    # IPv4アドレスパターン（文脈を考慮して公開IPをマスク）
    # ただし、10.55.0.10 のような内部IPは保持
    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    # HOME_NET行などは慎重に処理（コメント行は除外）
    lines = content.split('\n')
    masked_lines = []
    for line in lines:
        # コメント行や設定のキー部分は除外
        if not line.strip().startswith('#'):
            # IPアドレスを検出してマスク判定
            line = re.sub(ip_pattern, mask_public_ip, line)
        masked_lines.append(line)
    content = '\n'.join(masked_lines)
    
    if content != original_content:
        file_path.write_text(content, encoding='utf-8')
        return True
    
    return False

def mask_snapshot(snapshot_dir: Path) -> Dict[str, Any]:
    """
    スナップショットディレクトリ全体をマスク
    """
    masked_files = []
    total_files = 0
    
    # 再帰的にすべてのファイルを処理
    for file_path in snapshot_dir.rglob('*'):
        if file_path.is_file():
            total_files += 1
            
            # バイナリファイルはスキップ
            if file_path.suffix in ['.bin', '.so', '.pyc']:
                continue
            
            if mask_file(file_path):
                masked_files.append(str(file_path.relative_to(snapshot_dir)))
    
    return {
        'total_files': total_files,
        'masked_files': len(masked_files),
        'files': masked_files
    }

def generate_snapshot_json(snapshot_dir: Path) -> Path:
    """
    snapshot/ 配下の raw データから snapshot.json を生成
    （簡易版：後続の generate_profile.py で詳細解析）
    """
    json_path = snapshot_dir / 'snapshot.json'
    
    # meta.json を読み込み
    meta = {}
    meta_path = snapshot_dir / 'meta.json'
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    
    snapshot_data = {
        'meta': meta,
        'snapshot_dir': str(snapshot_dir),
        'raw_data': {
            'network': str(snapshot_dir / 'network'),
            'firewall': str(snapshot_dir / 'firewall'),
            'services': str(snapshot_dir / 'services'),
            'system': str(snapshot_dir / 'system'),
            'config': str(snapshot_dir / 'config'),
        },
        'masked': True,
        'note': 'This is a raw snapshot. Use generate_profile.py to create deployment profile.'
    }
    
    json_path.write_text(json.dumps(snapshot_data, indent=2, ensure_ascii=False))
    return json_path

def main():
    parser = argparse.ArgumentParser(description='Mask secrets in Azazel-Gadget snapshot')
    parser.add_argument('--snapshot', type=Path, required=True, help='Snapshot directory path')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be masked without modifying')
    
    args = parser.parse_args()
    
    if not args.snapshot.exists():
        print(f"ERROR: Snapshot directory not found: {args.snapshot}")
        return 1
    
    print(f"=== Masking Secrets in Snapshot ===")
    print(f"Directory: {args.snapshot}")
    print()
    
    if args.dry_run:
        print("DRY-RUN mode: No files will be modified")
        print()
    
    # バックアップ作成（dry-runでない場合）
    if not args.dry_run:
        backup_dir = args.snapshot.parent / f"{args.snapshot.name}_backup"
        if not backup_dir.exists():
            print(f"Creating backup: {backup_dir}")
            shutil.copytree(args.snapshot, backup_dir)
    
    # マスク実行
    result = mask_snapshot(args.snapshot)
    
    print(f"Total files: {result['total_files']}")
    print(f"Masked files: {result['masked_files']}")
    
    if result['files']:
        print("\nMasked files:")
        for f in result['files']:
            print(f"  - {f}")
    
    # snapshot.json生成
    if not args.dry_run:
        json_path = generate_snapshot_json(args.snapshot)
        print(f"\nGenerated: {json_path}")
        print("\nNext step:")
        print(f"  python3 installer/generate_profile.py --snapshot {json_path}")
    
    return 0

if __name__ == '__main__':
    exit(main())
