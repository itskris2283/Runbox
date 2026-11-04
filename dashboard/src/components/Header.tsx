import React, { useState } from 'react';
import { ShieldCheck, Activity, Terminal, Layers, KeyRound } from 'lucide-react';
import { HealthData } from '../types/api';
import { getStoredApiKey, setStoredApiKey } from '../services/api';

interface HeaderProps {
  health: HealthData | null;
  activeTab: 'console' | 'explorer' | 'system';
  setActiveTab: (tab: 'console' | 'explorer' | 'system') => void;
}

export const Header: React.FC<HeaderProps> = ({ health, activeTab, setActiveTab }) => {
  const isReady = health?.status === 'ready';
  const [apiKey, setApiKey] = useState<string>(getStoredApiKey());
  const [showKeyInput, setShowKeyInput] = useState<boolean>(false);

  const handleSaveKey = (val: string) => {
    setApiKey(val);
    setStoredApiKey(val);
    setShowKeyInput(false);
  };

  return (
    <header className="header">
      <div className="header-left">
        <div className="logo-box">
          <ShieldCheck className="logo-icon" size={24} />
          <span className="logo-title">RUNBOX</span>
          <span className="version-pill">v0.1.1</span>
        </div>
        <div className="status-badge-container">
          <span className={`status-dot ${isReady ? 'ready' : 'degraded'}`}></span>
          <span className="status-label">{isReady ? 'Engine Active' : 'System Degraded'}</span>
          <span className="status-sub">cgroups v2 + seccomp + landlock</span>
        </div>
      </div>

      <nav className="header-nav">
        <button
          className={`nav-btn ${activeTab === 'console' ? 'active' : ''}`}
          onClick={() => setActiveTab('console')}
        >
          <Terminal size={16} />
          <span>Execution Console</span>
        </button>
        <button
          className={`nav-btn ${activeTab === 'explorer' ? 'active' : ''}`}
          onClick={() => setActiveTab('explorer')}
        >
          <Layers size={16} />
          <span>Executions Explorer</span>
        </button>
        <button
          className={`nav-btn ${activeTab === 'system' ? 'active' : ''}`}
          onClick={() => setActiveTab('system')}
        >
          <Activity size={16} />
          <span>Cluster Telemetry</span>
        </button>
        <button
          className={`nav-btn ${apiKey ? 'active' : ''}`}
          onClick={() => setShowKeyInput(!showKeyInput)}
          title="Configure API Token / Key"
        >
          <KeyRound size={16} />
          <span>{apiKey ? 'API Key Set' : 'Set API Key'}</span>
        </button>
      </nav>

      {showKeyInput && (
        <div style={{
          position: 'absolute',
          top: '60px',
          right: '24px',
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '8px',
          padding: '12px 16px',
          boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
          zIndex: 100,
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          width: '320px'
        }}>
          <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 600 }}>API Authentication Token</label>
          <input
            type="password"
            placeholder="e.g. sec_token_prod_user..."
            defaultValue={apiKey}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSaveKey((e.target as HTMLInputElement).value);
              }
            }}
            id="runbox-api-key-input"
            style={{
              padding: '8px 12px',
              background: '#0f172a',
              border: '1px solid #475569',
              borderRadius: '6px',
              color: '#f8fafc',
              fontSize: '13px'
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '4px' }}>
            <button
              onClick={() => handleSaveKey('')}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#ef4444',
                fontSize: '12px',
                cursor: 'pointer'
              }}
            >
              Clear
            </button>
            <button
              onClick={() => {
                const input = document.getElementById('runbox-api-key-input') as HTMLInputElement;
                if (input) handleSaveKey(input.value);
              }}
              style={{
                background: '#3b82f6',
                border: 'none',
                borderRadius: '4px',
                padding: '4px 12px',
                color: '#fff',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Save
            </button>
          </div>
        </div>
      )}
    </header>
  );
};

