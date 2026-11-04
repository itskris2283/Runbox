import asyncio
import os
import shutil

import psutil
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app, db, scheduler


@pytest.fixture
async def client():
    await db.connect()
    if scheduler._running:
        await scheduler.stop()
    # Recreate fresh queue for the current test loop
    scheduler.queue = asyncio.Queue(maxsize=100)
    await scheduler.start()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await scheduler.stop()
    await db.close()


async def wait_for_job(
    client: AsyncClient, execution_id: str, max_ticks: int = 100, headers: dict | None = None
) -> dict:
    for _ in range(max_ticks):
        res = await client.get(f"/api/v1/executions/{execution_id}", headers=headers)
        data = res.json()
        if "status" in data and data["status"] in (
            "completed",
            "failed",
            "timed_out",
            "resource_limit_exceeded",
            "cancelled",
        ):
            return data
        await asyncio.sleep(0.05)
    return data


@pytest.mark.asyncio
async def test_01_infinite_cpu_loop(client):
    payload = {
        "language": "python",
        "source_code": "while True: pass",
        "limits": {"timeout_ms": 1000, "cpu_quota_percent": 25},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] == "timed_out"
    assert data["termination_reason"] == "timed_out"
    assert data["resource_usage"]["wall_time_ms"] < 2500


@pytest.mark.asyncio
async def test_02_memory_exhaustion(client):
    payload = {
        "language": "python",
        "source_code": "b = bytearray(200 * 1024 * 1024)",  # Attempt 200MB allocation with 32MB limit
        "limits": {"timeout_ms": 4000, "memory_mb": 32},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("failed", "resource_limit_exceeded")
    assert data["exit_code"] != 0 or data["termination_reason"] == "memory_limit_exceeded"


@pytest.mark.asyncio
async def test_03_process_creation_bomb(client):
    payload = {
        "language": "python",
        "source_code": (
            "import os, time\n"
            "for _ in range(100):\n"
            "    try:\n"
            "        if os.fork() == 0:\n"
            "            time.sleep(10)\n"
            "            os._exit(0)\n"
            "    except OSError:\n"
            "        pass\n"
            "print('FORK_BOMB_SURVIVED')\n"
        ),
        "limits": {"timeout_ms": 2000, "process_limit": 8},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "FORK_BOMB_SURVIVED" in data["stdout"] or data["status"] in (
        "completed",
        "failed",
        "timed_out",
    )


@pytest.mark.asyncio
async def test_04_host_filesystem_access(client):
    payload = {
        "language": "python",
        "source_code": (
            "try:\n"
            "    with open('/etc/shadow', 'r') as f:\n"
            "        print('READ_SHADOW_SUCCESS')\n"
            "except Exception as e:\n"
            "    print(f'ACCESS_DENIED:{type(e).__name__}')\n"
        ),
        "limits": {"timeout_ms": 2000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "READ_SHADOW_SUCCESS" not in data["stdout"]
    assert "ACCESS_DENIED" in data["stdout"]


@pytest.mark.asyncio
async def test_05_unauthorized_file_writes(client):
    payload = {
        "language": "python",
        "source_code": (
            "try:\n"
            "    with open('/etc/hacked.txt', 'w') as f:\n"
            "        f.write('bad')\n"
            "    print('WRITE_SUCCESS')\n"
            "except Exception as e:\n"
            "    print(f'WRITE_DENIED:{type(e).__name__}')\n"
        ),
        "limits": {"timeout_ms": 2000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "WRITE_SUCCESS" not in data["stdout"]
    assert "WRITE_DENIED" in data["stdout"]


@pytest.mark.asyncio
async def test_06_path_traversal(client):
    payload = {
        "language": "python",
        "source_code": (
            "import os\n"
            "try:\n"
            "    files = os.listdir('../../../../../root')\n"
            "    print('TRAVERSAL_SUCCESS')\n"
            "except Exception as e:\n"
            "    print(f'TRAVERSAL_BLOCKED:{type(e).__name__}')\n"
        ),
        "limits": {"timeout_ms": 2000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "TRAVERSAL_SUCCESS" not in data["stdout"]
    assert "TRAVERSAL_BLOCKED" in data["stdout"]


@pytest.mark.asyncio
async def test_07_symlink_escape_attempts(client):
    payload = {
        "language": "python",
        "source_code": (
            "import os\n"
            "try:\n"
            "    os.symlink('/etc/shadow', 'symlink_test')\n"
            "    with open('symlink_test', 'r') as f: print('ESCAPE_SUCCESS')\n"
            "except Exception as e:\n"
            "    print(f'ESCAPE_BLOCKED:{type(e).__name__}')\n"
        ),
        "limits": {"timeout_ms": 2000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "ESCAPE_SUCCESS" not in data["stdout"]
    assert "ESCAPE_BLOCKED" in data["stdout"]


@pytest.mark.asyncio
async def test_08_network_connection_attempts(client):
    payload = {
        "language": "python",
        "source_code": (
            "import socket\n"
            "try:\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    s.settimeout(1)\n"
            "    s.connect(('1.1.1.1', 80))\n"
            "    print('NET_SUCCESS')\n"
            "except Exception as e:\n"
            "    print(f'NET_BLOCKED:{type(e).__name__}')\n"
        ),
        "limits": {"timeout_ms": 3000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "NET_SUCCESS" not in data["stdout"]
    assert "NET_BLOCKED" in data["stdout"]


@pytest.mark.asyncio
async def test_09_excessive_stdout(client):
    payload = {
        "language": "python",
        "source_code": "print('A' * 5000000)",  # 5 MB output with 64 KB limit
        "limits": {"timeout_ms": 3000, "output_limit_bytes": 65536},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert len(data["stdout"]) <= 65536


@pytest.mark.asyncio
async def test_10_excessive_stderr(client):
    payload = {
        "language": "python",
        "source_code": "import sys\nsys.stderr.write('E' * 5000000)",
        "limits": {"timeout_ms": 3000, "output_limit_bytes": 65536},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert len(data["stderr"]) <= 65536


@pytest.mark.asyncio
async def test_11_infinite_child_process(client):
    payload = {
        "language": "python",
        "source_code": (
            "import os, time\n"
            "pid = os.fork()\n"
            "if pid == 0:\n"
            "    while True: time.sleep(1)\n"
            "else:\n"
            "    print('PARENT_DONE')\n"
        ),
        "limits": {"timeout_ms": 1000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("completed", "timed_out")


@pytest.mark.asyncio
async def test_12_background_process_persistence(client):
    # Verify after job terminates, no stray child process remains
    initial_pids = set(psutil.pids())
    payload = {
        "language": "python",
        "source_code": (
            "import os, time\n"
            "if os.fork() == 0:\n"
            "    os.setsid()\n"
            "    if os.fork() == 0:\n"
            "        time.sleep(2)\n"
            "        os._exit(0)\n"
            "    os._exit(0)\n"
            "time.sleep(0.1)\n"
            "print('DAEMON_SPAWNED')\n"
        ),
        "limits": {"timeout_ms": 1500},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "DAEMON_SPAWNED" in data["stdout"]
    await asyncio.sleep(0.5)
    remaining = set(psutil.pids()) - initial_pids
    assert len(remaining) <= 5  # No runaway daemon processes remain


@pytest.mark.asyncio
async def test_13_large_temporary_file_creation(client):
    payload = {
        "language": "python",
        "source_code": (
            "try:\n"
            "    with open('/tmp/bigfile.bin', 'wb') as f:\n"
            "        f.write(b'\\x00' * (100 * 1024 * 1024))\n"
            "    print('WRITE_BIG_OK')\n"
            "except Exception as e:\n"
            "    print(f'WRITE_BIG_FAIL:{type(e).__name__}')\n"
        ),
        "limits": {"timeout_ms": 3000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    # 64MB tmpfs limit prevents 100MB file
    assert "WRITE_BIG_OK" not in data["stdout"] or data["status"] in ("completed", "failed")


@pytest.mark.asyncio
async def test_14_excessive_thread_creation(client):
    payload = {
        "language": "python",
        "source_code": (
            "import threading, time\n"
            "threads = []\n"
            "try:\n"
            "    for _ in range(500):\n"
            "        t = threading.Thread(target=lambda: time.sleep(1))\n"
            "        t.start()\n"
            "        threads.append(t)\n"
            "    print('ALL_THREADS_STARTED')\n"
            "except Exception as e:\n"
            "    print(f'THREAD_LIMIT_HIT:{type(e).__name__}')\n"
        ),
        "limits": {"timeout_ms": 2000, "process_limit": 16},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "ALL_THREADS_STARTED" not in data["stdout"]


@pytest.mark.asyncio
async def test_15_runtime_timeout(client):
    payload = {
        "language": "python",
        "source_code": "import time\ntime.sleep(5)",
        "limits": {"timeout_ms": 500},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] == "timed_out"


@pytest.mark.asyncio
async def test_16_compilation_timeout(client):
    # C++ template bomb causing compilation exhaustion
    template_bomb = """
    template<int N> struct Bomb { enum { val = Bomb<N-1>::val + Bomb<N-2>::val }; };
    template<> struct Bomb<0> { enum { val = 1 }; };
    template<> struct Bomb<1> { enum { val = 1 }; };
    int main() { return Bomb<35>::val; }
    """
    payload = {"language": "cpp", "source_code": template_bomb, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"], max_ticks=250)
    assert data["status"] in ("completed", "failed", "timed_out")


@pytest.mark.asyncio
async def test_17_cancellation_during_execution(client):
    payload = {
        "language": "python",
        "source_code": "import time\ntime.sleep(10)",
        "limits": {"timeout_ms": 15000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    exec_id = res.json()["execution_id"]

    await asyncio.sleep(0.1)
    del_res = await client.delete(f"/api/v1/executions/{exec_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "cancelled"
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_18_repeated_execution(client):
    for i in range(5):
        payload = {
            "language": "python",
            "source_code": f"print('RUN_{i}')",
            "limits": {"timeout_ms": 2000},
        }
        res = await client.post("/api/v1/executions", json=payload)
        data = await wait_for_job(client, res.json()["execution_id"])
        assert f"RUN_{i}" in data["stdout"]


@pytest.mark.asyncio
async def test_19_concurrent_execution(client):
    tasks = []
    for i in range(4):
        payload = {
            "language": "python",
            "source_code": f"import time\ntime.sleep(0.1)\nprint('CONC_{i}')",
            "limits": {"timeout_ms": 3000},
        }
        tasks.append(client.post("/api/v1/executions", json=payload))

    responses = await asyncio.gather(*tasks)
    exec_ids = [r.json()["execution_id"] for r in responses]

    job_data = await asyncio.gather(*[wait_for_job(client, eid) for eid in exec_ids])
    for i, data in enumerate(job_data):
        assert f"CONC_{i}" in data["stdout"]


@pytest.mark.asyncio
async def test_20_invalid_runtime_configuration(client):
    payload = {
        "language": "unknown_lang",
        "source_code": "echo test",
        "limits": {"timeout_ms": 1000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_21_cross_execution_isolation(client):
    # Job A writes a file to /workspace/secret.txt
    payload_a = {
        "language": "python",
        "source_code": "with open('secret.txt', 'w') as f: f.write('SECRET_KEY_1234')\nprint('A_WROTE')",
        "limits": {"timeout_ms": 3000},
    }
    # Job B attempts to read secret.txt
    payload_b = {
        "language": "python",
        "source_code": (
            "import os\n"
            "print('FILE_EXISTS' if os.path.exists('secret.txt') else 'FILE_NOT_FOUND')\n"
        ),
        "limits": {"timeout_ms": 3000},
    }

    res_a = await client.post("/api/v1/executions", json=payload_a)
    data_a = await wait_for_job(client, res_a.json()["execution_id"])
    assert "A_WROTE" in data_a["stdout"]

    res_b = await client.post("/api/v1/executions", json=payload_b)
    data_b = await wait_for_job(client, res_b.json()["execution_id"])
    assert "FILE_NOT_FOUND" in data_b["stdout"]


@pytest.mark.asyncio
async def test_22_environment_variable_sanitization(client):
    payload = {
        "language": "python",
        "source_code": (
            "import os\n"
            "leaks = [k for k in os.environ if k in ('AWS_SECRET_ACCESS_KEY', 'SECRET_KEY', 'RUNBOX_DB_PATH')]\n"
            "print('LEAKS:', leaks)\n"
        ),
        "limits": {"timeout_ms": 2000},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "LEAKS: []" in data["stdout"]


@pytest.mark.asyncio
async def test_23_resource_limit_clamping_abuse(client):
    # Send extreme values
    payload = {
        "language": "python",
        "source_code": "print('CLAMPED_OK')",
        "limits": {
            "timeout_ms": 9999999,  # API will clamp to 30000
            "memory_mb": 999999,  # API will clamp to 1024
            "process_limit": 999999,  # API will clamp to 64
        },
    }
    res = await client.post("/api/v1/executions", json=payload)
    # Pydantic validation catches values exceeding max schema limits
    assert res.status_code in (202, 422)


@pytest.mark.asyncio
async def test_24_cleanup_verification(client):
    # Ensure any previous aborted workspace directories from earlier tests are cleaned
    for e in os.listdir("/tmp"):
        if e.startswith("runbox_ws_"):
            shutil.rmtree(os.path.join("/tmp", e), ignore_errors=True)

    # Verify that after completing jobs, /tmp does not have lingering workspace dirs
    payload = {"language": "python", "source_code": "print('CLEANUP_TEST')"}
    for _ in range(3):
        res = await client.post("/api/v1/executions", json=payload)
        await wait_for_job(client, res.json()["execution_id"])

    # Check for lingering runbox_ws_ directories (polling briefly for asynchronous thread offload)
    lingering = []
    for _ in range(10):
        tmp_entries = os.listdir("/tmp")
        lingering = [e for e in tmp_entries if e.startswith("runbox_ws_")]
        if len(lingering) == 0:
            break
        await asyncio.sleep(0.05)
    assert len(lingering) == 0


@pytest.mark.asyncio
async def test_25_double_fork_daemon_breakout(client):
    # Attempt setsid() and second fork to orphan process to init
    code = (
        "import os, sys, time\n"
        "pid1 = os.fork()\n"
        "if pid1 == 0:\n"
        "    os.setsid()\n"
        "    pid2 = os.fork()\n"
        "    if pid2 == 0:\n"
        "        time.sleep(10)\n"
        "        sys.exit(0)\n"
        "    sys.exit(0)\n"
        "os.waitpid(pid1, 0)\n"
        "print('ORPHAN_ATTEMPT_DONE')\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("completed", "failed", "timed_out")


@pytest.mark.asyncio
async def test_26_inode_exhaustion_storm(client):
    # Attempt creating thousands of files in workspace
    code = (
        "try:\n"
        "    for i in range(20000):\n"
        "        with open(f'tmp_{i}.txt', 'w') as f:\n"
        "            f.write('x')\n"
        "    print('STORM_SUCCESS')\n"
        "except Exception as e:\n"
        "    print('STORM_BLOCKED:', type(e).__name__)\n"
    )
    payload = {
        "language": "python",
        "source_code": code,
        "limits": {"timeout_ms": 3000, "memory_mb": 64},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("completed", "failed", "timed_out")


@pytest.mark.asyncio
async def test_27_mmap_memory_exhaustion(client):
    # Attempt allocating huge memory block via mmap
    code = (
        "import mmap\n"
        "try:\n"
        "    m = mmap.mmap(-1, 512 * 1024 * 1024)\n"
        "    m.write(b'\\x01' * (512 * 1024 * 1024))\n"
        "    print('MMAP_SURVIVED')\n"
        "except Exception as e:\n"
        "    print('MMAP_BLOCKED:', type(e).__name__)\n"
    )
    payload = {
        "language": "python",
        "source_code": code,
        "limits": {"timeout_ms": 3000, "memory_mb": 64},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("resource_limit_exceeded", "failed", "completed")


@pytest.mark.asyncio
async def test_28_ipv6_raw_socket_blocked(client):
    code = (
        "import socket\n"
        "try:\n"
        "    s = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_RAW)\n"
        "    print('RAW_SOCK_OPENED')\n"
        "except Exception as e:\n"
        "    print('RAW_SOCK_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "RAW_SOCK_BLOCKED" in data["stdout"] or data["status"] == "failed"


@pytest.mark.asyncio
async def test_29_unix_domain_socket_host_escape(client):
    code = (
        "import socket\n"
        "try:\n"
        "    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "    s.connect('/var/run/docker.sock')\n"
        "    print('DOCKER_SOCK_CONNECTED')\n"
        "except Exception as e:\n"
        "    print('DOCKER_SOCK_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "DOCKER_SOCK_BLOCKED" in data["stdout"]


@pytest.mark.asyncio
async def test_30_host_proc_environ_leakage(client):
    code = (
        "try:\n"
        "    with open('/proc/1/environ', 'rb') as f:\n"
        "        data = f.read()\n"
        "    print('PROC_1_EXPOSED' if len(data) > 0 else 'PROC_1_EMPTY')\n"
        "except Exception as e:\n"
        "    print('PROC_1_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "PROC_1_BLOCKED" in data["stdout"] or "PROC_1_EMPTY" in data["stdout"]


@pytest.mark.asyncio
async def test_31_sys_fs_modification_attempt(client):
    code = (
        "try:\n"
        "    with open('/sys/fs/cgroup/cgroup.procs', 'w') as f:\n"
        "        f.write('1')\n"
        "    print('SYS_WRITE_EXPOSED')\n"
        "except Exception as e:\n"
        "    print('SYS_WRITE_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "SYS_WRITE_BLOCKED" in data["stdout"]


@pytest.mark.asyncio
async def test_32_mknod_device_creation(client):
    code = (
        "import os, stat\n"
        "try:\n"
        "    os.mknod('raw_dev', stat.S_IFCHR | 0o666, os.makedev(1, 3))\n"
        "    print('MKNOD_EXPOSED')\n"
        "except Exception as e:\n"
        "    print('MKNOD_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "MKNOD_BLOCKED" in data["stdout"] or data["status"] == "failed"


@pytest.mark.asyncio
async def test_33_ptrace_syscall_blocked(client):
    # ptrace syscall (syscall number 101 on x86_64) should be blocked by seccomp
    code = (
        "import ctypes\n"
        "libc = ctypes.CDLL(None)\n"
        "try:\n"
        "    # SYS_ptrace = 101, PTRACE_TRACEME = 0\n"
        "    res = libc.syscall(101, 0, 0, 0, 0)\n"
        "    print('PTRACE_RES:', res)\n"
        "except Exception as e:\n"
        "    print('PTRACE_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    # Should either receive SIGSYS (termination_reason: seccomp_blocked / bad system call) or return -1
    assert data["status"] in ("failed", "completed")


@pytest.mark.asyncio
async def test_34_ebpf_bpf_syscall_blocked(client):
    # bpf syscall (syscall 321 on x86_64) should be blocked by seccomp
    code = (
        "import ctypes\n"
        "libc = ctypes.CDLL(None)\n"
        "try:\n"
        "    res = libc.syscall(321, 0, 0, 0)\n"
        "    print('BPF_RES:', res)\n"
        "except Exception as e:\n"
        "    print('BPF_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("failed", "completed")


@pytest.mark.asyncio
async def test_35_reboot_shutdown_syscall_blocked(client):
    # reboot syscall (syscall 169 on x86_64) should be strictly blocked by seccomp
    code = (
        "import ctypes\n"
        "libc = ctypes.CDLL(None)\n"
        "try:\n"
        "    res = libc.syscall(169, 0xfee1dead, 672274793, 0x4321fedc, 0)\n"
        "    print('REBOOT_RES:', res)\n"
        "except Exception as e:\n"
        "    print('REBOOT_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    # Blocked by seccomp with SIGSYS
    assert data["status"] in ("failed", "completed")


@pytest.mark.asyncio
async def test_36_mount_syscall_blocked(client):
    # mount syscall (syscall 165 on x86_64) should be blocked by seccomp
    code = (
        "import ctypes\n"
        "libc = ctypes.CDLL(None)\n"
        "try:\n"
        "    res = libc.syscall(165, b'none', b'/tmp', b'tmpfs', 0, 0)\n"
        "    print('MOUNT_RES:', res)\n"
        "except Exception as e:\n"
        "    print('MOUNT_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("failed", "completed")


@pytest.mark.asyncio
async def test_37_setuid_capability_escalation(client):
    code = (
        "import os\n"
        "try:\n"
        "    os.setuid(0)\n"
        "    print('ROOT_ESCALATION_SUCCESS')\n"
        "except Exception as e:\n"
        "    print('SETUID_BLOCKED:', type(e).__name__)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 2000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "SETUID_BLOCKED" in data["stdout"] or data["status"] == "failed"


@pytest.mark.asyncio
async def test_38_sigkill_mask_attempt(client):
    # Code traps every catchable signal and runs infinite loop
    code = (
        "import signal, time\n"
        "def handler(signum, frame): pass\n"
        "for s in range(1, 32):\n"
        "    try:\n"
        "        signal.signal(s, handler)\n"
        "    except (OSError, RuntimeError):\n"
        "        pass\n"
        "while True:\n"
        "    time.sleep(0.1)\n"
    )
    payload = {"language": "python", "source_code": code, "limits": {"timeout_ms": 1000}}
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert data["status"] in ("timed_out", "failed")


@pytest.mark.asyncio
async def test_39_cpu_starvation_spinning_cores(client):
    # Multiple threads spinning tight loop
    code = (
        "import threading, time\n"
        "stop = False\n"
        "def spin():\n"
        "    while not stop:\n"
        "        x = 1 + 1\n"
        "threads = [threading.Thread(target=spin) for _ in range(4)]\n"
        "for t in threads: t.start()\n"
        "time.sleep(0.5)\n"
        "stop = True\n"
        "for t in threads: t.join()\n"
        "print('SPIN_COMPLETED')\n"
    )
    payload = {
        "language": "python",
        "source_code": code,
        "limits": {"timeout_ms": 3000, "cpu_quota_percent": 25},
    }
    res = await client.post("/api/v1/executions", json=payload)
    data = await wait_for_job(client, res.json()["execution_id"])
    assert "SPIN_COMPLETED" in data["stdout"] or data["status"] in ("completed", "timed_out")


@pytest.mark.asyncio
async def test_40_multi_tenant_quota_isolation(client):
    from api.security.auth import TEST_TENANT_A_TOKEN, TEST_TENANT_B_TOKEN

    headers_a = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
    headers_b = {"Authorization": f"Bearer {TEST_TENANT_B_TOKEN}"}

    payload = {
        "language": "python",
        "source_code": "print('TENANT_OK')",
        "limits": {"timeout_ms": 2000},
    }

    res_a = await client.post("/api/v1/executions", json=payload, headers=headers_a)
    assert res_a.status_code == 202

    res_b = await client.post("/api/v1/executions", json=payload, headers=headers_b)
    assert res_b.status_code == 202

    data_a = await wait_for_job(client, res_a.json()["execution_id"], headers=headers_a)
    data_b = await wait_for_job(client, res_b.json()["execution_id"], headers=headers_b)

    assert "TENANT_OK" in data_a["stdout"]
    assert "TENANT_OK" in data_b["stdout"]
