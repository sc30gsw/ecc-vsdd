from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check-line-coverage.py"


class LineCoverageGateTest(unittest.TestCase):
    def run_gate(self, covered: int, statements: int) -> subprocess.CompletedProcess[str]:
        root = Path(tempfile.mkdtemp(prefix="ecc-vsdd-line-coverage-"))
        target = root / "runtime.py"
        target.write_text("pass\n", encoding="utf-8")
        report = root / "coverage.json"
        report.write_text(
            json.dumps(
                {
                    "files": {
                        str(target): {
                            "summary": {
                                "covered_lines": covered,
                                "num_statements": statements,
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(report),
                "--minimum",
                "80",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_exact_threshold_passes(self) -> None:
        result = self.run_gate(80, 100)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("80.0%", result.stdout)

    def test_below_threshold_fails(self) -> None:
        result = self.run_gate(79, 100)

        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
