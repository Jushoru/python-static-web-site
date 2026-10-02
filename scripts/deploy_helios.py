"""Upload a built report via OpenSSH SFTP to its fixed Helios directory.

Only the CI job calls the real upload. --dry-run validates the local artifact
without reading credentials or connecting to a server. No remote deletion.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


REMOTE = "/home/studs/s370419/public_html/python-static-web-site"
USER = "s370419"
MARKER = "PYTHON-STATIC-REPORT-T1-P3"


def make_batch(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Artifact must be a directory, not a symbolic link")
    files, directories = [], []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError("Symbolic links are not allowed in the artifact")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in relative.parts):
            raise ValueError(f"Unsupported artifact filename: {relative}")
        if path.is_dir():
            directories.append(relative.as_posix())
        elif path.is_file():
            files.append(relative.as_posix())
        else:
            raise ValueError(f"Unsupported artifact entry: {relative}")
    for required in ("index.html", "results.html", "search/search_index.json"):
        if required not in files:
            raise ValueError(f"Missing report file: {required}")
    if MARKER not in (root / "index.html").read_text(encoding="utf-8"):
        raise ValueError("The artifact is not the expected report")
    # The directory already exists after the initial manual deployment.
    lines = [f'cd "{REMOTE}"']
    for directory in sorted(directories, key=lambda p: (p.count("/"), p)):
        lines += [f'-mkdir "./{directory}"', f'chmod 755 "./{directory}"']
    # Resources first, HTML afterwards; results.html with the commit ID goes last.
    files.sort(key=lambda p: (2 if p == "results.html" else int(p.endswith(".html")), p))
    for file in files:
        lines += [f'put "./{file}" "./{file}"', f'chmod 644 "./{file}"']
    lines.append("bye")
    return "\n".join(lines) + "\n", len(files)


def connection():
    host = os.environ.get("HELIOS_HOST", "")
    port = os.environ.get("HELIOS_PORT", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host):
        raise ValueError("Set HELIOS_HOST to the SSH hostname")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("Set HELIOS_PORT to a port between 1 and 65535")
    return host, port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=Path("_published/helios"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    batch, count = make_batch(args.site_dir)
    if args.dry_run:
        print(f"Validated {count} files; fixed destination: {REMOTE}; no connection made.")
        return
    host, port = connection()
    key = os.environ.get("HELIOS_SSH_KEY", "").replace("\r\n", "\n").strip()
    known_hosts = os.environ.get("HELIOS_KNOWN_HOSTS", "").replace("\r\n", "\n").strip()
    if not key or not known_hosts:
        raise ValueError("Set HELIOS_SSH_KEY and HELIOS_KNOWN_HOSTS environment secrets")
    # Credentials live only in a private temporary directory, outside artifacts.
    with tempfile.TemporaryDirectory(prefix="helios-deploy-") as work:
        work = Path(work)
        identity, hosts, commands = work / "identity", work / "known_hosts", work / "batch"
        for path, contents in ((identity, key), (hosts, known_hosts), (commands, batch)):
            path.write_text(contents + "\n", encoding="utf-8")
            path.chmod(0o600)
        child_env = {k: v for k, v in os.environ.items()
                     if k not in {"HELIOS_SSH_KEY", "HELIOS_KNOWN_HOSTS"}}
        subprocess.run([
            "sftp", "-F", os.devnull, "-b", str(commands), "-P", port,
            "-i", str(identity), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={hosts}",
            "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3", f"{USER}@{host}",
        ], cwd=args.site_dir.resolve(), env=child_env, check=True, timeout=480)
    print(f"Uploaded {count} files to the Helios report directory.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Helios upload failed: {error}") from error
