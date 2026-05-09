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
    <div className="panel-section">
      <div className="task-input-header">
        <div className="task-input-title">
          Context Workflow
        </div>
        {hasTaskState && (
          <button
            className="task-clear-btn"
            onClick={onClear}
            disabled={loading}
            title="Clear workflow"
            type="button"
          >
            <X size={12} />
            <span>Clear</span>
          </button>
        )}
      </div>

      <div className="task-input-shell">
        <label className="task-field-label">Mode</label>
        <select 
          className="task-mode-select"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          disabled={loading || disabled}
        >
          <option value="feature">Feature</option>
          <option value="bugfix">Bugfix</option>
          <option value="refactor">Refactor</option>
          <option value="architecture">Analysis</option>
        </select>
        
        <div className="task-label-row">
          <label className="task-field-label">Task</label>
        </div>
        <textarea
          className="task-goal-input"
          placeholder="Describe your modification goal..."
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
          {loading ? 'Retrieving...' : 'Retrieve Context'}
        </button>

        {hasRuntime && (
          <div className="mt-2 flex items-center justify-center gap-1.5 opacity-40 text-[9px] italic">
            <Sparkles size={10} />
            <span>Execution-aware ranking active</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default TaskInput;
