import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Braces, FileText, Folder, LoaderCircle, PanelLeft, PanelRight, Play, Search, Terminal, X } from 'lucide-react';
import ConfirmDialog from './components/ui/ConfirmDialog';
import { buildTree, FileNode } from './utils/buildTree';

const Explorer = lazy(() => import('./components/Explorer'));
const Editor = lazy(() => import('./components/Editor'));
const RightPanel = lazy(() => import('./components/RightPanel'));
const TerminalPanel = lazy(() => import('./components/TerminalPanel'));

const API_BASE = 'http://127.0.0.1:8000';

export type Tab = {
  path: string;
  content: string;
  savedContent: string;
  isDirty: boolean;
};

type WorkspaceSymbol = {
  name: string;
  type: string;
  file: string;
  start_line: number;
  end_line: number;
  parent?: string | null;
};

type WorkspaceSearchMatch =
  | { type: 'file'; file: FileNode }
  | { type: 'symbol'; symbol: WorkspaceSymbol };

const App: React.FC = () => {
  const [tree, setTree] = useState<FileNode[]>([]);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  
  const [isProjectLoaded, setIsProjectLoaded] = useState<boolean>(false);
  const [pathInput, setPathInput] = useState<string>('');
  const [workspaceSearchQuery, setWorkspaceSearchQuery] = useState<string>('');
  const [workspaceSearchOpen, setWorkspaceSearchOpen] = useState<boolean>(false);
  const [workspaceSearchIndex, setWorkspaceSearchIndex] = useState<number>(0);
  const workspaceSearchResultRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [workspaceSymbols, setWorkspaceSymbols] = useState<WorkspaceSymbol[]>([]);
  const diagnosticsTimers = useRef<Record<string, number>>({});
  const diagnosticsSeq = useRef<Record<string, number>>({});

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [errorDialogOpen, setErrorDialogOpen] = useState<boolean>(false);
  const [errorDialogTitle, setErrorDialogTitle] = useState<string>('Runtime Error');
  const [errorDialogHint, setErrorDialogHint] = useState<string>('');
  const [errorDialogCopyText, setErrorDialogCopyText] = useState<string>('');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [consoleOpen, setConsoleOpen] = useState<boolean>(false);
  const [terminalSessionId, setTerminalSessionId] = useState<string | null>(null);
  const [pendingRunPath, setPendingRunPath] = useState<string | null>(null);
  const [terminalPanelKey, setTerminalPanelKey] = useState<number>(0);
  const pendingRunPathRef = useRef<string | null>(null);

  const [showExplorer, setShowExplorer] = useState(true);
  const [showRightPanel, setShowRightPanel] = useState(true);

  // Custom Confirmation state
  const [confirmConfig, setConfirmConfig] = useState<{
    isOpen: boolean;
    title: string;
    description: string;
    confirmText?: string;
    onConfirm: () => void;
    variant?: 'default' | 'destructive';
  }>({
    isOpen: false,
    title: '',
    description: '',
    onConfirm: () => {},
  });

  const confirm = (config: Omit<typeof confirmConfig, 'isOpen'>) => {
    setConfirmConfig({ ...config, isOpen: true });
  };

  const deriveErrorMeta = (message: string, fallback = 'Runtime Error') => {
    const text = message.toLowerCase();
    if (text.includes('c++ compiler')) {
      return {
        title: 'C++ Runtime Missing',
        hint: 'Drop a bundled MinGW / g++ toolchain into backend/runtimes/gcc/ to run C++ files inside Nexus.',
      };
    }
    if (text.includes('c compiler')) {
      return {
        title: 'C Runtime Missing',
        hint: 'Drop a bundled MinGW / gcc toolchain into backend/runtimes/gcc/ to run C files inside Nexus.',
      };
    }
    if (text.includes('python runtime')) {
      return {
        title: 'Python Runtime Missing',
        hint: 'Add a Nexus-packaged Python runtime to backend/runtimes/python/ so Python runs stay local.',
      };
    }
    if (text.includes('node runtime')) {
      return {
        title: 'Node.js Runtime Missing',
        hint: 'Add a Nexus-packaged Node runtime to backend/runtimes/node/ so JS files run without host installs.',
      };
    }
    if (text.includes('typescript support')) {
      return {
        title: 'TypeScript Runtime Missing',
        hint: 'Ship Node plus tsx or ts-node in backend/runtimes/node/node_modules/.bin/ for TypeScript runs.',
      };
    }
    if (text.includes('java runtime')) {
      return {
        title: 'Java Runtime Missing',
        hint: 'Add a bundled Java runtime to backend/runtimes/java/ so Java files run inside Nexus.',
      };
    }
    if (text.includes('c# compiler')) {
      return {
        title: 'C# Runtime Missing',
        hint: 'Add a bundled .NET SDK or C# compiler under backend/runtimes/dotnet/ for C# execution.',
      };
    }
    if (text.includes('bash runtime')) {
      return {
        title: 'Shell Runtime Missing',
        hint: 'Add a bundled Bash runtime to backend/runtimes/bash/ for shell script execution.',
      };
    }
    if (text.includes('powershell runtime')) {
      return {
        title: 'PowerShell Runtime Missing',
        hint: 'Add a bundled PowerShell runtime to backend/runtimes/powershell/ for script execution.',
      };
    }
    if (text.includes('no run configuration')) {
      return {
        title: 'Unsupported File Type',
        hint: 'This file type does not have a run target yet. Add a runtime mapping in Nexus to enable it.',
      };
    }
    return {
      title: fallback,
      hint: 'Nexus could not complete the requested action.',
    };
  };

  const showErrorDialog = (message: string, title = 'Runtime Error', hint = '', copyText = '') => {
    setError(message);
    setErrorDialogTitle(title);
    setErrorDialogHint(hint);
    setErrorDialogCopyText(copyText || message);
    setErrorDialogOpen(true);
  };

  const closeErrorDialog = () => {
    setErrorDialogOpen(false);
    setError(null);
    setErrorDialogHint('');
    setErrorDialogCopyText('');
  };

  const copyErrorDetails = async () => {
    const payload = [errorDialogTitle, errorDialogHint, errorDialogCopyText].filter(Boolean).join('\n\n');
    if (!payload) return;
    await navigator.clipboard.writeText(payload);
  };

  useEffect(() => {
    return () => {
      Object.values(diagnosticsTimers.current).forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  useEffect(() => {
    pendingRunPathRef.current = pendingRunPath;
  }, [pendingRunPath]);

  const fetchProject = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/scan`);
      if (!res.ok) throw new Error('Failed to scan project');
      const data = await res.json();
      setTree(buildTree(data.files));
      setError(null);
    } catch (err: any) {
      const meta = deriveErrorMeta(err.message, 'Workspace Scan Failed');
      showErrorDialog(err.message, meta.title, meta.hint);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenFolder = async () => {
    const root = pathInput.trim();
    if (!root) return;

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/set-root`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: root })
      });
      if (!res.ok) throw new Error("Failed to set root");
      
      setIsProjectLoaded(true);
      await fetchProject();
      await fetchWorkspaceSymbols();
    } catch (err: any) {
      const meta = deriveErrorMeta(err.message, 'Open Folder Failed');
      showErrorDialog(err.message, meta.title, meta.hint);
      setLoading(false);
    }
  };

  const handleCloseFolder = () => {
    Object.values(diagnosticsTimers.current).forEach((timer) => window.clearTimeout(timer));
    diagnosticsTimers.current = {};
    diagnosticsSeq.current = {};
    setIsProjectLoaded(false);
    setTree([]);
    setTabs([]);
    setActiveTabPath(null);
    setWorkspaceSearchQuery('');
    setWorkspaceSearchOpen(false);
    setWorkspaceSearchIndex(0);
    setWorkspaceSymbols([]);
    setError(null);
    setErrorDialogOpen(false);
  };

  const fetchWorkspaceSymbols = async () => {
    try {
      const res = await fetch(`${API_BASE}/context/symbols`);
      if (!res.ok) {
        setWorkspaceSymbols([]);
        return;
      }
      const data = await res.json();
      setWorkspaceSymbols(data.symbols || []);
    } catch (err) {
      console.error('[IDE] Symbol search unavailable:', err);
      setWorkspaceSymbols([]);
    }
  };

  const handleFileSelect = async (path: string) => {
    const existingTab = tabs.find(t => t.path === path);
    if (existingTab) {
      setActiveTabPath(path);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/file?path=${encodeURIComponent(path)}`);
      if (!res.ok) throw new Error(`Failed to load: ${res.status}`);
      const text = await res.text();

      const newTab = { path, content: text, savedContent: text, isDirty: false };
      setTabs(prev => [...prev, newTab]);
      setActiveTabPath(path);
    } catch (err: any) {
      console.error('[IDE] Error:', err);
      const meta = deriveErrorMeta(err.message, 'File Open Failed');
      showErrorDialog(err.message, meta.title, meta.hint, `Path: ${path}`);
    }
  };

  const handleCloseTab = (e: React.MouseEvent, path: string) => {
    e.stopPropagation();
    
    if (!Array.isArray(tabs)) return;
    const tabToClose = tabs.find(t => t.path === path);
    if (tabToClose?.isDirty) {
      confirm({
        title: `Unsaved Changes`,
        description: `You have unsaved changes in ${path.split('/').pop()}. Close anyway?`,
        confirmText: 'Close Anyway',
        variant: 'destructive',
        onConfirm: () => {
          const newTabs = tabs.filter(t => t.path !== path);
          setTabs(newTabs);
          if (activeTabPath === path) {
            setActiveTabPath(newTabs.length ? newTabs[newTabs.length - 1].path : null);
          }
        }
      });
      return;
    }

    const newTabs = tabs.filter(t => t.path !== path);
    setTabs(newTabs);

    if (activeTabPath === path) {
      setActiveTabPath(newTabs.length ? newTabs[newTabs.length - 1].path : null);
    }
  };

  const handleTabContentChange = (path: string, newContent: string) => {
    setTabs(prev => {
      if (!Array.isArray(prev)) return [];
      return prev.map(tab => {
        if (tab.path === path) {
          const isDirty = newContent !== tab.savedContent;
          return { ...tab, content: newContent, isDirty };
        }
        return tab;
      });
    });

    scheduleLiveDiagnostics(path, newContent);
  };

  const scheduleLiveDiagnostics = (path: string, content: string) => {
    if (diagnosticsTimers.current[path]) {
      window.clearTimeout(diagnosticsTimers.current[path]);
    }

    const seq = (diagnosticsSeq.current[path] || 0) + 1;
    diagnosticsSeq.current[path] = seq;
    const version = Date.now() + seq;

    diagnosticsTimers.current[path] = window.setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/file/diagnostics`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, content, version })
        });

        if (!res.ok) return;
        const data = await res.json();
        if (!data.applied || diagnosticsSeq.current[path] !== seq) return;
        window.dispatchEvent(new CustomEvent('nexus-runtime-updated', { detail: { path } }));
      } catch (err) {
        console.error('[Diagnostics] Live diagnostics failed', err);
      }
    }, 450);
  };

  const handleSaveFile = async () => {
    if (!tabs || !Array.isArray(tabs) || !activeTab || !activeTab.isDirty) return;
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/file/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: activeTab.path, content: activeTab.content })
      });
      if (!res.ok) throw new Error("Failed to save");
      window.dispatchEvent(new CustomEvent('nexus-runtime-updated', { detail: { path: activeTab.path } }));
      
      setTabs(prev => {
        if (!Array.isArray(prev)) return [];
        return prev.map(tab => {
          if (tab.path === activeTab.path) {
            return { ...tab, savedContent: tab.content, isDirty: false };
          }
          return tab;
        });
      });
    } catch (err: any) {
      const meta = deriveErrorMeta(err.message, 'Save Failed');
      showErrorDialog(err.message, meta.title, meta.hint, `Path: ${activeTab.path}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSaveFile();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTabPath, tabs]);

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!Array.isArray(tabs)) return;
      const hasDirtyTabs = tabs.some(t => t.isDirty);
      if (hasDirtyTabs) {
        e.preventDefault();
        e.returnValue = ''; // Required for Chrome
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [tabs]);

  const handleCreateFile = async (path: string, isFolder: boolean) => {
    try {
      setLoading(true);
      const endpoint = isFolder ? '/folder/create' : '/file/create';
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Creation failed");
      }
      await fetchProject();
      if (!isFolder) {
        handleFileSelect(path);
      }
    } catch (err: any) {
      alert(`Error creating: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRename = async (oldPath: string, newPath: string) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/file/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_path: oldPath, new_path: newPath })
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Rename failed");
      }
      
      // Update tabs
      setTabs(prev => {
        if (!Array.isArray(prev)) return [];
        return prev.map(tab => {
          if (tab.path === oldPath || tab.path.startsWith(oldPath + '/')) {
            return { ...tab, path: tab.path.replace(oldPath, newPath) };
          }
          return tab;
        });
      });

      if (activeTabPath === oldPath || (activeTabPath && activeTabPath.startsWith(oldPath + '/'))) {
        setActiveTabPath(prev => prev ? prev.replace(oldPath, newPath) : null);
      }

      await fetchProject();
    } catch (err: any) {
      alert(`Error renaming: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleMove = async (sourcePath: string, targetDirPath: string) => {
    try {
      setLoading(true);
      const fileName = sourcePath.split('/').filter(Boolean).pop();
      if (!fileName) throw new Error("Invalid source path");

      // Dest path is the target directory + the file name
      const destPath = targetDirPath ? `${targetDirPath}/${fileName}` : fileName;

      if (sourcePath === destPath) return; // No-op

      const res = await fetch(`${API_BASE}/file/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: sourcePath, dest_path: destPath })
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Move failed");
      }

      // Update tabs (remap paths for moved files or folders)
      setTabs(prev => {
        if (!Array.isArray(prev)) return [];
        return prev.map(tab => {
          if (tab.path === sourcePath || tab.path.startsWith(sourcePath + '/')) {
            return { ...tab, path: tab.path.replace(sourcePath, destPath) };
          }
          return tab;
        });
      });

      if (activeTabPath === sourcePath || (activeTabPath && activeTabPath.startsWith(sourcePath + '/'))) {
        setActiveTabPath(prev => prev ? prev.replace(sourcePath, destPath) : null);
      }

      await fetchProject();
    } catch (err: any) {
      alert(`Error moving: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (path: string) => {
    const findNode = (nodes: FileNode[], targetPath: string): FileNode | null => {
      for (const node of nodes) {
        if (node.path === targetPath) return node;
        if (node.children) {
          const found = findNode(node.children, targetPath);
          if (found) return found;
        }
      }
      return null;
    };

    const targetNode = findNode(tree, path);
    const isFolder = targetNode?.type === 'folder';
    const nodeName = targetNode?.name || path.split('/').filter(Boolean).pop();

    confirm({
      title: `Delete ${isFolder ? 'Folder' : 'File'}`,
      description: `Are you sure you want to delete "${nodeName}"? ${isFolder ? 'This will recursively delete all contents and subfolders.' : ''} This action cannot be undone.`,
      confirmText: 'Delete',
      variant: 'destructive',
      onConfirm: async () => {
        try {
          setLoading(true);
          const res = await fetch(`${API_BASE}/file/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
          });
          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || "Delete failed");
          }

          // Close relevant tabs
          setTabs(prev => {
            if (!Array.isArray(prev)) return [];
            return prev.filter(tab => tab.path !== path && !tab.path.startsWith(path + '/'));
          });

          // Update active tab path if it was deleted
          if (activeTabPath === path || (activeTabPath && activeTabPath.startsWith(path + '/'))) {
            setActiveTabPath(null);
          }

          await fetchProject();
        } catch (err: any) {
          alert(`Error deleting: ${err.message}`);
        } finally {
          setLoading(false);
        }
      }
    });
  };

  const activeTab = useMemo(() => {
    if (!Array.isArray(tabs)) return null;
    return tabs.find(t => t.path === activeTabPath) || null;
  }, [tabs, activeTabPath]);

  const saveTab = async (tab: Tab) => {
    const res = await fetch(`${API_BASE}/file/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: tab.path, content: tab.content })
    });
    if (!res.ok) throw new Error("Failed to save");
    window.dispatchEvent(new CustomEvent('nexus-runtime-updated', { detail: { path: tab.path } }));

    setTabs(prev => {
      if (!Array.isArray(prev)) return [];
      return prev.map(item =>
        item.path === tab.path
          ? { ...item, savedContent: tab.content, isDirty: false }
          : item
      );
    });
  };

  const sendRunToTerminal = async (sessionId: string, path: string) => {
    const res = await fetch(`${API_BASE}/terminal/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, path })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Run failed');
    if (data?.provenance) {
      window.dispatchEvent(new CustomEvent('nexus-run-provenance', { detail: data.provenance }));
    }
  };

  const handleTerminalSessionReady = useCallback((sessionId: string | null) => {
    setTerminalSessionId(sessionId);
    if (!sessionId && pendingRunPathRef.current) {
      setIsRunning(false);
    }
  }, []);

  const handleTerminalKilled = useCallback(() => {
    setTerminalSessionId(null);
    setPendingRunPath(null);
    setIsRunning(false);
    setConsoleOpen(false);
    setTerminalPanelKey((key) => key + 1);
  }, []);

  const shouldRenderTerminal = consoleOpen || Boolean(terminalSessionId) || Boolean(pendingRunPath);

  useEffect(() => {
    if (!terminalSessionId || !pendingRunPath) return;

    sendRunToTerminal(terminalSessionId, pendingRunPath)
      .catch((err: any) => {
        const meta = deriveErrorMeta(err.message, 'Run Failed');
        showErrorDialog(err.message, meta.title, meta.hint, pendingRunPathRef.current ? `Path: ${pendingRunPathRef.current}` : '');
      })
      .finally(() => {
        setPendingRunPath(null);
        setIsRunning(false);
      });
  }, [terminalSessionId, pendingRunPath]);

  const handleRunActiveFile = async () => {
    if (!activeTab || isRunning) return;

    try {
      setIsRunning(true);
      setConsoleOpen(true);

      if (activeTab.isDirty) {
        await saveTab(activeTab);
      }

      if (!terminalSessionId) {
        setPendingRunPath(activeTab.path);
        return;
      }

      await sendRunToTerminal(terminalSessionId, activeTab.path);
    } catch (err: any) {
      const meta = deriveErrorMeta(err.message, 'Run Failed');
      showErrorDialog(err.message, meta.title, meta.hint, pendingRunPathRef.current ? `Path: ${pendingRunPathRef.current}` : '');
      setPendingRunPath(null);
      setIsRunning(false);
    }
  };

  const dirtyPaths = useMemo(() => {
    if (!Array.isArray(tabs)) return new Set<string>();
    return new Set(tabs.filter(t => t.isDirty).map(t => t.path));
  }, [tabs]);

  const searchableFiles = useMemo(() => {
    const files: FileNode[] = [];

    const collectFiles = (nodes: FileNode[]) => {
      nodes.forEach((node) => {
        if (node.type === 'file') {
          files.push(node);
          return;
        }

        if (node.children) {
          collectFiles(node.children);
        }
      });
    };

    collectFiles(tree);
    return files;
  }, [tree]);

  const workspaceSearchMatches = useMemo<WorkspaceSearchMatch[]>(() => {
    const query = workspaceSearchQuery.trim().toLowerCase();
    if (!query) return [];

    const fileMatches: WorkspaceSearchMatch[] = searchableFiles
      .filter((file) => {
        const name = file.name.toLowerCase();
        const path = file.path.toLowerCase();
        return name.includes(query) || path.includes(query);
      })
      .map((file) => ({ type: 'file', file }));

    const symbolMatches: WorkspaceSearchMatch[] = workspaceSymbols
      .filter((symbol) => {
        const name = symbol.name.toLowerCase();
        const file = symbol.file.toLowerCase();
        const parent = symbol.parent?.toLowerCase() || '';
        return name.includes(query) || file.includes(query) || parent.includes(query);
      })
      .map((symbol) => ({ type: 'symbol', symbol }));

    return [...symbolMatches, ...fileMatches].slice(0, 12);
  }, [searchableFiles, workspaceSearchQuery, workspaceSymbols]);

  useEffect(() => {
    if (!workspaceSearchOpen) return;

    workspaceSearchResultRefs.current[workspaceSearchIndex]?.scrollIntoView({
      block: 'nearest'
    });
  }, [workspaceSearchIndex, workspaceSearchOpen]);

  const openWorkspaceSearchMatch = (match: WorkspaceSearchMatch) => {
    const path = match.type === 'symbol' ? match.symbol.file : match.file.path;
    handleFileSelect(path);
    setWorkspaceSearchOpen(false);
  };

  const handleWorkspaceSearchSubmit = () => {
    const match = workspaceSearchMatches[workspaceSearchIndex] || workspaceSearchMatches[0];

    if (match) {
      openWorkspaceSearchMatch(match);
    }
  };

  const handleWorkspaceSearchChange = (value: string) => {
    setWorkspaceSearchQuery(value);
    setWorkspaceSearchIndex(0);
    setWorkspaceSearchOpen(Boolean(value.trim()));
  };

  const clearWorkspaceSearch = () => {
    setWorkspaceSearchQuery('');
    setWorkspaceSearchOpen(false);
    setWorkspaceSearchIndex(0);
  };

  return (
    <div className="flex h-full w-full overflow-hidden">
      
      {/* Confirmation Dialog */}
      <ConfirmDialog
        isOpen={confirmConfig.isOpen}
        title={confirmConfig.title}
        description={confirmConfig.description}
        confirmText={confirmConfig.confirmText}
        variant={confirmConfig.variant}
        loading={loading}
        onConfirm={() => {
          confirmConfig.onConfirm();
          setConfirmConfig(prev => ({ ...prev, isOpen: false }));
        }}
        onCancel={() => setConfirmConfig(prev => ({ ...prev, isOpen: false }))}
      />
      <ConfirmDialog
        isOpen={errorDialogOpen}
        title={errorDialogTitle}
        description={[errorDialogHint, error].filter(Boolean).join('\n\n') || 'Something went wrong.'}
        confirmText="OK"
        hideCancel
        secondaryText="Copy Details"
        onSecondaryAction={copyErrorDetails}
        variant="destructive"
        onConfirm={closeErrorDialog}
        onCancel={closeErrorDialog}
      />
      {/* ===== LEFT PANEL ===== */}
      {showExplorer && (
        <Suspense fallback={<div className="sidebar flex flex-col h-full active-context"><div className="p-16 text-[10px] opacity-50 italic text-center">Loading...</div></div>}>
        <div className="sidebar flex flex-col h-full active-context">
          <div className="sidebar-header">

            {/* LEFT SPACER */}
            <div className="header-spacer" />

            {/* CENTER TITLE */}
            <div className="explorer-title">
              Explorer
            </div>

            {/* RIGHT BUTTON */}
            <div
              className="btn-icon"
              onClick={() => setShowExplorer(false)}
            >
              <PanelLeft size={16} />
            </div>

          </div>

          <div className="flex-1 min-h-0 flex flex-col">
            <div className="explorer-controls">
              {!isProjectLoaded ? (
                <>
                  <div className="explorer-input-wrap">
                    <input
                      className="explorer-input"
                      placeholder="Project path..."
                      value={pathInput}
                      onChange={(e) => setPathInput(e.target.value)}
                    />
                    {pathInput && (
                      <button
                        className="explorer-clear-btn"
                        onClick={() => setPathInput('')}
                      >
                        ×
                      </button>
                    )}
                  </div>
                  <button 
                    className="btn btn-primary w-full text-xs" 
                    onClick={handleOpenFolder}
                    disabled={!pathInput.trim()}
                  >
                    Open Folder
                  </button>
                </>
              ) : (
                <button className="btn w-full text-xs" onClick={handleCloseFolder}>
                  Close Folder
                </button>
              )}
            </div>

            {loading ? (
              <div className="p-16 text-[10px] opacity-50 italic text-center">Scanning...</div>
            ) : !isProjectLoaded ? (
              <div className="explorer-empty">
                <div className="empty-icon">
                  <Folder size={18} />
                </div>
                <div className="empty-title">No folder opened</div>
                <div className="empty-sub">
                  Open a project folder to begin
                </div>
              </div>
            ) : (
              <div className="flex-1 min-h-0 flex flex-col">
                <Explorer
                  tree={tree}
                  selectedPath={activeTabPath}
                  dirtyPaths={dirtyPaths}
                  onFileSelect={handleFileSelect}
                  onCreateFile={handleCreateFile}
                  onRename={handleRename}
                  onDelete={handleDelete}
                  onMove={handleMove}
                />
              </div>
            )}
          </div>
        </div>
        </Suspense>
      )}

      {/* ===== MAIN AREA ===== */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ===== HEADER ===== */}
        <div className="app-header">

          {/* LEFT */}
          <div className="header-left">
            {!showExplorer && (
              <div className="btn-icon" onClick={() => setShowExplorer(true)}>
                <PanelLeft size={16} />
              </div>
            )}

            <div className="logo-icon">{">_"}</div>
            <div className="logo-text">
              NEXUS <span className="accent">IDE</span>
            </div>
          </div>

          {/* CENTER SEARCH */}
          <div className="header-search-wrap">
            <div className="header-search">
              <Search size={13} className="search-leading-icon" />
              <input
                className="search-input"
                placeholder="Search files or symbols..."
                value={workspaceSearchQuery}
                onFocus={() => {
                  if (isProjectLoaded) {
                    fetchWorkspaceSymbols();
                  }
                  if (workspaceSearchQuery.trim()) {
                    setWorkspaceSearchOpen(true);
                  }
                }}
                onBlur={() => setWorkspaceSearchOpen(false)}
                onChange={(e) => handleWorkspaceSearchChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleWorkspaceSearchSubmit();
                  } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setWorkspaceSearchOpen(workspaceSearchMatches.length > 0);
                    setWorkspaceSearchIndex((index) =>
                      workspaceSearchMatches.length
                        ? (index + 1) % workspaceSearchMatches.length
                        : 0
                    );
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setWorkspaceSearchOpen(workspaceSearchMatches.length > 0);
                    setWorkspaceSearchIndex((index) =>
                      workspaceSearchMatches.length
                        ? (index - 1 + workspaceSearchMatches.length) % workspaceSearchMatches.length
                        : 0
                    );
                  } else if (e.key === 'Escape') {
                    setWorkspaceSearchOpen(false);
                  }
                }}
              />
              {workspaceSearchQuery && (
                <button
                  className="search-clear-btn"
                  onClick={clearWorkspaceSearch}
                  title="Clear workspace search"
                  type="button"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {workspaceSearchOpen && workspaceSearchQuery.trim() && (
              <div
                className="workspace-search-preview"
                onMouseDown={(e) => e.preventDefault()}
              >
                <div className="workspace-search-preview-header">
                  <span>Workspace matches</span>
                  <span>{workspaceSearchMatches.length}</span>
                </div>

                {workspaceSearchMatches.length > 0 ? (
                  <div className="workspace-search-results">
                    {workspaceSearchMatches.map((match, index) => {
                      const isSymbol = match.type === 'symbol';
                      const name = isSymbol ? match.symbol.name : match.file.name;
                      const path = isSymbol ? match.symbol.file : match.file.path;
                      const meta = isSymbol
                        ? `${match.symbol.type}${match.symbol.parent ? ` in ${match.symbol.parent}` : ''} · line ${match.symbol.start_line}`
                        : 'file';

                      return (
                      <button
                        key={`${match.type}:${isSymbol ? `${match.symbol.file}:${match.symbol.name}:${match.symbol.start_line}` : match.file.path}`}
                        ref={(element) => {
                          workspaceSearchResultRefs.current[index] = element;
                        }}
                        className={`workspace-search-result ${index === workspaceSearchIndex ? 'active' : ''}`}
                        onMouseEnter={() => setWorkspaceSearchIndex(index)}
                        onClick={() => openWorkspaceSearchMatch(match)}
                        type="button"
                      >
                        {isSymbol ? (
                          <Braces size={13} className="workspace-search-result-icon symbol" />
                        ) : (
                          <FileText size={13} className="workspace-search-result-icon" />
                        )}
                        <span className="workspace-search-result-main">
                          <span className="workspace-search-result-name">
                            {name}
                            <span className="workspace-search-result-kind">{meta}</span>
                          </span>
                          <span className="workspace-search-result-path">{path}</span>
                        </span>
                      </button>
                    )})}
                  </div>
                ) : (
                  <div className="workspace-search-empty">
                    No file matches yet
                  </div>
                )}
              </div>
            )}
          </div>

          {/* RIGHT */}
          <div className="header-right">
            <button
              className={`run-button ${isRunning ? 'running' : ''}`}
              onClick={handleRunActiveFile}
              disabled={!activeTab || isRunning}
              title={activeTab ? `Run ${activeTab.path.split('/').pop()}` : 'Open a file to run'}
              type="button"
            >
              {isRunning ? <LoaderCircle size={13} className="run-spinner" /> : <Play size={13} fill="currentColor" />}
              <span>{isRunning ? 'Running' : 'Run'}</span>
            </button>
            <button
              className={`terminal-toggle ${consoleOpen ? 'active' : ''} ${terminalSessionId ? 'connected' : ''}`}
              onClick={() => setConsoleOpen(open => !open)}
              title={consoleOpen ? 'Terminal visible' : 'Show terminal'}
              type="button"
            >
              <Terminal size={16} />
            </button>
            {!showRightPanel && (
              <div className="btn-icon" onClick={() => setShowRightPanel(true)}>
                <PanelRight size={16} />
              </div>
            )}
          </div>
        </div>

        {/* ===== EDITOR ===== */}
        <div className="flex-1 overflow-hidden editor-workbench">
          <Suspense fallback={<div className="p-16 text-[10px] opacity-50 italic text-center">Loading editor...</div>}>
            <Editor
              activeTab={activeTab}
              tabs={tabs}
              onSelectTab={setActiveTabPath}
              onCloseTab={handleCloseTab}
              onContentChange={handleTabContentChange}
            />
            {shouldRenderTerminal && (
              <TerminalPanel
                key={terminalPanelKey}
                sessionId={terminalSessionId}
                visible={consoleOpen}
                onSessionReady={handleTerminalSessionReady}
                onSessionKilled={handleTerminalKilled}
                onClose={() => setConsoleOpen(false)}
              />
            )}
          </Suspense>
        </div>
      </div>

      {/* ===== RIGHT PANEL ===== */}
      {showRightPanel && (
        <Suspense fallback={<div className="right-panel flex flex-col"><div className="p-16 text-[10px] opacity-50 italic text-center">Loading intelligence...</div></div>}>
        <div className="right-panel flex flex-col">
          <div className="sidebar-header">

            {/* LEFT SPACER */}
            <div className="header-spacer" />

            {/* CENTER TITLE */}
            <div className="explorer-title">
              Intelligence
            </div>

            {/* RIGHT BUTTON */}
            <div className="btn-icon" onClick={() => setShowRightPanel(false)}>
              <PanelRight size={16} />
            </div>

          </div>

          <RightPanel 
            activeTab={activeTab} 
            isProjectLoaded={isProjectLoaded} 
            onFileSelect={handleFileSelect}
            workspaceFiles={searchableFiles.map((file) => ({ path: file.path, name: file.name }))}
            dirtyPaths={dirtyPaths}
          />
        </div>
        </Suspense>
      )}

    </div>
  );
};

export default App;
