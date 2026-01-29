#!/usr/bin/env python3
"""
Web API 動作テスト
コントローラーなしで Web API サーバーを起動して動作確認
"""

import time
import threading
from azazel_zero.first_minute.web_api import make_web_server, add_history_event, WebAPIHandler

# モックステータスデータ
mock_status = {
    "start_time": time.time(),
    "stage": "NORMAL",
    "suspicion": 15,
    "reason": "プローブテスト中",
    "upstream_if": "wlan0",
    "downstream_if": "usb0",
    "mgmt_ip": "10.55.0.10",
    "ssid": "TestNetwork",
    "bssid": "AA:BB:CC:DD:EE:FF",
    "signal_dbm": -55,
    "rtt_ms": 0,
    "rate_mbps": 0,
    "last_signals": {
        "wifi_tags": 0,
        "probe_fail": 0,
        "dns_mismatch": 1,
        "suricata_alert": 0,
        "cert_mismatch": 0,
    },
    "degrade_threshold": 20,
    "normal_threshold": 8,
    "contain_threshold": 50,
    "decay_per_sec": 3,
    "suricata_cooldown_sec": 30,
}

def main():
    print("🚀 Web API テストサーバー起動中...")
    
    # ステータスコンテキストを設定
    WebAPIHandler.status_ctx = mock_status
    
    # 履歴にダミーイベントを追加
    add_history_event("INIT", "NORMAL", 0, "システム起動")
    add_history_event("NORMAL", "PROBE", 12, "DNS 不一致検知")
    add_history_event("PROBE", "DEGRADED", 22, "プローブ失敗継続")
    add_history_event("DEGRADED", "NORMAL", 7, "疑わしさ低下")
    
    # サーバー起動
    server = make_web_server("127.0.0.1", 8083, mock_status)
    
    print(f"✅ Web UI が起動しました: http://127.0.0.1:8083/")
    print("   ブラウザでアクセスしてください。")
    print("   終了するには Ctrl+C を押してください。\n")
    
    # バックグラウンドで疑わしさを変動させる
    def simulate_changes():
        stages = ["NORMAL", "PROBE", "DEGRADED", "NORMAL", "CONTAIN", "NORMAL"]
        suspicions = [5, 15, 25, 10, 55, 3]
        idx = 0
        
        while True:
            time.sleep(5)
            idx = (idx + 1) % len(stages)
            old_stage = mock_status["stage"]
            mock_status["stage"] = stages[idx]
            mock_status["suspicion"] = suspicions[idx]
            mock_status["last_signals"]["dns_mismatch"] = idx % 3
            mock_status["last_signals"]["probe_fail"] = idx % 2
            
            if old_stage != stages[idx]:
                add_history_event(old_stage, stages[idx], suspicions[idx], f"自動遷移 (シミュレーション)")
                print(f"🔄 ステージ変更: {old_stage} → {stages[idx]} (疑わしさ: {suspicions[idx]})")
    
    sim_thread = threading.Thread(target=simulate_changes, daemon=True)
    sim_thread.start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 サーバー停止中...")
        server.shutdown()
        print("✅ 終了しました。")

if __name__ == "__main__":
    main()
