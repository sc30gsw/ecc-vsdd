from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNED_ROOTS = ("agents", "docs", "scripts", "skills", "tests")


class ArtifactRootTest(unittest.TestCase):
    def test_distribution_uses_non_protected_vsdd_artifact_root(self) -> None:
        files = [ROOT / "README.md"]
        for directory in SCANNED_ROOTS:
            files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())

        legacy_root = ".claude" + "/specs"
        stale = []
        current = []
        for path in files:
            if path.suffix not in {".md", ".py"}:
                continue
            text = path.read_text(encoding="utf-8")
            if legacy_root in text:
                stale.append(path.relative_to(ROOT).as_posix())
            if ".vsdd/specs" in text:
                current.append(path.relative_to(ROOT).as_posix())

        self.assertEqual(stale, [])
        self.assertIn("scripts/vsdd-runtime-state.py", current)
        self.assertIn("skills/vsdd-run/SKILL.md", current)
        self.assertIn("README.md", current)


if __name__ == "__main__":
    unittest.main()
