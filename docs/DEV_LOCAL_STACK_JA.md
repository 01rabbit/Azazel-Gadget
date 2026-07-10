# 開発用ローカルスタック（macOS / ハードウェア不要）

Azazel-Gadget（AZ-02）を、Raspberry Pi ハードウェア**なし**で開発マシン
（macOS またはプレーンな Linux）上で動かします。`wlan0`/`usb0`・`nft`/`tc`・
E-Paper・OpenCanary/Suricata/dnsmasq は不要です。Azazel-Edge の dev スタック
（`bin/azazel-edge-devstack`）と同じ方式です。

dev スタックは **実際の** first-minute コントローラと Flask Web UI を、
**安全な dev モード（dry-run：判断は行うがファイアウォール・トラフィック制御・
無線には一切触れない）** で起動します。E-Paper に表示される内容はブラウザで
確認できます。

## クイックスタート

```bash
# 1. pip 依存をインストール（venv 推奨）
pip install -r requirements.txt        # Flask, requests, PyYAML, azazel-common

# 2. 起動（tools/dev/env.sh を自動で読み込みます）
bin/azazel-gadget-devstack up
```

表示例：

```
  Dashboard   : http://127.0.0.1:8084/
  EPD preview : http://127.0.0.1:8084/dev/epd
  State API   : http://127.0.0.1:8084/api/state
  EPD API     : http://127.0.0.1:8084/api/epd
```

その他のサブコマンド：`status` / `logs` / `restart` / `down`。

## dev モードの中身

dev モードは `tools/dev/env.sh`（ランチャーが読み込む）が環境変数を設定するだけ
です。アプリ側に `if MOCK:` のような分岐は無く、これらの変数が未設定なら
appliance の挙動は変わりません。

| 項目 | 実機 | dev（`tools/dev/env.sh`） |
|---|---|---|
| ランタイムdir | `/run/azazel-gadget` | `$HOME/.azazel-gadget-dev/run` |
| 制御ソケット | `/run/azazel/control.sock` | `…/run/control.sock` |
| Suricata イベント | `/var/log/suricata/eve.json` | `…/suricata/eve.json` |
| Web バインド | `0.0.0.0:8084` | `127.0.0.1`（ループバックのみ） |
| root / `nft`/`tc` | 必須 | `AZAZEL_GADGET_DEV=1` で preflight をスキップ |
| FW / TC / EPD / dnsmasq | 適用する | **dry-run のみ（触れない）** |

dev の状態はすべて `~/.azazel-gadget-dev/` 配下に置かれ、`/run`・`/etc`・`/var`
には何も書き込みません。リセットはこのディレクトリを削除するだけです。

## E-Paper（EPD）を Web で

実機の E-Paper が無い環境向けに、パネル内容をブラウザで提供します：

- `GET /api/epd` — パネル内容を JSON で（モード、`normal|warning|danger`、
  リスク表示、SSID、電波強度）。
- `GET /dev/epd` — 250×122 パネルを描画し 2 秒ごとに更新する自己完結プレビュー。

パネルと同じライブ状態から生成しており、ブラウザプレビューに Pillow/Waveshare
などのハードウェアライブラリは不要です。

**注意：このブラウザプレビューはパネル画像のキャプチャではなく、再現実装した
「デジタルツイン」です。** `/dev/epd` は、実パネルに供給されるのと同じ入力信号
（モード・姿勢・SSID・疑わしさ）から駆動される、独立実装の HTML/CSS 近似表示
であり、実際の描画経路（`py/azazel_epd.py`）は通っていません（dev モードでは
バイパスされます）。そのため実機 E-Paper パネルとのピクセル一致は保証されません。
`/dev/epd` は内容・状態のプレビューであり、ピクセル精度のプレビューではないもの
として扱ってください。（参考：Azazel-Edge の同等プレビューは、実際の PIL
レンダラーが描画した `/api/epd/preview.png` も併せて提供します。Gadget の dev
スタックには、まだこのピクセル精度の経路はありません。）

## 注意・制限

- **dry-run が強制されます。** コントローラは実際の判断ループを回しますが、
  `nft`/`tc`/`dnsmasq`/EPD/sysctl は適用しません（`AZAZEL_GADGET_DEV=1` が
  `dry_run` を強制）。Edge の `AZAZEL_DEFENSE_DRY_RUN=true` と同じ姿勢です。
- **実 Wi-Fi なし。** 無線が無いため上流インターフェースはループバックに解決され、
  ダッシュボード上は Wi-Fi 切断表示になります（dev では想定どおり）。
- **dev では Web トークンなし。** UI はループバックのみで開放されます
  （トークンファイルが無ければ `verify_token()` は通過）。dev ポートを
  ループバック外に晒さないでください。
- **`azazel-common`**（Azazel-Fabric、旧称 Azazel-Common。v0.3.0 から配布名は
  `azazel-fabric`）が共有ステータス・ビューモデルを提供します。導入時
  （`requirements.txt` に含む）は `/api/state` に `status_view` が付与され、
  コントローラが `ui_status_view.json` を出力します。詳細は
  [`concepts/azazel-common-usage.md`](concepts/azazel-common-usage.md)。