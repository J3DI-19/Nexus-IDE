import React, { useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Circle, Route, Zap } from 'lucide-react';

interface ScoreBreakdown {
  factor: string;
  points: number;
  reason: string;
  path?: string[];
}

interface CodeSlice {
  content: string;
  start_line: number;
  end_line: number;
  reason: string;
  expansion_type: string;
  anchor_symbol?: string;
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
  relationship_path: string[];
  slices?: CodeSlice[];
}

interface CandidateListProps {
  candidates: Candidate[];
  selectedPaths: Set<string>;
  fullFileOverrides: Set<string>;
  sliceSelection: Record<string, Set<number>>;
  autoSliceSelection: Record<string, Set<number>>;
  toggleSelection: (path: string) => void;
  toggleSlice: (path: string, index: number) => void;
  toggleFullFile: (path: string) => void;
  selectAllSlices: (path: string) => void;
  expandedCand: string | null;
  setExpandedCand: (path: string | null) => void;
  onAssemble: () => void;
  loading: boolean;
  mode?: string;
}

const AUTO_SELECT_THRESHOLD = 40;

const formatPoints = (points: number) => `${points > 0 ? '+' : ''}${Math.round(points)} pts`;

const getPathType = (breakdown: ScoreBreakdown[] = []) => {
  const pathFactor = breakdown.find((item) => item.path?.length)?.factor.toLowerCase() || '';
  if (pathFactor.includes('runtime') || pathFactor.includes('execution')) return 'Runtime chain';
  if (pathFactor.includes('call')) return 'Call chain';
  if (pathFactor.includes('reverse')) return 'Reverse dependency';
  if (pathFactor.includes('dependency') || pathFactor.includes('import')) return 'Direct dependency';
  return 'Relationship path';
};

const ScoreBreakdownPanel: React.FC<{ breakdown: ScoreBreakdown[]; score: number; mode?: string }> = ({
  breakdown,
  score,
  mode
}) => {
  const groups = useMemo(() => {
    const sorted = [...(breakdown || [])].sort((a, b) => b.points - a.points);
    return {
      primary: sorted.filter((item) => item.points >= 35),
      supporting: sorted.filter((item) => item.points >= 0 && item.points < 35),
      penalties: sorted.filter((item) => item.points < 0)
    };
  }, [breakdown]);

  const renderGroup = (label: string, items: ScoreBreakdown[]) => {
    if (!items.length) return null;

    return (
      <div className="score-breakdown-group">
        <div className="score-breakdown-group-title">{label}</div>
        <div className="score-breakdown-items">
          {items.map((item, index) => (
            <div className={`score-breakdown-row ${item.points < 0 ? 'penalty' : ''}`} key={`${item.factor}-${index}`}>
              <span className="score-breakdown-points">{formatPoints(item.points)}</span>
              <div className="score-breakdown-copy">
                <span className="score-breakdown-factor">{item.factor}</span>
                <span className="score-breakdown-reason">{item.reason}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="score-breakdown-panel">
      <div className="score-breakdown-summary">
        <span className="score-breakdown-total">{Math.round(score)} pts</span>
        <span className="score-breakdown-threshold">
          Auto-selects at {AUTO_SELECT_THRESHOLD}+ pts in {mode || 'feature'} mode
        </span>
      </div>
      {renderGroup('Primary Signals', groups.primary)}
      {renderGroup('Supporting Signals', groups.supporting)}
      {renderGroup('Penalties', groups.penalties)}
    </div>
  );
};

const RelationshipPath: React.FC<{ path: string[]; breakdown?: ScoreBreakdown[]; expanded?: boolean }> = ({
  path,
  breakdown = [],
  expanded = false
}) => {
  if (!path || path.length === 0) return null;

  const pathType = getPathType(breakdown);
  if (!expanded) {
    return (
      <div className="relationship-path compact-dependency" title={path.join(' -> ')}>
        <div className="relationship-path-label">
          <Route size={10} />
          <span>{pathType}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="relationship-path expanded">
      <div className="relationship-path-label">
        <Route size={10} />
        <span>{pathType}</span>
      </div>
      <div className="relationship-path-chain">
        {path.map((node, i) => (
          <React.Fragment key={`${node}-${i}`}>
            <span className={`chain-node ${i === path.length - 1 ? 'active' : ''}`} title={path[i]}>
              {node.includes(':') ? node.split(':').pop() || node : node.split('/').pop() || node}
            </span>
            {i < path.length - 1 && <ChevronRight size={8} className="opacity-30" />}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export const ConnectionChain: React.FC<{ path: string[] }> = ({ path }) => (
  <RelationshipPath path={path} />
);

const SliceCard: React.FC<{
  slice: CodeSlice;
  isSelected: boolean;
  isAuto: boolean;
  onToggle: () => void;
}> = ({ slice, isSelected, isAuto, onToggle }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const isManuallySelected = isSelected && !isAuto;
  const isManuallyExcluded = !isSelected && isAuto;
  const isUnselected = !isSelected && !isAuto;
  const cardClass = [
    'slice-card',
    slice.expansion_type || 'proximity',
    isManuallySelected ? 'manually-selected' : '',
    isManuallyExcluded ? 'manually-excluded' : '',
    isUnselected ? 'unselected optional-slice' : ''
  ].filter(Boolean).join(' ');
  const badgeClass = `slice-badge badge-${slice.expansion_type || 'proximity'}`;
  const selectionLabel = isManuallySelected
    ? 'Manually selected'
    : isManuallyExcluded
      ? 'Auto suggestion removed'
      : isAuto
        ? 'Auto selected'
        : 'Optional';

  return (
    <div className={cardClass} style={{ transform: isSelected ? 'translateY(0px)' : 'translateY(1px)' }}>
      <div className="slice-card-header">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <button
            className={`slice-toggle ${isSelected ? 'selected' : ''} ${isManuallySelected ? 'manual' : ''}`}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            type="button"
            title={selectionLabel}
          >
            {isSelected ? <CheckCircle2 size={14} /> : <Circle size={14} />}
          </button>

          <div className="slice-anchor-symbol truncate">
            {slice.anchor_symbol || 'logic_fragment'}()
          </div>
        </div>

        <div className="slice-card-meta">
          <span className={badgeClass}>{slice.expansion_type || 'proximity'}</span>
          <span className="slice-line-range">L{slice.start_line}-L{slice.end_line}</span>
        </div>
      </div>

      <div className="slice-code-container" onClick={() => setIsExpanded(!isExpanded)}>
        <pre className={`slice-code-preview ${isExpanded ? 'expanded' : ''}`}>
          <code>{slice.content}</code>
        </pre>
        {!isExpanded && (
          <div className="slice-view-code">
            View Code
          </div>
        )}
      </div>

      <div className="slice-reason-row">
        <span className="slice-reason">Reason: {slice.reason}</span>
        <span className={`slice-selection-state ${isManuallySelected ? 'manual' : isManuallyExcluded ? 'excluded' : ''}`}>
          {selectionLabel}
        </span>
      </div>
    </div>
  );
};

const FileSelectionControls: React.FC<{
  path: string;
  isFullFile: boolean;
  allSlicesSelected: boolean;
  loading: boolean;
  selectAllSlices: (path: string) => void;
  toggleFullFile: (path: string) => void;
}> = ({ path, isFullFile, allSlicesSelected, loading, selectAllSlices, toggleFullFile }) => (
  <div className="file-selection-controls">
    <button
      className={`full-file-toggle ${allSlicesSelected ? 'active' : ''}`}
      onClick={(e) => { e.stopPropagation(); selectAllSlices(path); }}
      disabled={loading}
      type="button"
    >
      Include All Fragments
    </button>
    <button
      className={`full-file-toggle ${isFullFile ? 'active' : ''}`}
      onClick={(e) => { e.stopPropagation(); toggleFullFile(path); }}
      disabled={loading}
      type="button"
    >
      {isFullFile ? 'Full File Enabled' : 'Include Full File'}
    </button>
  </div>
);

const CandidateList: React.FC<CandidateListProps> = ({
  candidates,
  selectedPaths,
  fullFileOverrides,
  sliceSelection,
  autoSliceSelection,
  toggleSelection,
  toggleSlice,
  toggleFullFile,
  selectAllSlices,
  expandedCand,
  setExpandedCand,
  loading,
  mode
}) => {
  return (
    <div className="candidate-list-root">
      <div className="candidate-list custom-scrollbar space-y-3">
        {candidates.map((cand) => {
          const path = cand.file_metadata.rel_path;
          const isFileSelected = selectedPaths.has(path);
          const isFullFile = fullFileOverrides.has(path);
          const activeSlicesCount = sliceSelection[path]?.size || 0;
          const totalSlices = cand.slices?.length || 0;
          const allSlicesSelected = totalSlices > 0 && activeSlicesCount === totalSlices;
          const isExpanded = expandedCand === path;
          const isEmpty = isFileSelected && activeSlicesCount === 0 && !isFullFile;
          const autoSelected = cand.score >= AUTO_SELECT_THRESHOLD;

          return (
            <div
              key={path}
              className={`file-bubble ${isFileSelected ? 'selected' : ''} ${isFullFile ? 'full-file-override' : ''} ${isEmpty ? 'is-empty' : ''}`}
            >
              <div
                className="file-bubble-header"
                onClick={() => setExpandedCand(isExpanded ? null : path)}
              >
                <button
                  className={`candidate-toggle ${isFileSelected ? 'selected' : ''} ${isFullFile ? 'full-file' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleSelection(path);
                  }}
                  type="button"
                  title={isFileSelected ? 'Remove file from prompt' : 'Select auto-passing slices for this file'}
                >
                  {isFileSelected ? <CheckCircle2 size={14} /> : <Circle size={14} className="opacity-30" />}
                </button>

                <div className="file-bubble-meta">
                  <div className="flex items-center justify-between mb-1 gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="candidate-name truncate">{path.split('/').pop()}</span>
                      <span className="candidate-badge accent">{cand.file_metadata.classification}</span>
                      {autoSelected && <span className="candidate-badge auto">Auto threshold</span>}
                    </div>
                    <div className="flex items-center gap-1.5 min-w-[64px] justify-end">
                      <span className="candidate-score-badge">
                        {Math.round(cand.score)} pts
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-3">
                    {isFileSelected && (
                      <div className="shrink-0 flex justify-end">
                        <span className={`candidate-selection-badge ${isFullFile ? 'purple' : isEmpty ? 'red' : 'blue'}`}>
                          {isFullFile ? 'FULL FILE' : `${activeSlicesCount} SLICE${activeSlicesCount !== 1 ? 'S' : ''}`}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="candidate-expand opacity-40 ml-2">
                  {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </div>
              </div>

              {isExpanded && (
                <div className="file-bubble-details animate-in slide-in-from-top-1 duration-200 pb-2">
                  <div className="file-detail-toolbar">
                    <ScoreBreakdownPanel breakdown={cand.score_breakdown} score={cand.score} mode={mode} />
                    <FileSelectionControls
                      path={path}
                      isFullFile={isFullFile}
                      allSlicesSelected={allSlicesSelected}
                      loading={loading}
                      selectAllSlices={selectAllSlices}
                      toggleFullFile={toggleFullFile}
                    />
                  </div>

                  {cand.relationship_path?.length > 1 && (
                    <div className="file-detail-path">
                      <RelationshipPath path={cand.relationship_path} breakdown={cand.score_breakdown} expanded />
                    </div>
                  )}

                  <div className="file-detail-path">
                    <div className="candidate-path" title={path}>{path}</div>
                  </div>

                  {isEmpty && (
                    <div className="empty-slices-warning">
                      <AlertCircle size={10} />
                      <span>No slices selected. Pick fragments or explicitly include the full file.</span>
                    </div>
                  )}

                  <div className="px-3 pb-2 space-y-2">
                    {isFullFile ? (
                      <div className="full-file-indicator">
                        <Zap size={10} className="text-purple-400" />
                        <span>Full file explicitly selected. Slice pruning is bypassed for this file.</span>
                      </div>
                    ) : totalSlices > 0 ? (
                      cand.slices?.map((slice, i) => (
                        <SliceCard
                          key={`${slice.start_line}-${slice.end_line}-${i}`}
                          slice={slice}
                          isSelected={sliceSelection[path]?.has(i) || false}
                          isAuto={autoSliceSelection[path]?.has(i) || false}
                          onToggle={() => toggleSlice(path, i)}
                        />
                      ))
                    ) : (
                      <div className="text-[10px] opacity-50 italic py-4 text-center">
                        No semantic slices available. Use full file if this candidate is needed.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default CandidateList;
