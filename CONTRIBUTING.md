# Contributing to Runbox

Thank you for your interest in contributing to **Runbox**! We welcome pull requests, bug reports, security disclosures, and architectural feedback from systems engineers, kernel researchers, and open-source developers.

---

## 1. Development Principles

When contributing to Runbox, adhere to these fundamental engineering standards:
1. **Security & Correctness First:** Security mechanisms must never be weakened or bypassed to improve benchmarks or simplify code.
2. **Empirical Verification:** Do not claim a capability or performance metric without providing tests or microbenchmark evidence demonstrating it.
3. **No Compiler Warnings or Linter Errors:** All C++ code must compile cleanly under `-Wall -Wextra -Wpedantic -Werror`. All Python code must pass `ruff check .` and `ruff format .`.
4. **Regression Test Coverage:** Every bug fix or security patch must include an accompanying GoogleTest or Pytest test case.

---

## 2. Setting Up the Development Environment

### Prerequisites (Ubuntu 24.04 LTS)
```bash
sudo apt-get update && sudo apt-get install -y \
    build-essential cmake libseccomp-dev python3.12 python3.12-venv nodejs npm
```

### Cgroups v2 Setup
Runbox requires unprivileged user delegation on unified cgroups v2:
```bash
sudo mkdir -p /sys/fs/cgroup/runbox
echo "+memory +cpu +pids" | sudo tee /sys/fs/cgroup/cgroup.subtree_control
echo "+memory +cpu +pids" | sudo tee /sys/fs/cgroup/runbox/cgroup.subtree_control
sudo chown -R $USER:$USER /sys/fs/cgroup/runbox
```

### Building C++ Core & Tests
```bash
mkdir -p build-release && cd build-release
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build . -j$(nproc)
./runbox_tests
```

### Python Virtualenv & Testing
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
PYTHONPATH=. pytest tests/unit tests/integration tests/adversarial
```

### Frontend Dashboard
```bash
cd dashboard
npm ci
npm run build
```

---

## 3. Pull Request Guidelines

1. Fork the repository and create a feature branch (`git checkout -b feature/kernel-enhancement`).
2. Implement your changes following existing architectural boundaries:
   - Linux kernel primitives belong in `core/`.
   - API endpoints, persistence, and scheduling belong in `api/`.
   - Runtime execution adapters belong in `runtimes/`.
   - Web UI components belong in `dashboard/`.
3. Verify all 232 automated tests pass:
   ```bash
   ./build-release/runbox_tests                                          # 93 C++ GoogleTests
   PYTHONPATH=. pytest tests/unit tests/integration tests/adversarial    # 139 Python tests
   ```
4. Verify code coverage meets project thresholds:
   - Total C++ Core: $\ge 80.0\%$
   - Supervisor Core: $\ge 80.0\%$
   - Python Control Plane: $\ge 85.0\%$
5. Verify zero linting, formatting, and secret leaks:
   ```bash
   ruff check .
   ruff format --check .
   python3 scripts/secret_scan.py
   ```
6. Submit a pull request describing the change, security implications, and empirical test results.
