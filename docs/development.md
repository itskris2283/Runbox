# Runbox Developer & Contributor Guide

**Project:** Runbox — Secure Code Execution & Sandboxing Infrastructure  
**Target Platform:** Linux x86_64 (Canonical environment: Ubuntu 24.04 LTS)  
**Document Version:** 1.0.0

---

## 1. System Requirements & Prerequisites

Runbox relies on contemporary Linux kernel features that must be verified before developing or deploying:
- **Operating System:** Ubuntu 24.04 LTS (Kernel 6.8+ or WSL2 Kernel 6.18+)
- **Architecture:** x86_64
- **Cgroups:** Cgroups v2 unified hierarchy mounted at `/sys/fs/cgroup`
- **Namespaces:** User namespaces, PID namespaces, and Network namespaces enabled
- **Security Subsystems:** `libseccomp` 2.5.5+, Landlock LSM enabled in kernel (`CONFIG_SECURITY_LANDLOCK=y`)

### 1.1 Toolchain & Package Installation

Execute the following on Ubuntu 24.04 to install all build and runtime dependencies:

```bash
sudo apt-get update && sudo apt-get install -y \
    build-essential \
    cmake \
    libseccomp-dev \
    python3.12 \
    python3.12-venv \
    python3-pip \
    nodejs \
    npm \
    git \
    pkg-config
```

---

## 2. Kernel & Cgroups v2 Configuration

Runbox manages execution resource limits through unified cgroups v2. Ensure the delegation controllers are active:

```bash
# Verify cgroups v2 is active
stat -fc %T /sys/fs/cgroup
# Output must be: cgroup2fs

# Create the dedicated runbox cgroup hierarchy
sudo mkdir -p /sys/fs/cgroup/runbox

# Enable memory, cpu, and pids controllers in root and runbox cgroups
echo "+memory +cpu +pids" | sudo tee /sys/fs/cgroup/cgroup.subtree_control
echo "+memory +cpu +pids" | sudo tee /sys/fs/cgroup/runbox/cgroup.subtree_control

# Grant execution user ownership over the runbox cgroup
sudo chown -R $USER:$USER /sys/fs/cgroup/runbox
```

---

## 3. Building the C++ Sandbox Core

The C++ supervisor is built using CMake and requires a C++20 compliant compiler (GCC 13+ or Clang 17+).

```bash
# From the repository root:
mkdir -p build && cd build

# Configure Release build with strict compiler warnings enabled
cmake -DCMAKE_BUILD_TYPE=Release ..

# Compile using all available CPU cores
make -j$(nproc)
```

This compiles:
- `librunbox_core.a`: Core static library containing namespaces, cgroups, seccomp, and filesystem logic.
- `runbox-supervisor`: The standalone execution supervisor binary.
- `runbox_tests`: The GoogleTest unit and integration test binary.

### 3.1 Executing the C++ Test Suite

Run the compiled GoogleTest binary:

```bash
# Execute unit and integration tests
./build/runbox_tests --gtest_color=yes
```

All 16 test cases must pass cleanly.

---

## 4. Python Environment & API Setup

Set up a Python 3.12 virtual environment for the FastAPI control plane and test runner:

```bash
# Create and activate virtual environment
python3.12 -m venv /opt/runbox_venv
source /opt/runbox_venv/bin/activate

# Install required Python dependencies
pip install --upgrade pip
pip install \
    fastapi \
    uvicorn \
    pydantic \
    aiosqlite \
    psutil \
    pytest \
    pytest-asyncio \
    pytest-cov \
    ruff \
    httpx
```

### 4.1 Running the Python Test Suite

The test suite is organized into unit, integration, and adversarial security suites:

```bash
# Run complete test suite with coverage
PYTHONPATH=. pytest tests/ -v --cov=api --cov=runtimes

# Run only the 24-test adversarial attack suite
PYTHONPATH=. pytest tests/adversarial/test_adversarial_suite.py -v

# Run API integration tests
PYTHONPATH=. pytest tests/integration/test_api.py -v
```

### 4.2 Static Analysis & Linting

We enforce zero warnings and strict formatting:

```bash
# Check code style and formatting with Ruff
ruff check .
```

---

## 5. Building the Developer Dashboard

The frontend is built with React 18, TypeScript, and Vite:

```bash
cd dashboard

# Install npm dependencies
npm install

# Run Vite development server with hot module reloading
npm run dev

# Compile production bundle
npm run build
```

Production static assets are generated into `dashboard/dist/`, which FastAPI automatically mounts and serves at `/`.

---

## 6. Running the Complete Runbox Service

Launch the FastAPI application:

```bash
# Start server with 4 worker threads on port 8000
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Once running:
- **Interactive Web Dashboard:** `http://localhost:8000/`
- **Interactive OpenAPI Documentation (Swagger UI):** `http://localhost:8000/docs`
- **ReDoc API Documentation:** `http://localhost:8000/redoc`

---

## 7. Running the Benchmark Suite

To measure system performance, latency distributions, and timeout jitter:

```bash
PYTHONPATH=. python3 benchmarks/run_benchmarks.py
```

This runs 5 complete trials (250 Python executions, 75 C++ executions, 75 timeout tests, and concurrency bursts) and outputs summary JSON data to `benchmarks/data/summary.json`.

---

## 8. Code Contribution Guidelines

1. **RAII Invariants:** Never use raw file descriptors or unmanaged memory in C++. Encapsulate all OS resources in RAII classes.
2. **Security Invariants:** Never bypass Seccomp, Landlock, or cgroup checks. Never weaken security filters to satisfy a failing test.
3. **No Shell Invocations:** Workloads must be executed directly via `execve`-style argument vectors. Never interpolate strings into shell commands.
4. **Clean Builds:** All code must compile with zero warnings under `-Wall -Wextra -Wpedantic -Werror`.
