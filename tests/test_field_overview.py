from pathlib import Path
import shutil
import subprocess
import unittest


class FieldOverviewTest(unittest.TestCase):
    def test_model(self):
        if not shutil.which('node'):
            self.skipTest('Node unavailable')
        root=Path(__file__).resolve().parents[1]
        subprocess.run(['node',str(root/'tests/js/field_overview.test.js')],cwd=root,check=True)
