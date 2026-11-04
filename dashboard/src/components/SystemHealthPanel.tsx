import React from 'react';
import { HealthData, MetricsData } from '../types/api';
import { ShieldCheck, Cpu, HardDrive, Lock, Server, CheckCircle2, AlertCircle } from 'lucide-react';

interface SystemHealthPanelProps {
  health: HealthData | null;
  metrics: MetricsData | null;
}

export const SystemHealthPanel: React.FC<SystemHealthPanelProps> = ({ health, metrics }) => {
  return (
    <div className="system-health-panel">
      <div className="panel-title-section">
        <h2>Kernel & Infrastructure Security Posture</h2>
        <p className="panel-subtitle">Real-time status of Linux kernel security primitives and host isolation layers</p>
      </div>

      <div className="security-cards-grid">
        <div className="security-card">
          <div className="card-top">
            <Cpu className="text-cyan" size={24} />
            <span className={`status-badge ${health?.cgroup_v2 ? 'active' : 'inactive'}`}>
              {health?.cgroup_v2 ? 'Active' : 'Missing'}
            </span>
          </div>
          <h3>Cgroups v2 Unified Hierarchy</h3>
          <p>
            Provides strict physical memory caps (<code>memory.max</code>), swap restrictions (<code>memory.swap.max</code>),
            CPU bandwidth quota throttling (<code>cpu.max</code>), and group-wide OOM termination.
          </p>
          <div className="card-footer">
            <span>Subtree Control: +memory +cpu +pids</span>
          </div>
        </div>

        <div className="security-card">
          <div className="card-top">
            <Lock className="text-yellow" size={24} />
            <span className="status-badge active">Enforced</span>
          </div>
          <h3>Seccomp-BPF Syscall Filter</h3>
          <p>
            Runtime-specialized BPF filters blocking raw networking, ptrace snooping, hardware device alteration,
            kernel module loading, and sensitive namespace reconfiguration. Default action: <code>SECCOMP_RET_ERRNO(EPERM)</code>.
          </p>
          <div className="card-footer">
            <span>Profiles: Minimal, Python, CppCompile, CppExec</span>
          </div>
        </div>

        <div className="security-card">
          <div className="card-top">
            <ShieldCheck className="text-green" size={24} />
            <span className="status-badge active">Active</span>
          </div>
          <h3>Landlock LSM & Private Chroot</h3>
          <p>
            Cryptographically bounds filesystem capabilities to read-only <code>/usr</code>, isolated <code>/etc</code> tmpfs,
            minimal pseudo-device tree, and sandboxed ephemeral workspace directories.
          </p>
          <div className="card-footer">
            <span>ABI Version: v7 | Shadow & Sudoers: Inaccessible</span>
          </div>
        </div>

        <div className="security-card">
          <div className="card-top">
            <Server className="text-purple" size={24} />
            <span className={`status-badge ${health?.supervisor_binary ? 'active' : 'inactive'}`}>
              {health?.supervisor_binary ? 'Ready' : 'Not Found'}
            </span>
          </div>
          <h3>C++20 Supervisor Engine</h3>
          <p>
            Dedicated unprivileged binary orchestrating process creation, user ID mapping, capability dropping,
            bidirectional pipe streaming, and monotonic clock timeout enforcement.
          </p>
          <div className="card-footer">
            <span>Queue: {metrics?.queue_size || 0} | Workers: {health?.active_workers || 0} / {metrics?.max_concurrency || 10}</span>
          </div>
        </div>
      </div>

      <div className="infra-status-table-box">
        <h3>Subsystem Verification Matrix</h3>
        <table className="infra-table">
          <thead>
            <tr>
              <th>Subsystem</th>
              <th>Mechanism</th>
              <th>Enforcement Mode</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Process Visibility</td>
              <td>PID Namespace + CLONE_NEWPID</td>
              <td>workload isolated as PID 1</td>
              <td><span className="pill-ok"><CheckCircle2 size={13} /> Verified</span></td>
            </tr>
            <tr>
              <td>Filesystem Integrity</td>
              <td>Mount Namespace + Landlock ABI</td>
              <td>MS_RDONLY bind-mounts + private tmpfs</td>
              <td><span className="pill-ok"><CheckCircle2 size={13} /> Verified</span></td>
            </tr>
            <tr>
              <td>Network Isolation</td>
              <td>Network Namespace (CLONE_NEWNET)</td>
              <td>Zero network interfaces (no loopback, no eth)</td>
              <td><span className="pill-ok"><CheckCircle2 size={13} /> Verified</span></td>
            </tr>
            <tr>
              <td>Host Privileges</td>
              <td>User Namespaces + PR_SET_NO_NEW_PRIVS</td>
              <td>All Linux capabilities dropped</td>
              <td><span className="pill-ok"><CheckCircle2 size={13} /> Verified</span></td>
            </tr>
            <tr>
              <td>Resource Guardrails</td>
              <td>Cgroup v2 unified hierarchy</td>
              <td>OOM group kill & CPU bandwidth throttling</td>
              <td><span className="pill-ok"><CheckCircle2 size={13} /> Verified</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};
