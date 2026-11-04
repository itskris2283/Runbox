## Description

Brief description of the changes introduced in this pull request.

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Security hardening / remediation
- [ ] Performance improvement
- [ ] Documentation update
- [ ] CI / Build system improvement

## Subsystems Affected

- [ ] C++20 Sandbox Core (`core/`)
- [ ] Linux Supervisor / Isolation (`core/supervisor/`, `runtimes/`)
- [ ] Python Control Plane / Async API (`api/`)
- [ ] React 18 Dashboard (`dashboard/`)
- [ ] Test Suite (`tests/`)
- [ ] Benchmark Harness (`benchmarks/`)

## Verification & Testing

- [ ] C++ GoogleTests pass (`./build-release/runbox_tests`)
- [ ] Python unit & integration tests pass (`pytest tests/unit tests/integration`)
- [ ] Adversarial security test suite passes (`pytest tests/adversarial`)
- [ ] Ruff static analysis & formatting checks clean (`ruff check . && ruff format --check .`)
- [ ] Secret scanner clean (`python3 scripts/secret_scan.py`)
- [ ] No regression in code coverage ($\ge 80\%$ C++, $\ge 85\%$ Python)

## Security Checklist

- [ ] PR_SET_PDEATHSIG and PID namespace guarantees preserved
- [ ] Seccomp filter invariants intact
- [ ] No race conditions introduced in quota or rate limiter management
- [ ] Anti-enumeration status codes and timing considerations maintained
