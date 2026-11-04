import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { MetricsOverview } from './components/MetricsOverview';
import { SubmissionConsole } from './components/SubmissionConsole';
import { ExecutionExplorer } from './components/ExecutionExplorer';
import { ExecutionDetailModal } from './components/ExecutionDetailModal';
import { SystemHealthPanel } from './components/SystemHealthPanel';
import { ExecutionRecord, MetricsData, HealthData } from './types/api';
import { getMetrics, getHealth, listExecutions } from './services/api';
import './App.css';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'console' | 'explorer' | 'system'>('console');
  const [health, setHealth] = useState<HealthData | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<ExecutionRecord | null>(null);

  const fetchGlobalState = useCallback(async () => {
    try {
      const [h, m, execList] = await Promise.all([
        getHealth().catch(() => null),
        getMetrics().catch(() => null),
        listExecutions(50, 0).catch(() => ({ executions: [] })),
      ]);

      if (h) setHealth(h);
      if (m) setMetrics(m);
      if (execList && execList.executions) setExecutions(execList.executions);
    } catch (err) {
      console.error('Error fetching global Runbox telemetry:', err);
    }
  }, []);

  useEffect(() => {
    fetchGlobalState();
    const interval = setInterval(fetchGlobalState, 3000);
    return () => clearInterval(interval);
  }, [fetchGlobalState]);

  return (
    <div className="app-root">
      <Header health={health} activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="main-content">
        <MetricsOverview metrics={metrics} />

        <div className="tab-viewport">
          {activeTab === 'console' && (
            <SubmissionConsole onExecutionCompleted={fetchGlobalState} />
          )}

          {activeTab === 'explorer' && (
            <ExecutionExplorer
              executions={executions}
              onRefresh={fetchGlobalState}
              onSelectExecution={(item) => setSelectedExecution(item)}
            />
          )}

          {activeTab === 'system' && (
            <SystemHealthPanel health={health} metrics={metrics} />
          )}
        </div>
      </main>

      {selectedExecution && (
        <ExecutionDetailModal
          execution={selectedExecution}
          onClose={() => setSelectedExecution(null)}
        />
      )}
    </div>
  );
};

export default App;
