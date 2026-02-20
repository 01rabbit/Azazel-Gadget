# CLI Unified ⇄ E-Paper Display Integration

## 概要

`py/azazel_zero/cli_unified.py` は E-Paper ディスプレイと連動し、TUI の状態変化に応じて自動的にディスプレイを更新します。

## 状態マッピング

TUI の `user_state` から EPD の表示状態へ以下のようにマッピングされます：

| TUI State | EPD State | 表示内容 |
|-----------|-----------|----------|
| `SAFE` | `normal` | SSID、**wlan0 の IP アドレス**、**wlan0 の信号レベル** |
| `CHECKING` | `normal` | SSID、**wlan0 の IP アドレス**、**wlan0 の信号レベル** |
| `LIMITED` | `warning` | 制限モード警告 + 推奨メッセージ |
| `CONTAINED` | `danger` | 隔離モード警告 + 推奨メッセージ（赤背景） |
| `DECEPTION` | `stale` | デセプションモード表示 |

**注意**: IP アドレスと信号強度は、**upstream インターフェース (wlan0)** から取得します。downstream (usb0) ではありません。

## 使い方

### EPD 更新を有効化（デフォルト）

```bash
sudo python3 py/azazel_zero/cli_unified.py
```

または明示的に：

```bash
sudo python3 py/azazel_zero/cli_unified.py --enable-epd
```

### EPD 更新を無効化

```bash
python3 py/azazel_zero/cli_unified.py --disable-epd
```

### 推奨ワークフロー

1. **初回起動時**: EPD が接続されていることを確認し、sudo 権限で起動
   ```bash
   sudo python3 py/azazel_zero/cli_unified.py --enable-epd
   ```

2. **状態確認**: TUI 画面で `[U]` キーを押してスナップショット更新
   - 状態が変化した場合、EPD が自動的に更新されます

3. **手動 EPD テスト**: EPD の動作確認は単体でも可能
   ```bash
   # NORMAL 状態テスト
   sudo python3 py/azazel_epd.py --state normal --ssid "TestNet" --ip "192.168.7.1" --signal 80
   
   # WARNING 状態テスト
   sudo python3 py/azazel_epd.py --state warning --msg "LIMITED MODE"
   
   # DANGER 状態テスト
   sudo python3 py/azazel_epd.py --state danger --msg "ISOLATED"
   ```

## 技術詳細

### wlan IP アドレス取得

EPD に表示する IP アドレスは、**upstream インターフェース (通常は wlan0)** から取得します。

- `_get_interface_ip()` 関数が `ip -4 addr show wlan0` を実行
- IPv4 アドレスを抽出して `snap.up_ip` に格納
- 取得失敗時は `"-"` を表示

### 信号強度変換

TUI のスナップショットから取得した **wlan0 の信号強度（dBm）** を 0-100% に変換：

- **-30 dBm** = 100% (excellent)
- **-90 dBm** = 0% (poor)
- デフォルト（変換失敗時） = 50%

変換式：
```python
signal_pct = max(0, min(100, (dbm + 90) * 100 / 60))
```

### 非同期更新

EPD 更新は非ブロッキングで実行されます（`subprocess.Popen` with `start_new_session=True`）。
TUI の応答性を維持しつつ、バックグラウンドで EPD を更新します。

### エラーハンドリング

- EPD スクリプトが見つからない → サイレントに無視
- EPD 更新エラー → サイレントに無視（TUI 動作に影響なし）
- EPD ハードウェアなし → `azazel_epd.py` 側でエラーメッセージ表示

## トラブルシューティング

### EPD が更新されない

1. **権限確認**: sudo で実行していますか？
   ```bash
   sudo python3 py/azazel_zero/cli_unified.py --enable-epd
   ```

2. **EPD スクリプト存在確認**:
   ```bash
   ls -la py/azazel_epd.py
   ```

3. **EPD ハードウェア確認**:
   ```bash
   sudo python3 py/azazel_epd.py --state normal --ssid "Test" --ip "127.0.0.1" --signal 50
   ```

4. **アイコンファイル確認**:
   ```bash
   ls -la icons/epd/
   ```
   必要なファイル: `wifi_3.png`, `wifi_2.png`, `wifi_1.png`, `wifi_notconnected.png`, `warning.png`, `danger.png`

### 状態が変化しても EPD が更新されない

- TUI で `[U]` キーを押してスナップショット更新を確認
- EPD 更新は **状態変化時のみ** トリガーされます（同じ状態なら更新しません）

### EPD 更新が遅い

- E-Paper は物理的な更新時間（約 2-3 秒）が必要です
- 複数の状態変化が短時間に発生した場合、最後の更新のみ反映される場合があります

## 関連ファイル

- `py/azazel_zero/cli_unified.py` - TUI メインプログラム（EPD 連動機能含む）
- `py/azazel_epd.py` - EPD 制御スクリプト
- `icons/epd/` - EPD 用アイコンディレクトリ
- `fonts/` - EPD 用フォントディレクトリ
- `docs/dev-archive/azazel_epd_usage.md` - EPD 単体の使い方

## 参考

EPD 単体の詳細な使い方とトラブルシューティングについては [azazel_epd_usage.md](./azazel_epd_usage.md) を参照してください。
