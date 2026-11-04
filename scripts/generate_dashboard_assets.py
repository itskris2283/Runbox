#!/usr/bin/env python3
import os

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "assets"))
os.makedirs(ASSETS_DIR, exist_ok=True)


def create_main_dashboard_svg():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 700" width="100%" height="100%">
  <rect width="1200" height="700" fill="#0d1117"/>
  <!-- Header Bar -->
  <rect width="1200" height="60" fill="#161b22" stroke="#30363d" stroke-width="1"/>
  <circle cx="35" cy="30" r="14" fill="#238636"/>
  <text x="35" y="35" text-anchor="middle" fill="#fff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14" font-weight="bold">R</text>
  <text x="60" y="36" fill="#58a6ff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="18" font-weight="bold">Runbox</text>
  <text x="135" y="36" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13">Secure Sandbox Infrastructure v0.1.1</text>

  <!-- Header Buttons -->
  <rect x="940" y="15" width="120" height="30" rx="6" fill="#21262d" stroke="#30363d"/>
  <text x="1000" y="35" text-anchor="middle" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">API Key: Active</text>
  <rect x="1075" y="15" width="100" height="30" rx="6" fill="#238636"/>
  <text x="1125" y="35" text-anchor="middle" fill="#fff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12" font-weight="bold">+ New Job</text>

  <!-- KPI Metrics Row -->
  <g transform="translate(40, 85)">
    <!-- Metric 1 -->
    <rect width="260" height="90" rx="8" fill="#161b22" stroke="#30363d"/>
    <text x="20" y="30" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">PYTHON LATENCY (P50)</text>
    <text x="20" y="65" fill="#2ea043" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="28" font-weight="bold">118.07 ms</text>
    <text x="170" y="65" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">P95: 159.3ms</text>

    <!-- Metric 2 -->
    <rect x="285" width="260" height="90" rx="8" fill="#161b22" stroke="#30363d"/>
    <text x="305" y="30" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">C++ E2E LATENCY (P50)</text>
    <text x="305" y="65" fill="#58a6ff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="28" font-weight="bold">916.38 ms</text>
    <text x="460" y="65" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">Target &lt; 1s</text>

    <!-- Metric 3 -->
    <rect x="570" width="260" height="90" rx="8" fill="#161b22" stroke="#30363d"/>
    <text x="590" y="30" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">TIMEOUT JITTER (P95)</text>
    <text x="590" y="65" fill="#a371f7" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="28" font-weight="bold">39.0 ms</text>
    <text x="735" y="65" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">Max: 79ms</text>

    <!-- Metric 4 -->
    <rect x="855" width="265" height="90" rx="8" fill="#161b22" stroke="#30363d"/>
    <text x="875" y="30" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">CONCURRENT THROUGHPUT</text>
    <text x="875" y="65" fill="#2ea043" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="28" font-weight="bold">90.65 jobs/s</text>
    <text x="1035" y="65" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">Peak: 94.4/s</text>
  </g>

  <!-- Left: Submission Console Preview -->
  <g transform="translate(40, 200)">
    <rect width="545" height="465" rx="8" fill="#161b22" stroke="#30363d"/>
    <text x="20" y="35" fill="#e6edf3" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="16" font-weight="bold">Sandbox Execution Console</text>

    <!-- Language Tabs -->
    <rect x="20" y="55" width="90" height="28" rx="4" fill="#238636"/>
    <text x="65" y="74" text-anchor="middle" fill="#fff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12" font-weight="bold">Python 3.12</text>
    <rect x="120" y="55" width="80" height="28" rx="4" fill="#21262d" stroke="#30363d"/>
    <text x="160" y="74" text-anchor="middle" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">C++20</text>

    <!-- Code Editor Box -->
    <rect x="20" y="95" width="505" height="220" rx="6" fill="#0d1117" stroke="#30363d"/>
    <text x="35" y="125" fill="#ff7b72" font-family="Consolas,monospace" font-size="13">import</text>
    <text x="85" y="125" fill="#e6edf3" font-family="Consolas,monospace" font-size="13">os, sys, platform</text>
    <text x="35" y="150" fill="#d2a8ff" font-family="Consolas,monospace" font-size="13">print</text>
    <text x="75" y="150" fill="#a5d6ff" font-family="Consolas,monospace" font-size="13">(f"Python Version: {platform.python_version()}")</text>
    <text x="35" y="175" fill="#d2a8ff" font-family="Consolas,monospace" font-size="13">print</text>
    <text x="75" y="175" fill="#a5d6ff" font-family="Consolas,monospace" font-size="13">(f"Sandbox UID: {os.getuid()} | GID: {os.getgid()}")</text>
    <text x="35" y="200" fill="#8b949e" font-family="Consolas,monospace" font-size="13"># Workload isolated inside PID, NET, Mount &amp; Landlock namespaces</text>

    <!-- Submit Button -->
    <rect x="20" y="415" width="130" height="35" rx="6" fill="#238636"/>
    <text x="85" y="437" text-anchor="middle" fill="#fff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="13" font-weight="bold">Execute Code</text>
  </g>

  <!-- Right: Execution Explorer Table -->
  <g transform="translate(615, 200)">
    <rect width="545" height="465" rx="8" fill="#161b22" stroke="#30363d"/>
    <text x="20" y="35" fill="#e6edf3" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="16" font-weight="bold">Execution Explorer</text>

    <!-- Table Header -->
    <rect x="20" y="55" width="505" height="32" fill="#21262d" rx="4"/>
    <text x="30" y="76" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">EXECUTION ID</text>
    <text x="180" y="76" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">LANG</text>
    <text x="240" y="76" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">STATUS</text>
    <text x="330" y="76" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">DURATION</text>
    <text x="430" y="76" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">MEMORY</text>

    <!-- Row 1 -->
    <text x="30" y="115" fill="#58a6ff" font-family="Consolas,monospace" font-size="12">b78b0fae-6e84...</text>
    <text x="180" y="115" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">python</text>
    <rect x="240" y="102" width="70" height="20" rx="10" fill="#238636" opacity="0.2"/>
    <text x="275" y="116" text-anchor="middle" fill="#3fb950" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">COMPLETED</text>
    <text x="330" y="115" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">71.4 ms</text>
    <text x="430" y="115" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">12.2 MB</text>

    <!-- Row 2 -->
    <text x="30" y="155" fill="#58a6ff" font-family="Consolas,monospace" font-size="12">c91d2a10-4f11...</text>
    <text x="180" y="155" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">cpp</text>
    <rect x="240" y="142" width="70" height="20" rx="10" fill="#238636" opacity="0.2"/>
    <text x="275" y="156" text-anchor="middle" fill="#3fb950" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">COMPLETED</text>
    <text x="330" y="155" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">562.9 ms</text>
    <text x="430" y="155" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">34.8 MB</text>

    <!-- Row 3 -->
    <text x="30" y="195" fill="#58a6ff" font-family="Consolas,monospace" font-size="12">e44a9801-12cd...</text>
    <text x="180" y="195" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">python</text>
    <rect x="240" y="182" width="70" height="20" rx="10" fill="#a371f7" opacity="0.2"/>
    <text x="275" y="196" text-anchor="middle" fill="#d2a8ff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11" font-weight="bold">TIMED OUT</text>
    <text x="330" y="195" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">502.5 ms</text>
    <text x="430" y="195" fill="#c9d1d9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">8.4 MB</text>
  </g>
</svg>"""
    with open(os.path.join(ASSETS_DIR, "main_dashboard.svg"), "w", encoding="utf-8") as f:
        f.write(svg)


def create_system_health_svg():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" width="100%" height="100%">
  <rect width="800" height="450" fill="#0d1117" rx="8"/>
  <rect width="800" height="50" fill="#161b22" stroke="#30363d" stroke-width="1" rx="8"/>
  <text x="30" y="32" fill="#58a6ff" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="16" font-weight="bold">Runbox System Health &amp; Kernel Diagnostics</text>

  <!-- Status Cards -->
  <g transform="translate(30, 70)">
    <!-- Card 1: Supervisor Binary -->
    <rect width="360" height="80" rx="6" fill="#161b22" stroke="#30363d"/>
    <circle cx="30" cy="40" r="12" fill="#238636"/>
    <text x="30" y="45" text-anchor="middle" fill="#fff" font-size="14">✓</text>
    <text x="55" y="35" fill="#e6edf3" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14" font-weight="bold">C++ Supervisor Binary</text>
    <text x="55" y="55" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">build-release/runbox-supervisor (ELF 64-bit)</text>

    <!-- Card 2: Cgroups v2 -->
    <rect x="380" width="360" height="80" rx="6" fill="#161b22" stroke="#30363d"/>
    <circle cx="410" cy="40" r="12" fill="#238636"/>
    <text x="410" y="45" text-anchor="middle" fill="#fff" font-size="14">✓</text>
    <text x="435" y="35" fill="#e6edf3" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14" font-weight="bold">Unified Cgroups v2</text>
    <text x="435" y="55" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">/sys/fs/cgroup/runbox (+memory +cpu +pids)</text>

    <!-- Card 3: Linux Namespaces -->
    <rect y="95" width="360" height="80" rx="6" fill="#161b22" stroke="#30363d"/>
    <circle cx="30" cy="135" r="12" fill="#238636"/>
    <text x="30" y="140" text-anchor="middle" fill="#fff" font-size="14">✓</text>
    <text x="55" y="130" fill="#e6edf3" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14" font-weight="bold">Linux Namespaces (6/6)</text>
    <text x="55" y="150" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">PID 1 Mapping, NET, NS, IPC, UTS, CGROUP</text>

    <!-- Card 4: Landlock & Seccomp -->
    <rect x="380" y="95" width="360" height="80" rx="6" fill="#161b22" stroke="#30363d"/>
    <circle cx="410" cy="135" r="12" fill="#238636"/>
    <text x="410" y="140" text-anchor="middle" fill="#fff" font-size="14">✓</text>
    <text x="435" y="130" fill="#e6edf3" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14" font-weight="bold">Kernel LSM &amp; Seccomp</text>
    <text x="435" y="150" fill="#8b949e" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="12">Landlock ABI v3 Active | Seccomp BPF Kill Action</text>

    <!-- Worker Pool Telemetry -->
    <rect y="190" width="740" height="150" rx="6" fill="#161b22" stroke="#30363d"/>
    <text x="25" y="225" fill="#e6edf3" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="14" font-weight="bold">Scheduler Worker Pool &amp; Queue Status</text>

    <text x="25" y="260" fill="#8b949e" font-size="12">Active Concurrency Slots: 25</text>
    <text x="250" y="260" fill="#8b949e" font-size="12">Worker Depth: 0 Active / 25 Idle</text>
    <text x="480" y="260" fill="#8b949e" font-size="12">Queue Depth: 0 Pending</text>

    <text x="25" y="295" fill="#8b949e" font-size="12">Database Persistence: SQLite 3.45 (WAL Mode)</text>
    <text x="480" y="295" fill="#8b949e" font-size="12">Synchronous Pragma: NORMAL</text>
    <text x="25" y="325" fill="#2ea043" font-size="13" font-weight="bold">All 6 Concentric Kernel Isolation Layers Operating Nominally</text>
  </g>
</svg>"""
    with open(os.path.join(ASSETS_DIR, "system_health.svg"), "w", encoding="utf-8") as f:
        f.write(svg)


if __name__ == "__main__":
    create_main_dashboard_svg()
    create_system_health_svg()
    print("Dashboard documentation visual assets created in docs/assets/")
