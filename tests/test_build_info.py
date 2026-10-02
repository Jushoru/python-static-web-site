"""Check provenance against a real disposable Git repository."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_info


class BuildInfoTests(unittest.TestCase):
    def test_derived_files_do_not_hide_or_invent_source_changes(self):
        parent = ROOT / "_build" / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        # Keep the isolated repository under the ignored test directory.
        work = Path(tempfile.mkdtemp(prefix="provenance-", dir=parent))

        def git(*args):
            return subprocess.run(["git", *args], cwd=work, check=True,
                                  capture_output=True, text=True).stdout.strip()

        def write(name, value):
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")

        git("init", "--quiet")
        write("data/build_times.metadata.json", json.dumps({"dataset_version": "v1"}))
        write("data/build_times.csv", "original")
        write("docs/results.md", "derived")
        write("docs/downloads/theory-original.txt", "theory")
        git("add", ".")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")
        with patch.object(build_info, "ROOT", work), patch.dict(os.environ, {"GITHUB_SHA": ""}):
            self.assertEqual(build_info.read_build_info({})["worktree"], "чистое")
            write("docs/results.md", "regenerated on Linux")
            self.assertEqual(build_info.read_build_info({})["worktree"], "чистое")
            write("data/build_times.csv", "edited measurements")
            self.assertEqual(build_info.read_build_info({})["worktree"], "есть локальные изменения")
            write("data/build_times.csv", "original")
            write("docs/downloads/theory-original.txt", "edited theory")
            self.assertEqual(build_info.read_build_info({})["worktree"], "есть локальные изменения")
            write("docs/downloads/theory-original.txt", "theory")
            write("LICENSE-CONTENT.md", "new license")
            self.assertEqual(build_info.read_build_info({})["worktree"], "есть локальные изменения")
