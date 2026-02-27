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

from azazel_gadget import control_plane, path_schema


class PathSchemaTests(unittest.TestCase):
    def test_status_contains_deadline(self):
        data = path_schema.status()
        self.assertIn("legacy_deprecation_date", data)
        self.assertIn(data["active_schema"], ("v1", "v2"))

    def test_migrate_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            result = path_schema.migrate_schema("v2", dry_run=True, home=Path(td))
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("dry_run"))
        self.assertGreater(len(result.get("actions", [])), 0)


class ControlPlaneFallbackTests(unittest.TestCase):
    def test_write_command_file_fallback_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "run" / "ui_command.json"
            written = control_plane.write_command_file_fallback("contain", explicit_path=out)
            self.assertEqual(written, out)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["action"], "contain")

    def test_read_snapshot_from_files(self):
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "ui_snapshot.json"
            snap.write_text(json.dumps({"user_state": "SAFE"}), encoding="utf-8")
            with patch("azazel_gadget.control_plane.snapshot_path_candidates", return_value=[snap]):
                data, path = control_plane.read_snapshot_from_files()
            self.assertEqual(path, snap)
            self.assertEqual(data.get("user_state"), "SAFE")


if __name__ == "__main__":
    unittest.main()
