# Runbox v0.1.1 — Authentication & Multi-Tenant Security Architecture

## 1. Executive Summary

Runbox v0.1.1 introduces an end-to-end, zero-trust authentication, tenant isolation, and abuse prevention layer to the control plane. While v0.1.0 operated with open development endpoints, v0.1.1 enforces cryptographically sound authentication, constant-time token comparison, tenant resource scoping with anti-enumeration protections, sliding-window rate limiting, and per-tenant concurrency quotas.

---

## 2. Authentication Subsystem (`api/security/auth.py`)

### 2.1 Cryptographic Token Model
API tokens are verified against persistent SHA-256 digests. Raw API keys are never stored in plaintext within the persistent database or log files.

- **Token Storage Format**: Tokens are represented as SHA-256 hashes (`hashlib.sha256(token.encode("utf-8")).hexdigest()`).
- **Constant-Time Verification**: All token evaluations use `secrets.compare_digest()` to perform constant-time string comparison, mitigating side-channel timing attacks that could reveal token fragments. As with all web services, overall request latency may vary due to framework, routing, and database overhead, but the secret token digest evaluation itself is constant-time.
- **Dual Transport Mechanisms**:
  1. `Authorization: Bearer <token>`
  2. `X-API-Key: <token>`

### 2.2 Operational Modes
Runbox supports two operational environments controlled by `ENVIRONMENT`:
- `development`: If no tokens are configured, unauthenticated requests are assigned to `usr_dev` to enable local debugging. If tokens are configured, valid credentials map to their respective tenant IDs.
- `production`: Unconditional enforcement. Unauthenticated requests or invalid tokens are rejected with HTTP 401 Unauthorized (`{"detail": "Invalid or missing API key"}`).

### 2.3 System Health Endpoint Exemption
Health probes (`/health/ready`, `/health/live`, `/healthz`, `/readyz`) explicitly bypass the authentication dependency to enable orchestrators (Kubernetes, Nomad, systemd) to perform non-disruptive liveness and readiness polling.

---

## 3. Multi-Tenant Resource Isolation & Anti-Enumeration

### 3.1 Tenant Identity Binding
Upon authenticated entry, the request context is permanently associated with the resolved `tenant_id` (`UserContext`):
- `usr_admin`: Superuser role authorized to monitor, query, and cancel all platform executions across any tenant.
- `usr_tenant_1`, `usr_tenant_2`, ...: Isolated tenant identities bounded strictly to their owned workloads.

### 3.2 Anti-Enumeration Protection (Section 4.3 Requirement)
A key security vulnerability in multi-tenant systems is resource ID enumeration, where an attacker determines whether a job ID exists by observing distinct HTTP status codes (e.g. 403 Forbidden vs. 404 Not Found).

Runbox v0.1.1 implements strict anti-enumeration:
- When a tenant requests status or cancellation of an execution belonging to another tenant, the system returns **HTTP 404 Not Found** (`{"detail": "Execution not found"}`), identical to the response for a non-existent UUID.
- An attacker cannot deduce the existence or timing of other tenants' jobs through ID probing.
- All listing operations (`GET /api/v1/executions`) automatically append `WHERE user_id = :tenant_id` at the database layer (unless invoked by `usr_admin`).

---

## 4. Abuse Prevention & Resource Governance

### 4.1 Sliding-Window Rate Limiter (`api/security/rate_limiter.py`)
To protect the control plane and supervisor dispatch queue from denial-of-service bursts:
- Each tenant is governed by an in-memory sliding-window log (`deque[float]`).
- Default limit: 60 requests per 60-second window (configurable).
- When a tenant exceeds the rate limit, the API immediately halts execution with **HTTP 429 Too Many Requests**, returning a `Retry-After: <seconds>` header indicating the exact backoff period until the oldest request exits the window.

### 4.2 Per-Tenant Concurrency Quotas (`api/security/quotas.py`)
To prevent noisy-neighbor starvation where a single tenant consumes all available worker execution slots:
- Default concurrency quota: 5 concurrent execution slots per tenant.
- Admin quota: unbounded / platform maximum.
- Slot allocation is acquired synchronously before job queue insertion (`quota_manager.acquire_slot(tenant_id)`).
- If the tenant already has 5 active executions (running or queued), the API returns **HTTP 429 Too Many Requests** (`{"detail": "Tenant concurrency quota exceeded"}`).
- Slots are deterministically released via `quota_manager.release_slot(tenant_id)` inside the scheduler worker `finally` block or upon job cancellation.

### 4.3 Payload Bounds Middleware (`api/main.py`)
- Unbounded HTTP POST request bodies can cause memory exhaustion in ASGI servers.
- `RequestBodySizeLimitMiddleware` inspects `Content-Length` headers and streams incoming chunks, rejecting any payload exceeding 1 MB (1,048,576 bytes) with **HTTP 413 Content Too Large** before JSON parsing or SQLite interaction occurs.

---

## 5. Automated Verification
The authentication and tenant isolation subsystems are covered by:
- `tests/unit/test_security_auth.py` (12 tests)
- `tests/unit/test_security_quotas.py` (11 tests)
- `tests/integration/test_auth_api.py` (11 tests)
- `tests/adversarial/test_adversarial_suite.py::test_40_multi_tenant_quota_isolation`
