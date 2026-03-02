# Docs Guide

このディレクトリは開発アーカイブ専用です。

## 開発アーカイブ

- `dev-archive/`
- `presentation/` (HTML スライド資料)

設計検討、実装マニフェスト、機能別メモ、移行履歴などはすべてここに集約しています。

プレゼン資料は `presentation/index.html` から起動できます。

## リリース時の扱い

利用者向け配布物では、必要に応じて次を除外できます。

```bash
rm -rf docs/dev-archive
```
