import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, CheckCircle2, Database, FileCode, Layers, RefreshCw, Sparkles, X } from 'lucide-react';
import { Tab } from '../App';

import TaskInput from './Intelligence/TaskInput';
import CandidateList from './Intelligence/CandidateList';
import PromptPreview from './Intelligence/PromptPreview';
import ImpactAnalysis from './Intelligence/ImpactAnalysis';
import RuntimeDiagnostics from './Intelligence/RuntimeDiagnostics';

interface RightPanelProps {
  activeTab: Tab | null;
  isProjectLoaded: boolean;
}

const API_BASE = 'http://127.0.0.1:8000';

interface ContextStatus {
  initialized: boolean;
  root: string | null;
  files: number;
  symbols: number;
  artifacts: number;
  frameworks: string[];
}

const getLanguage = (path: string | null) => {
  if (!path) return 'None';
  const ext = path.split('.').pop()?.toLowerCase();
  return ext ? ext.toUpperCase() : 'Text';
};

const RightPanel: React.FC<RightPanelProps> = ({ activeTab, isProjectLoaded }) => {
  const [goal, setGoal] = useState('');
  const [mode, setMode] = useState('feature');
  const [candidates, setCandidates] = useState<any[]>([]);
  const [impactCandidates, setImpactCandidates] = useState<any[]>([]);
  const [runtimeArtifacts, setRuntimeArtifacts] = useState<any[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [impactLoading, setImpactLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedCand, setExpandedCand] = useState<string | null>(null);
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [initializing, setInitializing] = useState(false);
  const [retrievalOpen, setRetrievalOpen] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);

  const runtimeFetchInFlight = useRef(false);

  const contextReady = Boolean(contextStatus?.initialized);
  const activeFramework = contextStatus?.frameworks?.[0] || 'No framework';
  const activeLanguage = getLanguage(activeTab?.path || null);

  const fetchContextStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const res = await fetch(`${API_BASE}/context/status`);
      if (!res.ok) throw new Error(`Context status failed: ${res.status}`);
      setContextStatus(await res.json());
    } catch (err) {
      console.error('Context status failed', err);
      setContextStatus(null);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const fetchRuntime = useCallback(async () => {
    if (runtimeFetchInFlight.current) return;
    runtimeFetchInFlight.current = true;
    try {
      const res = await fetch(`${API_BASE}/context/runtime`);
      if (res.ok) {
        const data = await res.json();
        setRuntimeArtifacts(data.artifacts || []);
      }
    } catch (err) {
      console.error('Runtime fetch failed', err);
    } finally {
      runtimeFetchInFlight.current = false;
    }
  }, []);

  const resetWorkflowState = useCallback(() => {
    setGoal('');
    setMode('feature');
    setCandidates([]);
    setImpactCandidates([]);
    setRuntimeArtifacts([]);
    setSelectedPaths(new Set());
    setExpandedCand(null);
    setPrompt('');
    setRetrievalOpen(false);
    setPromptOpen(false);
    setError(null);
  }, []);

  useEffect(() => {
    if (!isProjectLoaded) {
      resetWorkflowState();
      setContextStatus(null);
      setStatusLoading(false);
      setInitializing(false);
      return;
    }

    setCandidates([]);
    setImpactCandidates([]);
    setSelectedPaths(new Set());
    setExpandedCand(null);
    setPrompt('');
    setRetrievalOpen(false);
    setPromptOpen(false);
    setError(null);
    fetchContextStatus();
    fetchRuntime();
  }, [activeTab?.path, fetchContextStatus, fetchRuntime, isProjectLoaded, resetWorkflowState]);

  const initializeContext = async () => {
    if (!isProjectLoaded) return;

    setInitializing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/context/initialize`, { method: 'POST' });
      if (!res.ok) throw new Error(`Context initialization failed: ${res.status}`);
      await fetchContextStatus();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setInitializing(false);
    }
  };

  const fetchImpact = async (filePath: string) => {
    setImpactLoading(true);
    try {
      const res = await fetch(`${API_BASE}/context/impact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_file: filePath })
      });
      if (res.ok) {
        const data = await res.json();
        setImpactCandidates(data.candidates || []);
      }
    } catch (err) {
      console.error('Impact analysis failed', err);
    } finally {
      setImpactLoading(false);
    }
  };

  const handleClearRuntime = async () => {
    try {
      await fetch(`${API_BASE}/context/runtime/clear`, { method: 'POST' });
      setRuntimeArtifacts([]);
    } catch (err) {
      console.error(err);
    }
  };

  const handleRetrieve = async () => {
    if (!activeTab || !goal.trim()) return;
    if (!contextReady) {
      setError('Initialize the Context Engine before retrieving context.');
      return;
    }

    setLoading(true);
    setError(null);
    setCandidates([]);
    setImpactCandidates([]);
    setSelectedPaths(new Set());
    setExpandedCand(null);
    setPrompt('');
    setPromptOpen(false);

    try {
      await fetchRuntime();
      const res = await fetch(`${API_BASE}/context/retrieve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: activeTab.path, goal })
      });
      if (!res.ok) throw new Error(`Retrieval failed: ${res.status}`);

      const data = await res.json();
      const nextCandidates = data.candidates || [];
      const autoSelected = new Set<string>();
      nextCandidates.forEach((candidate: any) => {
        if (candidate.score >= 40) autoSelected.add(candidate.file_metadata.rel_path);
      });

      setCandidates(nextCandidates);
      setSelectedPaths(autoSelected);
      setRetrievalOpen(true);
      fetchImpact(activeTab.path);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAssemble = async () => {
    if (!activeTab) return;
    if (!contextReady) {
      setError('Initialize the Context Engine before assembling a prompt.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/context/assemble`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: goal,
          active_file: activeTab.path,
          selected_files: Array.from(selectedPaths),
          mode
        })
      });
      if (!res.ok) throw new Error(`Assembly failed: ${res.status}`);
      const data = await res.json();
      setPrompt(data.prompt);
      setRetrievalOpen(false);
      setPromptOpen(true);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelection = (path: string) => {
    const next = new Set(selectedPaths);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setSelectedPaths(next);
  };

  const handleCopyPrompt = () => {
    if (prompt) navigator.clipboard.writeText(prompt);
  };

  const stats = useMemo(() => [
    { label: 'Files', value: contextStatus?.files || 0 },
    { label: 'Symbols', value: contextStatus?.symbols || 0 },
    { label: 'Frameworks', value: contextStatus?.frameworks?.length || 0 }
  ], [contextStatus]);

  return (
    <div className="right-panel-root">
      <div className="right-panel-content compact-workflow">
        <div className="panel-section">
          <div className="panel-title accent">
            <Database size={13} />
            <span>Project Intelligence</span>
          </div>

          <div className="panel-card context-status-card">
            <div className="context-status-row">
              <span className={`context-status-dot ${contextReady ? 'ready' : ''}`} />
              <span>
                {statusLoading
                  ? 'Checking context engine...'
                  : !isProjectLoaded
                    ? 'Pick a project root first'
                    : contextReady
                    ? 'Context Engine initialized'
                    : 'Context Engine not initialized'}
              </span>
            </div>

            {!isProjectLoaded ? (
              <div className="context-status-meta">
                Open a project folder from Explorer before initializing project intelligence.
              </div>
            ) : contextReady ? (
              <>
                <div className="context-stat-grid">
                  {stats.map((stat) => (
                    <div className="context-stat" key={stat.label}>
                      <span>{stat.value}</span>
                      <small>{stat.label}</small>
                    </div>
                  ))}
                </div>
                <div className="context-status-meta">
                  {contextStatus?.frameworks.length
                    ? contextStatus.frameworks.join(' / ')
                    : 'No framework markers detected'}
                </div>
              </>
            ) : (
              <div className="context-status-meta">
                Build the in-memory file, symbol, dependency, and framework index for this project.
              </div>
            )}

            <button
              className="btn btn-primary w-full flex items-center justify-center gap-2"
              onClick={initializeContext}
              disabled={!isProjectLoaded || initializing}
            >
              <RefreshCw size={13} />
              {!isProjectLoaded
                ? 'Pick Project Root First'
                : initializing
                  ? 'Initializing...'
                  : contextReady
                    ? 'Refresh Index'
                    : 'Initialize Context Engine'}
            </button>
          </div>
        </div>

        {contextReady && (
          <div className="panel-section">
            <div className="panel-title">
              <FileCode size={13} />
              <span>Active Context</span>
            </div>
            <div className="panel-card active-context-card">
              <div className="panel-file-row">
                <FileCode size={14} className="text-blue-400" />
                <span className="panel-file">
                  {activeTab ? activeTab.path.split('/').pop() : 'No active file'}
                </span>
              </div>
              <div className="active-context-meta">
                <span>{activeLanguage}</span>
                <span>{activeFramework}</span>
                <span>{runtimeArtifacts.length ? `${runtimeArtifacts.length} runtime item(s)` : 'No runtime data'}</span>
              </div>
              {activeTab && <div className="panel-path opacity-40">{activeTab.path}</div>}
            </div>
          </div>
        )}

        {contextReady && (
          <TaskInput
            goal={goal}
            setGoal={setGoal}
            mode={mode}
            setMode={setMode}
            loading={loading}
            disabled={!activeTab}
            onRetrieve={handleRetrieve}
            onClear={() => {
              setGoal('');
              setMode('feature');
              setCandidates([]);
              setImpactCandidates([]);
              setSelectedPaths(new Set());
              setExpandedCand(null);
              setPrompt('');
              setRetrievalOpen(false);
              setPromptOpen(false);
              setError(null);
            }}
          />
        )}

        {error && <div className="px-4 text-[10px] text-red-400">Error: {error}</div>}
      </div>

      <div className="panel-footer">
        NEXUS CONTEXT ENGINE v0.2.0
      </div>

      {retrievalOpen && (
        <div className="intel-modal-backdrop">
          <div className="intel-modal">
            <div className="intel-modal-header">
              <div>
                <div className="panel-title accent">
                  <Layers size={13} />
                  <span>Retrieved Context</span>
                </div>
                <div className="intel-modal-subtitle">
                  Ranked context for {activeTab?.path.split('/').pop()}
                </div>
              </div>
              <button className="intel-modal-close" onClick={() => setRetrievalOpen(false)} type="button">
                <X size={14} />
              </button>
            </div>

            <div className="intel-modal-body">
              <CandidateList
                candidates={candidates}
                selectedPaths={selectedPaths}
                toggleSelection={toggleSelection}
                expandedCand={expandedCand}
                setExpandedCand={setExpandedCand}
                onAssemble={handleAssemble}
                loading={loading}
              />

              <details className="intel-disclosure">
                <summary>
                  <Activity size={13} />
                  Runtime Diagnostics
                  <span>{runtimeArtifacts.length}</span>
                </summary>
                <RuntimeDiagnostics artifacts={runtimeArtifacts} onClear={handleClearRuntime} />
              </details>

              <details className="intel-disclosure">
                <summary>
                  <Sparkles size={13} />
                  Impact Analysis
                  <span>{impactLoading ? '...' : impactCandidates.length}</span>
                </summary>
                <ImpactAnalysis impactCandidates={impactCandidates} loading={impactLoading} />
              </details>
            </div>
          </div>
        </div>
      )}

      {promptOpen && (
        <div className="intel-modal-backdrop">
          <div className="intel-modal prompt-modal">
            <div className="intel-modal-header">
              <div>
                <div className="panel-title accent">
                  <CheckCircle2 size={13} />
                  <span>Prompt Preview</span>
                </div>
                <div className="intel-modal-subtitle">Structured engineering briefing</div>
              </div>
              <button className="intel-modal-close" onClick={() => setPromptOpen(false)} type="button">
                <X size={14} />
              </button>
            </div>
            <div className="intel-modal-body">
              <PromptPreview
                prompt={prompt}
                onCopy={handleCopyPrompt}
                onBack={() => {
                  setPromptOpen(false);
                  setRetrievalOpen(true);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RightPanel;
