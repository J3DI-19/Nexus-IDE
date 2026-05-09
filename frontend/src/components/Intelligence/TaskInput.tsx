import React from 'react';
import { Sparkles, Wand2, X } from 'lucide-react';

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
  impactCandidates,
  hasRuntime = false
}) => {
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
      
      <select 
        className="task-mode-select"
        value={mode}
        onChange={(e) => setMode(e.target.value)}
        disabled={loading || disabled}
      >
        <option value="feature">Feature Development</option>
        <option value="bugfix">Bug Fix / Hotfix</option>
        <option value="refactor">Code Refactoring</option>
        <option value="architecture">Architectural Analysis</option>
      </select>
      
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
