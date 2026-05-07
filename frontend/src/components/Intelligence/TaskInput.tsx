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
}

const TaskInput: React.FC<TaskInputProps> = ({ 
  goal, 
  setGoal,
  mode,
  setMode,
  loading, 
  disabled, 
  onRetrieve,
  onClear
}) => {
  const hasTaskState = Boolean(goal.trim()) || mode !== 'feature';

  return (
    <div className="panel-section">
      <div className="panel-title accent">
        <Sparkles size={13} />
        <span>Context Workflow</span>
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
          {hasTaskState && (
            <button
              className="task-clear-btn"
              onClick={onClear}
              disabled={loading}
              title="Clear task"
              type="button"
            >
              <X size={11} />
              Clear
            </button>
          )}
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
      </div>
    </div>
  );
};

export default TaskInput;
