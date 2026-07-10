"""Tests for reading the shared StatusView back through control_plane.

This exercises the read side only (plain JSON), so it needs neither
azazel_covenant nor azazel_common and runs in CI unconditionally.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_ROOT = REPO_ROOT / "py"
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_gadget import control_plane


class StatusViewReadbackTest(unittest.TestCase):
    def test_reads_status_view_beside_snapshot(self):
        d = Path(tempfile.mkdtemp())
        snap_path = d / "ui_snapshot.json"
        view = {"product": "gadget", "mode": {"name": "scapegoat"}, "posture": "deception"}
        (d / "ui_status_view.json").write_text(json.dumps(view), encoding="utf-8")

        with patch.object(control_plane, "snapshot_path_candidates", return_value=[snap_path]):
            data, source = control_plane.read_status_view_payload()

        self.assertIsNotNone(data)
        self.assertEqual(data["product"], "gadget")
        self.assertEqual(data["posture"], "deception")
        self.assertTrue(source.startswith("FILE:"))

    def test_absent_status_view_returns_none(self):
        d = Path(tempfile.mkdtemp())  # no ui_status_view.json written
        snap_path = d / "ui_snapshot.json"
        with patch.object(control_plane, "snapshot_path_candidates", return_value=[snap_path]):
            data, source = control_plane.read_status_view_payload()
        self.assertIsNone(data)
        self.assertEqual(source, "NONE")


if __name__ == "__main__":
    unittest.main()
