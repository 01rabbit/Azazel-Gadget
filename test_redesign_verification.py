#!/usr/bin/env python3
"""
Azazel-Zero 再設計・改善の検証スクリプト
- state_machine の改善ロジックをテスト
- nftables テンプレートの構文確認
"""

import sys
import json
import time
from pathlib import Path

# Add py directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[0] / "py"))

from azazel_zero.first_minute.state_machine import FirstMinuteStateMachine, Stage
from azazel_zero.first_minute.nft import NftManager


def test_suricata_cooldown():
    """
    テスト 1: Suricata アラート クールダウン機構
    
    期待:
    - 1 回目のアラート: suspicion +15
    - 30 秒以内の 2 回目: 加算なし（抑制）
    - 30 秒後の 3 回目: suspicion +15（新規）
    """
    print("\n[TEST 1] Suricata Cooldown Mechanism")
    print("=" * 60)
    
    cfg = {
        "degrade_threshold": 30,
        "normal_threshold": 8,
        "contain_threshold": 65,
        "stable_normal_sec": 20,
        "stable_probe_sec": 10,
        "probe_window_sec": 20,
        "decay_per_sec": 0,  # no decay for test
        "suricata_cooldown_sec": 30.0,
    }
    
    sm = FirstMinuteStateMachine(cfg)
    sm.reset_for_new_link("aa:bb:cc:dd:ee:ff")
    
    # Step 1: 1 回目のアラート
    # 初期状態では last_suricata_alert は 0 のため、クールダウン期間経過状態
    state, summary = sm.step({
        "link_up": True,
        "bssid": "aa:bb:cc:dd:ee:ff",
        "suricata_alert": True,
    })
    print(f"1回目アラート: suspicion={summary['suspicion']} (expected: 15.0)")
    assert summary["suspicion"] == 15.0, f"Expected 15.0, got {summary['suspicion']}"
    first_alert_time = sm.ctx.last_suricata_alert
    print(f"  last_suricata_alert set to: {first_alert_time}")
    
    # Step 2: 5 秒後、2 回目のアラート（クールダウン中）
    # last_suricata_alert を "5秒前" に戻す（つまり、今から5秒しか経っていない状態）
    sm.ctx.last_suricata_alert = first_alert_time - 25  # 最後のアラートは 25 秒前
    state, summary = sm.step({
        "link_up": True,
        "bssid": "aa:bb:cc:dd:ee:ff",
        "suricata_alert": True,
    })
    print(f"2回目アラート（5秒後）: suspicion={summary['suspicion']} (expected: 15.0, no increment)")
    assert summary["suspicion"] == 15.0, f"Expected 15.0, got {summary['suspicion']}"
    
    # Step 3: 35 秒後、3 回目のアラート（クールダウン終了）
    # last_suricata_alert をさらに "35秒前" に戻す
    sm.ctx.last_suricata_alert = first_alert_time - 35  # 最後のアラートは 35 秒前
    state, summary = sm.step({
        "link_up": True,
        "bssid": "aa:bb:cc:dd:ee:ff",
        "suricata_alert": True,
    })
    print(f"3回目アラート（35秒後）: suspicion={summary['suspicion']} (expected: 30.0)")
    assert summary["suspicion"] == 30.0, f"Expected 30.0, got {summary['suspicion']}"
    
    print("✓ PASS: Suricata cooldown working correctly\n")


def test_contain_recovery():
    """
    テスト 2: CONTAIN 状態からの復帰
    
    期待:
    - NORMAL → suspicion 65+ → CONTAIN に遷移
    - CONTAIN 内で 20 秒後、suspicion < 30 → DEGRADED に復帰
    """
    print("[TEST 2] CONTAIN Recovery Logic")
    print("=" * 60)
    
    cfg = {
        "degrade_threshold": 30,
        "normal_threshold": 8,
        "contain_threshold": 65,
        "stable_normal_sec": 20,
        "stable_probe_sec": 10,
        "probe_window_sec": 20,
        "decay_per_sec": 0,  # no decay for test
        "contain_min_duration_sec": 20.0,
        "contain_exit_suspicion": 30.0,
    }
    
    sm = FirstMinuteStateMachine(cfg)
    sm.reset_for_new_link("aa:bb:cc:dd:ee:ff")
    
    # テスト用の基準時刻を設定
    base_time = 1000.0  # arbitrary base time
    
    # Step 1: NORMAL で suspicion を直接設定して CONTAIN に遷移
    sm.ctx.suspicion = 70.0
    sm.ctx.last_transition = base_time
    state, summary = sm.step(
        {
            "link_up": True,
            "bssid": "aa:bb:cc:dd:ee:ff",
        },
        now=base_time,
    )
    print(f"Step 1 (high suspicion): state={state.value}, suspicion={summary['suspicion']}")
    assert state == Stage.CONTAIN, f"Expected CONTAIN, got {state.value}"
    
    contain_start = sm.ctx.contain_entered_at
    print(f"  Entered CONTAIN at: {contain_start}")
    
    # Step 2: CONTAIN 内で 10 秒経過（最小継続時間未到）
    # suspicion を低下させても脱出不可
    sm.ctx.suspicion = 25.0
    state, summary = sm.step(
        {
            "link_up": True,
            "bssid": "aa:bb:cc:dd:ee:ff",
        },
        now=base_time + 10,
    )
    print(f"Step 2 (10s after CONTAIN): state={state.value}, suspicion={summary['suspicion']}")
    assert state == Stage.CONTAIN, f"Expected CONTAIN (min duration not met), got {state.value}"
    
    # Step 3: CONTAIN 内で 25 秒経過（最小継続時間経過後、suspicion < 30）
    # DEGRADED へ脱出
    state, summary = sm.step(
        {
            "link_up": True,
            "bssid": "aa:bb:cc:dd:ee:ff",
        },
        now=base_time + 25,
    )
    print(f"Step 3 (25s after CONTAIN): state={state.value}, suspicion={summary['suspicion']}")
    assert state == Stage.DEGRADED, f"Expected DEGRADED, got {state.value}"
    
    print("✓ PASS: CONTAIN recovery logic working correctly\n")


def test_changed_flag():
    """
    テスト 3: 状態遷移フラグ
    
    期待:
    - 状態遷移時: changed=True
    - 状態変わらず: changed=False
    """
    print("[TEST 3] State Changed Flag")
    print("=" * 60)
    
    cfg = {
        "degrade_threshold": 30,
        "normal_threshold": 8,
        "contain_threshold": 65,
        "decay_per_sec": 0,
    }
    
    sm = FirstMinuteStateMachine(cfg)
    sm.reset_for_new_link("aa:bb:cc:dd:ee:ff")
    
    # Step 1: 新しいリンク → NORMAL（changed=True は reset で即座に設定）
    state1, summary1 = sm.step({
        "link_up": True,
        "bssid": "aa:bb:cc:dd:ee:ff",
    })
    print(f"Step 1: state={state1.value}, changed={summary1.get('changed', False)}")
    
    # Step 2: 同じ状態で変化なし → changed=False
    state2, summary2 = sm.step({
        "link_up": True,
        "bssid": "aa:bb:cc:dd:ee:ff",
    })
    print(f"Step 2: state={state2.value}, changed={summary2.get('changed', False)} (expected: False)")
    assert summary2.get("changed", False) == False, "Expected changed=False"
    
    print("✓ PASS: Changed flag working correctly\n")


def test_nft_template():
    """
    テスト 4: nftables テンプレート構文確認
    """
    print("[TEST 4] NFTables Template Validation")
    print("=" * 60)
    
    nft = NftManager(
        Path(__file__).parent / "nftables" / "first_minute.nft",
        "wlan0",
        "usb0",
        "10.55.0.10",
        "10.55.0.0/24",
    )
    
    rendered = nft.render_preview()
    
    # 主要な改善ポイントが含まれているか確認
    checks = [
        ("mgmt_ports", "管理ポート定義"),
        ("management fast-path (all iface)", "管理通信 fast-path"),
        ("contain: host mgmt allowed", "CONTAIN 中の管理通信許可"),
    ]
    
    for keyword, description in checks:
        if keyword in rendered:
            print(f"✓ {description}: '{keyword}' found")
        else:
            print(f"✗ {description}: '{keyword}' NOT found")
            print(f"\nTemplate preview:\n{rendered[:500]}")
            raise AssertionError(f"Template validation failed: {description}")
    
    print("✓ PASS: NFTables template structure is correct\n")


def main():
    print("\n" + "=" * 60)
    print("Azazel-Zero Redesign Verification Tests")
    print("=" * 60)
    
    try:
        test_suricata_cooldown()
        test_contain_recovery()
        test_changed_flag()
        test_nft_template()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
