from __future__ import annotations

import unittest
from pathlib import Path


class PowerShellCompatibilityTests(unittest.TestCase):
    def test_windows_scripts_have_utf8_bom(self):
        root = Path(__file__).resolve().parents[1]
        scripts = sorted((root / "scripts").glob("*.ps1"))
        self.assertTrue(scripts)
        for script in scripts:
            with self.subTest(script=script.name):
                data = script.read_bytes()
                self.assertTrue(
                    data.startswith(b"\xef\xbb\xbf"),
                    f"{script.name} must use UTF-8 BOM for Windows PowerShell 5.1",
                )


if __name__ == "__main__":
    unittest.main()
