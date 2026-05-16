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
  workspaceFiles?: { path: string; name: string }[];
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

interface PromptPreset {
  id: string;
  name: string;
  description: string;
  isDefault?: boolean;
}

interface RuntimeSettings {
  python: string;
  node: string;
  java: string;
  gcc: string;
  gpp: string;
  dotnet: string;
  bash: string;
  powershell: string;
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

const RightPanel: React.FC<RightPanelProps> = ({ activeTab, isProjectLoaded, onFileSelect, workspaceFiles = [] }) => {
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'runtime' | 'prompts'>('runtime');
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettings>({
    python: '',
    node: '',
    java: '',
    gcc: '',
    gpp: '',
    dotnet: '',
    bash: '',
    powershell: ''
  });
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState('');
  const [promptPresets, setPromptPresets] = useState<PromptPreset[]>([
    { id: 'default', name: 'Nexus Default', description: 'Locked system template that ships with Nexus.', isDefault: true },
    { id: 'system-safe', name: 'System Safe', description: 'Compact, structured prompt for routine work.' },
    { id: 'deep-debug', name: 'Deep Debug', description: 'Biases toward runtime and failure analysis.' }
  ]);
  const [selectedPromptPresetId, setSelectedPromptPresetId] = useState('default');
  const [promptSettingsOpen, setPromptSettingsOpen] = useState(false);
  const [newPresetName, setNewPresetName] = useState('My Prompt Preset');
  const [newPresetDescription, setNewPresetDescription] = useState('A custom prompt framing preset.');
  const [editPresetName, setEditPresetName] = useState('');
  const [editPresetDescription, setEditPresetDescription] = useState('');
  const [manualPromptAddEnabled, setManualPromptAddEnabled] = useState(false);
  const [manualPromptSearch, setManualPromptSearch] = useState('');

  const runtimeFetchInFlight = useRef(false);
  const runtimeFetchQueued = useRef(false);
  const diagnosticsVersionRef = useRef(0);
  const selectedPreset = promptPresets.find((preset) => preset.id === selectedPromptPresetId) || promptPresets[0];

  useEffect(() => {
    if (!selectedPreset) return;
    setEditPresetName(selectedPreset.isDefault ? '' : selectedPreset.name);
    setEditPresetDescription(selectedPreset.isDefault ? '' : selectedPreset.description);
  }, [selectedPreset?.id]);

  const openSettings = (tab: 'runtime' | 'prompts' = 'runtime') => {
    setSettingsTab(tab);
    setSettingsOpen(true);
  };

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

  const fetchRuntimeSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/runtimes`);
      if (!res.ok) return;
      const data = await res.json();
      setRuntimeSettings({
        python: data.python || '',
        node: data.node || '',
        java: data.java || '',
        gcc: data.gcc || '',
        gpp: data.gpp || '',
        dotnet: data.dotnet || '',
        bash: data.bash || '',
        powershell: data.powershell || ''
      });
    } catch (err) {
      console.error('Runtime settings fetch failed', err);
    }
  }, []);

  const saveRuntimeSettings = useCallback(async () => {
    setSettingsSaving(true);
    setSettingsStatus('');
    try {
      const res = await fetch(`${API_BASE}/settings/runtimes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(runtimeSettings)
      });
      if (!res.ok) throw new Error('Failed to save runtime settings');
      setSettingsStatus('Saved runtime paths');
      window.setTimeout(() => setSettingsStatus(''), 1800);
    } catch (err) {
      setSettingsStatus('Could not save runtime paths');
      console.error('Runtime settings save failed', err);
    } finally {
      setSettingsSaving(false);
    }
  }, [runtimeSettings]);

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
    fetchRuntimeSettings();

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
  }, [fetchContextStatus, fetchRuntime, fetchRuntimeSettings, isProjectLoaded, resetWorkflowState]);

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

  const createPromptPreset = () => {
    const name = newPresetName.trim();
    const description = newPresetDescription.trim();
    if (!name || !description) return;
    const id = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || `preset-${Date.now()}`;
    setPromptPresets((prev) => [...prev, { id, name, description }]);
    setSelectedPromptPresetId(id);
    setEditPresetName(name);
    setEditPresetDescription(description);
  };

  const updatePromptPreset = () => {
    if (!selectedPreset || selectedPreset.isDefault) return;
    setPromptPresets((prev) =>
      prev.map((preset) =>
        preset.id === selectedPreset.id
          ? { ...preset, name: editPresetName.trim() || preset.name, description: editPresetDescription.trim() || preset.description }
          : preset
      )
    );
  };

  const deletePromptPreset = () => {
    if (!selectedPreset || selectedPreset.isDefault) return;
    setPromptPresets((prev) => prev.filter((preset) => preset.id !== selectedPreset.id));
    setSelectedPromptPresetId('default');
  };

  const manualPromptMatches = useMemo(() => {
    const query = manualPromptSearch.trim().toLowerCase();
    if (!manualPromptAddEnabled || !query) return [];
    return workspaceFiles
      .filter((file) => file.path.toLowerCase().includes(query) || file.name.toLowerCase().includes(query))
      .slice(0, 8);
  }, [manualPromptAddEnabled, manualPromptSearch, workspaceFiles]);

  const addManualPromptFile = (path: string) => {
    const next = new Set(selectedPaths);
    next.add(path);
    setSelectedPaths(next);
    setManualPromptSearch('');
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
        <button className="footer-settings-btn" title="Nexus Settings" onClick={() => openSettings('runtime')} type="button">
          <Settings size={12} />
        </button>
      </div>

      {settingsOpen && (
        <div className="intel-modal-backdrop">
          <div className="intel-modal settings-modal">
            <div className="intel-modal-header">
              <div className="intel-modal-header-main">
                <div className="intel-modal-title accent">
                  <Settings size={16} strokeWidth={2.5} />
                  <span>Nexus Settings</span>
                </div>
                <div className="intel-modal-subtitle">
                  <span>Runtime paths and prompt presets live in one Nexus settings hub.</span>
                </div>
              </div>
              <button className="intel-modal-close" onClick={() => setSettingsOpen(false)} type="button">
                <X size={16} />
              </button>
            </div>

            <div className="intel-modal-body custom-scrollbar settings-modal-body">
              <div className="settings-tabbar">
                <button
                  type="button"
                  className={`settings-tab ${settingsTab === 'runtime' ? 'active' : ''}`}
                  onClick={() => setSettingsTab('runtime')}
                >
                  Runtimes
                </button>
                <button
                  type="button"
                  className={`settings-tab ${settingsTab === 'prompts' ? 'active' : ''}`}
                  onClick={() => setSettingsTab('prompts')}
                >
                  Prompt Presets
                </button>
              </div>

              <div className="settings-hero">
                <div className="settings-hero-copy">
                  <div className="settings-hero-title">Language runtime registry</div>
                  <div className="settings-hero-subtitle">
                    Keep Nexus self-contained now, and switch any runtime to a custom path later without changing the workflow.
                  </div>
                </div>
                <div className="settings-hero-badge">Nexus first, custom optional</div>
              </div>

              <div className="settings-grid">
                {[
                  { key: 'python', label: 'Python', placeholder: 'backend/runtimes/python/python.exe' },
                  { key: 'node', label: 'Node.js', placeholder: 'backend/runtimes/node/node.exe' },
                  { key: 'java', label: 'Java', placeholder: 'backend/runtimes/java/bin/java.exe' },
                  { key: 'gcc', label: 'C compiler', placeholder: 'backend/runtimes/gcc/bin/gcc.exe' },
                  { key: 'gpp', label: 'C++ compiler', placeholder: 'backend/runtimes/gcc/bin/g++.exe' },
                  { key: 'dotnet', label: 'C# compiler', placeholder: 'backend/runtimes/dotnet/sdk/csc.exe' },
                  { key: 'bash', label: 'Bash', placeholder: 'backend/runtimes/bash/bin/bash.exe' },
                  { key: 'powershell', label: 'PowerShell', placeholder: 'backend/runtimes/powershell/bin/powershell.exe' },
                ].map((runtime) => (
                  <label className="runtime-setting-row" key={runtime.key}>
                    <div className="runtime-setting-meta">
                      <span className="runtime-setting-label">{runtime.label}</span>
                      <span className="runtime-setting-hint">Executable path for this language</span>
                    </div>
                    <input
                      className="runtime-setting-input"
                      value={runtimeSettings[runtime.key as keyof RuntimeSettings]}
                      onChange={(e) => setRuntimeSettings((prev) => ({ ...prev, [runtime.key]: e.target.value }))}
                      placeholder={runtime.placeholder}
                      spellCheck={false}
                    />
                  </label>
                ))}
              </div>

              <div className="settings-note">
                Later we can add auto-detect, download/install, and per-project runtime overrides without changing this layout.
              </div>

              {settingsTab === 'prompts' && (
                <div className="settings-grid prompt-settings-grid">
                  <div className="settings-panel">
                    <div className="settings-panel-title">Available presets</div>
                    <div className="prompt-preset-admin-list">
                      {promptPresets.map((preset) => (
                        <button
                          key={preset.id}
                          className={`prompt-preset-admin-row ${selectedPromptPresetId === preset.id ? 'active' : ''}`}
                          onClick={() => {
                            setSelectedPromptPresetId(preset.id);
                            setEditPresetName(preset.isDefault ? '' : preset.name);
                            setEditPresetDescription(preset.isDefault ? '' : preset.description);
                          }}
                          type="button"
                        >
                          <span>{preset.name}</span>
                          {preset.isDefault ? <span className="prompt-preset-admin-tag">Default</span> : <span className="prompt-preset-admin-tag">Custom</span>}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="settings-panel">
                    <div className="settings-panel-title">Edit preset</div>
                    <div className="settings-panel-copy">
                      Default preset is locked. Select a custom preset to rename or refine it.
                    </div>
                    <input
                      className="runtime-setting-input"
                      placeholder="Preset name"
                      value={editPresetName}
                      onChange={(e) => setEditPresetName(e.target.value)}
                      disabled={selectedPreset?.isDefault}
                    />
                    <textarea
                      className="runtime-setting-input settings-textarea"
                      placeholder="Preset description"
                      value={editPresetDescription}
                      onChange={(e) => setEditPresetDescription(e.target.value)}
                      disabled={selectedPreset?.isDefault}
                    />
                    <div className="settings-actions compact">
                      <button className="modal-btn modal-btn-secondary" onClick={updatePromptPreset} disabled={selectedPreset?.isDefault} type="button">
                        Update
                      </button>
                      <button className="modal-btn modal-btn-confirm destructive" onClick={deletePromptPreset} disabled={selectedPreset?.isDefault} type="button">
                        Delete
                      </button>
                    </div>
                  </div>

                  <div className="settings-panel full-span">
                    <div className="settings-panel-title">Create preset</div>
                    <div className="settings-panel-copy">
                      Start from a fresh prompt style. This only creates custom presets.
                    </div>
                    <input
                      className="runtime-setting-input"
                      placeholder="New preset name"
                      value={newPresetName}
                      onChange={(e) => setNewPresetName(e.target.value)}
                    />
                    <textarea
                      className="runtime-setting-input settings-textarea"
                      placeholder="New preset description"
                      value={newPresetDescription}
                      onChange={(e) => setNewPresetDescription(e.target.value)}
                    />
                    <div className="settings-actions compact">
                      <button className="modal-btn modal-btn-cancel" onClick={createPromptPreset} type="button">
                        Create preset
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="intel-modal-footer settings-modal-footer">
              <div className="settings-status">{settingsStatus || 'Settings are stored locally by Nexus.'}</div>
              <div className="settings-actions">
                <button
                  className="modal-btn modal-btn-cancel"
                  onClick={() => setRuntimeSettings({
                    python: '',
                    node: '',
                    java: '',
                    gcc: '',
                    gpp: '',
                    dotnet: '',
                    bash: '',
                    powershell: ''
                  })}
                  type="button"
                >
                  Reset
                </button>
                <button className="modal-btn modal-btn-confirm default" onClick={saveRuntimeSettings} disabled={settingsSaving} type="button">
                  {settingsSaving ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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
              <div className="prompt-preset-strip">
                <div className="prompt-preset-strip-header">
                  <div>
                    <div className="prompt-preset-strip-title">Prompt preset</div>
                    <div className="prompt-preset-strip-subtitle">
                      Select a template for how Nexus should frame the assembled prompt.
                    </div>
                  </div>
                  <button className="footer-settings-btn" onClick={() => openSettings('prompts')} type="button" title="Manage prompt presets">
                    <Settings size={12} />
                  </button>
                </div>
                <div className="prompt-preset-list">
                  {promptPresets.map((preset) => (
                    <button
                      key={preset.id}
                      className={`prompt-preset-chip ${selectedPromptPresetId === preset.id ? 'active' : ''} ${preset.isDefault ? 'locked' : ''}`}
                      onClick={() => setSelectedPromptPresetId(preset.id)}
                      type="button"
                    >
                      <span>{preset.name}</span>
                      {preset.isDefault && <span className="prompt-preset-lock">Locked</span>}
                    </button>
                  ))}
                </div>
                <div className="prompt-preset-note">
                  {selectedPreset?.description}
                </div>
                <div className="manual-add-row">
                  <label className="manual-add-toggle">
                    <input
                      type="checkbox"
                      checked={manualPromptAddEnabled}
                      onChange={(e) => setManualPromptAddEnabled(e.target.checked)}
                    />
                    <span>Allow manual file add in context preview</span>
                  </label>
                  {manualPromptAddEnabled && (
                    <div className="manual-add-panel">
                      <input
                        className="manual-add-search"
                        placeholder="Search any workspace file..."
                        value={manualPromptSearch}
                        onChange={(e) => setManualPromptSearch(e.target.value)}
                        type="text"
                      />
                      <div className="manual-add-results">
                        {manualPromptSearch.trim() ? (
                          manualPromptMatches.length ? (
                            manualPromptMatches.map((file) => (
                              <button
                                key={file.path}
                                className={`manual-add-result ${selectedPaths.has(file.path) ? 'selected' : ''}`}
                                onClick={() => addManualPromptFile(file.path)}
                                type="button"
                              >
                                <span className="manual-add-result-name">{file.name}</span>
                                <span className="manual-add-result-path">{file.path}</span>
                                <span className="manual-add-result-action">
                                  {selectedPaths.has(file.path) ? 'Added' : 'Add'}
                                </span>
                              </button>
                            ))
                          ) : (
                            <div className="manual-add-empty">No matching files yet.</div>
                          )
                        ) : (
                          <div className="manual-add-empty">Search any file in the workspace, even if Nexus did not score it.</div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>

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

      {promptSettingsOpen && (
        <div className="intel-modal-backdrop">
          <div className="intel-modal settings-modal">
            <div className="intel-modal-header">
              <div className="intel-modal-header-main">
                <div className="intel-modal-title accent">
                  <Sparkles size={16} strokeWidth={2.5} />
                  <span>Prompt Presets</span>
                </div>
                <div className="intel-modal-subtitle">
                  <span>Default preset is locked. Create or adjust your own prompt styles here.</span>
                </div>
              </div>
              <button className="intel-modal-close" onClick={() => setPromptSettingsOpen(false)} type="button">
                <X size={16} />
              </button>
            </div>

            <div className="intel-modal-body custom-scrollbar settings-modal-body">
              <div className="settings-grid prompt-settings-grid">
                <div className="settings-panel">
                  <div className="settings-panel-title">Available presets</div>
                  <div className="prompt-preset-admin-list">
                    {promptPresets.map((preset) => (
                      <button
                        key={preset.id}
                        className={`prompt-preset-admin-row ${selectedPromptPresetId === preset.id ? 'active' : ''}`}
                        onClick={() => {
                          setSelectedPromptPresetId(preset.id);
                          setNewPresetName(preset.name);
                          setNewPresetDescription(preset.description);
                        }}
                        type="button"
                      >
                        <span>{preset.name}</span>
                        {preset.isDefault ? <span className="prompt-preset-admin-tag">Default</span> : <span className="prompt-preset-admin-tag">Custom</span>}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="settings-panel">
                  <div className="settings-panel-title">Edit preset</div>
                  <div className="settings-panel-copy">
                    Default preset is locked. Select a custom preset to rename or refine it.
                  </div>
                  <input
                    className="runtime-setting-input"
                    placeholder="Preset name"
                    value={editPresetName}
                    onChange={(e) => setEditPresetName(e.target.value)}
                    disabled={selectedPreset?.isDefault}
                  />
                  <textarea
                    className="runtime-setting-input settings-textarea"
                    placeholder="Preset description"
                    value={editPresetDescription}
                    onChange={(e) => setEditPresetDescription(e.target.value)}
                    disabled={selectedPreset?.isDefault}
                  />
                  <div className="settings-actions compact">
                    <button className="modal-btn modal-btn-secondary" onClick={updatePromptPreset} disabled={selectedPreset?.isDefault} type="button">
                      Update
                    </button>
                    <button className="modal-btn modal-btn-confirm destructive" onClick={deletePromptPreset} disabled={selectedPreset?.isDefault} type="button">
                      Delete
                    </button>
                  </div>
                </div>

                <div className="settings-panel">
                  <div className="settings-panel-title">Create preset</div>
                  <div className="settings-panel-copy">
                    Start from a fresh prompt style. This only creates custom presets.
                  </div>
                  <input
                    className="runtime-setting-input"
                    placeholder="New preset name"
                    value={newPresetName}
                    onChange={(e) => setNewPresetName(e.target.value)}
                  />
                  <textarea
                    className="runtime-setting-input settings-textarea"
                    placeholder="New preset description"
                    value={newPresetDescription}
                    onChange={(e) => setNewPresetDescription(e.target.value)}
                  />
                  <div className="settings-actions compact">
                    <button className="modal-btn modal-btn-cancel" onClick={createPromptPreset} type="button">
                      Create preset
                    </button>
                  </div>
                </div>
              </div>
              <div className="settings-note">
                This is a placeholder UI for now. The backend template management will plug into these controls later.
              </div>
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
