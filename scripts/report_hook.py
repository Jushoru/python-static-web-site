"""Generate results before MkDocs scans docs; never rerun the benchmark here."""

import subprocess
import sys
import importlib.util
import json
import logging
import os
from pathlib import Path

from mkdocs.exceptions import PluginError


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_info", ROOT / "scripts" / "build_info.py")
build_info = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_info)
log = logging.getLogger("mkdocs.report")
info = {}


def on_pre_build(config):
    global info
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare_report.py"), "--json"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if result.returncode:
        raise PluginError("Report generation failed: " + (result.stderr or result.stdout))
    status = json.loads(result.stdout)
    log.info("Report cache %s [%s]", status["status"], status["key"][:12])
    info = build_info.read_build_info(status)


def on_page_markdown(markdown, page, config, files):
    # Dynamic provenance lives in the HTML, never in watched Markdown files.
    if page.file.src_uri == "build.md":
        return markdown.replace("<!-- BUILD_INFO -->", build_info.provenance_table(info)).replace(
            "<!-- CACHE_TIMINGS -->", build_info.cache_timings(info["key"])
        )
    if page.file.src_uri == "results.md":
        return markdown + "\n\n## Версия этой сборки\n\n" + build_info.provenance_table(info) + "\n"
    if page.file.src_uri == "deployment.md":
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        return markdown.replace("<!-- WORKFLOW_SOURCE -->", "```yaml\n" + workflow.rstrip() + "\n```")
    return markdown
