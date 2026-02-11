#!/usr/bin/env python3
"""
generate_profile.py - Profile Generator for Azazel-Gadget
snapshot.json から決定論的デプロイ用 YAML profile を生成
"""

import argparse
import json
import re
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

def parse_ip_addr(snapshot_dir: Path) -> Dict[str, Any]:
    """ip addr から interface 情報を抽出"""
    ip_addr_file = snapshot_dir / 'network' / 'ip_addr.txt'
    if not ip_addr_file.exists():
        return {}
    
    content = ip_addr_file.read_text()
    interfaces = {}
    
    current_if = None
    for line in content.split('\n'):
        # インターフェース名
        match = re.match(r'^\d+:\s+(\S+):', line)
        if match:
            current_if = match.group(1).replace('@NONE', '')
            interfaces[current_if] = {'addrs': [], 'state': 'DOWN'}
            continue
        
        # 状態
        if current_if and 'state UP' in line:
            interfaces[current_if]['state'] = 'UP'
        
        # IPv4アドレス
        if current_if:
            match = re.search(r'inet\s+(\S+)', line)
            if match:
                interfaces[current_if]['addrs'].append(match.group(1))
    
    return interfaces

def parse_ip_route(snapshot_dir: Path) -> Dict[str, Any]:
    """ip route からデフォルトゲートウェイを抽出"""
    route_file = snapshot_dir / 'network' / 'ip_route.txt'
    if not route_file.exists():
        return {}
    
    content = route_file.read_text()
    default_route = {}
    
    for line in content.split('\n'):
        if line.startswith('default'):
            match = re.search(r'via\s+(\S+)\s+dev\s+(\S+)', line)
            if match:
                default_route = {
                    'gateway': match.group(1),
                    'interface': match.group(2)
                }
                break
    
    return default_route

def parse_ss(snapshot_dir: Path) -> List[Dict[str, Any]]:
    """ss から listening sockets を抽出"""
    listeners = []
    
    for proto in ['tcp', 'udp']:
        ss_file = snapshot_dir / 'network' / f'ss_{proto}.txt'
        if not ss_file.exists():
            continue
        
        content = ss_file.read_text()
        for line in content.split('\n')[1:]:  # ヘッダー行をスキップ
            parts = line.split()
            if len(parts) < 5:
                continue
            
            # Local Address:Port
            local = parts[4] if len(parts) > 4 else ''
            if ':' in local:
                addr, port = local.rsplit(':', 1)
                
                # Process情報
                process = parts[-1] if len(parts) > 6 else ''
                pid_match = re.search(r'pid=(\d+)', process)
                pid = int(pid_match.group(1)) if pid_match else None
                
                listeners.append({
                    'proto': proto,
                    'addr': addr.replace('[', '').replace(']', ''),
                    'port': port,
                    'pid': pid,
                    'process': process
                })
    
    return listeners

def parse_firewall(snapshot_dir: Path) -> Dict[str, Any]:
    """ファイアウォール状態を解析"""
    fw = {'backend': None, 'nat_enabled': False, 'forward_enabled': False}
    
    # nftables優先
    nft_file = snapshot_dir / 'firewall' / 'nft_ruleset.txt'
    if nft_file.exists():
        content = nft_file.read_text()
        fw['backend'] = 'nftables'
        
        if 'type nat' in content or 'masquerade' in content.lower():
            fw['nat_enabled'] = True
        
        if 'chain forward' in content.lower():
            fw['forward_enabled'] = True
    
    # iptables (fallback)
    iptables_nat = snapshot_dir / 'firewall' / 'iptables_nat.txt'
    if iptables_nat.exists() and not fw['backend']:
        content = iptables_nat.read_text()
        fw['backend'] = 'iptables'
        
        if 'MASQUERADE' in content:
            fw['nat_enabled'] = True
    
    return fw

def parse_systemd_services(snapshot_dir: Path) -> List[Dict[str, Any]]:
    """systemd サービス情報を抽出"""
    services = []
    services_dir = snapshot_dir / 'services'
    
    if not services_dir.exists():
        return services
    
    # Azazel関連サービス
    for service_file in services_dir.glob('*_show.txt'):
        service_name = service_file.stem.replace('_show', '')
        
        content = service_file.read_text()
        
        # ExecStart抽出
        exec_start = None
        for line in content.split('\n'):
            if line.startswith('ExecStart='):
                exec_start = line.split('=', 1)[1].strip()
                break
        
        # 状態
        active_state = None
        for line in content.split('\n'):
            if line.startswith('ActiveState='):
                active_state = line.split('=', 1)[1].strip()
                break
        
        services.append({
            'name': service_name,
            'exec_start': exec_start,
            'active_state': active_state
        })
    
    return services

def parse_tc(snapshot_dir: Path, interface: str) -> Dict[str, Any]:
    """tc（トラフィック制御）状態を抽出"""
    tc_file = snapshot_dir / 'network' / f'tc_{interface}.txt'
    if not tc_file.exists():
        return {'enabled': False}
    
    content = tc_file.read_text()
    
    # qdiscが設定されているか
    if 'qdisc noqueue' in content or 'qdisc pfifo_fast' in content:
        return {'enabled': False}
    
    # HTB or netemなどが設定されている
    if any(qdisc in content for qdisc in ['htb', 'netem', 'tbf', 'sfq']):
        return {
            'enabled': True,
            'details': content.strip()
        }
    
    return {'enabled': False}

def infer_azazel_topology(interfaces: Dict, default_route: Dict, listeners: List[Dict]) -> Dict[str, Any]:
    """
    Azazel-Gadgetトポロジーを推論
    - inside_if: 10.55.0.10 を持つインターフェース（usb0想定）
    - outside_if: デフォルトルートのインターフェース（wlan0想定）
    """
    inside_if = None
    inside_ip = None
    outside_if = None
    outside_ip = None
    
    # 10.55.0.10 を探す（管理IP）
    for if_name, if_data in interfaces.items():
        for addr in if_data.get('addrs', []):
            if addr.startswith('10.55.0.10'):
                inside_if = if_name
                inside_ip = addr.split('/')[0]
                break
    
    # デフォルトルートから外向きIFを推論
    if default_route:
        outside_if = default_route.get('interface')
        # 外向きIPはDHCPで変動するため、現在の値を記録
        if outside_if and outside_if in interfaces:
            addrs = interfaces[outside_if].get('addrs', [])
            if addrs:
                outside_ip = addrs[0].split('/')[0]
    
    return {
        'inside_if': inside_if or 'usb0',  # デフォルト
        'inside_ip': inside_ip or '10.55.0.10',
        'outside_if': outside_if or 'wlan0',  # デフォルト
        'outside_ip': outside_ip,  # None可（DHCP）
    }

def generate_profile(snapshot_dir: Path) -> Dict[str, Any]:
    """スナップショットから profile を生成"""
    
    # meta情報
    meta = {}
    meta_file = snapshot_dir / 'meta.json'
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
    
    # 各種解析
    interfaces = parse_ip_addr(snapshot_dir)
    default_route = parse_ip_route(snapshot_dir)
    listeners = parse_ss(snapshot_dir)
    firewall = parse_firewall(snapshot_dir)
    services = parse_systemd_services(snapshot_dir)
    topology = infer_azazel_topology(interfaces, default_route, listeners)
    
    # トラフィック制御（外向きIFのみ）
    tc_state = parse_tc(snapshot_dir, topology['outside_if'])
    
    # 管理UIリスナー検出
    mgmt_ui_port = None
    for listener in listeners:
        if listener['addr'] in ['0.0.0.0', topology['inside_ip'], '*'] and listener['port'] in ['8081', '80', '443']:
            if 'azazel' in listener.get('process', '').lower() or 'python' in listener.get('process', ''):
                mgmt_ui_port = listener['port']
                break
    
    # OpenCanaryリスナー検出
    opencanary_enabled = any('opencanary' in s['name'] for s in services if s.get('active_state') == 'active')
    
    # Suricata検出
    suricata_enabled = any('suricata' in s['name'] for s in services if s.get('active_state') == 'active')
    
    # ntfy検出（config/first_minute.yaml から）
    ntfy_mode = 'none'
    first_minute_yaml = snapshot_dir / 'config' / 'configs' / 'first_minute.yaml'
    if first_minute_yaml.exists():
        try:
            fm_config = yaml.safe_load(first_minute_yaml.read_text())
            if 'ntfy' in fm_config:
                if fm_config['ntfy'].get('enabled'):
                    ntfy_mode = fm_config['ntfy'].get('mode', 'client')
        except:
            pass
    
    # Profile生成
    profile = {
        'profile_version': '1.0',
        'generated_at': datetime.now().isoformat(),
        'source_snapshot': {
            'hostname': meta.get('hostname', 'unknown'),
            'collected_at': meta.get('collected_at', 'unknown'),
            'snapshot_dir': str(snapshot_dir),
        },
        
        # 必須トポロジー
        'topology': {
            'inside_if': topology['inside_if'],
            'inside_ip': topology['inside_ip'],
            'outside_if': topology['outside_if'],
            'outside_ip_dhcp': topology['outside_ip'] is None or True,  # DHCPが標準
        },
        
        # 必須：NAT/Forward
        'network': {
            'nat_enabled': firewall['nat_enabled'],
            'ip_forward': True,  # NAT有効なら必須
            'firewall_backend': firewall['backend'] or 'nftables',
        },
        
        # 必須：管理UI
        'management_ui': {
            'enabled': mgmt_ui_port is not None,
            'port': mgmt_ui_port or 8081,
            'bind_inside_only': True,  # usb0側のみ
        },
        
        # 必須：Suricata
        'suricata': {
            'enabled': suricata_enabled,
            'monitor_interface': topology['outside_if'],  # wlan0のみ
        },
        
        # 任意：OpenCanary
        'opencanary': {
            'enabled': opencanary_enabled,
            'expose_outside': True,  # wlan0側へ公開
        },
        
        # 任意：Traffic Control
        'traffic_control': {
            'enabled': tc_state['enabled'],
            'interface': topology['outside_if'],
        },
        
        # 任意：ntfy
        'ntfy': {
            'mode': ntfy_mode,  # client/server/none
        },
        
        # SSH（USB経由維持は絶対条件）
        'ssh': {
            'enabled': True,
            'key_only': True,
            'allow_inside': True,  # usb0経由
        },
        
        # systemd services
        'services': [s for s in services if s.get('active_state') == 'active'],
    }
    
    return profile

def main():
    parser = argparse.ArgumentParser(description='Generate deployment profile from snapshot')
    parser.add_argument('--snapshot', type=Path, required=True, help='snapshot.json or snapshot directory')
    parser.add_argument('--out', type=Path, help='Output profile YAML path')
    
    args = parser.parse_args()
    
    # snapshot.json or directory
    if args.snapshot.is_file():
        snapshot_data = json.loads(args.snapshot.read_text())
        snapshot_dir = Path(snapshot_data['snapshot_dir'])
    else:
        snapshot_dir = args.snapshot
    
    if not snapshot_dir.exists():
        print(f"ERROR: Snapshot directory not found: {snapshot_dir}")
        return 1
    
    print(f"=== Generating Profile ===")
    print(f"Source: {snapshot_dir}")
    print()
    
    # Profile生成
    profile = generate_profile(snapshot_dir)
    
    # 出力パス決定
    if args.out:
        out_path = args.out
    else:
        timestamp = datetime.now().strftime('%Y%m%d')
        out_path = Path('installer/profiles') / f'gadget_profile_{timestamp}.yaml'
        out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # YAML出力
    out_path.write_text(yaml.dump(profile, default_flow_style=False, allow_unicode=True, sort_keys=False))
    
    print(f"Profile generated: {out_path}")
    print()
    print("Next steps:")
    print(f"  # 新機でdry-run:")
    print(f"  sudo installer/apply.sh --profile {out_path} --dry-run")
    print(f"  # 新機で適用:")
    print(f"  sudo installer/apply.sh --profile {out_path}")
    print(f"  # 検証:")
    print(f"  sudo installer/validate.sh --profile {out_path}")
    
    return 0

if __name__ == '__main__':
    exit(main())
