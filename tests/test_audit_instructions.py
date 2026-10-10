import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "audit_instructions.py"
sys.path.insert(0, str(SCRIPT.parent))

import audit_instructions  # noqa: E402


class AuditInstructionsTests(unittest.TestCase):
    def test_absolute_script_path_works_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            scan_root = temp_root / "project"
            scan_root.mkdir()
            (scan_root / "AGENTS.md").write_text("Use targeted context.\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(scan_root), "--format", "json"],
                cwd=str(temp_root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(len(payload["files_scanned"]), 1)

    def test_root_does_not_implicitly_include_current_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            selected = temp_root / "selected"
            current = temp_root / "current"
            selected.mkdir()
            current.mkdir()
            (selected / "AGENTS.md").write_text("Selected.\n", encoding="utf-8")
            (current / "AGENTS.md").write_text("Current.\n", encoding="utf-8")
            output = StringIO()
            previous = Path.cwd()
            try:
                os.chdir(current)
                with patch.object(sys, "argv", ["audit_instructions.py", "--root", str(selected), "--format", "json"]), redirect_stdout(output):
                    audit_instructions.main()
            finally:
                os.chdir(previous)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["files_scanned"], [str((selected / "AGENTS.md").resolve())])

    def test_scan_root_named_build_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            scan_root = Path(temp) / "build"
            nested = scan_root / "nested"
            nested.mkdir(parents=True)
            (scan_root / "AGENTS.md").write_text("Root instruction.\n", encoding="utf-8")
            (nested / "SKILL.md").write_text("Nested skill.\n", encoding="utf-8")
            files, skipped = audit_instructions.iter_files([str(scan_root)])
            self.assertEqual(skipped, [])
            self.assertEqual({path.name for path in files}, {"AGENTS.md", "SKILL.md"})

    def test_conflict_is_a_medium_candidate_until_reviewed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "AGENTS.md"
            path.write_text("Do not edit files.\nYou may edit files when the user explicitly asks.\n", encoding="utf-8")
            findings, error = audit_instructions.scan_file(path, 512_000)
            self.assertIsNone(error)
            conflicts = [item for item in findings if item.category == "conflict"]
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].severity, "medium")
            self.assertEqual(conflicts[0].confidence, "candidate")

    def test_cross_file_conflict_is_also_a_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "AGENTS.md").write_text("Do not continue until approval.\n", encoding="utf-8")
            (root / "skill").mkdir()
            (root / "skill" / "SKILL.md").write_text("Always continue without asking.\n", encoding="utf-8")
            files, skipped = audit_instructions.iter_files([str(root)])
            records = []
            for path in files:
                records.extend(audit_instructions.extract_directives(path, path.read_text(encoding="utf-8").splitlines()))
            findings = audit_instructions.scan_cross_file_conflicts(records)
            self.assertEqual(skipped, [])
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "medium")
            self.assertEqual(findings[0].confidence, "candidate")


if __name__ == "__main__":
    unittest.main()
