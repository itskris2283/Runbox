# Runbox v0.1.1 — Production Deployment Guide (Ubuntu 24.04 LTS)

## 1. System Requirements

### 1.1 Hardware Specifications
- **Architecture**: x86_64 or aarch64 Linux.
- **CPU**: 4 physical or virtual cores minimum.
- **Memory**: 8 GB RAM minimum.
- **Storage**: 40 GB NVMe or SSD storage.

### 1.2 Kernel & Operating System
- **OS**: Ubuntu 24.04 LTS (Noble Numbat).
- **Kernel**: Linux 6.8+ (Cgroups v2 unified hierarchy, Seccomp BPF, Landlock LSM ABI v1-v3).
- **Cgroups Configuration**: Unified hierarchy enabled (`cgroup_no_v1=all systemd.unified_cgroup_hierarchy=1`).

---

## 2. Prerequisites & System Configuration

### 2.1 Package Dependencies
Install the required systems build and runtime libraries:
```bash
sudo apt update && sudo apt install -y \
    build-essential \
    cmake \
    ninja-build \
    libseccomp-dev \
    pkg-config \
    python3 \
    python3-dev \
    python3-venv \
    python3-pip \
    libsqlite3-dev
```

### 2.2 Unprivileged User Namespaces & Cgroups v2
Ensure unprivileged user namespace creation is permitted by the kernel:
```bash
sudo sysctl -w kernel.unprivileged_userns_clone=1
echo "kernel.unprivileged_userns_clone=1" | sudo tee -a /etc/sysctl.d/99-runbox.conf
```

Verify Cgroups v2 hierarchy and controllers:
```bash
mount | grep cgroup2
cat /sys/fs/cgroup/cgroup.controllers
# Output must include: memory cpu pids
```

Create base cgroup with delegation for the Runbox service user:
```bash
sudo mkdir -p /sys/fs/cgroup/runbox
echo "+memory +cpu +pids" | sudo tee /sys/fs/cgroup/cgroup.subtree_control
sudo chown -R root:root /sys/fs/cgroup/runbox
sudo chmod 0755 /sys/fs/cgroup/runbox
```

---

## 3. Building the C++ Supervisor Core

```bash
cd /opt/runbox
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release -DENABLE_COVERAGE=OFF ..
make -j$(nproc) runbox-supervisor runbox_tests

# Run self-test suite
./runbox_tests
```

Install the supervisor binary to `/usr/local/bin`:
```bash
sudo cp runbox-supervisor /usr/local/bin/runbox-supervisor
sudo chmod 0755 /usr/local/bin/runbox-supervisor
```

---

## 4. Setting Up the Control Plane (FastAPI)

```bash
# Set up Python virtual environment
python3 -m venv /opt/runbox/venv
source /opt/runbox/venv/bin/activate
pip install -U pip setuptools wheel
pip install -r /opt/runbox/requirements.txt

# Production configuration environment
sudo mkdir -p /etc/runbox /var/lib/runbox
```

Create `/etc/runbox/runbox.env`:
```ini
ENVIRONMENT=production
RUNBOX_DB_PATH=/var/lib/runbox/runbox.db
RUNBOX_SUPERVISOR_BIN=/usr/local/bin/runbox-supervisor
MAX_CONCURRENCY=10
DEFAULT_TIMEOUT_MS=3000
DEFAULT_MEMORY_MB=128
DEFAULT_CPU_QUOTA_PERCENT=50
DEFAULT_PROCESS_LIMIT=32

# Authentication API keys (colon-delimited tokens)
API_KEYS=sec_token_prod_admin:sec_token_tenant_alpha:sec_token_tenant_beta
ADMIN_API_KEYS=sec_token_prod_admin
```

---

## 5. Systemd Service Configuration

Create `/etc/systemd/system/runbox.service`:
```ini
[Unit]
Description=Runbox Secure Code Execution Engine
After=network.target local-fs.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/runbox
EnvironmentFile=/etc/runbox/runbox.env
ExecStart=/opt/runbox/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5s
LimitNOFILE=65536
LimitNPROC=32768
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable runbox
sudo systemctl start runbox
sudo systemctl status runbox
```

---

## 6. Verification & Health Probes

```bash
# Verify health probes
curl -i http://localhost:8000/api/v1/health/ready
curl -i http://localhost:8000/healthz

# Test authenticated execution
curl -X POST http://localhost:8000/api/v1/executions \
  -H "X-API-Key: sec_token_prod_admin" \
  -H "Content-Type: application/json" \
  -d '{"language": "python", "source_code": "print(42)"}'
```
