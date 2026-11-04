import React, { useState } from 'react';
import { Play, RotateCcw, AlertTriangle, CheckCircle, Clock, Cpu, HardDrive } from 'lucide-react';
import { ExecutionRecord, ExecutionSubmission } from '../types/api';
import { submitExecution, getExecution } from '../services/api';

const SAMPLE_PYTHON = `import sys
import math

print("=== Runbox Sandbox Python Worker ===")
print(f"Python: {sys.version.split()[0]}")
print(f"Euler's e: {math.e:.8f}")

# Perform bounded computation
primes = [x for x in range(2, 50) if all(x % d != 0 for d in range(2, int(x**0.5) + 1))]
print(f"Found {len(primes)} primes: {primes[:10]}...")
`;

const SAMPLE_CPP = `#include <iostream>
#include <vector>
#include <numeric>

int main() {
    std::cout << "=== Runbox C++20 Native Execution ===" << std::endl;
    std::vector<int> nums = {10, 20, 30, 40, 50};
    int sum = std::accumulate(nums.begin(), nums.end(), 0);
    std::cout << "Sum of elements: " << sum << std::endl;
    return 0;
}
`;

interface SubmissionConsoleProps {
  onExecutionCompleted: () => void;
}

export const SubmissionConsole: React.FC<SubmissionConsoleProps> = ({ onExecutionCompleted }) => {
  const [language, setLanguage] = useState<'python' | 'cpp'>('python');
  const [sourceCode, setSourceCode] = useState<string>(SAMPLE_PYTHON);
  const [stdinData, setStdinData] = useState<string>('');
  const [timeoutMs, setTimeoutMs] = useState<number>(5000);
  const [memoryMb, setMemoryMb] = useState<number>(128);
  const [cpuQuota, setCpuQuota] = useState<number>(100);
  const [processLimit, setProcessLimit] = useState<number>(32);

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [currentResult, setCurrentResult] = useState<ExecutionRecord | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleLanguageChange = (newLang: 'python' | 'cpp') => {
    setLanguage(newLang);
    if (newLang === 'python') {
      setSourceCode(SAMPLE_PYTHON);
    } else {
      setSourceCode(SAMPLE_CPP);
    }
  };

  const handleRun = async () => {
    setIsRunning(true);
    setErrorMsg(null);
    setCurrentResult(null);

    const submission: ExecutionSubmission = {
      language,
      source_code: sourceCode,
      stdin: stdinData,
      limits: {
        timeout_ms: timeoutMs,
        memory_mb: memoryMb,
        cpu_quota_percent: cpuQuota,
        process_limit: processLimit,
      },
    };

    try {
      const resp = await submitExecution(submission);
      const execId = resp.execution_id;

      // Poll until finished
      const maxAttempts = 120;
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise((r) => setTimeout(r, 100));
        const rec = await getExecution(execId);
        if (rec.status !== 'queued' && rec.status !== 'running') {
          setCurrentResult(rec);
          onExecutionCompleted();
          break;
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Execution error');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="console-container">
      <div className="editor-panel">
        <div className="editor-toolbar">
          <div className="language-selector">
            <button
              className={`lang-btn ${language === 'python' ? 'active' : ''}`}
              onClick={() => handleLanguageChange('python')}
              disabled={isRunning}
            >
              Python 3.12
            </button>
            <button
              className={`lang-btn ${language === 'cpp' ? 'active' : ''}`}
              onClick={() => handleLanguageChange('cpp')}
              disabled={isRunning}
            >
              C++20 (GCC 13)
            </button>
          </div>

          <div className="toolbar-actions">
            <button
              className="reset-btn"
              onClick={() => handleLanguageChange(language)}
              disabled={isRunning}
              title="Reset Code Template"
            >
              <RotateCcw size={14} />
            </button>
            <button
              className={`run-btn ${isRunning ? 'running' : ''}`}
              onClick={handleRun}
              disabled={isRunning || !sourceCode.trim()}
            >
              <Play size={15} fill="currentColor" />
              <span>{isRunning ? 'Executing...' : 'Run in Sandbox'}</span>
            </button>
          </div>
        </div>

        <div className="code-area-wrapper">
          <textarea
            className="code-textarea"
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            disabled={isRunning}
            spellCheck={false}
            placeholder="Enter source code to execute inside Linux sandbox..."
          />
        </div>

        <div className="limits-bar">
          <div className="limit-input-group">
            <label>Timeout (ms)</label>
            <input
              type="number"
              value={timeoutMs}
              onChange={(e) => setTimeoutMs(Number(e.target.value))}
              min={100}
              max={30000}
              disabled={isRunning}
            />
          </div>
          <div className="limit-input-group">
            <label>Memory (MB)</label>
            <input
              type="number"
              value={memoryMb}
              onChange={(e) => setMemoryMb(Number(e.target.value))}
              min={16}
              max={1024}
              disabled={isRunning}
            />
          </div>
          <div className="limit-input-group">
            <label>CPU Quota (%)</label>
            <input
              type="number"
              value={cpuQuota}
              onChange={(e) => setCpuQuota(Number(e.target.value))}
              min={10}
              max={100}
              disabled={isRunning}
            />
          </div>
          <div className="limit-input-group">
            <label>Max PIDs</label>
            <input
              type="number"
              value={processLimit}
              onChange={(e) => setProcessLimit(Number(e.target.value))}
              min={1}
              max={64}
              disabled={isRunning}
            />
          </div>
        </div>

        <div className="stdin-section">
          <label className="stdin-label">Standard Input (stdin)</label>
          <input
            className="stdin-input"
            type="text"
            placeholder="Optional input lines delivered to execution stdin pipe..."
            value={stdinData}
            onChange={(e) => setStdinData(e.target.value)}
            disabled={isRunning}
          />
        </div>
      </div>

      <div className="output-panel">
        <div className="output-header">
          <span className="output-title">Execution Terminal & Telemetry</span>
          {currentResult && (
            <div className={`status-pill ${currentResult.status}`}>
              {currentResult.status === 'completed' && <CheckCircle size={14} />}
              {currentResult.status !== 'completed' && <AlertTriangle size={14} />}
              <span>{currentResult.status.toUpperCase()}</span>
              {currentResult.exit_code !== undefined && <span>(exit: {currentResult.exit_code})</span>}
            </div>
          )}
        </div>

        {errorMsg && (
          <div className="error-banner">
            <AlertTriangle size={16} />
            <span>{errorMsg}</span>
          </div>
        )}

        {currentResult && (
          <div className="telemetry-bar">
            <div className="telem-item" title="Wall Clock Time">
              <Clock size={14} className="text-cyan" />
              <span>{currentResult.wall_time_ms} ms</span>
            </div>
            <div className="telem-item" title="Kernel CPU Time">
              <Cpu size={14} className="text-yellow" />
              <span>{currentResult.cpu_time_ms} ms CPU</span>
            </div>
            <div className="telem-item" title="Peak Memory (Cgroups v2)">
              <HardDrive size={14} className="text-purple" />
              <span>{((currentResult.memory_peak_bytes || 0) / (1024 * 1024)).toFixed(2)} MB</span>
            </div>
            {currentResult.pids_peak !== undefined && (
              <div className="telem-item" title="Peak Process Count">
                <span>PIDs: {currentResult.pids_peak}</span>
              </div>
            )}
            {currentResult.compilation_duration_ms && (
              <div className="telem-item highlight" title="Compile Stage">
                <span>Compile: {currentResult.compilation_duration_ms} ms</span>
              </div>
            )}
          </div>
        )}

        <div className="terminal-box">
          {isRunning && (
            <div className="terminal-loading">
              <div className="spinner"></div>
              <span>Enforcing namespaces, seccomp & cgroups v2...</span>
            </div>
          )}

          {!isRunning && !currentResult && !errorMsg && (
            <div className="terminal-placeholder">
              Ready for submission. Click "Run in Sandbox" to trigger an isolated execution cycle.
            </div>
          )}

          {currentResult && (
            <>
              {currentResult.stdout && (
                <div className="terminal-stream stdout">
                  <div className="stream-badge">STDOUT ({currentResult.stdout_bytes || 0} bytes)</div>
                  <pre>{currentResult.stdout}</pre>
                </div>
              )}

              {currentResult.stderr && (
                <div className="terminal-stream stderr">
                  <div className="stream-badge">STDERR ({currentResult.stderr_bytes || 0} bytes)</div>
                  <pre>{currentResult.stderr}</pre>
                </div>
              )}

              {!currentResult.stdout && !currentResult.stderr && (
                <div className="terminal-empty-output">Process produced no standard I/O streams.</div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
