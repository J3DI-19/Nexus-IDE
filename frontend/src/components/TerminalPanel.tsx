import React, { useEffect, useRef, useState } from 'react';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { ClipboardCopy, Minus, Square, Terminal as TerminalIcon, X } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000';
const WS_BASE = 'ws://127.0.0.1:8000';

type TerminalPanelProps = {
  sessionId: string | null;
  visible: boolean;
  onSessionReady: (sessionId: string | null) => void;
  onSessionKilled: () => void;
  onClose: () => void;
};

const TerminalPanel: React.FC<TerminalPanelProps> = ({ sessionId: existingSessionId, visible, onSessionReady, onSessionKilled, onClose }) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const sessionRef = useRef<string | null>(null);
  const initialSessionRef = useRef<string | null>(existingSessionId);
  const onSessionReadyRef = useRef(onSessionReady);
  const onSessionKilledRef = useRef(onSessionKilled);
  const [displaySessionId, setDisplaySessionId] = useState<string | null>(existingSessionId);
  const [shellName, setShellName] = useState<string>('terminal');
  const [terminalStatus, setTerminalStatus] = useState<'starting' | 'connected' | 'stopped'>('starting');
  const [hasSelection, setHasSelection] = useState(false);

  useEffect(() => {
    onSessionReadyRef.current = onSessionReady;
  }, [onSessionReady]);

  useEffect(() => {
    onSessionKilledRef.current = onSessionKilled;
  }, [onSessionKilled]);

  useEffect(() => {
    if (!visible || !fitRef.current || !terminalRef.current) return;
    window.requestAnimationFrame(() => {
      fitRef.current?.fit();
      terminalRef.current?.focus();
    });
  }, [visible]);

  useEffect(() => {
    let disposed = false;
    let closingIntentionally = false;

    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      lineHeight: 1.35,
      letterSpacing: 0.2,
      scrollback: 8000,
      allowTransparency: true,
      theme: {
        background: '#0b0f14',
        foreground: '#d7e1f0',
        cursor: '#8cc2ff',
        cursorAccent: '#0b0f14',
        selectionBackground: 'rgba(122, 162, 247, 0.28)',
        black: '#1f2937',
        red: '#f38ba8',
        green: '#a6e3a1',
        yellow: '#f9e2af',
        blue: '#89b4fa',
        magenta: '#cba6f7',
        cyan: '#94e2d5',
        white: '#cdd6f4',
        brightBlack: '#6b7280',
        brightRed: '#fda4af',
        brightGreen: '#86efac',
        brightYellow: '#fde68a',
        brightBlue: '#93c5fd',
        brightMagenta: '#d8b4fe',
        brightCyan: '#99f6e4',
        brightWhite: '#e5e7eb'
      }
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminalRef.current = terminal;
    fitRef.current = fitAddon;

    if (hostRef.current) {
      terminal.open(hostRef.current);
      fitAddon.fit();
    }

    terminal.attachCustomKeyEventHandler((event) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'c') {
        return false;
      }
      return true;
    });

    const refreshSelectionState = () => setHasSelection(terminal.hasSelection());
    terminal.onSelectionChange(refreshSelectionState);

    const resize = () => {
      fitAddon.fit();
      const session = sessionRef.current;
      if (session) {
        fetch(`${API_BASE}/terminal/resize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: session,
            cols: terminal.cols,
            rows: terminal.rows
          })
        }).catch(() => {});
      }
    };

    const resizeObserver = new ResizeObserver(resize);
    if (hostRef.current) resizeObserver.observe(hostRef.current);

    const start = async () => {
      try {
        const session = initialSessionRef.current
          ? { session_id: initialSessionRef.current, shell: 'terminal' }
          : await fetch(`${API_BASE}/terminal/session`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({})
            }).then(async (res) => {
              const data = await res.json();
              if (!res.ok) throw new Error(data.detail || 'Failed to create terminal session');
              return data;
            });
        if (disposed) return;

        sessionRef.current = session.session_id;
        setDisplaySessionId(session.session_id);
        setShellName(session.shell?.split(/[\\/]/).pop() || 'terminal');
        onSessionReadyRef.current(session.session_id);

        const socket = new WebSocket(`${WS_BASE}/terminal/ws/${session.session_id}`);
        socketRef.current = socket;
        socket.onmessage = (event) => terminal.write(event.data);
        socket.onerror = () => {
          if (!closingIntentionally) {
            terminal.writeln('\r\n[terminal websocket failed: install backend WebSocket support with pip install -r requirements.txt, then restart Nexus]');
            setTerminalStatus('stopped');
          }
        };
        socket.onclose = () => {
          if (!closingIntentionally) {
            terminal.writeln('\r\n[terminal disconnected]');
            setTerminalStatus('stopped');
          }
        };

        terminal.onData((data) => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'input', data }));
          }
        });

        socket.onopen = () => {
          setTerminalStatus('connected');
          resize();
          terminal.focus();
        };
      } catch (err: any) {
        terminal.writeln(`Failed to start terminal: ${err.message}`);
        onSessionReady(null);
        setTerminalStatus('stopped');
      }
    };

    start();

    const handleProvenance = (event: Event) => {
      const custom = event as CustomEvent<any>;
      const detail = custom.detail || {};
      const runtime = detail.runtime || 'runtime';
      const source = detail.source || 'unknown';
      const determinism = detail.determinism || 'unknown';
      const runMode = detail.run_mode || 'direct';
      const path = detail.path || 'unresolved';
      const version = detail.version || '';
      // Clear any partially-rendered prompt line before printing provenance block.
      terminal.write('\x1b[2K\r');
      terminal.writeln(`[runtime] ${String(runtime).toUpperCase()} | ${source} | ${determinism} | run=${runMode}`);
      terminal.writeln(`[runtime] path: ${path}`);
      if (version) terminal.writeln(`[runtime] version: ${version}`);
      terminal.writeln('');
    };
    window.addEventListener('nexus-run-provenance', handleProvenance);

    return () => {
      disposed = true;
      closingIntentionally = true;
      window.removeEventListener('nexus-run-provenance', handleProvenance);
      resizeObserver.disconnect();
      socketRef.current?.close();
      terminal.dispose();
    };
  }, []);

  const interrupt = async () => {
    if (!sessionRef.current) return;
    await fetch(`${API_BASE}/terminal/interrupt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionRef.current, data: '' })
    });
    terminalRef.current?.focus();
  };

  const copyConsole = async () => {
    const terminal = terminalRef.current;
    if (!terminal) return;
    const text = terminal.hasSelection()
      ? terminal.getSelection()
      : Array.from({ length: terminal.buffer.active.length }, (_, index) => {
          const line = terminal.buffer.active.getLine(index);
          return line ? line.translateToString(true) : '';
        }).join('\n').trimEnd();
    if (!text) return;

    await navigator.clipboard.writeText(text);
    terminal.focus();
  };

  const kill = async () => {
    if (!sessionRef.current) return;
    const killedSession = sessionRef.current;
    try {
      await fetch(`${API_BASE}/terminal/kill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: killedSession, data: '' })
      });
    } finally {
      socketRef.current?.close();
      sessionRef.current = null;
      setTerminalStatus('stopped');
      onSessionReadyRef.current(null);
      setDisplaySessionId(null);
      onSessionKilledRef.current();
    }
  };

  return (
    <div className={`run-console terminal-panel ${visible ? '' : 'minimized'}`}>
      <div className="run-console-header">
        <div className="run-console-title">
          <TerminalIcon size={14} />
          <span>Terminal</span>
          <span className={`terminal-status ${terminalStatus}`}>
            {terminalStatus === 'connected' ? 'Ready' : terminalStatus === 'starting' ? 'Starting' : 'Stopped'}
          </span>
          <span className="terminal-session-label">
            {displaySessionId ? 'Interactive PTY session' : 'Terminal session ended'}
          </span>
        </div>
        <div className="run-console-meta">
          <span className="terminal-shell-label">{displaySessionId ? shellName : 'No session'}</span>
          <button
            className="terminal-control copy"
            onClick={copyConsole}
            title={hasSelection ? 'Copy selected console text' : 'Copy console output'}
            type="button"
          >
            <ClipboardCopy size={12} />
          </button>
          <button
            className="terminal-control stop"
            onClick={interrupt}
            disabled={!displaySessionId}
            title="Stop running process (Ctrl+C)"
            type="button"
          >
            <Square size={12} />
          </button>
          <button
            className="terminal-control danger"
            onClick={kill}
            disabled={!displaySessionId}
            title="Kill terminal session"
            type="button"
          >
            <X size={13} />
          </button>
          <button className="terminal-control minimize" onClick={onClose} title="Hide terminal" type="button">
            <Minus size={14} />
          </button>
        </div>
      </div>
      <div className="terminal-frame">
        <div className="terminal-host" ref={hostRef} />
      </div>
    </div>
  );
};

export default TerminalPanel;
