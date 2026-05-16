import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, CheckCircle2, Database, FileCode, Layers, RefreshCw, Settings, Sparkles, Terminal, X, Zap } from 'lucide-react';
import { Tab } from '../App';

import TaskInput from './Intelligence/TaskInput';
import CandidateList from './Intelligence/CandidateList';
import GlobalIntelligence from './Intelligence/GlobalIntelligence';
import PromptPreview from './Intelligence/PromptPreview';
import ImpactAnalysis from './Intelligence/ImpactAnalysis';
import RuntimeDiagnostics from './Intelligence/RuntimeDiagnostics';

import '../styles/IntelligenceShared.css';
import '../styles/RightPanel.css';
import '../styles/IntelligenceModal.css';

interface RightPanelProps {
  activeTab: Tab | null;
  isProjectLoaded: boolean;
  onFileSelect?: (path: string, line?: number) => void;
}

interface ContextStatus {
  initialized: boolean;
  root: string | null;
  files: number;
  symbols: number;
  artifacts: number;
  frameworks: string[];
}

interface PromptStats {
  files: number;
  context_lines: number;
  prompt_tokens: number;
}

const getLanguage = (path: string | null) => {
  if (!path) return 'None';
  const ext = path.split('.').pop()?.toLowerCase();
  const map: Record<string, string> = {
    'py': 'Python',
    'js': 'JavaScript',
    'ts': 'TypeScript',
    'tsx': 'React TS',
    'jsx': 'React JS',
    'java': 'Java',
    'cpp': 'C++',
    'cs': 'C#',
    'go': 'Go',
    'rs': 'Rust',
    'html': 'HTML',
    'css': 'CSS'
  };
  return map[ext || ''] || 'Plain Text';
};

const API_BASE = 'http://127.0.0.1:8000';

const RightPanel: React.FC<RightPanelProps> = ({ activeTab, isProjectLoaded, onFileSelect }) => {
  const [goal, setGoal] = useState('');
  const [mode, setMode] = useState('feature');
  const [loading, setLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [fullFileOverrides, setFullFileOverrides] = useState<Set<string>>(new Set());
  const [sliceSelection, setSliceSelection] = useState<Record<string, Set<number>>>({});
  const [autoSliceSelection, setAutoSliceSelection] = useState<Record<string, Set<number>>>({});
  const [expandedCand, setExpandedCand] = useState<string | null>(null);
  const [retrievalOpen, setRetrievalOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [promptStats, setPromptStats] = useState<PromptStats | null>(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const [showCopied, setShowCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(false);
  const [activeIntelView, setActiveIntelView] = useState<'none' | 'runtime' | 'impact'>('none');
  
  // Runtime State
  const [runtimeArtifacts, setRuntimeArtifacts] = useState<any[]>([]);
  const [executionChains, setExecutionChains] = useState<any[]>([]);
  const [hotSymbols, setHotSymbols] = useState<any[]>([]);
  
  // Impact State
  const [impactCandidates, setImpactCandidates] = useState<any[]>([]);
  const [impactLoading, setImpactLoading] = useState(false);

  const runtimeFetchInFlight = useRef(false);
  const runtimeFetchQueued = useRef(false);
  const diagnosticsVersionRef = useRef(0);

  const fetchContextStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/context/status`);
      if (res.ok) {
        const data = await res.json();
        setContextStatus(data);
      }
    } catch (err) {
      console.error('Status fetch failed', err);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const fetchRuntime = useCallback(async () => {
    if (runtimeFetchInFlight.current) {
      runtimeFetchQueued.current = true;
      return;
    }
    runtimeFetchInFlight.current = true;
    try {
      const res = await fetch(`${API_BASE}/context/runtime`);
      if (res.ok) {
        const data = await res.json();
        setRuntimeArtifacts(data.artifacts || []);
        setExecutionChains(data.execution_chains || []);
        setHotSymbols(data.hot_symbols || []);
      }
    } catch (err) {
      console.error('Runtime fetch failed', err);
    } finally {
      runtimeFetchInFlight.current = false;
      if (runtimeFetchQueued.current) {
        runtimeFetchQueued.current = false;
        void fetchRuntime();
      }
    }
  }, []);

  const flushActiveFileDiagnostics = useCallback(async () => {
    if (!activeTab) return;

    diagnosticsVersionRef.current += 1;
    try {
      const res = await fetch(`${API_BASE}/file/diagnostics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: activeTab.path,
          content: activeTab.content || '',
          version: Date.now() + diagnosticsVersionRef.current
        })
      });

      if (res.ok) {
        window.dispatchEvent(new CustomEvent('nexus-runtime-updated', { detail: { path: activeTab.path } }));
      }
    } catch (err) {
      console.error('Active file diagnostics flush failed', err);
    }
  }, [activeTab]);

  const resetWorkflowState = useCallback(() => {
    setGoal('');
    setMode('feature');
    setCandidates([]);
    setImpactCandidates([]);
    setRuntimeArtifacts([]);
    setExecutionChains([]);
    setHotSymbols([]);
    setSelectedPaths(new Set());
    setFullFileOverrides(new Set());
    setSliceSelection({});
    setAutoSliceSelection({});
    setExpandedCand(null);
    setPrompt('');
    setPromptStats(null);
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

    // Initial fetch
    fetchContextStatus();
    fetchRuntime();

    // Background polling for runtime telemetry (VS Code-like reactive behavior)
    const runtimeInterval = setInterval(() => {
      fetchRuntime();
    }, 5000);

    const handleRuntimeUpdated = () => {
      fetchRuntime();
    };
    window.addEventListener('nexus-runtime-updated', handleRuntimeUpdated);

    return () => {
      clearInterval(runtimeInterval);
      window.removeEventListener('nexus-runtime-updated', handleRuntimeUpdated);
    };
  }, [fetchContextStatus, fetchRuntime, isProjectLoaded, resetWorkflowState]);

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
        const rawCandidates = data.candidates || [];
        
        // Deduplicate and merge candidates by relative path
        const map = new Map<string, any>();
        rawCandidates.forEach((cand: any) => {
          const path = cand.file_metadata.rel_path;
          if (map.has(path)) {
            const existing = map.get(path);
            const allSymbols = new Set([...existing.affected_symbols, ...cand.affected_symbols]);
            map.set(path, {
              ...existing,
              affected_symbols: Array.from(allSymbols),
              traversal_depth: Math.min(existing.traversal_depth, cand.traversal_depth),
              impact_score: Math.max(existing.impact_score, cand.impact_score)
            });
          } else {
            map.set(path, { ...cand });
          }
        });
        
        setImpactCandidates(Array.from(map.values()).sort((a, b) => b.impact_score - a.impact_score));
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

  const clearRetrievalState = useCallback(() => {
    setCandidates([]);
    setImpactCandidates([]);
    setSelectedPaths(new Set());
    setFullFileOverrides(new Set());
    setSliceSelection({});
    setAutoSliceSelection({});
    setExpandedCand(null);
    setPrompt('');
    setPromptStats(null);
    setPromptOpen(false);
  }, []);

  const handleRetrieve = async () => {
    if (!activeTab || !goal.trim()) return;
    if (!contextReady) {
      setError('Initialize the Context Engine before retrieving context.');
      return;
    }

    setLoading(true);
    setError(null);
    clearRetrievalState();

    try {
      await flushActiveFileDiagnostics();
      await fetchRuntime();
      const res = await fetch(`${API_BASE}/context/retrieve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          file: activeTab.path, 
          goal,
          mode,
          include_slices: true
        })
      });
      if (!res.ok) throw new Error(`Retrieval failed: ${res.status}`);

      const data = await res.json();
      const nextCandidates = data.candidates || [];
      const autoSelectedFiles = new Set<string>();
      const autoSlices: Record<string, Set<number>> = {};
      const currentSlices: Record<string, Set<number>> = {};

      nextCandidates.forEach((candidate: any) => {
        const path = candidate.file_metadata.rel_path;
        if (candidate.score >= 40) autoSelectedFiles.add(path);
        
        const autoIdx = new Set<number>();
        const currentIdx = new Set<number>();
        if (candidate.slices) {
          candidate.slices.forEach((slice: any, idx: number) => {
            if (['exact', 'runtime', 'dependency'].includes(slice.expansion_type)) {
              autoIdx.add(idx);
              currentIdx.add(idx);
            }
          });
        }
        autoSlices[path] = autoIdx;
        currentSlices[path] = currentIdx;
      });

      setCandidates(nextCandidates);
      setSelectedPaths(autoSelectedFiles);
      setAutoSliceSelection(autoSlices);
      setSliceSelection(currentSlices);
      setRetrievalOpen(true);
      
      await fetchImpact(activeTab.path);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAssemble = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/context/assemble`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: goal,
          active_file: activeTab?.path,
          selected_files: Array.from(selectedPaths),
          selected_candidates: candidates.filter((candidate) => selectedPaths.has(candidate.file_metadata.rel_path)),
          selected_slices: Object.fromEntries(
            Object.entries(sliceSelection).map(([k, v]) => [k, Array.from(v)])
          ),
          full_file_overrides: Array.from(fullFileOverrides),
          mode
        })
      });
      if (!res.ok) throw new Error(`Assembly failed: ${res.status}`);
      const data = await res.json();
      setPrompt(data.prompt);
      setPromptStats(data.stats || null);
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
    if (next.has(path)) {
      next.delete(path);
      const nextOverrides = new Set(fullFileOverrides);
      nextOverrides.delete(path);
      setFullFileOverrides(nextOverrides);
      setSliceSelection(prev => {
        const nextSlice = { ...prev };
        delete nextSlice[path];
        return nextSlice;
      });
    } else {
      next.add(path);
      setSliceSelection(prev => ({
        ...prev,
        [path]: new Set(autoSliceSelection[path] || [])
      }));
    }
    setSelectedPaths(next);
  };

  const toggleSlice = (path: string, index: number) => {
    setSliceSelection(prev => {
      const nextSet = new Set(prev[path] || []);
      if (nextSet.has(index)) nextSet.delete(index);
      else nextSet.add(index);
      
      const isNowSelected = nextSet.size > 0;
      setSelectedPaths(current => {
        const next = new Set(current);
        if (isNowSelected) next.add(path);
        else if (!fullFileOverrides.has(path)) next.delete(path);
        return next;
      });

      return { ...prev, [path]: nextSet };
    });
  };

  const selectAllSlices = (path: string) => {
    const cand = candidates.find(c => c.file_metadata.rel_path === path);
    if (!cand || !cand.slices) return;
    const allIndices = cand.slices.map((_: any, i: number) => i);
    const current = sliceSelection[path] || new Set<number>();
    const allSelected = allIndices.length > 0 && current.size === allIndices.length;

    if (allSelected) {
      setSliceSelection(prev => ({ ...prev, [path]: new Set<number>() }));
      if (!fullFileOverrides.has(path)) {
        setSelectedPaths(currentPaths => {
          const nextPaths = new Set(currentPaths);
          nextPaths.delete(path);
          return nextPaths;
        });
      }
      return;
    }
    
    setSliceSelection(prev => ({
      ...prev,
      [path]: new Set(allIndices)
    }));
    
    if (!selectedPaths.has(path)) {
      const next = new Set(selectedPaths);
      next.add(path);
      setSelectedPaths(next);
    }
  };

  const toggleFullFile = (path: string) => {
    const next = new Set(fullFileOverrides);
    if (next.has(path)) {
      next.delete(path);
      if (!sliceSelection[path] || sliceSelection[path].size === 0) {
        setSelectedPaths(current => {
          const nextPaths = new Set(current);
          nextPaths.delete(path);
          return nextPaths;
        });
      }
    } else {
      next.add(path);
      if (!selectedPaths.has(path)) {
        const nextPaths = new Set(selectedPaths);
        nextPaths.add(path);
        setSelectedPaths(nextPaths);
      }
    }
    setFullFileOverrides(next);
  };

  const handleCopyPrompt = () => {
    if (prompt) {
      navigator.clipboard.writeText(prompt);
      setShowCopied(true);
      setTimeout(() => setShowCopied(false), 2000);
    }
  };

  const handleJumpToSource = (path: string, line?: number) => {
    if (onFileSelect) {
      onFileSelect(path, line);
      setRetrievalOpen(false);
    }
  };

  const contextReady = contextStatus?.initialized || false;
  const activeLanguage = getLanguage(activeTab?.path || null);
  const activeFramework = contextStatus?.frameworks?.length ? contextStatus.frameworks[0] : 'No Framework';

  const stats = useMemo(() => [
    { label: 'Files', value: contextStatus?.files || 0 },
    { label: 'Symbols', value: contextStatus?.symbols || 0 },
    { label: 'Frameworks', value: contextStatus?.frameworks?.length || 0 }
  ], [contextStatus]);

  return (
    <div className="right-panel-root">
      {showCopied && (
        <div className="copy-feedback-bubble fixed-top">
          <CheckCircle2 size={12} className="text-white" />
          <span>Copied to Clipboard!</span>
        </div>
      )}

      <div className="right-panel-content custom-scrollbar">
        {/* Card 1: Overview */}
        <div className="panel-section">
          <div className="panel-title accent">
            <Database size={13} />
            <span>Project Overview</span>
          </div>

          <div className="panel-card context-status-card">
            <div className="context-status-row">
              <span className={`context-status-dot ${contextReady ? 'ready' : ''}`} />
              <span className="truncate">
                {statusLoading
                  ? 'Checking context engine...'
                  : !isProjectLoaded
                    ? 'Pick a project root first'
                    : contextReady
                    ? 'Context Engine initialized'
                    : 'Context Engine not initialized'}
              </span>
            </div>

            {contextReady && (
              <div className="context-stat-grid">
                {stats.map((stat) => (
                  <div className="context-stat" key={stat.label}>
                    <span>{stat.value}</span>
                    <small>{stat.label}</small>
                  </div>
                ))}
              </div>
            )}

            <button
              className="btn btn-primary w-full flex items-center justify-center gap-2"
              onClick={initializeContext}
              disabled={!isProjectLoaded || initializing}
            >
              <RefreshCw size={13} />
              <span className="truncate">
                {!isProjectLoaded
                  ? 'Pick Project Root First'
                  : initializing
                    ? 'Initializing...'
                    : contextReady
                      ? 'Refresh Index'
                      : 'Initialize Context Engine'}
              </span>
            </button>
          </div>
        </div>

        {/* Card 2: Active Context */}
        {contextReady && (
          <div className="panel-section">
            <div className="panel-title">
              <FileCode size={13} />
              <span>Active Context</span>
            </div>
            <div className="panel-card active-context-card">
              <div className="panel-file-row">
                <FileCode size={14} className="text-blue-400" />
                <span className="panel-file truncate">
                  {activeTab ? activeTab.path.split('/').pop() : 'No active file'}
                </span>
              </div>
              <div className="active-context-meta">
                <span>{activeLanguage}</span>
                <span>{activeFramework}</span>
              </div>
              
              {activeTab && <div className="panel-path opacity-40 mt-1 truncate">{activeTab.path}</div>}
            </div>
          </div>
        )}

        {/* Card 3: Context Workflow */}
        {contextReady && (
          <div className="panel-section">
            <div className="panel-title">
              <Sparkles size={13} />
              <span>Context Workflow</span>
            </div>
            <div className="panel-card">
              <TaskInput
                goal={goal}
                setGoal={setGoal}
                mode={mode}
                setMode={setMode}
                loading={loading}
                disabled={!activeTab}
                onRetrieve={handleRetrieve}
                candidates={candidates}
                prompt={prompt}
                impactCandidates={impactCandidates}
                hasRuntime={runtimeArtifacts.length > 0}
                onClear={() => {
                  setGoal('');
                  setMode('feature');
                  setCandidates([]);
                  setImpactCandidates([]);
                  setSelectedPaths(new Set());
                  setFullFileOverrides(new Set());
                  setSliceSelection({});
                  setAutoSliceSelection({});
                  setExpandedCand(null);
                  setPrompt('');
                  setPromptStats(null);
                  setRetrievalOpen(false);
                  setPromptOpen(false);
                  setError(null);
                }}
              />
            </div>
          </div>
        )}

        {/* Card 4: Executor */}
        {contextReady && (
          <div className="panel-section">
            <div className="panel-title">
              <Terminal size={13} />
              <span>Execution Engine</span>
            </div>
            <div className="panel-card">
              <button className="btn w-full flex items-center justify-center gap-2 opacity-60">
                <Terminal size={13} />
                <span className="font-bold">Executor</span>
              </button>
            </div>
          </div>
        )}

        {error && <div className="px-4 text-[10px] text-red-400">Error: {error}</div>}
      </div>

      <div className="panel-footer">
        <span>NEXUS CONTEXT ENGINE v0.2.0</span>
        <button className="footer-settings-btn" title="Intelligence Settings">
          <Settings size={12} />
        </button>
      </div>

      {retrievalOpen && (
        <div className="intel-modal-backdrop">
          <div className={`intel-modal ${mode === 'fix' ? 'mode-fix' : mode === 'refactor' ? 'mode-refactor' : ''}`}>
            <div className="intel-modal-header">
              <div className="intel-modal-header-main">
                <div className="intel-modal-title accent">
                  {activeIntelView === 'runtime' ? <Activity size={16} strokeWidth={2.5} /> : 
                   activeIntelView === 'impact' ? <Database size={16} strokeWidth={2.5} /> : 
                   <Layers size={16} strokeWidth={2.5} />}
                  <span>
                    {activeIntelView === 'runtime' ? 'Telemetry Diagnostics' : 
                     activeIntelView === 'impact' ? 'Downstream Impact Radius' : 
                     'Surgical Engineering Intelligence'}
                  </span>
                </div>
                <div className="intel-modal-subtitle">
                  <span className="intel-header-file-pill">
                    <FileCode size={10} className="opacity-50" />
                    {activeTab?.path.split('/').pop()}
                  </span>
                  <div className="intel-subtitle-divider"></div>
                  <span className="intel-stat-highlight">
                    {activeIntelView === 'runtime' ? `${runtimeArtifacts.length} Artifacts` : 
                     activeIntelView === 'impact' ? `${impactCandidates.length} Impacted Files` : 
                     `${candidates.length} Files Ranked`}
                  </span>
                </div>
              </div>
              <button className="intel-modal-close" onClick={() => setRetrievalOpen(false)} type="button">
                <X size={16} />
              </button>
            </div>

            <div className="intel-modal-body custom-scrollbar">
              <GlobalIntelligence 
                runtimeCount={runtimeArtifacts.length}
                impactCount={impactCandidates.length}
                activeView={activeIntelView}
                setActiveView={setActiveIntelView}
              />

              {activeIntelView === 'runtime' && (
                <RuntimeDiagnostics 
                  artifacts={runtimeArtifacts} 
                  executionChains={executionChains}
                  hotSymbols={hotSymbols}
                  onClear={handleClearRuntime}
                  onJumpToFile={handleJumpToSource}
                />
              )}

              {activeIntelView === 'impact' && (
                <ImpactAnalysis 
                  impactCandidates={impactCandidates} 
                  loading={impactLoading}
                  onJumpToFile={handleJumpToSource}
                />
              )}

              {activeIntelView === 'none' && (
                <CandidateList
                  candidates={candidates}
                  selectedPaths={selectedPaths}
                  fullFileOverrides={fullFileOverrides}
                  sliceSelection={sliceSelection}
                  autoSliceSelection={autoSliceSelection}
                  toggleSelection={toggleSelection}
                  toggleSlice={toggleSlice}
                  toggleFullFile={toggleFullFile}
                  selectAllSlices={selectAllSlices}
                  expandedCand={expandedCand}
                  setExpandedCand={setExpandedCand}
                  onAssemble={handleAssemble}
                  loading={loading}
                  mode={mode}
                />
              )}
            </div>

            <div className="intel-modal-footer">
              <button
                className="btn btn-primary w-full flex items-center justify-center gap-2"
                onClick={handleAssemble}
                disabled={loading || selectedPaths.size === 0}
              >
                <Zap size={14} />
                Assemble Prompt
              </button>
            </div>
          </div>
        </div>
      )}

      {promptOpen && (
        <div className="intel-modal-backdrop">
          <div className="intel-modal prompt-modal">
            <div className="intel-modal-header">
              <div className="intel-modal-header-main">
                <div className="intel-modal-title accent">
                  <CheckCircle2 size={16} strokeWidth={2.5} />
                  <span>Prompt Ready</span>
                </div>
                <div className="intel-modal-subtitle">
                  <span className="intel-header-file-pill">
                    {mode.toUpperCase()}
                  </span>
                </div>
              </div>
              <button className="intel-modal-close" onClick={() => setPromptOpen(false)} type="button">
                <X size={16} />
              </button>
            </div>

            <div className="intel-modal-body custom-scrollbar">
              <PromptPreview 
                prompt={prompt}
                stats={promptStats}
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
