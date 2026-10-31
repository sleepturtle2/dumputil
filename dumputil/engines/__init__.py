"""Shared helpers for engine modules.

An engine module exposes: NAME, add_ops(subparsers), schema(path, profile, args) -> list[str],
text(path, profile, args) -> iterable of (group, line). cli.py registers engines; diff.py compares.
"""
import hashlib
import os
import subprocess
from pathlib import Path


class DumpError(Exception):
    """Operator-facing failure; cli prints the message and exits 2."""


def run(cmd, stdin=None, env=None):
    """Streams stdout lines (newline stripped) of cmd. stderr passes through. Non-zero exit → DumpError."""
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin is not None else None,
                             stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
    except FileNotFoundError:
        raise DumpError(f"{cmd[0]}: not found") from None
    if stdin is not None:
        p.stdin.write(stdin)
        p.stdin.close()
    for line in p.stdout:
        yield line.rstrip("\n")
    if p.wait() != 0:
        raise DumpError(f"{cmd[0]} exited {p.returncode}")


def check(cmd, env=None):
    """Runs cmd to completion, output passes through. Non-zero exit → DumpError."""
    try:
        r = subprocess.run(cmd, env=env)
    except FileNotFoundError:
        raise DumpError(f"{cmd[0]}: not found") from None
    if r.returncode != 0:
        raise DumpError(f"{cmd[0]} exited {r.returncode}")


def tool(profile, key, name):
    """Binary `name` under the directory in profile[key], else from PATH."""
    d = profile.get(key, "")
    return os.path.join(d, name) if d else os.path.basename(name)


def sha256_file(path):
    """Writes/updates `<dir>/SHA256` (shasum -c compatible) with path's digest; returns the digest."""
    path = Path(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sums = path.parent / "SHA256"
    keep = [l for l in (sums.read_text().splitlines() if sums.exists() else [])
            if not l.endswith("  " + path.name)]
    sums.write_text("\n".join(keep + [f"{h.hexdigest()}  {path.name}"]) + "\n")
    return h.hexdigest()
