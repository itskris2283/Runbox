---
name: Security Vulnerability Report
about: Report a potential security flaw or sandbox breakout vector
title: "[SECURITY] "
labels: ["security"]
assignees: ""
---

> [!CAUTION]
> If this vulnerability affects live production deployments or allows sandbox breakout, please review `SECURITY.md` for responsible disclosure instructions before filing a public issue.

### Vulnerability Summary
High-level description of the security issue.

### Boundary Affected
- [ ] Linux Namespaces (PID, Mount, IPC, UTS, Network, User)
- [ ] Seccomp-BPF Syscall Filter
- [ ] Cgroups v2 Resource Enforcement (OOM, CPU, PID ceiling)
- [ ] Ephemeral Filesystem Isolation (Overlayfs / tmpfs leak)
- [ ] API Authentication & Tenant Isolation
- [ ] Supervisor Lifecycle & Signal Handling (`PR_SET_PDEATHSIG`)

### Proof of Concept (PoC)
Code snippet or script demonstrating the isolation violation:
```python
# Insert minimal reproduction code here
```

### Impact & Remediation Suggestion
Describe potential blast radius and suggested remediation.
