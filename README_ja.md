# AZ-02 Azazel-Gadget - パーソナル戦術防御ゲートウェイ

> **コードネーム:** `TACMOD`

![Azazel-Gadget Banner](images/Azazel-Gadget_Banner.png)
[![CI](https://github.com/01rabbit/Azazel-Gadget/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/01rabbit/Azazel-Gadget/actions/workflows/ci-tests.yml)
[![Release](https://img.shields.io/github/v/release/01rabbit/Azazel-Gadget)](https://github.com/01rabbit/Azazel-Gadget/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-index-blue)](docs/INDEX.md)
[![Pages](https://github.com/01rabbit/Azazel-Gadget/actions/workflows/pages.yml/badge.svg)](https://github.com/01rabbit/Azazel-Gadget/actions/workflows/pages.yml)
![Platform: Raspberry Pi](https://img.shields.io/badge/Platform-Raspberry%20Pi-C51A4A?logo=raspberry-pi)
![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web%20UI-000000?logo=flask)
![JavaScript](https://img.shields.io/badge/JavaScript-UI-F7DF1E?logo=javascript&logoColor=black)
[![Language: Japanese](https://img.shields.io/badge/Language-日本語-2ea44f)](./README_ja.md)
[![Language: English](https://img.shields.io/badge/Language-English-1f6feb)](./README.md)

Azazel-Gadget は Azazel システムの AZ-02 ポータブル構成であり、低信頼 Wi-Fi・敵対的ローカルセグメント・現場運用向けのパーソナル戦術防御ゲートウェイ / Cyber Scapegoat Gateway です。ユーザー端末と周辺ネットワークの間に立ち、初期ネットワーク挙動を観測し、`portal` / `shield` / `scapegoat` の決定論的モードで露出を制御し、Web UI・TUI・E-paper・（任意）ローカル通知で運用状態を可視化します。

Azazel-Gadget は、敵対的ローカルネットワークにおける最初の接触面を、ユーザー端末の外側へ移します。

Azazel-Gadget は VPN ではなく、汎用トラベルルーターでもなく、完全な攻撃防止を約束するものでもありません。

**対象ユーザー:** セキュリティ研究者、フィールド防御担当者、旅行者、インシデントレスポンダー、レッド/ブルーチーム運用者、および低信頼ネットワークでポータブル防御ゲートウェイを必要とするユーザー。

## なぜ必要か

- 公衆Wi-Fiや敵対的ローカルセグメントでは、端末がローカル探索・プロービング・機会的攻撃に晒されます。
- VPNは通信経路を保護できますが、端末のローカル接触面そのものを消すわけではありません。
- エンドポイントファイアウォールは端末上で動作します。
- 旅行用ルーターは接続性に主眼があり、観測可能な戦術的デセプション・ゲートウェイとしては設計されていません。
- Azazel-Gadget は、端末の前段に制御可能なゲートウェイ境界と、必要に応じた scapegoat 面を配置します。

## 要件

| 要件 | 内容 |
|---|---|
| ハードウェア | Raspberry Pi Zero 2 W / Raspberry Pi 4 クラス |
| OS | Raspberry Pi OS / Linux |
| ランタイム | Python 3.x、Flask ベースのローカル Web UI |
| ネットワーク | `usb0` 保護クライアント側、`wlan0` 上流側 |
| 任意機能 | E-paper、OpenCanary、Suricata、ntfy、portal viewer |

## クイックスタート

```bash
sudo ./install.sh --all
# 再起動が必要な場合:
sudo ./install.sh --resume
```

最小確認:

```bash
sudo systemctl status azazel-mode azazel-first-minute azazel-control-daemon azazel-web --no-pager
```

## アーキテクチャ概要

```mermaid
flowchart LR
    U[Protected Endpoint] --> G[Azazel-Gadget Gateway]
    G --> M[Mode Controller]
    M --> P[Portal]
    M --> S[Shield]
    M --> D[Scapegoat]
    G --> O[Operator Interfaces]
    O --> W[Web UI]
    O --> T[TUI]
    O --> E[E-paper]
    D --> C[OpenCanary / Deception]
    G --> A[Audit and State Files]
```

## Azazel-Gadget が行うこと

- ポータブル防御ゲートウェイとして動作する。
- 決定論的な運用モードを提供する。
- 保護対象 `usb0` クライアントを上流からの inbound と分離する。
- Web UI・TUI・E-paper による可視性を提供する。
- 必要に応じて OpenCanary の隔離デコイ公開を行う。
- 実装されている範囲で Suricata / OpenCanary / ntfy 状態を反映する。
- 状態とモード変更を運用者レビュー可能な形で記録する。

## Security Boundary Summary

Azazel-Gadget の主張:

- ローカルファーストな防御ゲートウェイ挙動
- 運用者が明示選択するモード
- 上流 `wlan0` から保護側 `usb0` クライアントへの inbound 経路がないこと
- 監査可能な状態を伴う決定論的モード切替
- 保護クライアント側から分離された任意デコイ公開

Azazel-Gadget が主張しないこと:

- あらゆる敵対 Wi-Fi 攻撃への完全防御
- エンドポイント防御、VPN、企業 NAC の置き換え
- 自律的攻撃応答
- 不可視・無操作のセキュリティ
- アクティブモードを理解しないままでの安全運用

## Operating Modes

| Mode | 挙動 | EPD サンプル |
|---|---|---|
| `portal` | 保護対象 `usb0` クライアント向け NAT/ゲートウェイ挙動。デコイ公開は無効。 | ![Portal mode EPD sample](images/portal_composite.png) |
| `shield`（既定） | 既定の防御姿勢。`wlan0` からの inbound を遮断しつつ、保護側の outbound を維持。 | ![Shield mode EPD sample](images/shield_composite.png) |
| `scapegoat` | OpenCanary の許可ポートのみ公開。Canary は `az_canary` ネームスペースで隔離し、保護側と分離。 | ![Scapegoat mode EPD sample](images/scapegoat_composite.png) |

警告表示（モードではない）:

| 表示 | トリガー | EPD サンプル |
|---|---|---|
| `WARNING` | 監視パイプラインが警告条件を検知。 | ![Warning EPD sample](images/warning_composite.png) |

## デモプロファイル

1. 保護対象端末を Azazel-Gadget 経由で接続する。
2. Azazel-Gadget を低信頼Wi-Fiまたは敵対的ローカルセグメントへ接続する。
3. 同一セグメント上のピアから探索/プロービングを実施する。
4. `shield` では上流側 inbound 露出が遮断されることを示す。
5. `scapegoat` では allowlist されたデコイサービスのみ公開されることを示す。
6. Web UI・TUI・E-paper・（任意）通知経路で運用状態が可視化されることを示す。

詳細: [Submission Demo Profile](docs/demo/submission-demo-profile.md)

## ハードウェアバリエーション

プロジェクト名と実装名は分離して扱います。

- プロジェクト: **Azazel-Gadget**
- Raspberry Pi Zero 2 W 実装: **Azazel-Gadget Shield**
- Raspberry Pi 3/4/4B 実装: **Azazel-Gadget Dock**

| Azazel-Gadget Shield | Azazel-Gadget Dock |
|---|---|
| Raspberry Pi Zero 2 W 実装<br>![Azazel-Gadget Shield](images/Azazel-Gadget_Portable.png) | Raspberry Pi 3/4/4B 実装<br>![Azazel-Gadget Dock](images/Azazel-Gadget_Shield.png) |

## インターフェース

| Web UI | Unified TUI |
|---|---|
| [![Azazel-Gadget Web UI screenshot](images/WebUI.png)](images/WebUI.png) | [![Azazel-Gadget unified TUI screenshot](images/TUI.png)](images/TUI.png) |

- Web UI バックエンドとダッシュボード: `azazel_web/`
- 統合 TUI モニタ/メニュー: `py/azazel_gadget/cli_unified.py`
- 互換メニューランチャー: `py/azazel_menu.py`
- 端末ステータス表示: `py/azazel_status.py`
- E-paper 描画/制御: `py/azazel_epd.py`, `py/boot_splash_epd.py`

## インストールオプション

エントリポイント: `install.sh`

| オプション | 効果 |
|---|---|
| `--with-canary` | OpenCanary を導入/有効化 |
| `--with-epd` | Waveshare E-Paper 依存を有効化（既定有効） |
| `--with-webui` | Flask venv + Caddy HTTPS リバースプロキシを導入 |
| `--with-ntfy` | ローカル ntfy サーバと通知連携を導入 |
| `--with-portal-viewer` | noVNC/Chromium Captive Portal Viewer 構成を導入 |
| `--all` | 上記の任意機能を一括有効化 |
| `--resume` | 再起動が必要なネットワーク段の後続処理を再開 |

## Web API

| Endpoint | 内容 |
|---|---|
| `GET /` | ダッシュボード HTML |
| `GET /api/state` | 現在スナップショット |
| `GET /api/state/stream` | 状態 SSE |
| `GET /api/mode` | 現在モード情報 |
| `POST /api/mode` | モード切替（`portal`/`shield`/`scapegoat`） |
| `GET /api/portal-viewer` | noVNC 状態/URL |
| `POST /api/portal-viewer/open` | portal viewer 起動/表示 |
| `GET /api/events/stream` | ntfy イベント SSE ブリッジ |
| `POST /api/action` | アクション（v1形式） |
| `POST /api/action/<action>` | アクション（legacy形式） |
| `GET /api/wifi/scan` | Wi-Fi スキャン |
| `POST /api/wifi/connect` | Wi-Fi 接続 |
| `GET /api/certs/azazel-webui-local-ca/meta` | ローカルCAメタ情報 |
| `GET /api/certs/azazel-webui-local-ca.crt` | ローカルCAダウンロード |
| `GET /health` | バックエンドヘルス |

許可アクション:
`refresh`, `reprobe`, `contain`, `release`, `details`, `stage_open`, `disconnect`, `wifi_scan`, `wifi_connect`, `portal_viewer_open`, `mode_set`, `mode_status`, `mode_get`, `mode_portal`, `mode_shield`, `mode_scapegoat`, `shutdown`, `reboot`

トークン認証:

- Header: `X-AZAZEL-TOKEN` または `X-Auth-Token`
- Query: `?token=...`

## Azazel シリーズ

Azazel-Gadget（AZ-02）は Azazel シリーズを構成する製品の一つです。

| リポジトリ | 役割 |
|---|---|
| [01rabbit/Azazel](https://github.com/01rabbit/Azazel) | シリーズ全体の教義ハブ兼プロジェクトサイト（"Cyber Scapegoat Gateway"） |
| [01rabbit/Azazel-Edge](https://github.com/01rabbit/Azazel-Edge)（AZ-01） | 決定論的な Edge SOC/NOC ゲートウェイ — ピア製品 |
| **Azazel-Gadget（AZ-02、本リポジトリ）** | パーソナル戦術防御ゲートウェイ — ピア製品 |
| Azazel-Boot（AZ-03） | 予約済みシリーズ枠。リポジトリは未公開 |
| [01rabbit/Azazel-Grimoire](https://github.com/01rabbit/Azazel-Grimoire) | AZ-04 Azazel-Grimoire（旧称 Azazel-CTI、正式名 Azazel-Grimoire Advisor）。助言専用・決定論的なオンプレ戦術 CTI ナレッジプレーンノード。Azazel-Edge と対を成し、決して命令はせず、最終権限は常に Edge にあり、CTI ノードが不在でも Edge は完全に機能する。Gadget は現時点で CTI 連携を持たず、予定もない。 |
| [01rabbit/Azazel-Covenant](https://github.com/01rabbit/Azazel-Covenant) | AZ-05 Azazel-Covenant（旧称 Azazel-Common）。シリーズ共有の契約ライブラリ（配布名 `azazel-common`、git タグ固定でインストール。v0.3.0 から `azazel-covenant`）。Gadget は現時点で最も本格的な利用者 — 詳細は [Gadget での Azazel-Covenant 活用](docs/concepts/azazel-common-usage.md)を参照。 |

詳細は [Series Positioning and Terms](docs/SERIES_POSITIONING_AND_TERMS.md) および
[Azazel System Product Map](docs/concepts/azazel-system-product-map.md) を参照してください。

## Documentation Map

主要エントリ:

- [Documentation Index](docs/INDEX.md)
- [Personal Cyber Scapegoat Gateway](docs/concepts/personal-cyber-scapegoat-gateway.md)
- [First-Contact Surface Relocation](docs/concepts/first-contact-surface-relocation.md)
- [Azazel System Product Map](docs/concepts/azazel-system-product-map.md)
- [開発用ローカルスタック（ハードウェア不要）](docs/DEV_LOCAL_STACK_JA.md)
- [Gadget での Azazel-Covenant 活用](docs/concepts/azazel-common-usage.md)
- [Submission Demo Profile](docs/demo/submission-demo-profile.md)
- [Demo Evidence Checklist](docs/demo/evidence-checklist.md)
- [Series Positioning and Terms](docs/SERIES_POSITIONING_AND_TERMS.md)
- [Security Claim Policy](docs/SECURITY_CLAIM_POLICY.md)
- [Installer Guide](installer/README.md)
- [Release Process](docs/RELEASE_PROCESS.md)
- [Release Notes Template](docs/RELEASE_NOTES_TEMPLATE.md)
- [Changelog](docs/CHANGELOG.md)

## Repository Layout

| Path | 役割 |
|---|---|
| `py/azazel_gadget/` | コントローラ、センサー、tactics engine、path schema |
| `py/azazel_control/` | control daemon、Wi-Fi ハンドラ、アクションスクリプト |
| `azazel_web/` | Flask バックエンドとダッシュボード資産 |
| `systemd/` | service/timer ユニット |
| `installer/` | 段階的インストーラ構成 |
| `configs/` | 既定ランタイム設定 |
| `scripts/` | ランタイム補助とテストスクリプト |
| `docs/` | ドキュメントとプレゼン資産 |
| `images/` | README/ドキュメント用画像資産 |

## ライセンス

このプロジェクトは MIT License で提供されます。詳細は [LICENSE](LICENSE) を参照してください。
