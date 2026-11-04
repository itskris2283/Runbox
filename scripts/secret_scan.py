#!/usr/bin/env python3
import os
import re

PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[0-9a-zA-Z]{36}"),
    re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"),
    re.compile(r"(?:sk_live|rk_live)_[0-9a-zA-Z]{24}"),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{64,}", re.IGNORECASE),
]

IGNORE_DIRS = {
    "build",
    "build-release",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "data",
    "results",
    ".git",
}

IGNORE_EXTS = {
    ".db",
    ".db-wal",
    ".db-shm",
    ".pyc",
    ".png",
    ".svg",
    ".jpg",
    ".tar.gz",
    ".lock",
    ".coverage",
}


def scan():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    found = []

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1]
            if ext in IGNORE_EXTS or f.endswith(".json"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    for line_num, line in enumerate(fh, 1):
                        for pat in PATTERNS:
                            if pat.search(line):
                                # Skip test mock credentials
                                if "test" in path.lower() or "mock" in line.lower():
                                    continue
                                rel_path = os.path.relpath(path, repo_root)
                                found.append((rel_path, line_num))
            except Exception:
                pass

    print(f"Scan complete. Potential secrets detected: {len(found)}")
    for rel_path, line_num in found:
        print(f"  [FLAG] {rel_path}:{line_num}")
    return 1 if found else 0


if __name__ == "__main__":
    import sys

    sys.exit(scan())
