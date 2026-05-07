import React from 'react';
import { ChevronDown, ChevronRight, ShieldCheck, Zap, CheckCircle2, Circle } from 'lucide-react';

interface ScoreBreakdown {
  factor: string;
  points: number;
  reason: string;
}

interface Candidate {
  file_metadata: {
    rel_path: string;
    classification: string;
    language: string;
  };
  score: number;
  score_breakdown: ScoreBreakdown[];
  matched_symbols: string[];
  matched_artifacts: string[];
}

interface CandidateListProps {
  candidates: Candidate[];
  selectedPaths: Set<string>;
  toggleSelection: (path: string) => void;
  expandedCand: string | null;
  setExpandedCand: (path: string | null) => void;
  onAssemble: () => void;
  loading: boolean;
}

const CandidateList: React.FC<CandidateListProps> = ({
  candidates,
  selectedPaths,
  toggleSelection,
  expandedCand,
  setExpandedCand,
  onAssemble,
  loading
}) => {
  return (
    <div className="panel-section border-t border-white/5 pt-4">
      <div className="panel-title mb-2">
        <ShieldCheck size={13} />
        <span>Review Retrieved Context</span>
        <span className="ml-auto text-[10px] opacity-50">{candidates.length} found</span>
      </div>

      <div className="candidate-list">
        {candidates.map((cand) => {
          const path = cand.file_metadata.rel_path;
          const isSelected = selectedPaths.has(path);
          const isExpanded = expandedCand === path;

          return (
            <div
              key={path} 
              className={`context-card candidate-card ${isSelected ? 'selected' : ''}`}
            >
              <div className="candidate-card-main">
                <button
                  className={`candidate-toggle ${isSelected ? 'selected' : ''}`}
                  onClick={() => toggleSelection(path)}
                  title={isSelected ? 'Remove from prompt context' : 'Add to prompt context'}
                  type="button"
                >
                  {isSelected ? <CheckCircle2 size={14} className="text-blue-400" /> : <Circle size={14} className="opacity-30" />}
                </button>
                
                <button
                  className="candidate-info"
                  onClick={() => setExpandedCand(isExpanded ? null : path)}
                  type="button"
                >
                  <span className="candidate-title-row">
                    <span className="candidate-name">{path.split('/').pop()}</span>
                    <span className="candidate-badge">
                      {cand.file_metadata.language}
                    </span>
                    <span className="candidate-badge accent">
                      {cand.file_metadata.classification}
                    </span>
                  </span>
                  <span className="candidate-path">{path}</span>
                </button>

                <button
                  className="candidate-expand"
                  onClick={() => setExpandedCand(isExpanded ? null : path)}
                  title={isExpanded ? 'Hide details' : 'Show details'}
                  type="button"
                >
                  {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>

                <div className="candidate-score">
                  {Math.round(cand.score)}
                </div>
              </div>

              {isExpanded && (
                <div className="candidate-details">
                  <div className="candidate-detail-section">
                    <div className="candidate-detail-heading">Score reasoning</div>
                    <div className="candidate-score-list">
                      {cand.score_breakdown.map((s, i) => (
                        <div key={i} className="candidate-score-row">
                          <span>{s.reason}</span>
                          <strong>+{s.points}</strong>
                        </div>
                      ))}
                    </div>
                  </div>

                  {cand.matched_artifacts && cand.matched_artifacts.length > 0 && (
                    <div className="candidate-detail-section">
                      <div className="candidate-detail-heading">Framework relevance</div>
                      <div className="candidate-chip-list">
                        {Array.from(new Set(cand.matched_artifacts)).map(a => (
                          <span key={a as string} className="candidate-chip blue">{a as React.ReactNode}</span>
                        ))}
                      </div>
                    </div>
                  )}

                  {cand.matched_symbols && cand.matched_symbols.length > 0 && (
                    <div className="candidate-detail-section">
                      <div className="candidate-detail-heading">Structure and symbols</div>
                      <div className="candidate-chip-list">
                        {cand.matched_symbols.slice(0, 10).map(s => (
                          <span key={s} className={`candidate-chip ${s.startsWith('#') || s.startsWith('__') ? 'yellow' : s.startsWith('.') ? 'blue' : ''}`}>
                            {s}
                          </span>
                        ))}
                        {cand.matched_symbols.length > 10 && <span className="candidate-chip muted">+{cand.matched_symbols.length - 10} more</span>}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button
        className="btn btn-primary w-full mt-4 flex items-center justify-center gap-2"
        onClick={onAssemble}
        disabled={loading || selectedPaths.size === 0}
      >
        <Zap size={14} />
        Assemble Prompt
      </button>
    </div>
  );
};

export default CandidateList;
