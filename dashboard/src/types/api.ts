export interface ResourceUsage {
  wall_time_ms: number;
  cpu_time_ms: number;
  memory_peak_bytes: number;
  pids_peak: number;
  oom_killed: boolean;
}

export interface ExecutionRecord {
  execution_id: string;
  language: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'timed_out' | 'cancelled';
  exit_code?: number | null;
  termination_reason?: string | null;
  stdout?: string;
  stderr?: string;
  stdout_truncated?: boolean;
  stderr_truncated?: boolean;
  stdout_bytes?: number;
  stderr_bytes?: number;
  wall_time_ms?: number;
  cpu_time_ms?: number;
  memory_peak_bytes?: number;
  pids_peak?: number;
  compilation_duration_ms?: number | null;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ExecutionLimits {
  timeout_ms?: number;
  memory_mb?: number;
  cpu_quota_percent?: number;
  process_limit?: number;
  output_limit_bytes?: number;
}

export interface ExecutionSubmission {
  language: string;
  source_code: string;
  stdin?: string;
  limits?: ExecutionLimits;
}

export interface MetricsData {
  executions: {
    total: number;
    completed: number;
    failed: number;
    timed_out: number;
    avg_wall_time_ms: number;
    avg_cpu_time_ms: number;
  };
  active_jobs: number;
  queue_size: number;
  max_concurrency: number;
}

export interface HealthData {
  status: string;
  supervisor_binary: boolean;
  cgroup_v2: boolean;
  active_workers: number;
  queue_depth: number;
}
