"""Generate results before MkDocs scans docs; never rerun the benchmark here."""

import subprocess
import sys
from pathlib import Path

from mkdocs.exceptions import PluginError


ROOT = Path(__file__).resolve().parents[1]


def on_pre_build(config):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare_report.py")], cwd=ROOT
    )
    if result.returncode:
        raise PluginError("Report generation failed; check data and the message above.")
