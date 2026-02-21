# NetworkManager への移行ガイド

## 概要
Azazel-Gadget は Wi-Fi 制御を **wpa_supplicant から NetworkManager に完全移行**しました。

## 変更内容

### 削除された機能
- **wpa_supplicant/wpa_cli サポート**: すべての wpa_supplicant 関連コードを削除
- `check_wpa_supplicant()` 関数
- `get_saved_networks_wpa()` 関数
- `connect_wpa()` 関数
- `run_wpa_cli()`, `wpa_cli_ok()`, `parse_wpa_status()` ヘルパー関数

### 新しい仕様
- **NetworkManager 専用**: すべての Wi-Fi 操作を nmcli 経由で実行
- 簡素化されたコードパス：manager 検出の複雑なフォールバックロジックを削除
- 統一された動作：一貫した NetworkManager API を使用

## 影響を受けるファイル

### 主要ファイル
- [py/azazel_control/wifi_scan.py](../py/azazel_control/wifi_scan.py)
  - NetworkManager のみを使用してスキャン
  - wpa_supplicant 関連関数を削除
  
- [py/azazel_control/wifi_connect.py](../py/azazel_control/wifi_connect.py)
  - NetworkManager のみを使用して接続
  - wpa_cli 接続ロジックを削除
  
- [py/azazel_control/daemon.py](../py/azazel_control/daemon.py)
  - 起動時の自動接続抑制を NetworkManager のみに簡素化

### 設定ファイル

**注**: 以下のスクリプトは削除済みのため、参考情報としてのみ記載。現在は `./install.sh` で自動設定されます。

- ~~installer/apply.sh~~ （削除済み）
  - dhcpcd.conf から `nohook wpa_supplicant` を削除していた
  
- ~~bin/install_dependencies.sh~~ （削除済み）
  - wpasupplicant パッケージを依存関係から削除していた
  
- ~~installer/mask.py~~ （削除済み）
  - コメントを更新（NetworkManager connections に言及）していた

## 必要なパッケージ

### 必須パッケージ
```bash
sudo apt-get install network-manager
```

### 不要になったパッケージ
```bash
# オプション: wpa_supplicant を削除（他のシステムコンポーネントが依存している可能性があるため注意）
sudo apt-get remove wpasupplicant
```

## 移行手順

### 既存システムのアップグレード

1. **NetworkManager のインストール**
   ```bash
   sudo apt-get update
   sudo apt-get install network-manager
   ```

2. **wpa_supplicant の無効化（オプション）**
   ```bash
   sudo systemctl stop wpa_supplicant
   sudo systemctl disable wpa_supplicant
   ```

3. **NetworkManager の有効化**
   ```bash
   sudo systemctl enable NetworkManager
   sudo systemctl start NetworkManager
   ```

4. **既存の Wi-Fi 設定を NetworkManager に移行**
   ```bash
   # 既存の wpa_supplicant 設定を確認
   sudo cat /etc/wpa_supplicant/wpa_supplicant.conf
   
   # NetworkManager に手動で追加
   sudo nmcli dev wifi connect "SSID" password "PASSWORD"
   ```

5. **Azazel-Gadget サービスの再起動**
   ```bash
   sudo systemctl restart azazel-control-daemon
   sudo systemctl restart azazel-first-minute
   ```

### 動作確認

```bash
# NetworkManager が wlan0 を管理していることを確認
nmcli dev status

# Wi-Fi スキャンのテスト
python3 /home/azazel/Azazel-Zero/py/azazel_control/wifi_scan.py

# Wi-Fi 接続のテスト（該当する SSID/パスフレーズで置換）
python3 /home/azazel/Azazel-Zero/py/azazel_control/wifi_connect.py "TestSSID" --security WPA2 --passphrase "testpass"
```

## トラブルシューティング

### NetworkManager が wlan0 を管理しない

**症状**: `NetworkManager not found or not managing interface`

**解決策**:
```bash
# NetworkManager の設定を確認
sudo cat /etc/NetworkManager/NetworkManager.conf

# wlan0 を unmanaged から削除（必要に応じて）
sudo nmcli dev set wlan0 managed yes

# NetworkManager を再起動
sudo systemctl restart NetworkManager
```

### dhcpcd が wlan0 と競合

**症状**: IP アドレスが取得できない、または重複する

**解決策**:
```bash
# dhcpcd から wlan0 を除外
sudo tee -a /etc/dhcpcd.conf <<EOF
denyinterfaces wlan0
EOF

sudo systemctl restart dhcpcd
sudo systemctl restart NetworkManager
```

### 保存されたネットワークが表示されない

**症状**: 以前保存した Wi-Fi ネットワークが表示されない

**理由**: wpa_supplicant の設定は NetworkManager に自動移行されません

**解決策**: Wi-Fi ネットワークを NetworkManager に再登録してください

## API の変更

### Python API

#### 削除された関数
```python
# これらの関数は使用できません
from wifi_scan import check_wpa_supplicant  # 削除
from wifi_scan import get_saved_networks_wpa  # 削除
from wifi_connect import connect_wpa  # 削除
```

#### 新しい推奨 API
```python
from wifi_scan import (
    scan_wifi,                    # Wi-Fi AP スキャン
    get_wireless_interface,       # wlan インターフェース検出
    check_networkmanager,         # NetworkManager の可用性チェック
    get_saved_networks_nm,        # 保存されたネットワークの取得
)

from wifi_connect import (
    connect_wifi,                 # Wi-Fi 接続（NetworkManager 使用）
    update_state_json,            # 状態更新
)
```

## 設計上の利点

1. **簡素化**: manager 検出の複雑な分岐を削除
2. **保守性向上**: 単一の Wi-Fi 管理システムのみをサポート
3. **一貫性**: すべてのプラットフォームで統一された動作
4. **モダンなツール**: NetworkManager は現代的な Linux デスクトップ/モバイル環境の標準

## 参考リンク

- [NetworkManager 公式ドキュメント](https://networkmanager.dev/)
- [nmcli マニュアル](https://networkmanager.dev/docs/api/latest/nmcli.html)
- [Azazel-Gadget プロジェクトガイド](../.github/copilot-instructions.md)

---

**最終更新**: 2026年2月11日  
**バージョン**: v2.0 (NetworkManager 専用)
