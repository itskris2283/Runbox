import React from 'react';
import { ExecutionRecord } from '../types/api';
import { X, Clock, Cpu, HardDrive, CheckCircle, AlertTriangle, Copy } from 'lucide-react';

interface ExecutionDetailModalProps {
  execution: ExecutionRecord | null;
  onClose: () => void;
}

export const ExecutionDetailModal: React.FC<ExecutionDetailModalProps> = ({ execution, onClose }) => {
  if (!execution) return null;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <h3>Execution Telemetry Inspection</h3>
            <span className="font-mono text-cyan text-sm">{execution.execution_id}</span>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="detail-status-grid">
            <div className="detail-card">
              <span className="label">Status</span>
              <span className={`status-pill ${execution.status}`}>
                {execution.status.toUpperCase()}
              </span>
            </div>
            <div className="detail-card">
              <span className="label">Exit Code</span>
              <span className="val font-mono">{execution.exit_code !== null ? execution.exit_code : 'N/A'}</span>
            </div>
            <div className="detail-card">
              <span className="label">Termination Reason</span>
              <span className="val">{execution.termination_reason || 'normal_exit'}</span>
            </div>
            <div className="detail-card">
              <span className="label">Language Runtime</span>
              <span className="val uppercase">{execution.language}</span>
            </div>
          </div>

          <div className="telemetry-stat-row">
            <div className="stat-box">
              <Clock size={16} className="text-cyan" />
              <div>
                <div className="stat-label">Wall Clock Duration</div>
                <div className="stat-val">{execution.wall_time_ms || 0} ms</div>
              </div>
            </div>
            <div className="stat-box">
              <Cpu size={16} className="text-yellow" />
              <div>
                <div className="stat-label">Kernel CPU Time</div>
                <div className="stat-val">{execution.cpu_time_ms || 0} ms</div>
              </div>
            </div>
            <div className="stat-box">
              <HardDrive size={16} className="text-purple" />
              <div>
                <div className="stat-label">Peak RAM (cgroup v2)</div>
                <div className="stat-val">
                  {execution.memory_peak_bytes
                    ? `${(execution.memory_peak_bytes / (1024 * 1024)).toFixed(2)} MB`
                    : '0 MB'}
                </div>
              </div>
            </div>
            <div className="stat-box">
              <CheckCircle size={16} className="text-green" />
              <div>
                <div className="stat-label">Peak Process Count</div>
                <div className="stat-val">{execution.pids_peak || 1}</div>
              </div>
            </div>
          </div>

          {execution.compilation_duration_ms && (
            <div className="compilation-banner">
              <span>Isolated C++ Compilation Stage Duration:</span>
              <strong>{execution.compilation_duration_ms} ms</strong>
            </div>
          )}

          {execution.error_message && (
            <div className="error-banner">
              <AlertTriangle size={16} />
              <span>{execution.error_message}</span>
            </div>
          )}

          <div className="stream-container">
            <div className="stream-header">
              <span>STDOUT STREAM ({execution.stdout_bytes || 0} bytes)</span>
              {execution.stdout && (
                <button
                  className="copy-btn"
                  onClick={() => copyToClipboard(execution.stdout || '')}
                  title="Copy Stdout"
                >
                  <Copy size={13} />
                  <span>Copy</span>
                </button>
              )}
            </div>
            <pre className="stream-box stdout">
              {execution.stdout || '<empty>'}
            </pre>
          </div>

          <div className="stream-container">
            <div className="stream-header">
              <span>STDERR STREAM ({execution.stderr_bytes || 0} bytes)</span>
              {execution.stderr && (
                <button
                  className="copy-btn"
                  onClick={() => copyToClipboard(execution.stderr || '')}
                  title="Copy Stderr"
                >
                  <Copy size={13} />
                  <span>Copy</span>
                </button>
              )}
            </div>
            <pre className="stream-box stderr">
              {execution.stderr || '<empty>'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
