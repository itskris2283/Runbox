#!/usr/bin/env python3
"""Repository secret scanner auditing for keys, tokens, credentials, and sensitive tokens."""

import os
import re
import sys

PATTERNS = [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}", "GitHub Token"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "Hardcoded JWT Token"),
    (r"AIza[0-9A-Za-z-_]{35}", "Google API Key"),
    (r"sq0csp-[0-9A-Za-z-_]{43}", "Square OAuth Secret"),
    (r"sk_live_[0-9a-zA-Z]{24}", "Stripe Live Secret Key"),
]

EXCLUDE_DIRS = {
    ".git",
    "build",
    "build-release",
    "node_modules",
    "dist",
    ".pytest_cache",
    "__pycache__",
}


def scan():
    findings = []
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f.endswith((".png", ".jpg", ".svg", ".o", ".a", ".so", ".gcda", ".gcno")):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as handle:
                    content = handle.read()
                    for pattern, desc in PATTERNS:
                        matches = re.findall(pattern, content)
                        if matches:
                            findings.append((fpath, desc, len(matches)))
            except Exception:
                pass

    if findings:
        print(f"[ALERT] Secrets detected: {len(findings)}")
        for fpath, desc, count in findings:
            print(f"  - {os.path.relpath(fpath, root_dir)}: {desc} ({count} instances)")
        sys.exit(1)
    else:
        print("[SUCCESS] Secret scan clean: 0 private keys, API secrets, or credentials found.")
        sys.exit(0)


if __name__ == "__main__":
    scan()
