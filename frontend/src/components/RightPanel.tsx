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
  dirtyPaths?: Set<string>;
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
  template?: string;
  isDefault?: boolean;
}
interface PromptSettingsResponse {
  selected_preset_id: string;
  manual_file_add_enabled?: boolean;
  allow_preset_change_in_preview?: boolean;
  executor_response_format?: 'unified_diff' | 'nexus_edits_v2';
  presets: PromptPreset[];
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
interface RuntimeDiagnosticsMap {
  [key: string]: {
    configured: string | null;
    resolved: string | null;
    bundled_path?: string | null;
    bundled_installed?: boolean;
    source: 'configured' | 'bundled' | 'system' | 'missing';
  };
}
interface RuntimeCatalogItem {
  key: string;
  label: string;
  version: string;
  status: 'not_installed' | 'installing' | 'installed' | 'failed' | 'update_available';
  resolved?: string | null;
  source?: string | null;
  bundled_installed?: boolean;
}
interface RuntimeInstallJobItem {
  runtime: string;
  status: string;
  progress: number;
  message: string;
  installed_version?: string | null;
  target_version?: string | null;
}
interface RuntimePreflight {
  ok: boolean;
  checks: Record<string, { ok: boolean; message: string }>;
}
interface HistoryEntry {
  commit: string;
  timestamp: number;
  message: string;
  path?: string | null;
}
interface RestorePreview {
  commit_id: string;
  impacted_files: string[];
  conflicts: Array<{ path: string; reason: string }>;
  can_apply: boolean;
  can_force_apply?: boolean;
}
interface PatchPreviewResult {
  files: Array<{ path: string; hunk_count: number }>;
  issues: Array<{ reason: string; path?: string; line?: number; details?: string; fix_suggestion?: string }>;
  warnings: Array<{ reason: string; path?: string; line?: number; details?: string; fix_suggestion?: string }>;
  blockers: Array<{ reason: string; path?: string; line?: number; details?: string; fix_suggestion?: string }>;
  stats: { additions: number; deletions: number };
  can_apply: boolean;
  blocked_stage?: 'parse' | 'validate' | 'simulate' | 'intent_guard' | 'apply' | 'verify' | null;
  intent_checks?: {
    required_contains: string[];
    required_absent: string[];
    provenance?: {
      derived?: { required_contains?: string[]; required_absent?: string[]; confidence?: number; enforced?: boolean };
      model?: { required_contains?: string[]; required_absent?: string[] };
      user?: { required_contains?: string[]; required_absent?: string[] };
    };
  };
  stage_timings_ms?: Record<string, number>;
}
interface PatchApplyResult extends PatchPreviewResult {
  operation_id?: string;
  snapshot_id?: string | null;
  snapshot_created?: boolean;
  results: Array<{ path: string; status: string }>;
  verification_passed?: boolean;
  rollback?: { attempted: boolean; success: boolean; operation_id?: string; snapshot_id?: string; undo_mode?: string; undo_target?: string; error?: string };
}
interface AutoFetchResult {
  detected_format: string;
  normalized_text: string;
  issues: Array<{ reason: string }>;
}
type ExecutorState = 'idle' | 'loading_preview' | 'preview_ready' | 'blocked_conflict' | 'applying' | 'applied' | 'failed';
const executorStateLabel: Record<ExecutorState, string> = {
  idle: 'Idle',
  loading_preview: 'Previewing',
  preview_ready: 'Ready',
  blocked_conflict: 'Blocked',
  applying: 'Applying',
  applied: 'Verified',
  failed: 'Failed',
};

const runtimeStatusOrder: Record<RuntimeCatalogItem['status'], number> = {
  failed: 0,
  not_installed: 1,
  update_available: 2,
  installing: 3,
  installed: 4,
};

const scoreManualMatch = (query: string, file: { path: string; name: string }) => {
  const q = query.trim().toLowerCase();
  if (!q) return -1;
  const name = file.name.toLowerCase();
  const path = file.path.toLowerCase();
  if (name === q) return 1000;
  if (name.startsWith(q)) return 800;
  if (name.includes(q)) return 650;
  if (path.includes(q)) return 400;
  return -1;
};

const highlightMatch = (text: string, query: string) => {
  const q = query.trim();
  if (!q) return text;
  const source = text.toLowerCase();
  const needle = q.toLowerCase();
  const start = source.indexOf(needle);
  if (start < 0) return text;
  const end = start + needle.length;
  return (
    <>
      {text.slice(0, start)}
      <mark className="manual-add-highlight">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  );
};

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

const blockerGuidance = (reason: string) => {
  const map: Record<string, string> = {
    invalid_json: 'Ensure the response is strict JSON with escaped quotes and no prose.',
    invalid_diff: 'Ensure the diff contains valid --- / +++ / @@ unified diff markers.',
    unsupported_op: 'Use only replace_range, insert_after, insert_before, create_file, delete_file.',
    unsupported_edit_field: 'Remove extra keys from edits; keep canonical schema only.',
    edit_mismatch: 'Refresh context and ensure old_text matches current file content exactly.',
    unsafe_path: 'Use workspace-relative safe paths only.',
    intent_mismatch: 'Align output with required task semantics and intent checks.',
    verify_failed: 'Re-run preview and correct semantic assertions before applying again.',
  };
  return map[reason] || 'Resolve the listed blocker and re-run preview.';
};

const API_BASE = 'http://127.0.0.1:8000';

const RightPanel: React.FC<RightPanelProps> = ({ activeTab, isProjectLoaded, onFileSelect, workspaceFiles = [], dirtyPaths = new Set() }) => {
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
  const [runtimeSettingsOpen, setRuntimeSettingsOpen] = useState(false);
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
  const [settingsFlash, setSettingsFlash] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [runtimeDiagnostics, setRuntimeDiagnostics] = useState<RuntimeDiagnosticsMap>({});
  const [runtimeCatalog, setRuntimeCatalog] = useState<RuntimeCatalogItem[]>([]);
  const [selectedRuntimeKeys, setSelectedRuntimeKeys] = useState<Set<string>>(new Set());
  const [runtimeInstallJobId, setRuntimeInstallJobId] = useState<string | null>(null);
  const [runtimeInstallItems, setRuntimeInstallItems] = useState<Record<string, RuntimeInstallJobItem>>({});
  const [runtimeInstallerBusy, setRuntimeInstallerBusy] = useState(false);
  const [runtimePreflight, setRuntimePreflight] = useState<RuntimePreflight | null>(null);
  const [promptPresets, setPromptPresets] = useState<PromptPreset[]>([]);
  const [selectedPromptPresetId, setSelectedPromptPresetId] = useState('default');
  const [newPresetName, setNewPresetName] = useState('My Prompt Preset');
  const [newPresetDescription, setNewPresetDescription] = useState('A custom prompt framing preset.');
  const [newPresetTemplate, setNewPresetTemplate] = useState('Task: {{goal}}\nMode: {{mode}}\nUse selected context to produce implementation steps and code changes.');
  const [editPresetName, setEditPresetName] = useState('');
  const [editPresetDescription, setEditPresetDescription] = useState('');
  const [editPresetTemplate, setEditPresetTemplate] = useState('');
  const [manualPromptAddEnabled, setManualPromptAddEnabled] = useState(false);
  const [allowPresetChangeInPreview, setAllowPresetChangeInPreview] = useState(true);
  const [executorResponseFormat, setExecutorResponseFormat] = useState<'unified_diff' | 'nexus_edits_v2'>('nexus_edits_v2');
  const [manualPromptSearch, setManualPromptSearch] = useState('');
  const [manualPromptFocusedIndex, setManualPromptFocusedIndex] = useState(0);
  const [executorOpen, setExecutorOpen] = useState(false);
  const [executorTab, setExecutorTab] = useState<'patch' | 'recover'>('patch');
  const [patchFlowOpen, setPatchFlowOpen] = useState(false);
  const [patchFlowDetailsOpen, setPatchFlowDetailsOpen] = useState(false);
  const [fileHistory, setFileHistory] = useState<HistoryEntry[]>([]);
  const [projectHistory, setProjectHistory] = useState<HistoryEntry[]>([]);
  const [selectedCommit, setSelectedCommit] = useState<string>('');
  const [executorStatus, setExecutorStatus] = useState<string>('');
  const [commitPreview, setCommitPreview] = useState<string[]>([]);
  const [restorePreview, setRestorePreview] = useState<RestorePreview | null>(null);
  const [executorState, setExecutorState] = useState<ExecutorState>('idle');
  const [executorBanner, setExecutorBanner] = useState<{ type: 'info' | 'warning' | 'error' | 'success'; text: string } | null>(null);
  const [forceAck, setForceAck] = useState(false);
  const [showReloadPrompt, setShowReloadPrompt] = useState(false);
  const [patchRawText, setPatchRawText] = useState('');
  const [uncertainOutputText, setUncertainOutputText] = useState('');
  const [patchPreview, setPatchPreview] = useState<PatchPreviewResult | null>(null);
  const [patchApplyResult, setPatchApplyResult] = useState<PatchApplyResult | null>(null);

  const runtimeFetchInFlight = useRef(false);
  const runtimeFetchQueued = useRef(false);
  const diagnosticsVersionRef = useRef(0);
  const selectedPreset = promptPresets.find((preset) => preset.id === selectedPromptPresetId) || promptPresets[0];
  const sortedRuntimeCatalog = useMemo(
    () =>
      [...runtimeCatalog].sort((a, b) => {
        const diff = runtimeStatusOrder[a.status] - runtimeStatusOrder[b.status];
        if (diff !== 0) return diff;
        return a.label.localeCompare(b.label);
      }),
    [runtimeCatalog]
  );

  useEffect(() => {
    if (!selectedPreset) return;
    setEditPresetName(selectedPreset.isDefault ? '' : selectedPreset.name);
    setEditPresetDescription(selectedPreset.isDefault ? '' : selectedPreset.description);
    setEditPresetTemplate(selectedPreset.isDefault ? '' : (selectedPreset.template || ''));
  }, [selectedPreset?.id]);

  const openRuntimeSettings = () => {
    setRuntimeSettingsOpen(true);
    void fetchRuntimeSettings();
    void fetchRuntimeDiagnostics();
    void fetchRuntimeCatalog();
    void fetchRuntimePreflight();
    void fetchPromptSettings();
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

  const fetchRuntimeDiagnostics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/runtimes/diagnostics`);
      if (!res.ok) return;
      const data = await res.json();
      setRuntimeDiagnostics(data || {});
    } catch (err) {
      console.error('Runtime diagnostics fetch failed', err);
    }
  }, []);

  const fetchRuntimeCatalog = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/runtimes/catalog`);
      if (!res.ok) return;
      const data = await res.json();
      const items: RuntimeCatalogItem[] = Array.isArray(data.runtimes) ? data.runtimes : [];
      setRuntimeCatalog(items);
      if (selectedRuntimeKeys.size === 0) {
        const missing = items.filter((it) => it.status !== 'installed').map((it) => it.key);
        setSelectedRuntimeKeys(new Set(missing));
      }
    } catch (err) {
      console.error('Runtime catalog fetch failed', err);
    }
  }, [selectedRuntimeKeys.size]);

  const fetchRuntimePreflight = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/runtimes/preflight`);
      if (!res.ok) return;
      const data: RuntimePreflight = await res.json();
      setRuntimePreflight(data);
    } catch (err) {
      console.error('Runtime preflight fetch failed', err);
    }
  }, []);

  const fetchPromptSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/prompts`);
      if (!res.ok) return;
      const data: PromptSettingsResponse = await res.json();
      setPromptPresets(Array.isArray(data.presets) ? data.presets : []);
      setSelectedPromptPresetId(data.selected_preset_id || 'default');
      setManualPromptAddEnabled(Boolean(data.manual_file_add_enabled));
      setAllowPresetChangeInPreview(Boolean(data.allow_preset_change_in_preview ?? true));
      setExecutorResponseFormat(data.executor_response_format === 'nexus_edits_v2' ? 'nexus_edits_v2' : 'unified_diff');
    } catch (err) {
      console.error('Prompt settings fetch failed', err);
    }
  }, []);

  const saveRuntimeSettings = useCallback(async () => {
    setSettingsSaving(true);
    try {
      const res = await fetch(`${API_BASE}/settings/runtimes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(runtimeSettings)
      });
      if (!res.ok) throw new Error('Failed to save runtime settings');
      await fetchRuntimeDiagnostics();
      setSettingsFlash({ type: 'success', message: 'Runtime settings saved' });
      window.setTimeout(() => setSettingsFlash(null), 1800);
    } catch (err) {
      console.error('Runtime settings save failed', err);
      setSettingsFlash({ type: 'error', message: 'Could not save runtime settings' });
      window.setTimeout(() => setSettingsFlash(null), 2200);
    } finally {
      setSettingsSaving(false);
    }
  }, [fetchRuntimeDiagnostics, runtimeSettings]);

  const savePromptSettings = useCallback(async (nextPresets: PromptPreset[], nextSelectedId: string) => {
    setSettingsSaving(true);
    try {
      const res = await fetch(`${API_BASE}/settings/prompts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_preset_id: nextSelectedId,
          manual_file_add_enabled: manualPromptAddEnabled,
          allow_preset_change_in_preview: allowPresetChangeInPreview,
          executor_response_format: executorResponseFormat,
          presets: nextPresets
        })
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok || payload.status === 'error') {
        throw new Error(payload.message || 'Failed to save prompt settings');
      }
      setSettingsFlash({ type: 'success', message: 'Prompt presets saved' });
      window.setTimeout(() => setSettingsFlash(null), 1800);
    } catch (err) {
      console.error('Prompt settings save failed', err);
      setSettingsFlash({ type: 'error', message: 'Could not save prompt presets' });
      window.setTimeout(() => setSettingsFlash(null), 2200);
    } finally {
      setSettingsSaving(false);
    }
  }, [allowPresetChangeInPreview, manualPromptAddEnabled, executorResponseFormat]);

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
    fetchRuntimeDiagnostics();
    fetchRuntimeCatalog();
    fetchRuntimePreflight();
    fetchPromptSettings();

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
  }, [fetchContextStatus, fetchPromptSettings, fetchRuntime, fetchRuntimeCatalog, fetchRuntimeDiagnostics, fetchRuntimeSettings, isProjectLoaded, resetWorkflowState, fetchRuntimePreflight]);

  const startRuntimeInstall = useCallback(async (mode: 'install' | 'update', runtimes: string[], reinstall: boolean) => {
    setRuntimeInstallerBusy(true);
    try {
      const endpoint = mode === 'update' ? '/settings/runtimes/update' : '/settings/runtimes/install';
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ runtimes, reinstall }),
      });
      if (!res.ok) throw new Error('Failed to start runtime install');
      const data = await res.json();
      setRuntimeInstallJobId(data.job_id);
      setSettingsFlash({ type: 'success', message: 'Installation started' });
    } catch (err) {
      console.error(err);
      setSettingsFlash({ type: 'error', message: 'Could not start runtime install' });
      setRuntimeInstallerBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!runtimeInstallJobId) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/settings/runtimes/install/${runtimeInstallJobId}`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        setRuntimeInstallItems(data.items || {});
        if (data.status === 'completed' || data.status === 'failed') {
          setRuntimeInstallerBusy(false);
          setRuntimeInstallJobId(null);
          await fetchRuntimeSettings();
          await fetchRuntimeDiagnostics();
          await fetchRuntimeCatalog();
          await fetchRuntimePreflight();
          setSettingsFlash({
            type: data.status === 'completed' ? 'success' : 'error',
            message: data.status === 'completed' ? 'Runtime install finished' : `Runtime install failed: ${data.error || 'Check item status'}`
          });
        }
      } catch (err) {
        console.error('Runtime install polling failed', err);
      }
    }, 1200);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [runtimeInstallJobId, fetchRuntimeCatalog, fetchRuntimeDiagnostics, fetchRuntimeSettings, fetchRuntimePreflight]);

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
            mode,
            selected_preset_id: selectedPromptPresetId
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
    const nextPresets = [...promptPresets, { id, name, description, template: newPresetTemplate.trim() }];
    setPromptPresets(nextPresets);
    setSelectedPromptPresetId(id);
    setEditPresetName(name);
    setEditPresetDescription(description);
    setEditPresetTemplate(newPresetTemplate.trim());
    void savePromptSettings(nextPresets, id);
  };

  const updatePromptPreset = () => {
    if (!selectedPreset || selectedPreset.isDefault) return;
    const nextPresets = promptPresets.map((preset) =>
      preset.id === selectedPreset.id
        ? {
            ...preset,
            name: editPresetName.trim() || preset.name,
            description: editPresetDescription.trim() || preset.description,
            template: editPresetTemplate.trim() || preset.template || '',
          }
        : preset
    );
    setPromptPresets(nextPresets);
    void savePromptSettings(nextPresets, selectedPromptPresetId);
  };

  const deletePromptPreset = () => {
    if (!selectedPreset || selectedPreset.isDefault) return;
    const nextPresets = promptPresets.filter((preset) => preset.id !== selectedPreset.id);
    const nextSelectedId = 'default';
    setPromptPresets(nextPresets);
    setSelectedPromptPresetId('default');
    void savePromptSettings(nextPresets, nextSelectedId);
  };

  const manualPromptMatches = useMemo(() => {
    const query = manualPromptSearch.trim().toLowerCase();
    if (!manualPromptAddEnabled || !query) return [];
    return workspaceFiles
      .map((file) => ({ file, score: scoreManualMatch(query, file) }))
      .filter((entry) => entry.score >= 0)
      .sort((a, b) => b.score - a.score || a.file.path.localeCompare(b.file.path))
      .map((entry) => entry.file)
      .slice(0, 8);
  }, [manualPromptAddEnabled, manualPromptSearch, workspaceFiles]);
  const manualSelectedCount = selectedPaths.size;
  const manualSelectedPreview = useMemo(
    () => Array.from(selectedPaths).slice(0, 4),
    [selectedPaths]
  );

  useEffect(() => {
    setManualPromptFocusedIndex(0);
  }, [manualPromptSearch, manualPromptMatches.length]);

  const addManualPromptFile = (path: string) => {
    const next = new Set(selectedPaths);
    next.add(path);
    setSelectedPaths(next);
    setManualPromptSearch('');
  };
  const removeManualPromptFile = (path: string) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      next.delete(path);
      return next;
    });
  };

  useEffect(() => {
    if (!manualPromptAddEnabled) {
      setManualPromptSearch('');
    }
  }, [manualPromptAddEnabled]);

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

  const openExecutor = async () => {
    setExecutorOpen(true);
    setExecutorTab('patch');
    setExecutorStatus('');
    setExecutorState('idle');
    setExecutorBanner({ type: 'info', text: 'Paste AI output, auto-fetch payload if needed, then preview/apply.' });
    setForceAck(false);
    setShowReloadPrompt(false);
    if (activeTab?.path) {
      const fileRes = await fetch(`${API_BASE}/history/file?path=${encodeURIComponent(activeTab.path)}`);
      const fileData = await fileRes.json().catch(() => ({ entries: [] }));
      setFileHistory(fileData.entries || []);
    } else {
      setFileHistory([]);
    }
    const projectRes = await fetch(`${API_BASE}/history/project`);
    const projectData = await projectRes.json().catch(() => ({ entries: [] }));
    setProjectHistory(projectData.entries || []);
  };

  const restoreActiveFile = async () => {
    if (!activeTab?.path || !selectedCommit) return;
    if (restorePreview && !restorePreview.can_apply) {
      setExecutorState('blocked_conflict');
      setExecutorBanner({ type: 'warning', text: 'Conflicts detected. Save/discard editor changes first.' });
      return;
    }
    setExecutorState('applying');
    const res = await fetch(`${API_BASE}/history/restore/file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: activeTab.path,
        commit_id: selectedCommit,
        has_dirty_conflict: dirtyPaths.has(activeTab.path),
        force: false
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.status === 'conflict') {
      if (data.status === 'error' && data.code === 'restore_conflict') {
        setExecutorState('blocked_conflict');
        setExecutorBanner({ type: 'warning', text: 'Restore blocked by conflicts.' });
      } else {
        setExecutorState('failed');
        setExecutorBanner({ type: 'error', text: 'Restore failed.' });
      }
      return;
    }
      setExecutorState('applied');
    setExecutorBanner({ type: 'success', text: 'Restore applied.' });
    setShowReloadPrompt(true);
    await openExecutor();
  };

  const forceRestoreActiveFile = async () => {
    if (!activeTab?.path || !selectedCommit || !forceAck) return;
    setExecutorState('applying');
    const res = await fetch(`${API_BASE}/history/restore/file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: activeTab.path,
        commit_id: selectedCommit,
        has_dirty_conflict: dirtyPaths.has(activeTab.path),
        force: true
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.status === 'error') {
      setExecutorState('failed');
      setExecutorBanner({ type: 'error', text: 'Force restore failed.' });
      return;
    }
    setExecutorState('applied');
    setExecutorBanner({ type: 'success', text: 'Force restore applied.' });
    setShowReloadPrompt(true);
    await openExecutor();
  };

  const previewCommit = async (commitId: string) => {
    setExecutorState('loading_preview');
    setSelectedCommit(commitId);
    const res = await fetch(`${API_BASE}/history/commit/${encodeURIComponent(commitId)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setExecutorState('failed');
      setExecutorBanner({ type: 'error', text: 'Failed to load commit preview.' });
      return;
    }
    setCommitPreview(Array.isArray(data.changes) ? data.changes : []);

    if (activeTab?.path) {
      const previewRes = await fetch(`${API_BASE}/history/restore/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          commit_id: commitId,
          path: activeTab.path,
          has_dirty_conflict: dirtyPaths.has(activeTab.path),
          scope: 'file',
        }),
      });
      const previewData = await previewRes.json().catch(() => ({}));
      if (previewRes.ok) {
        setRestorePreview(previewData as RestorePreview);
        if (previewData.can_apply) {
          setExecutorState('preview_ready');
          setExecutorBanner({ type: 'info', text: 'Preview ready. Safe to restore.' });
        } else {
          setExecutorState('blocked_conflict');
          setExecutorBanner({ type: 'warning', text: 'Preview found conflicts. Resolve before restore.' });
        }
      }
    }
  };

  const previewProjectCommit = async (commitId: string) => {
    setSelectedCommit(commitId);
    setExecutorState('loading_preview');
    const res = await fetch(`${API_BASE}/history/restore/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ commit_id: commitId, scope: 'project' }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.status === 'error') {
      setExecutorState('failed');
      setExecutorBanner({ type: 'error', text: 'Project preview failed.' });
      return;
    }
    setRestorePreview(data as RestorePreview);
    setExecutorState(data.can_apply ? 'preview_ready' : 'blocked_conflict');
    setExecutorBanner({ type: data.can_apply ? 'info' : 'warning', text: data.can_apply ? 'Project preview ready.' : 'Project preview has conflicts.' });
  };

  const restoreProjectFromSelected = async () => {
    if (!selectedCommit) return;
    if (restorePreview && !restorePreview.can_apply) return;
    setExecutorState('applying');
    const res = await fetch(`${API_BASE}/history/restore/project`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ commit_id: selectedCommit }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.status === 'error') {
      setExecutorState('failed');
      setExecutorBanner({ type: 'error', text: 'Project restore failed.' });
      return;
    }
    setExecutorState('applied');
    setExecutorBanner({ type: 'success', text: 'Project restore applied.' });
    setShowReloadPrompt(true);
    await openExecutor();
  };

  const undoLast = async () => {
    const res = await fetch(`${API_BASE}/history/undo`, { method: 'POST' });
    if (!res.ok) {
      setExecutorStatus('Undo failed');
      return;
    }
    setExecutorStatus('Undo complete');
    setShowReloadPrompt(true);
    await openExecutor();
  };

  const previewPatch = async () => {
    setExecutorState('loading_preview');
    setExecutorStatus('Parsing patch payload...');
    setExecutorBanner(null);
    setPatchApplyResult(null);
    try {
      const res = await fetch(`${API_BASE}/executor/patch/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_text: patchRawText,
          response_format: executorResponseFormat,
          auto_extract: true,
          task: goal,
          mode,
          active_file: activeTab?.path || null,
        }),
      });
      const payload = await res.json();
      const preview: PatchPreviewResult = {
        ...payload.preview,
        issues: payload.preview?.issues || [],
        warnings: payload.preview?.warnings || [],
        blockers: payload.preview?.blockers || [],
      };
      setPatchPreview(preview);
      if (preview?.can_apply) {
        setExecutorState('preview_ready');
        const warningCount = preview?.warnings?.length || 0;
        setExecutorBanner({ type: warningCount > 0 ? 'warning' : 'success', text: warningCount > 0 ? `Patch preview ready with ${warningCount} warning(s).` : 'Patch preview ready.' });
      } else {
        setExecutorState('blocked_conflict');
        setExecutorBanner({ type: 'warning', text: `Patch blocked at ${preview?.blocked_stage || 'validate'}. Resolve blockers before apply.` });
      }
      setExecutorStatus(`Preview: ${preview?.files?.length || 0} files, +${preview?.stats?.additions || 0} / -${preview?.stats?.deletions || 0}`);
    } catch (e) {
      setExecutorState('failed');
      setExecutorBanner({ type: 'error', text: e instanceof Error ? e.message : 'Patch preview failed' });
    }
  };

  const applyPatch = async () => {
    if (!patchPreview?.can_apply) return;
    setExecutorState('applying');
    setExecutorStatus('Applying patch...');
    setExecutorBanner(null);
    try {
      const res = await fetch(`${API_BASE}/executor/patch/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_text: patchRawText,
          response_format: executorResponseFormat,
          auto_extract: true,
          task: goal,
          mode,
          active_file: activeTab?.path || null,
        }),
      });
      const payload = await res.json();
      const apply: PatchApplyResult = {
        ...payload.apply,
        issues: payload.apply?.issues || [],
        warnings: payload.apply?.warnings || [],
        blockers: payload.apply?.blockers || [],
      };
      setPatchApplyResult(apply);
      setPatchPreview(apply);
      if (apply?.can_apply) {
        setExecutorState('applied');
        setExecutorStatus(`Applied ${apply.results?.length || 0} files`);
        setExecutorBanner({ type: 'success', text: `Applied patch. Snapshot ${apply.snapshot_id || 'not created'}. Verification passed.` });
        setPatchFlowOpen(true);
        setShowReloadPrompt(true);
        await openExecutor();
      } else {
        setExecutorState('failed');
        if (apply?.blocked_stage === 'verify') {
          const rollbackText = apply?.rollback?.attempted
            ? `Rollback ${apply?.rollback?.success ? 'succeeded' : 'failed'}.`
            : 'Rollback was not attempted.';
          setExecutorBanner({ type: 'error', text: `Verification failed after apply. ${rollbackText}` });
          setPatchFlowOpen(true);
        } else {
          setExecutorBanner({ type: 'error', text: `Patch apply blocked at ${apply?.blocked_stage || 'apply'}.` });
          setPatchFlowOpen(true);
        }
      }
    } catch (e) {
      setExecutorState('failed');
      setExecutorBanner({ type: 'error', text: e instanceof Error ? e.message : 'Patch apply failed' });
      setPatchFlowOpen(true);
    }
  };

  const autoFetchFromUncertainOutput = async () => {
    if (!uncertainOutputText.trim()) return;
    setExecutorState('loading_preview');
    setExecutorStatus('Auto-fetching executable payload...');
    setExecutorBanner(null);
    try {
      const res = await fetch(`${API_BASE}/executor/patch/autofetch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_text: uncertainOutputText,
          response_format: executorResponseFormat,
        }),
      });
      const payload = await res.json().catch(() => ({}));
      const fetched: AutoFetchResult | undefined = payload.autofetch;
      if (!res.ok || !fetched || !fetched.normalized_text) {
        setExecutorState('failed');
        setExecutorBanner({ type: 'error', text: 'Could not auto-fetch a valid payload.' });
        return;
      }
      setPatchRawText(fetched.normalized_text);
      if (fetched.detected_format === 'nexus_edits_v2' || fetched.detected_format === 'unified_diff') {
        setExecutorResponseFormat(fetched.detected_format);
      }
      setExecutorState('idle');
      setExecutorStatus('Auto-fetch complete. Review and preview the payload.');
      setExecutorBanner({ type: 'info', text: `Detected ${fetched.detected_format}.` });
    } catch (e) {
      setExecutorState('failed');
      setExecutorBanner({ type: 'error', text: e instanceof Error ? e.message : 'Auto-fetch failed' });
    }
  };

  const normalizeExecutablePayload = async () => {
    if (!patchRawText.trim()) return;
    setExecutorStatus('Normalizing payload...');
    try {
      const res = await fetch(`${API_BASE}/executor/patch/autofetch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_text: patchRawText, response_format: executorResponseFormat }),
      });
      const payload = await res.json().catch(() => ({}));
      const fetched: AutoFetchResult | undefined = payload.autofetch;
      if (!res.ok || !fetched?.normalized_text) {
        setExecutorBanner({ type: 'error', text: 'Payload normalization failed.' });
        return;
      }
      setPatchRawText(fetched.normalized_text);
      setExecutorBanner({ type: 'info', text: 'Payload normalized.' });
      setExecutorStatus('Normalization complete.');
    } catch (e) {
      setExecutorBanner({ type: 'error', text: e instanceof Error ? e.message : 'Payload normalization failed' });
    }
  };

  const copyDiagnostics = async () => {
    const payload = {
      preview: patchPreview,
      apply: patchApplyResult,
      status: executorStatus,
      banner: executorBanner,
      state: executorState,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setExecutorBanner({ type: 'success', text: 'Diagnostics copied to clipboard.' });
    } catch {
      setExecutorBanner({ type: 'error', text: 'Could not copy diagnostics.' });
    }
  };

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
              <button className="btn w-full flex items-center justify-center gap-2 executor-launch-btn" onClick={() => void openExecutor()}>
                <Terminal size={13} />
                <span className="font-bold">Executor</span>
              </button>
            </div>
          </div>
        )}

        {error && <div className="px-4 text-[10px] text-red-400">Error: {error}</div>}
      </div>

      <div className="panel-footer">
        <span>NEXUS CONTEXT ENGINE v1.0</span>
        <button className="footer-settings-btn" title="Runtime Settings" onClick={openRuntimeSettings} type="button">
          <Settings size={12} />
        </button>
      </div>

      {runtimeSettingsOpen && (
        <div className="intel-modal-backdrop">
          <div className="intel-modal settings-modal">
            <div className="intel-modal-header">
              <div className="intel-modal-header-main">
                <div className="intel-modal-title accent">
                  <Settings size={16} strokeWidth={2.5} />
                  <span>Runtime Settings</span>
                </div>
                <div className="intel-modal-subtitle">
                  <span>Configure deterministic runtime paths and inspect runtime source resolution.</span>
                </div>
              </div>
              <button className="intel-modal-close" onClick={() => setRuntimeSettingsOpen(false)} type="button">
                <X size={16} />
              </button>
            </div>

            <div className="intel-modal-body custom-scrollbar settings-modal-body">
              <section className="settings-section">
                <div className="settings-section-label">Runtime Category</div>
                <div className="settings-hero">
                  <div className="settings-hero-copy">
                    <div className="settings-hero-title">Language runtime registry</div>
                    <div className="settings-hero-subtitle">Keep Nexus self-contained now, and switch any runtime to a custom path later without changing the workflow.</div>
                  </div>
                  <div className="settings-hero-badge">Nexus first, custom optional</div>
                </div>

                <div className="settings-grid">
                <div className="settings-panel full-span">
                  <div className="settings-panel-title">Runtime Installer</div>
                  <div className="settings-panel-copy">Select runtimes and install in one click. Status is refreshed automatically whenever this panel opens.</div>
                  {runtimePreflight && (
                    <div className={`runtime-preflight-chip ${runtimePreflight.ok ? 'ok' : 'warn'}`}>
                      {runtimePreflight.ok
                        ? 'Ready: installer prerequisites look good.'
                        : `Needs attention: ${Object.values(runtimePreflight.checks).find((c) => !c.ok)?.message || 'Check preflight.'}`}
                    </div>
                  )}
                  <div className="runtime-installer-toolbar">
                    <button
                      className="runtime-installer-link"
                      onClick={() => { void fetchRuntimeCatalog(); void fetchRuntimePreflight(); }}
                      disabled={runtimeInstallerBusy}
                      type="button"
                    >
                      Refresh status
                    </button>
                    <div className="runtime-installer-toolbar-actions">
                      <button
                        className="runtime-installer-link subtle"
                        onClick={() => {
                          const missing = sortedRuntimeCatalog
                            .filter((item) => item.status !== 'installed')
                            .map((item) => item.key);
                          setSelectedRuntimeKeys(new Set(missing));
                        }}
                        disabled={runtimeInstallerBusy}
                        type="button"
                      >
                        Select missing
                      </button>
                      <button
                        className="runtime-installer-link subtle"
                        onClick={() => setSelectedRuntimeKeys(new Set())}
                        disabled={runtimeInstallerBusy || selectedRuntimeKeys.size === 0}
                        type="button"
                      >
                        Clear
                      </button>
                      <span>{selectedRuntimeKeys.size} selected</span>
                    </div>
                  </div>
                  <div className="runtime-installer-list">
                    {sortedRuntimeCatalog.map((item) => {
                      const checked = selectedRuntimeKeys.has(item.key);
                      const jobItem = runtimeInstallItems[item.key];
                      return (
                        <button
                          key={item.key}
                          className={`runtime-installer-row ${checked ? 'selected' : ''}`}
                          onClick={() => {
                            setSelectedRuntimeKeys((prev) => {
                              const next = new Set(prev);
                              if (next.has(item.key)) next.delete(item.key);
                              else next.add(item.key);
                              return next;
                            });
                          }}
                          type="button"
                        >
                          <span className={`runtime-installer-check ${checked ? 'on' : ''}`}>{checked ? '✓' : ''}</span>
                          <span className="runtime-installer-name">{item.label}</span>
                          <span className={`runtime-installer-status ${item.status}`}>{item.status}</span>
                          <span className="runtime-installer-version">v{item.version}</span>
                          {jobItem && <span className="runtime-installer-progress">{jobItem.progress}% · {jobItem.message}</span>}
                        </button>
                      );
                    })}
                  </div>
                  <div className="settings-actions compact">
                    <button
                      className="modal-btn modal-btn-cancel"
                      onClick={() => { void startRuntimeInstall('install', Array.from(selectedRuntimeKeys), false); }}
                      disabled={runtimeInstallerBusy || selectedRuntimeKeys.size === 0}
                      type="button"
                    >
                      Install Selected
                    </button>
                    <button
                      className="modal-btn modal-btn-cancel"
                      onClick={() => { void startRuntimeInstall('install', sortedRuntimeCatalog.map((r) => r.key), false); }}
                      disabled={runtimeInstallerBusy}
                      type="button"
                    >
                      Install All
                    </button>
                    <button
                      className="modal-btn modal-btn-confirm default"
                      onClick={() => { void startRuntimeInstall('update', Array.from(selectedRuntimeKeys), true); }}
                      disabled={runtimeInstallerBusy || selectedRuntimeKeys.size === 0}
                      type="button"
                    >
                      Update Selected
                    </button>
                  </div>
                </div>
                {[
                  { key: 'python', label: 'Python', placeholder: 'backend/runtimes/python/python.exe' },
                  { key: 'node', label: 'Node.js', placeholder: 'backend/runtimes/node/node.exe' },
                  { key: 'java', label: 'Java', placeholder: 'backend/runtimes/java/bin/java.exe' },
                  { key: 'gcc', label: 'C compiler', placeholder: 'backend/runtimes/gcc/bin/gcc.exe' },
                  { key: 'gpp', label: 'C++ compiler', placeholder: 'backend/runtimes/gcc/bin/g++.exe' },
                  { key: 'dotnet', label: 'C# compiler', placeholder: 'backend/runtimes/dotnet/sdk/csc.exe' },
                  { key: 'bash', label: 'Bash', placeholder: 'backend/runtimes/bash/usr/bin/bash.exe' },
                  { key: 'powershell', label: 'PowerShell', placeholder: 'backend/runtimes/powershell/pwsh.exe' },
                ].map((runtime) => (
                  <label className="runtime-setting-row" key={runtime.key}>
                    <div className="runtime-setting-meta">
                      <span className="runtime-setting-label">{runtime.label}</span>
                      <span className="runtime-setting-hint">
                        Executable path for this language
                        {runtimeDiagnostics[runtime.key] && (
                          <> · {runtimeDiagnostics[runtime.key].source}</>
                        )}
                      </span>
                      {runtimeDiagnostics[runtime.key]?.bundled_installed !== undefined && (
                        <span className="runtime-setting-hint">
                          {runtimeDiagnostics[runtime.key]?.bundled_installed ? 'Bundled installed' : 'Bundled missing'}
                        </span>
                      )}
                      {runtimeDiagnostics[runtime.key]?.resolved && (
                        <span className="runtime-setting-hint">{runtimeDiagnostics[runtime.key].resolved}</span>
                      )}
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
              </section>

              <div className="settings-section-divider" />

              <section className="settings-section">
                <div className="settings-section-label">Prompt Category</div>
                <div className="settings-hero">
                  <div className="settings-hero-copy">
                    <div className="settings-hero-title">Prompt preset library</div>
                    <div className="settings-hero-subtitle">Create, edit, and select reusable prompt styles. Default preset stays locked.</div>
                  </div>
                  <div className="settings-hero-badge">Prompt controls</div>
                </div>

                <div className="settings-grid prompt-settings-grid">
                  <div className="settings-panel full-span">
                    <div className="settings-panel-title">Prompt context behavior</div>
                    <div className="settings-panel-copy">Global controls for Context Preview behavior.</div>
                    <div className="runtime-setting-meta mt-2">
                      <span className="runtime-setting-label">Executor Response Format</span>
                      <span className="runtime-setting-hint">Choose the output format AI should return for surgical edits.</span>
                    </div>
                    <select
                      className="runtime-setting-input executor-format-select"
                      value={executorResponseFormat}
                      onChange={(e) => setExecutorResponseFormat(e.target.value as 'unified_diff' | 'nexus_edits_v2')}
                    >
                      <option value="unified_diff">Unified Diff (Legacy)</option>
                      <option value="nexus_edits_v2">Nexus JSON Edits v2 (Recommended)</option>
                    </select>
                    <label className="manual-add-toggle switchy">
                      <input
                        type="checkbox"
                        checked={allowPresetChangeInPreview}
                        onChange={(e) => setAllowPresetChangeInPreview(e.target.checked)}
                      />
                      <span className="switch-track"><span className="switch-thumb" /></span>
                      <span>Allow prompt preset switching in Context Preview</span>
                    </label>
                    <label className="manual-add-toggle switchy">
                      <input
                        type="checkbox"
                        checked={manualPromptAddEnabled}
                        onChange={(e) => setManualPromptAddEnabled(e.target.checked)}
                      />
                      <span className="switch-track"><span className="switch-thumb" /></span>
                      <span>Enable manual file addition in Context Preview</span>
                    </label>
                  </div>

                  <div className="settings-panel">
                    <div className="settings-panel-title">Available presets</div>
                    <div className="prompt-preset-admin-list">
                      {promptPresets.map((preset) => (
                        <button key={preset.id} className={`prompt-preset-admin-row ${selectedPromptPresetId === preset.id ? 'active' : ''}`} onClick={() => { setSelectedPromptPresetId(preset.id); setEditPresetName(preset.isDefault ? '' : preset.name); setEditPresetDescription(preset.isDefault ? '' : preset.description); setEditPresetTemplate(preset.isDefault ? '' : (preset.template || '')); }} type="button">
                          <span>{preset.name}</span>
                          {preset.isDefault ? <span className="prompt-preset-admin-tag">Default</span> : <span className="prompt-preset-admin-tag">Custom</span>}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="settings-panel">
                    <div className="settings-panel-title">Edit preset</div>
                    <div className="settings-panel-copy">Default preset is locked. Select a custom preset to refine it.</div>
                    <input className="runtime-setting-input" placeholder="Preset name" value={editPresetName} onChange={(e) => setEditPresetName(e.target.value)} disabled={selectedPreset?.isDefault} />
                    <textarea className="runtime-setting-input settings-textarea" placeholder="Preset description" value={editPresetDescription} onChange={(e) => setEditPresetDescription(e.target.value)} disabled={selectedPreset?.isDefault} />
                    <textarea className="runtime-setting-input settings-textarea prompt-template-input" placeholder="Preset template body (supports tokens like {{goal}}, {{mode}}, {{active_file}})" value={editPresetTemplate} onChange={(e) => setEditPresetTemplate(e.target.value)} disabled={selectedPreset?.isDefault} />
                    <div className="settings-actions compact">
                      <button className="modal-btn modal-btn-secondary" onClick={updatePromptPreset} disabled={selectedPreset?.isDefault} type="button">Update</button>
                      <button className="modal-btn modal-btn-confirm destructive" onClick={deletePromptPreset} disabled={selectedPreset?.isDefault} type="button">Delete</button>
                    </div>
                    {!selectedPreset?.isDefault && (
                      <pre className="prompt-template-preview">{editPresetTemplate || '(Template preview will appear here)'}</pre>
                    )}
                  </div>
                  <div className="settings-panel full-span">
                    <div className="settings-panel-title">Create preset</div>
                    <input className="runtime-setting-input" placeholder="New preset name" value={newPresetName} onChange={(e) => setNewPresetName(e.target.value)} />
                    <textarea className="runtime-setting-input settings-textarea" placeholder="New preset description" value={newPresetDescription} onChange={(e) => setNewPresetDescription(e.target.value)} />
                    <textarea className="runtime-setting-input settings-textarea prompt-template-input" placeholder="New preset template body (supports tokens like {{goal}}, {{mode}}, {{active_file}})" value={newPresetTemplate} onChange={(e) => setNewPresetTemplate(e.target.value)} />
                    <pre className="prompt-template-preview">{newPresetTemplate}</pre>
                    <div className="settings-actions compact">
                      <button className="modal-btn modal-btn-cancel" onClick={createPromptPreset} type="button">Create preset</button>
                    </div>
                  </div>
                </div>
              </section>
            </div>

            <div className="intel-modal-footer settings-modal-footer">
              {settingsFlash && (
                <div className={`settings-flash ${settingsFlash.type}`}>{settingsFlash.message}</div>
              )}
              <div className="settings-actions">
                <button
                  className="modal-btn modal-btn-cancel"
                  onClick={() => {
                    void fetchRuntimeSettings();
                    void fetchRuntimeDiagnostics();
                    void fetchPromptSettings();
                  }}
                  type="button"
                >
                  Reload
                </button>
                <button
                  className="modal-btn modal-btn-confirm default"
                  onClick={() => { void saveRuntimeSettings(); void savePromptSettings(promptPresets, selectedPromptPresetId); }}
                  disabled={settingsSaving}
                  type="button"
                >
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
              {(allowPresetChangeInPreview || manualPromptAddEnabled) && (
                <div className="prompt-preset-strip">
                  {allowPresetChangeInPreview && (
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
                  )}
                  {manualPromptAddEnabled && (
                    <div className="manual-add-row">
                      <div className="manual-add-panel">
                        <input
                          className="manual-add-search"
                          placeholder="Search by file name or path..."
                          value={manualPromptSearch}
                          onChange={(e) => setManualPromptSearch(e.target.value)}
                          onKeyDown={(e) => {
                            if (!manualPromptMatches.length) return;
                            if (e.key === 'ArrowDown') {
                              e.preventDefault();
                              setManualPromptFocusedIndex((prev) => Math.min(prev + 1, manualPromptMatches.length - 1));
                            } else if (e.key === 'ArrowUp') {
                              e.preventDefault();
                              setManualPromptFocusedIndex((prev) => Math.max(prev - 1, 0));
                            } else if (e.key === 'Enter') {
                              e.preventDefault();
                              const target = manualPromptMatches[manualPromptFocusedIndex];
                              if (target) {
                                if (selectedPaths.has(target.path)) removeManualPromptFile(target.path);
                                else addManualPromptFile(target.path);
                              }
                            }
                          }}
                          type="text"
                        />
                        <div className="manual-add-hint-row">
                          <span>{manualSelectedCount} file{manualSelectedCount !== 1 ? 's' : ''} selected</span>
                          <span>Enter to add or remove</span>
                        </div>
                        <div className="manual-add-results">
                          {manualPromptSearch.trim() ? (
                            manualPromptMatches.length ? (
                              manualPromptMatches.map((file, idx) => (
                                <button
                                  key={file.path}
                                  className={`manual-add-result ${selectedPaths.has(file.path) ? 'selected' : ''} ${manualPromptFocusedIndex === idx ? 'focused' : ''}`}
                                  onClick={() => {
                                    if (selectedPaths.has(file.path)) removeManualPromptFile(file.path);
                                    else addManualPromptFile(file.path);
                                  }}
                                  onMouseEnter={() => setManualPromptFocusedIndex(idx)}
                                  type="button"
                                >
                                  <span className="manual-add-result-name">{highlightMatch(file.name, manualPromptSearch)}</span>
                                  <span className="manual-add-result-path">{highlightMatch(file.path, manualPromptSearch)}</span>
                                  <span className="manual-add-result-action">
                                    {selectedPaths.has(file.path) ? 'Remove' : 'Add'}
                                  </span>
                                </button>
                              ))
                            ) : (
                              <div className="manual-add-empty">No matching files yet.</div>
                            )
                          ) : (
                            <div className="manual-add-empty">Search any workspace file to include it in prompt context.</div>
                          )}
                        </div>
                        {manualSelectedCount > 0 && (
                          <div className="manual-selected-tray">
                            {manualSelectedPreview.map((path) => (
                              <button
                                key={path}
                                className="manual-selected-chip"
                                onClick={() => removeManualPromptFile(path)}
                                type="button"
                                title={path}
                              >
                                <span>{path.split('/').pop()}</span>
                                <X size={11} />
                              </button>
                            ))}
                            {manualSelectedCount > manualSelectedPreview.length && (
                              <span className="manual-selected-more">+{manualSelectedCount - manualSelectedPreview.length} more</span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

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

      {executorOpen && (
        <div className="intel-modal-backdrop">
          <div className="intel-modal executor-modal">
            <div className="intel-modal-header">
              <div className="intel-modal-title accent">
                <Terminal size={16} />
                <span>Executor</span>
              </div>
              <button className="intel-modal-close" onClick={() => setExecutorOpen(false)} type="button">
                <X size={16} />
              </button>
            </div>
            <div className="intel-modal-body custom-scrollbar">
              <div className="panel-card mb-2 executor-statebar">
                <div className="text-xs opacity-80">Execution State: <strong className={`executor-state-pill state-${executorState}`}>{executorStateLabel[executorState]}</strong></div>
              </div>
              <div className="settings-actions compact">
                <button className={`modal-btn ${executorTab === 'patch' ? 'modal-btn-confirm default' : 'modal-btn-cancel'}`} onClick={() => setExecutorTab('patch')} type="button">Patch</button>
                <button className={`modal-btn ${executorTab === 'recover' ? 'modal-btn-confirm default' : 'modal-btn-cancel'}`} onClick={() => setExecutorTab('recover')} type="button">Recover</button>
              </div>
              {showReloadPrompt && (
                <div className="panel-card mt-2">
                  <div className="text-xs text-amber-300">Reload open tabs to synchronize editor buffers with restored disk state.</div>
                </div>
              )}
              {executorTab === 'patch' && (
                <div className="panel-card executor-card">
                  <div className="executor-section-head">
                    <span className="executor-kicker">Patch Workspace</span>
                    <span className="executor-subtle">Format: {executorResponseFormat === 'nexus_edits_v2' ? 'Nexus JSON Edits v2' : 'Unified Diff'}</span>
                  </div>
                  <div className="executor-label mt-2">Uncertain AI Output</div>
                  <textarea
                    className="runtime-setting-input settings-textarea mt-2"
                    value={uncertainOutputText}
                    onChange={(e) => setUncertainOutputText(e.target.value)}
                    placeholder="Paste full uncertain AI output (with prose/markdown)."
                  />
                  <div className="settings-actions compact mt-2">
                    <button className="modal-btn modal-btn-secondary" onClick={() => void autoFetchFromUncertainOutput()} disabled={!uncertainOutputText.trim() || executorState === 'applying'} type="button">Auto Fetch Payload</button>
                  </div>
                  <div className="executor-label mt-3">Executable Payload</div>
                  <textarea
                    className="runtime-setting-input settings-textarea mt-2"
                    value={patchRawText}
                    onChange={(e) => setPatchRawText(e.target.value)}
                    placeholder={executorResponseFormat === 'nexus_edits_v2' ? 'Paste nexus_edits_v2 JSON payload' : 'Paste unified diff here (---, +++, @@ ...)'}
                  />
                  <div className="settings-actions compact mt-2">
                    <button className="modal-btn modal-btn-confirm default" onClick={() => setPatchFlowOpen(true)} disabled={!patchRawText.trim()} type="button">Open Preview Bubble</button>
                    <button className="modal-btn modal-btn-secondary" onClick={() => void normalizeExecutablePayload()} disabled={!patchRawText.trim() || executorState === 'applying'} type="button">Normalize Payload</button>
                    <button className="modal-btn modal-btn-secondary" onClick={() => void copyDiagnostics()} type="button">Copy Diagnostics</button>
                    <button className="modal-btn modal-btn-cancel" onClick={() => { setPatchRawText(''); setUncertainOutputText(''); setPatchPreview(null); setPatchApplyResult(null); setExecutorStatus(''); setExecutorBanner(null); setExecutorState('idle'); }} type="button">Reset</button>
                    <button className="modal-btn modal-btn-cancel" onClick={() => void undoLast()} type="button">Undo Last</button>
                  </div>
                  {patchFlowOpen && (
                    <div className="panel-card executor-card mt-3">
                      <div className="executor-bubble-head">
                        <div className="text-xs opacity-80">Preview Bubble</div>
                        <button className="modal-btn modal-btn-secondary" onClick={() => setPatchFlowDetailsOpen((v) => !v)} type="button">
                          {patchFlowDetailsOpen ? 'Hide Details' : 'Show Details'}
                        </button>
                      </div>
                      <div className="settings-actions compact">
                        <button className="modal-btn modal-btn-confirm default" onClick={() => void previewPatch()} disabled={!patchRawText.trim() || executorState === 'applying'} type="button">Preview Patch</button>
                        <button className="modal-btn modal-btn-secondary" onClick={() => void normalizeExecutablePayload()} disabled={!patchRawText.trim() || executorState === 'applying'} type="button">Normalize</button>
                        <button className="modal-btn modal-btn-secondary" onClick={() => void applyPatch()} disabled={executorState === 'applying' || !patchPreview?.can_apply} type="button">Apply</button>
                        <button className="modal-btn modal-btn-cancel" onClick={() => setPatchFlowOpen(false)} type="button">Close</button>
                      </div>
                      {!patchPreview && <div className="text-xs opacity-70 mt-2">Run preview to inspect impacted files and blockers.</div>}
                      {patchPreview && (
                        <div className="executor-bubble-stack mt-2">
                          <div className="executor-badge-row">
                            <span className="executor-chip">Files <span className="executor-chip-sep">|</span> ({patchPreview.files.length})</span>
                            <span className="executor-chip">Lines <span className="executor-chip-sep">|</span> +{patchPreview.stats.additions} <span className="executor-chip-sep">|</span> -{patchPreview.stats.deletions}</span>
                          </div>
                        </div>
                      )}
                      {executorStatus && !executorStatus.startsWith('Preview:') && <div className="executor-badge-row mt-2"><span className="executor-chip">{executorStatus}</span></div>}
                      {executorBanner && <div className="executor-badge-row mt-2"><span className={`executor-chip ${executorBanner.type === 'error' ? 'chip-error' : executorBanner.type === 'warning' ? 'chip-warning' : executorBanner.type === 'success' ? 'chip-success' : ''}`}>{executorBanner.text}</span></div>}
                      {patchFlowDetailsOpen && patchPreview?.warnings?.length ? (
                        <div className="executor-bubble-stack mt-2">
                          <div className="executor-inline-title">Warnings</div>
                          <div className="executor-badge-row">
                            {patchPreview.warnings.map((item, idx) => (
                              <span key={`${item.reason}-${idx}`} className="executor-chip chip-warning">{item.reason}</span>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      {patchFlowDetailsOpen && patchPreview?.blockers?.length ? (
                        <div className="executor-bubble-stack mt-2">
                          <div className="executor-inline-title">Blockers</div>
                          <div className="executor-badge-row">
                            {patchPreview.blockers.map((item, idx) => (
                              <span key={`${item.reason}-${idx}`} className="executor-chip chip-error">{item.reason}</span>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      {patchFlowDetailsOpen && patchApplyResult && (
                        <div className="text-xs mt-2">
                          <div>{executorBanner?.text || 'Patch flow completed.'}</div>
                          <div>Verification: {patchApplyResult.verification_passed ? 'Passed' : 'Failed'}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              {executorTab === 'recover' && (
                <div className="panel-card executor-card">
                  <div className="executor-section-head">
                    <span className="executor-kicker">Recovery Workspace</span>
                    <span className="executor-subtle">Undo and restore from file/project history</span>
                  </div>
                  <div className="settings-actions compact mt-2">
                    <button className="modal-btn modal-btn-cancel" onClick={() => void undoLast()} type="button">Undo Last</button>
                  </div>
                  <div className="executor-label mt-3">File History</div>
                  {(fileHistory || []).map((entry) => (
                    <button key={entry.commit} className="runtime-installer-row executor-history-row" onClick={() => void previewCommit(entry.commit)} type="button">
                      <span className="runtime-installer-name executor-history-title">{entry.message}</span>
                      <span className="runtime-setting-hint executor-history-meta">
                        <span className="executor-history-badge">FILE</span>
                        <span>{new Date(entry.timestamp * 1000).toLocaleString()}</span>
                      </span>
                    </button>
                  ))}
                  {commitPreview.length > 0 && (
                    <pre className="prompt-template-preview">{commitPreview.join('\n')}</pre>
                  )}
                  <div className="executor-label mt-3">Project History</div>
                  {(projectHistory || []).map((entry) => (
                    <button key={entry.commit} className="runtime-installer-row executor-history-row" onClick={() => void previewProjectCommit(entry.commit)} type="button">
                      <span className="runtime-installer-name executor-history-title">{entry.message}</span>
                      <span className="runtime-setting-hint executor-history-meta">
                        <span className="executor-history-badge project">PROJECT</span>
                        <span>{new Date(entry.timestamp * 1000).toLocaleString()}</span>
                      </span>
                    </button>
                  ))}
                  <div className="settings-actions compact mt-2">
                    <button className="modal-btn modal-btn-confirm default" onClick={() => void restoreProjectFromSelected()} disabled={!selectedCommit || (restorePreview ? !restorePreview.can_apply : false) || executorState === 'applying'} type="button">Restore Project to Selected Commit</button>
                    <button className="modal-btn modal-btn-confirm default" onClick={() => void restoreActiveFile()} disabled={!selectedCommit || !activeTab || (restorePreview ? !restorePreview.can_apply : false)} type="button">Restore Active File</button>
                    <button className="modal-btn modal-btn-secondary" onClick={() => void forceRestoreActiveFile()} disabled={!selectedCommit || !activeTab || executorState === 'applying' || !forceAck || (restorePreview ? !restorePreview.can_force_apply : true)} type="button">Force Restore</button>
                  </div>
                  <label className="manual-add-toggle switchy mt-2">
                    <input type="checkbox" checked={forceAck} onChange={(e) => setForceAck(e.target.checked)} />
                    <span className="switch-track"><span className="switch-thumb" /></span>
                    <span>I understand force restore may overwrite unsaved context.</span>
                  </label>
                  {restorePreview && (
                    <div className="text-xs mt-2 executor-impact-wrap">
                      <div className="executor-impact-title">Impacted files: {restorePreview.impacted_files.length}</div>
                      {restorePreview.impacted_files.length > 0 && (
                        <div className="executor-badge-row mt-2">
                          {restorePreview.impacted_files.map((path) => (
                            <span key={path} className="executor-chip chip-impact">{path}</span>
                          ))}
                        </div>
                      )}
                      {restorePreview.conflicts.length > 0 && (
                        <div className="text-red-400 mt-2">Conflicts: {restorePreview.conflicts.map((c) => `${c.path} (${c.reason})`).join(', ')}</div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RightPanel;
