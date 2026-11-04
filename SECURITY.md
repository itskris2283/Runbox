# Security Policy

## Supported Versions

Only the latest release of Runbox receives security updates and vulnerability patches.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.1   | :white_check_mark: |
| < 0.1.1 | :x:                |

---

## Reporting a Vulnerability

The Runbox team takes security vulnerabilities seriously. Because Runbox is designed to execute untrusted code in multi-tenant environments, sandbox escape vectors, privilege escalation flaws, and resource boundary bypasses are prioritized with the highest urgency.

### How to Report
- **DO NOT** report security vulnerabilities via public GitHub issues, discussions, or pull requests.
- Please report vulnerabilities privately by emailing the maintainers or filing a GitHub Private Security Advisory via GitHub's vulnerability reporting tab.
- Provide a detailed proof-of-concept (PoC) demonstrating the escape or resource bypass.
- Include the exact kernel version (`uname -r`), CPU architecture, and distribution details.

### What to Expect
- **Initial Response:** You will receive an acknowledgment within 48 hours.
- **Triage & Assessment:** The engineering team will triage the report and reproduce the PoC on native Ubuntu 24.04 LTS.
- **Coordination & Disclosure:** We practice coordinated vulnerability disclosure. We will agree upon a reasonable disclosure timeline (typically 30–90 days) to allow patch creation, testing, and deployment before public disclosure.

---

## Security Model Assumptions

Runbox provides container-grade isolation based on native Linux kernel mechanisms:
- Private Namespaces (`CLONE_NEWPID`, `CLONE_NEWNET`, `CLONE_NEWNS`, `CLONE_NEWIPC`, `CLONE_NEWUTS`, `CLONE_NEWCGROUP`)
- Unified Cgroups v2 controllers (`memory.max`, `memory.swap.max=0`, `cpu.max`, `pids.max`)
- Landlock LSM kernel path sandboxing
- Seccomp BPF syscall allowlisting with default kill action
- Ambient capability dropping and unprivileged user transitions (UID/GID 65534)

Kernel zero-day vulnerabilities in unpatched host kernels or hardware microarchitectural side-channel attacks are outside Runbox's threat model.
