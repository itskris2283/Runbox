import React from 'react';
import { MetricsData } from '../types/api';
import { CheckCircle2, XCircle, Clock, Zap, Cpu, Server } from 'lucide-react';

interface MetricsOverviewProps {
  metrics: MetricsData | null;
}

export const MetricsOverview: React.FC<MetricsOverviewProps> = ({ metrics }) => {
  if (!metrics) {
    return (
      <div className="metrics-grid">
        <div className="metric-card skeleton"></div>
        <div className="metric-card skeleton"></div>
        <div className="metric-card skeleton"></div>
        <div className="metric-card skeleton"></div>
      </div>
    );
  }

  const { executions, active_jobs, queue_size, max_concurrency } = metrics;
  const successRate = executions.total > 0
    ? ((executions.completed / executions.total) * 100).toFixed(1)
    : '100.0';

  return (
    <div className="metrics-grid">
      <div className="metric-card">
        <div className="metric-header">
          <span className="metric-title">Total Submissions</span>
          <Zap size={18} className="metric-icon text-cyan" />
        </div>
        <div className="metric-value">{executions.total}</div>
        <div className="metric-sub">
          <span>{executions.completed} ok</span>
          <span className="sep">•</span>
          <span>{executions.failed} err</span>
          <span className="sep">•</span>
          <span>{executions.timed_out} timeout</span>
        </div>
      </div>

      <div className="metric-card">
        <div className="metric-header">
          <span className="metric-title">Success Rate</span>
          <CheckCircle2 size={18} className="metric-icon text-green" />
        </div>
        <div className="metric-value">{successRate}%</div>
        <div className="metric-sub">
          <span>{executions.completed} / {executions.total} executions</span>
        </div>
      </div>

      <div className="metric-card">
        <div className="metric-header">
          <span className="metric-title">Mean Latency</span>
          <Clock size={18} className="metric-icon text-yellow" />
        </div>
        <div className="metric-value">{Math.round(executions.avg_wall_time_ms)} ms</div>
        <div className="metric-sub">
          <span>CPU time: {Math.round(executions.avg_cpu_time_ms)} ms</span>
        </div>
      </div>

      <div className="metric-card">
        <div className="metric-header">
          <span className="metric-title">Concurrency & Queue</span>
          <Server size={18} className="metric-icon text-purple" />
        </div>
        <div className="metric-value">{active_jobs} / {max_concurrency}</div>
        <div className="metric-sub">
          <span>Queue depth: {queue_size} pending</span>
        </div>
      </div>
    </div>
  );
};
