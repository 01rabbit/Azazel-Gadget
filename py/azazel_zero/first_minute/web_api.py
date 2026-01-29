#!/usr/bin/env python3
"""
Azazel-Zero Web UI API Server
リアルタイムダッシュボード用の HTTP API エンドポイント
"""

import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, List
from pathlib import Path


class WebAPIHandler(BaseHTTPRequestHandler):
    """HTTP リクエストハンドラー（Web UI 用）"""
    
    # クラス変数：コントローラーから共有される状態
    status_ctx: Dict[str, Any] = {}
    history: List[Dict[str, Any]] = []
    max_history = 100
    
    def _set_headers(self, content_type: str = "application/json", status_code: int = 200):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
    
    def do_GET(self):
        """GET リクエスト処理"""
        if self.path == "/" or self.path == "/index.html":
            self._serve_index()
        elif self.path == "/api/status":
            self._serve_status()
        elif self.path == "/api/history":
            self._serve_history()
        elif self.path == "/api/signals":
            self._serve_signals()
        elif self.path == "/api/config":
            self._serve_config()
        elif self.path == "/api/access":
            self._serve_access()
        elif self.path.startswith("/static/"):
            self._serve_static()
        else:
            self._set_headers("text/plain", 404)
            self.wfile.write(b"Not Found")
    
    def _serve_index(self):
        """メイン HTML ページを提供"""
        html = self._generate_html()
        self._set_headers("text/html; charset=utf-8")
        self.wfile.write(html.encode("utf-8"))
    
    def _serve_status(self):
        """現在のステータスを JSON で返す"""
        self._set_headers()
        data = {
            "timestamp": time.time(),
            "stage": self.status_ctx.get("stage", "INIT"),
            "suspicion": self.status_ctx.get("suspicion", 0),
            "reason": self.status_ctx.get("reason", ""),
            "uptime": time.time() - self.status_ctx.get("start_time", time.time()),
            "upstream": {
                "interface": self.status_ctx.get("upstream_if", "wlan0"),
                "ssid": self.status_ctx.get("ssid", "-"),
                "bssid": self.status_ctx.get("bssid", "-"),
                "signal": self.status_ctx.get("signal_dbm", "-"),
            },
            "downstream": {
                "interface": self.status_ctx.get("downstream_if", "usb0"),
                "ip": self.status_ctx.get("mgmt_ip", "-"),
            },
            "traffic_shaping": {
                "enabled": self.status_ctx.get("stage", "INIT") in ["PROBE", "DEGRADED"],
                "rtt_ms": self.status_ctx.get("rtt_ms", 0),
                "rate_mbps": self.status_ctx.get("rate_mbps", 0),
            }
        }
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def _serve_history(self):
        """ステージ遷移履歴を JSON で返す"""
        self._set_headers()
        data = {
            "history": self.history[-50:],  # 最新50件
            "total": len(self.history)
        }
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def _serve_signals(self):
        """シグナル情報を JSON で返す"""
        self._set_headers()
        signals = self.status_ctx.get("last_signals", {})
        data = {
            "timestamp": time.time(),
            "signals": {
                "wifi_tags": signals.get("wifi_tags", 0),
                "probe_fail": signals.get("probe_fail", 0),
                "dns_mismatch": signals.get("dns_mismatch", 0),
                "suricata_alert": signals.get("suricata_alert", 0),
                "cert_mismatch": signals.get("cert_mismatch", 0),
            }
        }
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def _serve_config(self):
        """設定情報を JSON で返す"""
        self._set_headers()
        data = {
            "thresholds": {
                "degrade": self.status_ctx.get("degrade_threshold", 20),
                "normal": self.status_ctx.get("normal_threshold", 8),
                "contain": self.status_ctx.get("contain_threshold", 50),
            },
            "decay_per_sec": self.status_ctx.get("decay_per_sec", 3),
            "suricata_cooldown_sec": self.status_ctx.get("suricata_cooldown_sec", 30),
        }
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def _serve_access(self):
        """現在のアクセス情報を JSON で返す（リモートアクセス用）"""
        self._set_headers()
        # リクエスト元のホストアドレスを検出
        client_addr = self.client_address[0]
        host_header = self.headers.get("Host", "localhost:8083")
        server_addr = host_header.split(":")[0] if ":" in host_header else host_header
        
        data = {
            "access_urls": {
                "current": f"http://{server_addr}:8083/",
                "localhost": "http://127.0.0.1:8083/",
                "management": "http://10.55.0.10:8083/",
            },
            "client_ip": client_addr,
            "access_method": "remote" if client_addr not in ("127.0.0.1", "::1") else "local",
        }
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    
    def _serve_static(self):
        """静的ファイルを提供（将来の拡張用）"""
        self._set_headers("text/plain", 404)
        self.wfile.write(b"Static files not implemented")
    
    def _generate_html(self) -> str:
        """メイン HTML を生成"""
        return """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Azazel-Zero Web UI</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header {
            background: rgba(0,0,0,0.3);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid #00d4ff;
        }
        h1 { color: #00d4ff; font-size: 2em; }
        .subtitle { color: #aaa; margin-top: 5px; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }
        .card {
            background: rgba(255,255,255,0.05);
            padding: 20px;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
        }
        .card h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.3em;
            border-bottom: 2px solid rgba(0,212,255,0.3);
            padding-bottom: 10px;
        }
        
        .status-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 5px;
            font-weight: bold;
            margin: 5px 0;
        }
        .stage-NORMAL { background: #2ecc71; color: #000; }
        .stage-PROBE { background: #f39c12; color: #000; }
        .stage-DEGRADED { background: #e67e22; color: #fff; }
        .stage-CONTAIN { background: #e74c3c; color: #fff; }
        .stage-INIT { background: #95a5a6; color: #000; }
        
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #aaa; }
        .metric-value {
            color: #fff;
            font-weight: bold;
            font-family: 'Courier New', monospace;
        }
        
        .suspicion-bar {
            width: 100%;
            height: 30px;
            background: rgba(0,0,0,0.3);
            border-radius: 5px;
            overflow: hidden;
            margin: 10px 0;
        }
        .suspicion-fill {
            height: 100%;
            background: linear-gradient(90deg, #2ecc71, #f39c12, #e74c3c);
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding: 0 10px;
            color: #fff;
            font-weight: bold;
        }
        
        #historyList {
            max-height: 400px;
            overflow-y: auto;
            font-size: 0.9em;
        }
        .history-item {
            padding: 8px;
            margin: 5px 0;
            background: rgba(0,0,0,0.2);
            border-radius: 5px;
            border-left: 3px solid #00d4ff;
        }
        .history-time { color: #00d4ff; font-family: monospace; }
        
        .signal-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px;
            margin: 5px 0;
            background: rgba(0,0,0,0.2);
            border-radius: 5px;
        }
        .signal-count {
            background: #e74c3c;
            color: #fff;
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: bold;
        }
        .signal-count.zero { background: #2ecc71; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .updating { animation: pulse 1s infinite; }
        
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🛡️ Azazel-Zero Dashboard</h1>
            <div class="subtitle">身代わり結界セキュリティゲートウェイ</div>
        </header>
        
        <div class="grid">
            <!-- 現在の状態 -->
            <div class="card">
                <h2>🎯 現在の状態</h2>
                <div class="metric">
                    <span class="metric-label">ステージ</span>
                    <span id="currentStage" class="status-badge stage-INIT">INIT</span>
                </div>
                <div class="metric">
                    <span class="metric-label">疑わしさスコア</span>
                    <span id="suspicionValue" class="metric-value">0</span>
                </div>
                <div class="suspicion-bar">
                    <div id="suspicionBar" class="suspicion-fill" style="width: 0%">0</div>
                </div>
                <div class="metric">
                    <span class="metric-label">理由</span>
                    <span id="reason" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">稼働時間</span>
                    <span id="uptime" class="metric-value">0s</span>
                </div>
            </div>
            
            <!-- ネットワーク情報 -->
            <div class="card">
                <h2>📡 ネットワーク</h2>
                <div class="metric">
                    <span class="metric-label">アップストリーム</span>
                    <span id="upstreamIf" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">SSID</span>
                    <span id="ssid" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">BSSID</span>
                    <span id="bssid" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">信号強度</span>
                    <span id="signal" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">ダウンストリーム</span>
                    <span id="downstreamIf" class="metric-value">-</span>
                </div>
            </div>
            
            <!-- トラフィック整形 -->
            <div class="card">
                <h2>🚦 トラフィック整形</h2>
                <div class="metric">
                    <span class="metric-label">状態</span>
                    <span id="shapingStatus" class="metric-value">無効</span>
                </div>
                <div class="metric">
                    <span class="metric-label">遅延追加</span>
                    <span id="rttMs" class="metric-value">0 ms</span>
                </div>
                <div class="metric">
                    <span class="metric-label">帯域制限</span>
                    <span id="rateMbps" class="metric-value">無制限</span>
                </div>
            </div>
            
            <!-- シグナル -->
            <div class="card">
                <h2>⚠️ 検知シグナル</h2>
                <div id="signalsList">
                    <div class="signal-item">
                        <span>Wi-Fi 安全性タグ</span>
                        <span id="sig-wifi" class="signal-count zero">0</span>
                    </div>
                    <div class="signal-item">
                        <span>プローブ失敗</span>
                        <span id="sig-probe" class="signal-count zero">0</span>
                    </div>
                    <div class="signal-item">
                        <span>DNS 不一致</span>
                        <span id="sig-dns" class="signal-count zero">0</span>
                    </div>
                    <div class="signal-item">
                        <span>Suricata アラート</span>
                        <span id="sig-suricata" class="signal-count zero">0</span>
                    </div>
                    <div class="signal-item">
                        <span>証明書不一致</span>
                        <span id="sig-cert" class="signal-count zero">0</span>
                    </div>
                </div>
            </div>
            
            <!-- 設定 -->
            <div class="card">
                <h2>⚙️ 設定閾値</h2>
                <div class="metric">
                    <span class="metric-label">DEGRADED 閾値</span>
                    <span id="cfg-degrade" class="metric-value">20</span>
                </div>
                <div class="metric">
                    <span class="metric-label">NORMAL 閾値</span>
                    <span id="cfg-normal" class="metric-value">8</span>
                </div>
                <div class="metric">
                    <span class="metric-label">CONTAIN 閾値</span>
                    <span id="cfg-contain" class="metric-value">50</span>
                </div>
                <div class="metric">
                    <span class="metric-label">減衰率 (/秒)</span>
                    <span id="cfg-decay" class="metric-value">3</span>
                </div>
            </div>
            
            <!-- リモートアクセス情報 -->
            <div class="card">
                <h2>🌐 アクセス情報</h2>
                <div class="metric">
                    <span class="metric-label">アクセス方式</span>
                    <span id="accessMethod" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">クライアント IP</span>
                    <span id="clientIp" class="metric-value">-</span>
                </div>
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.1);">
                    <p style="color: #aaa; font-size: 0.85em; margin-bottom: 8px;">📍 アクセス URL:</p>
                    <div class="metric">
                        <span class="metric-label">現在</span>
                        <span id="urlCurrent" class="metric-value" style="font-size: 0.85em;">-</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">ローカル</span>
                        <span id="urlLocal" class="metric-value" style="font-size: 0.85em;">127.0.0.1:8083</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">管理</span>
                        <span id="urlMgmt" class="metric-value" style="font-size: 0.85em;">10.55.0.10:8083</span>
                    </div>
                </div>
            </div>
            
            <!-- 履歴 -->
            <div class="card" style="grid-column: 1 / -1;">
                <h2>📜 ステージ遷移履歴</h2>
                <div id="historyList">
                    <p style="color: #666;">読み込み中...</p>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Azazel-Zero v1.0 | 最終更新: <span id="lastUpdate">-</span></p>
        </div>
    </div>
    
    <script>
        let updateInterval;
        
        // 初期化
        document.addEventListener('DOMContentLoaded', () => {
            fetchAll();
            updateInterval = setInterval(fetchAll, 2000); // 2秒ごとに更新
        });
        
        // すべてのデータを取得
        async function fetchAll() {
            await Promise.all([
                fetchStatus(),
                fetchSignals(),
                fetchConfig(),
                fetchHistory(),
                fetchAccessInfo()
            ]);
            document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('ja-JP');
        }
        
        // ステータス取得
        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                // ステージ表示
                const stageEl = document.getElementById('currentStage');
                stageEl.textContent = data.stage;
                stageEl.className = 'status-badge stage-' + data.stage;
                
                // 疑わしさスコア
                const suspicion = Math.round(data.suspicion);
                document.getElementById('suspicionValue').textContent = suspicion;
                const bar = document.getElementById('suspicionBar');
                bar.style.width = Math.min(suspicion, 100) + '%';
                bar.textContent = suspicion;
                
                // その他
                document.getElementById('reason').textContent = data.reason || '-';
                document.getElementById('uptime').textContent = formatUptime(data.uptime);
                
                // ネットワーク
                document.getElementById('upstreamIf').textContent = data.upstream.interface;
                document.getElementById('ssid').textContent = data.upstream.ssid;
                document.getElementById('bssid').textContent = data.upstream.bssid;
                document.getElementById('signal').textContent = data.upstream.signal + ' dBm';
                document.getElementById('downstreamIf').textContent = data.downstream.interface + ' (' + data.downstream.ip + ')';
                
                // トラフィック整形
                document.getElementById('shapingStatus').textContent = data.traffic_shaping.enabled ? '有効' : '無効';
                document.getElementById('rttMs').textContent = data.traffic_shaping.rtt_ms + ' ms';
                document.getElementById('rateMbps').textContent = data.traffic_shaping.rate_mbps > 0 
                    ? data.traffic_shaping.rate_mbps + ' Mbps' 
                    : '無制限';
            } catch (e) {
                console.error('Failed to fetch status:', e);
            }
        }
        
        // シグナル取得
        async function fetchSignals() {
            try {
                const res = await fetch('/api/signals');
                const data = await res.json();
                const signals = data.signals;
                
                updateSignal('sig-wifi', signals.wifi_tags);
                updateSignal('sig-probe', signals.probe_fail);
                updateSignal('sig-dns', signals.dns_mismatch);
                updateSignal('sig-suricata', signals.suricata_alert);
                updateSignal('sig-cert', signals.cert_mismatch);
            } catch (e) {
                console.error('Failed to fetch signals:', e);
            }
        }
        
        function updateSignal(id, count) {
            const el = document.getElementById(id);
            el.textContent = count;
            el.className = 'signal-count ' + (count === 0 ? 'zero' : '');
        }
        
        // 設定取得
        async function fetchConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                
                document.getElementById('cfg-degrade').textContent = data.thresholds.degrade;
                document.getElementById('cfg-normal').textContent = data.thresholds.normal;
                document.getElementById('cfg-contain').textContent = data.thresholds.contain;
                document.getElementById('cfg-decay').textContent = data.decay_per_sec;
            } catch (e) {
                console.error('Failed to fetch config:', e);
            }
        }
        
        // 履歴取得
        async function fetchHistory() {
            try {
                const res = await fetch('/api/history');
                const data = await res.json();
                
                const list = document.getElementById('historyList');
                if (data.history.length === 0) {
                    list.innerHTML = '<p style="color: #666;">履歴なし</p>';
                } else {
                    list.innerHTML = data.history.reverse().map(item => `
                        <div class="history-item">
                            <span class="history-time">${formatTime(item.timestamp)}</span>
                            <strong>${item.from_stage} → ${item.to_stage}</strong>
                            (疑わしさ: ${Math.round(item.suspicion)})
                            ${item.reason ? '<br><small>' + item.reason + '</small>' : ''}
                        </div>
                    `).join('');
                }
            } catch (e) {
                console.error('Failed to fetch history:', e);
            }
        }
        
        // アクセス情報取得
        async function fetchAccessInfo() {
            try {
                const res = await fetch('/api/access');
                const data = await res.json();
                
                document.getElementById('accessMethod').textContent = 
                    data.access_method === 'remote' ? '🌍 リモート' : '🖥️ ローカル';
                document.getElementById('clientIp').textContent = data.client_ip;
                document.getElementById('urlCurrent').textContent = data.access_urls.current;
                document.getElementById('urlLocal').textContent = data.access_urls.localhost;
                document.getElementById('urlMgmt').textContent = data.access_urls.management;
            } catch (e) {
                console.error('Failed to fetch access info:', e);
            }
        }
        
        function formatUptime(seconds) {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            return h > 0 ? `${h}h ${m}m ${s}s` : m > 0 ? `${m}m ${s}s` : `${s}s`;
        }
        
        function formatTime(timestamp) {
            return new Date(timestamp * 1000).toLocaleTimeString('ja-JP');
        }
    </script>
</body>
</html>"""
    
    def log_message(self, format, *args):
        """ログを抑制（オプション）"""
        pass  # サイレントモード


def make_web_server(host: str, port: int, status_ctx: Dict[str, Any]) -> HTTPServer:
    """Web UI サーバーを作成"""
    WebAPIHandler.status_ctx = status_ctx
    server = HTTPServer((host, port), WebAPIHandler)
    return server


def add_history_event(from_stage: str, to_stage: str, suspicion: float, reason: str = ""):
    """ステージ遷移を履歴に記録"""
    event = {
        "timestamp": time.time(),
        "from_stage": from_stage,
        "to_stage": to_stage,
        "suspicion": suspicion,
        "reason": reason
    }
    WebAPIHandler.history.append(event)
    # 最大件数を超えたら古いものを削除
    if len(WebAPIHandler.history) > WebAPIHandler.max_history:
        WebAPIHandler.history.pop(0)
