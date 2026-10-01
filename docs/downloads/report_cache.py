"""Content-addressed cache for generated report files (no third-party imports)."""

import hashlib
import json
import os
import platform
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    "data/build_times.csv", "data/build_times.metadata.json",
    "data/benchmark_environment.txt", "requirements.txt",
    "scripts/benchmark.py", "scripts/prepare_report.py", "scripts/report_cache.py",
)
OUTPUTS = (
    "results.md", "example.md", "assets/generated/build-times.svg",
    "assets/generated/build-times.png", "downloads/example-page.md.txt",
    "downloads/benchmark-config.yml", "downloads/build_times.csv",
    "downloads/build_times.metadata.json", "downloads/benchmark_environment.txt",
    "downloads/benchmark.py", "downloads/prepare_report.py", "downloads/report_cache.py",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def environment():
    return {
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "system": platform.system(), "machine": platform.machine(),
        "packages": {name: version(name) for name in (
            "matplotlib", "numpy", "pillow", "fonttools", "mkdocs", "mkdocs-material",
            "Markdown", "pymdown-extensions",
        )},
    }


def cache_key(root=ROOT, runtime=None):
    # File hashes cover actual bytes, not timestamps or the commit ID.
    description = {
        "schema": 1,
        "inputs": {name: digest((root / name).read_bytes()) for name in INPUTS},
        "environment": environment() if runtime is None else runtime,
    }
    return digest(json.dumps(description, sort_keys=True).encode("utf-8"))


def write_if_changed(path, content):
    payload = content.encode("utf-8") if isinstance(content, str) else content
    if path.exists() and path.read_bytes() == payload:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def restore(cache_dir, key, output_dir):
    entry = cache_dir / key
    try:
        manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
        if manifest["key"] != key or set(manifest["files"]) != set(OUTPUTS):
            return False
        # Use only known relative paths; verify every file before restoring any.
        payloads = {name: (entry / name).read_bytes() for name in OUTPUTS}
        if any(digest(payloads[name]) != manifest["files"][name] for name in OUTPUTS):
            return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    for name, payload in payloads.items():
        write_if_changed(output_dir / name, payload)
    return True


def save(cache_dir, key, output_dir):
    entry = cache_dir / key
    hashes = {}
    for name in OUTPUTS:
        payload = (output_dir / name).read_bytes()
        write_if_changed(entry / name, payload)
        hashes[name] = digest(payload)
    # Publish the manifest last so an incomplete entry cannot be a hit.
    write_if_changed(entry / "manifest.json", json.dumps({"key": key, "files": hashes}, indent=2))


def snapshot_matches(payload, recorded_hash):
    """Git may convert CRLF to LF without changing the dependency list."""
    lf = payload.replace(b"\r\n", b"\n")
    return recorded_hash in {digest(payload), digest(lf), digest(lf.replace(b"\n", b"\r\n"))}
