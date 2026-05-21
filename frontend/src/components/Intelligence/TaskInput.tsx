import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Wand2, X } from 'lucide-react';

interface TaskInputProps {
  goal: string;
  setGoal: (goal: string) => void;
  mode: string;
  setMode: (mode: string) => void;
  loading: boolean;
  disabled: boolean;
  onRetrieve: () => void;
  onClear: () => void;
  candidates: any[];
  prompt: string;
  impactCandidates: any[];
  hasRuntime?: boolean;
}

const TaskInput: React.FC<TaskInputProps> = ({ 
  goal, 
  setGoal,
  mode,
  setMode,
  loading, 
  disabled, 
  onRetrieve,
  onClear,
  candidates,
  prompt,
  impactCandidates
}) => {
  const [modeOpen, setModeOpen] = useState(false);
  const [activeModeIndex, setActiveModeIndex] = useState(0);
  const modeMenuRef = useRef<HTMLDivElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const modeOptions = [
    { value: 'feature', label: 'Feature Development' },
    { value: 'bugfix', label: 'Bug Fix / Hotfix' },
    { value: 'refactor', label: 'Code Refactoring' },
    { value: 'architecture', label: 'Architectural Analysis' }
  ];

  const currentModeLabel = modeOptions.find((option) => option.value === mode)?.label || 'Select mode';
  const currentModeIndex = Math.max(
    0,
    modeOptions.findIndex((option) => option.value === mode)
  );

  const openModeMenu = () => {
    setActiveModeIndex(currentModeIndex);
    setModeOpen(true);
  };

  const beginCloseModeMenu = () => {
    if (!modeOpen) return;
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
    }
    setModeOpen(false);
    closeTimerRef.current = null;
  };

  const selectActiveMode = () => {
    const option = modeOptions[activeModeIndex];
    if (!option) return;
    setMode(option.value);
    beginCloseModeMenu();
  };

  const handleMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      beginCloseModeMenu();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveModeIndex((index) => Math.min(index + 1, modeOptions.length - 1));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveModeIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      selectActiveMode();
    }
  };

  useEffect(() => {
    if (!modeOpen) return;

    optionRefs.current[activeModeIndex]?.focus();

    const handleOutsideClick = (event: MouseEvent) => {
      if (modeMenuRef.current && !modeMenuRef.current.contains(event.target as Node)) {
        if (closeTimerRef.current) {
          window.clearTimeout(closeTimerRef.current);
          closeTimerRef.current = null;
        }
        setModeOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);

    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      if (closeTimerRef.current) {
        window.clearTimeout(closeTimerRef.current);
      }
    };
  }, [modeOpen, activeModeIndex, modeOptions, beginCloseModeMenu]);

  const hasTaskState = Boolean(
    goal.trim() ||
    candidates.length ||
    prompt ||
    impactCandidates.length
  );

  return (
    <div className="task-input-shell">
      <div className="flex items-center justify-between">
        <label className="task-field-label">Goal Mode</label>
        {hasTaskState && (
          <button
            className="task-clear-btn"
            onClick={onClear}
            disabled={loading}
            title="Clear workflow"
            type="button"
          >
            <X size={11} />
            <span>RESET</span>
          </button>
        )}
      </div>
      
      <div className="task-mode-select-wrap" ref={modeMenuRef}>
        <button
          className="task-mode-select"
          type="button"
          onClick={() => {
            if (loading || disabled) return;
            if (modeOpen) beginCloseModeMenu();
            else openModeMenu();
          }}
          onKeyDown={(e) => {
            if (loading || disabled) return;
            if (!modeOpen && (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ')) {
              e.preventDefault();
              openModeMenu();
            }
          }}
          disabled={loading || disabled}
          aria-haspopup="listbox"
          aria-expanded={modeOpen}
          aria-controls="task-mode-menu"
        >
          <span className="task-mode-select-label">{currentModeLabel}</span>
          <ChevronDown size={12} className={`task-mode-select-icon ${modeOpen ? 'open' : ''}`} />
        </button>

        {modeOpen && !loading && !disabled && (
          <div
            id="task-mode-menu"
            className="task-mode-menu open"
            role="listbox"
            aria-label="Goal mode"
            tabIndex={-1}
            onKeyDown={handleMenuKeyDown}
          >
            {modeOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`task-mode-option ${mode === option.value ? 'selected' : ''} ${modeOptions[activeModeIndex]?.value === option.value ? 'active' : ''}`}
                ref={(el) => {
                  optionRefs.current[modeOptions.findIndex((entry) => entry.value === option.value)] = el;
                }}
                onClick={() => {
                  setMode(option.value);
                  beginCloseModeMenu();
                }}
                onMouseDown={(e) => {
                  // Commit selection on press so mode doesn't get lost during focus/close transitions.
                  e.preventDefault();
                  setMode(option.value);
                  beginCloseModeMenu();
                }}
                role="option"
                aria-selected={mode === option.value}
                aria-current={modeOptions[activeModeIndex]?.value === option.value}
                onMouseEnter={() => setActiveModeIndex(modeOptions.findIndex((entry) => entry.value === option.value))}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>
      
      <label className="task-field-label">Implementation Goal</label>
      <textarea
        className="task-goal-input"
        placeholder="e.g. Add logging to user auth flow..."
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        disabled={loading || disabled}
      />
      <button
        className="btn btn-primary w-full task-submit-btn"
        onClick={onRetrieve}
        disabled={disabled || !goal.trim() || loading}
      >
        <Wand2 size={13} />
        {loading ? 'Analyzing...' : 'Retrieve Context'}
      </button>
    </div>
  );
};

export default TaskInput;
