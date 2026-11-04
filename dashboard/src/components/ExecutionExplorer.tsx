import React, { useState } from 'react';
import { ExecutionRecord } from '../types/api';
import { RefreshCw, Search, Eye, XOctagon } from 'lucide-react';
import { cancelExecution } from '../services/api';

interface ExecutionExplorerProps {
  executions: ExecutionRecord[];
  onRefresh: () => void;
  onSelectExecution: (execution: ExecutionRecord) => void;
}

export const ExecutionExplorer: React.FC<ExecutionExplorerProps> = ({
  executions,
  onRefresh,
  onSelectExecution,
}) => {
  const [filterLang, setFilterLang] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const filtered = executions.filter((item) => {
    if (filterLang !== 'all' && item.language !== filterLang) return false;
    if (filterStatus !== 'all' && item.status !== filterStatus) return false;
    if (searchQuery.trim() && !item.execution_id.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    return true;
  });

  const handleCancel = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setCancellingId(id);
    try {
      await cancelExecution(id);
      onRefresh();
    } catch (err) {
      console.error(err);
    } finally {
      setCancellingId(null);
    }
  };

  return (
    <div className="explorer-container">
      <div className="explorer-toolbar">
        <div className="search-box">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            placeholder="Filter by Execution ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-controls">
          <select value={filterLang} onChange={(e) => setFilterLang(e.target.value)}>
            <option value="all">All Languages</option>
            <option value="python">Python</option>
            <option value="cpp">C++</option>
          </select>

          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="all">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="timed_out">Timed Out</option>
            <option value="running">Running</option>
            <option value="queued">Queued</option>
          </select>

          <button className="refresh-btn" onClick={onRefresh} title="Refresh Table">
            <RefreshCw size={15} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <div className="table-responsive">
        <table className="executions-table">
          <thead>
            <tr>
              <th>Execution ID</th>
              <th>Language</th>
              <th>Status</th>
              <th>Exit Code</th>
              <th>Termination Reason</th>
              <th>Wall Time</th>
              <th>Peak RAM</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="empty-row">
                  No execution records matched current filter criteria.
                </td>
              </tr>
            ) : (
              filtered.map((item) => (
                <tr
                  key={item.execution_id}
                  className="table-row"
                  onClick={() => onSelectExecution(item)}
                >
                  <td className="font-mono text-cyan">{item.execution_id.slice(0, 16)}...</td>
                  <td>
                    <span className="lang-tag">{item.language.toUpperCase()}</span>
                  </td>
                  <td>
                    <span className={`status-pill small ${item.status}`}>{item.status}</span>
                  </td>
                  <td className="font-mono">{item.exit_code !== null && item.exit_code !== undefined ? item.exit_code : '-'}</td>
                  <td>
                    <span className="reason-text">{item.termination_reason || '-'}</span>
                  </td>
                  <td>{item.wall_time_ms ? `${item.wall_time_ms} ms` : '-'}</td>
                  <td>
                    {item.memory_peak_bytes
                      ? `${(item.memory_peak_bytes / (1024 * 1024)).toFixed(1)} MB`
                      : '-'}
                  </td>
                  <td className="text-muted">
                    {new Date(item.created_at).toLocaleTimeString()}
                  </td>
                  <td>
                    <div className="action-buttons">
                      <button
                        className="btn-icon"
                        title="View Details"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectExecution(item);
                        }}
                      >
                        <Eye size={15} />
                      </button>
                      {(item.status === 'queued' || item.status === 'running') && (
                        <button
                          className="btn-icon cancel"
                          title="Cancel Job"
                          disabled={cancellingId === item.execution_id}
                          onClick={(e) => handleCancel(e, item.execution_id)}
                        >
                          <XOctagon size={15} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
