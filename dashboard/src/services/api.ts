import { ExecutionRecord, ExecutionSubmission, MetricsData, HealthData } from '../types/api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export function getStoredApiKey(): string {
  try {
    return localStorage.getItem('runbox_api_key') || '';
  } catch {
    return '';
  }
}

export function setStoredApiKey(key: string): void {
  try {
    if (key.trim()) {
      localStorage.setItem('runbox_api_key', key.trim());
    } else {
      localStorage.removeItem('runbox_api_key');
    }
  } catch {
    // fallback
  }
}

function getRequestHeaders(extraHeaders: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extraHeaders };
  const key = getStoredApiKey();
  if (key) {
    headers['X-API-Key'] = key;
  }
  return headers;
}

export async function submitExecution(data: ExecutionSubmission): Promise<{ execution_id: string; status: string; message: string }> {
  const res = await fetch(`${API_BASE}/executions`, {
    method: 'POST',
    headers: getRequestHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Execution submission failed');
  }
  return res.json();
}

export async function getExecution(id: string): Promise<ExecutionRecord> {
  const res = await fetch(`${API_BASE}/executions/${id}`, {
    headers: getRequestHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch execution: ${res.statusText}`);
  }
  return res.json();
}

export async function listExecutions(limit = 50, offset = 0): Promise<{ total: number; limit: number; offset: number; executions: ExecutionRecord[] }> {
  const res = await fetch(`${API_BASE}/executions?limit=${limit}&offset=${offset}`, {
    headers: getRequestHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to list executions: ${res.statusText}`);
  }
  return res.json();
}

export async function cancelExecution(id: string): Promise<{ execution_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/executions/${id}/cancel`, {
    method: 'POST',
    headers: getRequestHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to cancel execution: ${res.statusText}`);
  }
  return res.json();
}

export async function getMetrics(): Promise<MetricsData> {
  const res = await fetch(`${API_BASE}/metrics`, {
    headers: getRequestHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch metrics: ${res.statusText}`);
  }
  return res.json();
}

export async function getHealth(): Promise<HealthData> {
  const res = await fetch(`${API_BASE}/health/ready`, {
    headers: getRequestHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch health: ${res.statusText}`);
  }
  return res.json();
}

