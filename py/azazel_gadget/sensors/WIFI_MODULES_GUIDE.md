# Wi-Fi モジュール構成ガイド

## 📁 ディレクトリ構造

```
py/
├── azazel_gadget/
│   └── sensors/              # センサーモジュール（データ収集・分析）
│       ├── wifi_scanner.py          ✅ [共通] iw scan パーサー
│       ├── wifi_safety.py           ✅ [センサー] 脅威検知（MITM/Evil Twin/DNS）
│       ├── wifi_channel_scanner.py  ✅ [センサー] チャンネル混雑度分析
│       └── wifi_health_monitor.py   ✅ [NEW] ヘルスチェック統合モジュール
│
└── azazel_control/           # 制御モジュール（Web UI バックエンド）
    ├── wifi_scan.py                 ✅ [制御] AP一覧取得（環境自動検出）
    └── wifi_connect.py              ✅ [制御] AP接続+NAT設定

```

---

## 🎯 モジュール別機能一覧

### ✅ センサー層（sensors/）

#### 1. **wifi_scanner.py** - 共通スキャナー基盤
**目的**: iw scan の実行・パース・重複排除  
**提供機能**:
- `scan_and_parse()` - スキャン実行+パース+重複排除
- `parse_iw_scan()` - iw 出力の構造化
- `get_security_label()` - セキュリティラベル判定（OPEN/WPA/WPA2/WPA3）
- `deduplicate_by_ssid()` - SSID 重複排除（最強シグナル保持）

**依存**: なし  
**利用者**: wifi_scan.py, ssid_list.py

---

#### 2. **wifi_safety.py** - Wi-Fi 脅威検知センサー
**目的**: MITM・Evil Twin・DNS スプーフィング検知  
**提供機能**:
- `get_link_state()` - 接続中のAP情報取得
- `evaluate_wifi_safety()` - 脅威評価（judge_zero統合）
- `detect_evil_twin()` - Evil Twin AP検知
- `detect_dns_spoof()` - DNS スプーフィング検知
- `detect_mitm()` - MITM攻撃検知

**依存**: app/threat_judge.py  
**利用者**: first_minute/controller.py

---

#### 3. **wifi_channel_scanner.py** - チャンネル分析センサー
**目的**: Wi-Fiチャンネル混雑度測定  
**提供機能**:
- `scan_wifi_channels()` - チャンネルスキャン+混雑度分析
- 推奨チャンネル提案
- AP数カウント・分布分析

**依存**: wifi_scanner.py（内部でiw scanパース）  
**利用者**: cli_unified.py

---

#### 4. **wifi_health_monitor.py** - ヘルスチェック統合モジュール ✨ NEW
**目的**: Wi-Fi 接続のセキュリティヘルス評価  
**提供機能**:
- `evaluate_wifi_health()` - ワンショットヘルス評価
- `write_health_snapshot()` - ヘルス状態のJSON出力
- `read_health_snapshot()` - 最新ヘルス状態の読込
- CLI インターフェース（ループモード・出力形式選択）

**依存**: app/threat_judge.py  
**利用者**: CLI, systemd タイマー（将来）  

**統合対象**:
- ❌ `wifi_risk_check.py` → この機能を包含
- ❌ `wifi_health.py` → この機能を包含

---

### ✅ 制御層（azazel_control/）

#### 5. **wifi_scan.py** - AP一覧取得（Web UI用）
**目的**: Web UI 経由でのAP一覧取得  
**提供機能**:
- `scan_wifi()` - 環境自動検出（wpa/nmcli）
- 保存済みネットワーク判定
- レート制限（1秒/回）

**依存**: wifi_scanner.py  
**利用者**: azazel_control/daemon.py → Flask API

---

#### 6. **wifi_connect.py** - AP接続+NAT設定
**目的**: Web UI 経由でのAP接続・NAT有効化  
**提供機能**:
- `connect_wifi()` - 接続実行（wpa/nmcli自動選択）
- NAT/マスカレード設定（nft/iptables自動選択）
- キャプティブポータル検出
- state.json 更新

**依存**: wifi_scan.py  
**利用者**: azazel_control/daemon.py → Flask API

---

## ✅ 統合完了（削除済みモジュール）

以下のモジュールは `wifi_health_monitor.py` に統合され、削除されました：

### 🗑️ wifi_risk_check.py（削除済み）
**統合先**: `sensors/wifi_health_monitor.py`  
**削除理由**:
- wifi_health.py と機能が重複（どちらも judge_zero 呼び出し）
- CLI ツールとしての役割は wifi_health_monitor.py に統合
- 配置場所が不適切（py/直下 → sensors/が適切）

**移行済みコマンド**:
```bash
# 新規（同等機能）
python3 py/azazel_gadget/sensors/wifi_health_monitor.py --iface wlan0 --interval 10 --write
```

### 🗑️ wifi_health.py（削除済み）
**統合先**: `sensors/wifi_health_monitor.py`  
**削除理由**:
- センサー機能なのに azazel_gadget/ 直下にあった（sensors/が適切）
- wifi_health_monitor.py が同等機能を提供

**移行済みインポート**:
```python
# 新規（同等機能）
from azazel_gadget.sensors.wifi_health_monitor import evaluate_wifi_health, write_health_snapshot
```

**移行完了日**: 2026年1月30日  
**移行ステータス**: すべての依存関係を更新済み、旧モジュール削除完了

---

## 🔄 移行完了ステップ

### Phase 1: 新モジュールのテスト ✅
1. ✅ wifi_health_monitor.py を作成（完了）
2. ✅ 既存の wifi_risk_check.py の代わりに実行してテスト
3. ✅ 既存の wifi_health.py のインポート元を切り替えてテスト

### Phase 2: 段階的統合 ✅
1. ✅ controller.py のインポート更新
2. ✅ ドキュメント更新
3. ✅ 旧モジュールに deprecation 警告追加（削除前）

### Phase 3: クリーンアップ ✅
1. ✅ wifi_risk_check.py 削除
2. ✅ wifi_health.py 削除
3. ✅ すべての import 文を新モジュールに統一

---

## 📊 機能マトリクス

| 機能 | scanner | safety | channel | health | scan | connect |
|------|---------|--------|---------|--------|------|---------|
| **iw scan実行** | ✅ | ✅ | ✅ | - | ✅ | - |
| **パース** | ✅ | ✅ | ✅ | - | 委譲 | - |
| **脅威検知** | - | ✅ | - | ✅ | - | - |
| **混雑度分析** | - | - | ✅ | - | - | - |
| **AP接続** | - | - | - | - | - | ✅ |
| **NAT設定** | - | - | - | - | - | ✅ |
| **Web UI連携** | - | - | - | - | ✅ | ✅ |

---

## 💡 開発者ガイドライン

### モジュール選択チャート

```
あなたの目的は？
│
├─ AP をスキャンしたい
│  ├─ TUI/CLI で対話的に → ssid_list.py
│  ├─ Web UI 経由で → azazel_control/wifi_scan.py
│  └─ スキャンだけ（低レベル） → sensors/wifi_scanner.py
│
├─ AP に接続したい
│  ├─ Web UI 経由で（NAT込み） → azazel_control/wifi_connect.py
│  └─ TUI で対話的に → ssid_list.py
│
├─ 脅威を検知したい
│  ├─ リアルタイム監視 → sensors/wifi_safety.py
│  ├─ ヘルス評価（1回） → sensors/wifi_health_monitor.py
│  └─ 定期監視（ループ） → sensors/wifi_health_monitor.py --interval 60
│
└─ チャンネル混雑度を調べたい
   └─ sensors/wifi_channel_scanner.py
```

### インポート推奨パターン

```python
# ✅ GOOD: センサー層からの直接インポート
from azazel_gadget.sensors.wifi_scanner import scan_and_parse
from azazel_gadget.sensors.wifi_safety import evaluate_wifi_safety
from azazel_gadget.sensors.wifi_health_monitor import evaluate_wifi_health

# ✅ GOOD: 制御層の利用（Web UI バックエンド）
from azazel_control.wifi_scan import scan_wifi
from azazel_control.wifi_connect import connect_wifi
```

---

## 🎓 まとめ

**センサー層（sensors/）** = データ収集・分析  
**制御層（azazel_control/）** = Web UI バックエンド・システム制御  

各モジュールは**単一責任の原則**に従って整理され、明確な依存関係を持ちます。  
旧モジュール（wifi_risk_check.py、wifi_health.py）は wifi_health_monitor.py に統合され、コードベースから削除されました。
