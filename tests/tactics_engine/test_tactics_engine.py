"""
test_tactics_engine.py - Tactics Engine ユニット&統合テスト
"""

import pytest
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from azazel_zero.tactics_engine import ConfigHash, EVEParser, DecisionLogger
from azazel_zero.tactics_engine.decision_logger import (
    DecisionRecord, StateSnapshot, InputSnapshot, ScoreDelta, ChosenAction
)


class TestConfigHash:
    """ConfigHash のテスト"""

    def test_config_hash_format(self):
        """config_hash が sha256: で始まる64文字の16進数であること"""
        h = ConfigHash.compute(config_dict={"test": "value"})
        assert h.startswith("sha256:")
        hex_part = h[7:]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_config_hash_deterministic(self):
        """同一の config_dict なら同じ hash"""
        cfg1 = {"state_machine": {"contain_threshold": 50, "decay_per_sec": 3}}
        cfg2 = {"state_machine": {"contain_threshold": 50, "decay_per_sec": 3}}
        h1 = ConfigHash.compute(config_dict=cfg1)
        h2 = ConfigHash.compute(config_dict=cfg2)
        assert h1 == h2

    def test_config_hash_different(self):
        """異なる config_dict なら異なる hash"""
        cfg1 = {"state_machine": {"contain_threshold": 50}}
        cfg2 = {"state_machine": {"contain_threshold": 60}}
        h1 = ConfigHash.compute(config_dict=cfg1)
        h2 = ConfigHash.compute(config_dict=cfg2)
        assert h1 != h2

    def test_config_hash_validate(self):
        """config_hash の妥当性チェック"""
        h = ConfigHash.compute(config_dict={"test": "value"})
        assert ConfigHash.validate(h) is True
        assert ConfigHash.validate("invalid") is False
        assert ConfigHash.validate("sha256:zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz") is False


class TestEVEParser:
    """EVEParser のテスト"""

    def test_parse_valid_json(self):
        """正規のJSONを解析"""
        parser = EVEParser()
        line = '{"timestamp":"2026-01-21T12:00:00Z","alert":{"sid":1000001,"severity":1,"signature":"Test"}}'
        result = parser.parse_line(line)
        assert result is not None
        assert result.get("timestamp") == "2026-01-21T12:00:00Z"
        assert result["alert"]["sid"] == 1000001

    def test_parse_broken_json(self):
        """壊れたJSONは None を返す"""
        parser = EVEParser()
        line = '{"invalid json'
        result = parser.parse_line(line)
        assert result is None
        # 統計に反映されていることを確認
        assert parser.stats.json_decode_fails == 1

    def test_parse_empty_line(self):
        """空行はスキップ"""
        parser = EVEParser()
        result = parser.parse_line("")
        assert result is None
        assert parser.stats.skipped_lines == 1

    def test_extract_alert_features(self):
        """EVE オブジェクトから特徴抽出"""
        parser = EVEParser()
        eve_obj = {
            "timestamp": "2026-01-21T12:00:00Z",
            "alert": {
                "sid": 2000001,
                "severity": 2,
                "signature": "SQL Injection Attempt"
            }
        }
        features = parser.extract_alert_features(eve_obj)
        assert features is not None
        assert features["suricata_sid"] == 2000001
        assert features["suricata_sev"] == 2
        assert features["suricata_signature"] == "SQL Injection Attempt"

    def test_extract_alert_features_missing_fields(self):
        """不完全なalert でも既定値で埋める"""
        parser = EVEParser()
        eve_obj = {"timestamp": "2026-01-21T12:00:00Z"}
        features = parser.extract_alert_features(eve_obj)
        assert features is not None
        assert features["suricata_sid"] == 0
        assert features["suricata_sev"] == 0

    def test_compute_event_digest(self):
        """イベントダイジェストが計算される"""
        parser = EVEParser()
        eve_obj = {
            "timestamp": "2026-01-21T12:00:00Z",
            "alert": {"sid": 1000001, "severity": 1, "signature": "Test"}
        }
        digest = parser.compute_event_digest(eve_obj)
        assert digest.startswith("sha256:")
        assert len(digest) == 71  # "sha256:" + 64文字


class TestDecisionLogger:
    """DecisionLogger のテスト"""

    def test_create_record(self):
        """DecisionRecord を作成"""
        record = DecisionLogger.create_record(
            engine_version="0.1.0",
            config_hash="sha256:abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
            inputs_source="suricata",
            event_digest="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            event_min={
                "timestamp": "2026-01-21T12:00:00Z",
                "sid": 1000001,
                "severity": 1,
                "signature": "Test"
            },
            features={
                "suricata_sid": 1000001,
                "suricata_sev": 1,
                "suricata_signature": "Test"
            },
            state_before=StateSnapshot(state="NORMAL", user_state="SAFE", suspicion=0.0, risk_score=0),
            score_delta=ScoreDelta(suspicion_add=15.0, suspicion_decay=0.0),
            constraints_triggered=[],
            chosen=[ChosenAction(action_type="transition", detail={"to": "PROBE"})],
            state_after=StateSnapshot(state="PROBE", user_state="CHECKING", suspicion=15.0, risk_score=20),
        )
        assert record.decision_id  # UUID が生成されている
        assert record.ts  # ISO8601タイムスタンプ
        assert record.engine["version"] == "0.1.0"
        assert record.config_hash.startswith("sha256:")

    def test_decision_record_to_json(self):
        """DecisionRecord をJSON化"""
        record = DecisionLogger.create_record(
            engine_version="0.1.0",
            config_hash="sha256:abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
            inputs_source="suricata",
            event_digest="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            event_min={"timestamp": "2026-01-21T12:00:00Z", "sid": 1000001},
            features={"suricata_sid": 1000001, "suricata_sev": 1},
            state_before=StateSnapshot(state="NORMAL", user_state="SAFE", suspicion=0.0, risk_score=0),
            score_delta=ScoreDelta(suspicion_add=15.0),
            constraints_triggered=[],
            chosen=[ChosenAction(action_type="transition", detail={"to": "PROBE"})],
            state_after=StateSnapshot(state="PROBE", user_state="CHECKING", suspicion=15.0, risk_score=20),
        )
        json_str = record.to_json()
        # JSONL形式なので改行は含まない
        assert "\n" not in json_str
        # デコードして妥当性確認
        decoded = json.loads(json_str)
        assert decoded["decision_id"] == record.decision_id
        assert decoded["config_hash"] == record.config_hash
        assert decoded["state_before"]["state"] == "NORMAL"
        assert decoded["state_after"]["state"] == "PROBE"


class TestIntegration:
    """統合テスト"""

    def test_eve_parse_and_decision(self, tmp_path):
        """EVE パース → Decision ログ出力の統合"""
        # EVE ファイルを作成
        eve_file = tmp_path / "test.jsonl"
        eve_lines = [
            '{"timestamp":"2026-01-21T12:00:00Z","alert":{"sid":2000001,"severity":1,"signature":"SQL Injection"}}',
            '{"timestamp":"2026-01-21T12:00:01Z","alert":{"sid":2000002,"severity":2,"signature":"Buffer Overflow"}}',
        ]
        eve_file.write_text("\n".join(eve_lines) + "\n")

        # パース
        parser = EVEParser()
        parsed_count = 0
        for line in eve_file.read_text().splitlines():
            obj = parser.parse_line(line)
            if obj:
                parsed_count += 1

        assert parsed_count == 2
        assert parser.stats.successful_parses == 2

    def test_config_hash_consistency(self, tmp_path):
        """config_hash が複数回計算で一貫している"""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("state_machine:\n  contain_threshold: 50\n  decay_per_sec: 3\n")

        h1 = ConfigHash.compute(config_file=cfg_file)
        h2 = ConfigHash.compute(config_file=cfg_file)

        assert h1 == h2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
