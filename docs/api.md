# Runbox REST API Reference

Runbox provides a RESTful HTTP control plane built on FastAPI and SQLite with WAL mode.

- **Base URL:** `http://localhost:8000/api/v1`
- **Default Port:** `8000`
- **OpenAPI Schema:** `http://localhost:8000/docs` (Swagger UI) / `http://localhost:8000/openapi.json`

---

## 1. Endpoints

### 1.1 Submit Code Execution
`POST /api/v1/executions`

Queues a new program execution inside the isolated sandboxing infrastructure.

#### Request Headers
- `Content-Type: application/json`

#### Request Body Schema
```json
{
  "language": "python",
  "source_code": "print('Hello, Runbox!')",
  "stdin": "optional input string delivered via stdin pipe",
  "limits": {
    "timeout_ms": 5000,
    "memory_mb": 128,
    "cpu_quota_percent": 100,
    "process_limit": 32,
    "output_limit_bytes": 1048576
  }
}
```

#### Field Constraints
- `language`: Required. Must be `"python"` (or `"python3"`, `"py"`) or `"cpp"` (or `"c++"`, `"c"`).
- `source_code`: Required string, max length 524,288 bytes (512 KB).
- `limits.timeout_ms`: Integer between `100` and `30000` (default: 3000). Clamped to administrator hard ceilings.
- `limits.memory_mb`: Integer between `16` and `1024` (default: 128).
- `limits.cpu_quota_percent`: Integer between `10` and `100` (default: 50).
- `limits.process_limit`: Integer between `1` and `64` (default: 32).
- `limits.output_limit_bytes`: Integer between `1024` and `5242880` (default: 1,048,576).

#### Response (`202 Accepted`)
```json
{
  "execution_id": "job-a1b2c3d4e5f6",
  "status": "queued",
  "message": "Job accepted and queued for execution"
}
```

#### Error Responses
- `400 Bad Request`: Validation failure (unsupported language, empty source code, invalid limits).
- `503 Service Unavailable`: Execution queue capacity exceeded (backpressure).

---

### 1.2 Get Execution Status & Telemetry
`GET /api/v1/executions/{execution_id}`

Retrieves execution status, output streams, and resource telemetry for a specific execution ID.

#### Response (`200 OK`)
```json
{
  "execution_id": "job-a1b2c3d4e5f6",
  "language": "python",
  "status": "completed",
  "exit_code": 0,
  "termination_reason": "normal_exit",
  "stdout": "Hello, Runbox!\n",
  "stderr": "",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "stdout_bytes": 15,
  "stderr_bytes": 0,
  "compilation_duration_ms": null,
  "resource_usage": {
    "wall_time_ms": 48,
    "cpu_time_ms": 32,
    "memory_peak_bytes": 12582912,
    "pids_peak": 1,
    "oom_killed": false
  },
  "created_at": "2026-11-03T12:00:00Z"
}
```

#### Status Enum Values
- `"queued"`: Waiting in the scheduler queue.
- `"running"`: Active inside an isolated Linux sandbox worker.
- `"completed"`: Finished with exit code 0.
- `"failed"`: Terminated with non-zero exit code or internal error.
- `"timed_out"`: Monotonic clock timeout limit exceeded; killed via SIGKILL.
- `"resource_limit_exceeded"`: OOM killer triggered or task limit breached.
- `"cancelled"`: Aborted by user request.

---

### 1.3 Cancel Running Job
`DELETE /api/v1/executions/{execution_id}`

Cancels a queued or currently executing job.

#### Authorization & Anti-Enumeration Semantics
- **Owner Cancellation:** Returns `200 OK` with cancellation confirmation.
- **Cross-Tenant Cancellation:** Returns `404 Not Found` with payload `{"detail": "Execution '{execution_id}' not found"}` indistinguishable from a non-existent job ID. This eliminates cross-tenant enumeration oracles.
- **Admin Override:** Authenticated administrators (`role: admin`) can cancel jobs across any tenant.

#### Response (`200 OK`)
```json
{
  "execution_id": "job-a1b2c3d4e5f6",
  "status": "cancelled",
  "cancelled": true
}
```

#### Error Response (`404 Not Found`)
```json
{
  "detail": "Execution 'job-a1b2c3d4e5f6' not found"
}
```

---

### 1.4 List Recent Executions
`GET /api/v1/executions?limit=50&offset=0`

Paginated list of execution records.

#### Query Parameters
- `limit`: Integer, `1` to `100` (default: 50).
- `offset`: Integer, `>= 0` (default: 0).

#### Response (`200 OK`)
```json
{
  "total": 142,
  "limit": 50,
  "offset": 0,
  "executions": [ ... ]
}
```

---

### 1.5 System Health
`GET /api/v1/health/live` & `GET /api/v1/health/ready`

#### Response (`200 OK`)
```json
{
  "status": "ready",
  "supervisor_binary": true,
  "cgroup_v2": true,
  "active_workers": 2,
  "queue_depth": 0
}
```

---

### 1.6 Aggregate Metrics
`GET /api/v1/metrics`

Returns aggregate execution metrics across all recorded jobs.

#### Response (`200 OK`)
```json
{
  "executions": {
    "total": 240,
    "completed": 218,
    "failed": 14,
    "timed_out": 8,
    "avg_wall_time_ms": 112.4,
    "avg_cpu_time_ms": 68.2
  },
  "active_jobs": 0,
  "queue_size": 0,
  "max_concurrency": 10
}
```
