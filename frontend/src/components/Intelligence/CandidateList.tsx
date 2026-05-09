import React, { useState } from 'react';
import { ChevronDown, ChevronRight, ShieldCheck, Zap, CheckCircle2, Circle, AlertCircle } from 'lucide-react';

interface ScoreBreakdown {
  factor: string;
  points: number;
  reason: string;
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

const ExplainabilityHierarchy: React.FC<{ breakdown: ScoreBreakdown[] }> = ({ breakdown }) => {
  if (!breakdown || !Array.isArray(breakdown)) return null;

  // Sort by points descending and take top 3
  const topReasons = [...breakdown]
    .sort((a, b) => b.points - a.points)
    .slice(0, 3);

  return (
    <div className="explainability-hierarchy mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
      {topReasons.map((reason, i) => (
        <div
          key={i}
          className="flex items-center gap-1 rounded-md border border-white/5 bg-white/[0.03] px-1.5 py-0.5 text-[8px]"
        >
          <span className={`font-mono font-bold ${reason.points > 0 ? 'text-green-400/80' : 'text-red-400/80'}`}>
            {reason.points > 0 ? '+' : ''}{Math.round(reason.points)}
          </span>

          <span className="opacity-50 truncate max-w-[140px]">
            {reason.reason}
          </span>
        </div>
      ))}
    </div>
  );
};

const SliceCard: React.FC<{ 
  path: string;
  index: number;
  slice: CodeSlice;
  isSelected: boolean;
  isAuto: boolean;
  onToggle: () => void;
}> = ({ path, index, slice, isSelected, isAuto, onToggle }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Selection States
  const isManuallySelected = isSelected && !isAuto;
  const isManuallyExcluded = !isSelected && isAuto;
  const isUnselected = !isSelected && !isAuto;
  const isOptional = isUnselected;

  const cardClass = `
  slice-card
  ${slice.expansion_type || 'proximity'}
  ${isManuallySelected ? 'manually-selected' : ''}
  ${isManuallyExcluded ? 'manually-excluded' : ''}
  ${isOptional ? 'unselected optional-slice' : ''}
  `;
  const badgeClass = `slice-badge badge-${slice.expansion_type || 'proximity'}`;
  
  return (
    <div
      className={cardClass}
      style={{
        transform: isSelected ? 'translateY(0px)' : 'translateY(1px)'
      }}
    >
      <div className="slice-card-header">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <button 
            className={`opacity-40 hover:opacity-100 transition-opacity ${isSelected ? 'text-blue-400' : ''} ${isManuallySelected ? 'text-purple-400' : ''}`}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
          >
            {isSelected ? <CheckCircle2 size={14} className={isManuallySelected ? "drop-shadow-[0_0_5px_rgba(162,119,255,0.8)]" : ""} /> : <Circle size={14} />}
          </button>
          
          <div className="slice-anchor-symbol truncate">
            {slice.anchor_symbol || 'logic_fragment'}()
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <span className={badgeClass}>{slice.expansion_type}</span>
          <span className="text-[9px] opacity-40 font-mono">L{slice.start_line}</span>
        </div>
      </div>
      
      <div className="slice-code-container" onClick={() => setIsExpanded(!isExpanded)}>
        <pre className={`slice-code-preview ${isExpanded ? 'expanded' : ''}`}>
          <code>{slice.content}</code>
        </pre>
        {!isExpanded && (
          <div className="absolute bottom-1 right-2 text-[8px] opacity-40 bg-black/80 px-1.5 py-0.5 rounded border border-white/5">
            View Code
          </div>
        )}
      </div>
      
      <div className="px-3 py-1.5 flex items-center justify-between border-t border-white/5 bg-white/[0.01]">
        <span className="text-[8px] opacity-30 italic truncate pr-4">Reason: {slice.reason}</span>
        {isManuallySelected && <span className="text-[8px] text-purple-300 font-bold uppercase tracking-tighter">Human Overridden</span>}
      </div>
    </div>
  );
};

const ConnectionChain: React.FC<{ path: string[] }> = ({ path }) => {
  if (!path || path.length === 0) return null;
  
  return (
    <div className="connection-chain">
      <span className="text-[8px] uppercase tracking-[0.12em] opacity-20 mr-1">
  Flow
</span>
      {path.map((node, i) => (
        <React.Fragment key={i}>
          <span className={`chain-node ${i === path.length - 1 ? 'active' : ''}`}>
            {node.includes(':') ? node.split(':').pop() : node.split('/').pop()}
          </span>
          {i < path.length - 1 && <ChevronRight size={8} className="opacity-20" />}
        </React.Fragment>
      ))}
    </div>
  );
};

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
  onAssemble,
  loading
}) => {
  return (
    <div className="panel-section border-t border-white/5 pt-4">
      <div className="panel-title mb-4">
        <ShieldCheck size={13} />
        <span>Surgical Engineering Intelligence</span>
        <span className="ml-auto text-[10px] opacity-40 font-mono">
          {candidates.length} Files Ranked
        </span>
      </div>

      <div className="candidate-list custom-scrollbar space-y-3">
        {candidates.map((cand) => {
          const path = cand.file_metadata.rel_path;
          const isFileSelected = selectedPaths.has(path);
          const isFullFile = fullFileOverrides.has(path);
          const activeSlicesCount = sliceSelection[path]?.size || 0;
          const isExpanded = expandedCand === path;
          const isEmpty = isFileSelected && activeSlicesCount === 0 && !isFullFile;

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
                  className={`candidate-toggle ${isFileSelected ? 'selected' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleSelection(path);
                  }}
                  type="button"
                >
                  {isFileSelected ? <CheckCircle2 size={14} className="text-blue-400" /> : <Circle size={14} className="opacity-30" />}
                </button>
                
                <div className="file-bubble-meta">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="candidate-name">{path.split('/').pop()}</span>
                    <span className="candidate-badge accent opacity-60">{cand.file_metadata.classification}</span>
                    {isFileSelected && (
                      <span className={`text-[8px] px-1.5 rounded-full font-bold tracking-tight ${isFullFile ? 'bg-purple-500/20 text-purple-300' : isEmpty ? 'bg-red-500/10 text-red-400' : 'bg-blue-500/10 text-blue-400'}`}>
                        {isFullFile ? 'FULL OVERRIDE' : `${activeSlicesCount} SLICE${activeSlicesCount !== 1 ? 'S' : ''}`}
                      </span>
                    )}
                    <div className="ml-auto flex items-center gap-1.5">
                      <span className="text-[9px] font-mono opacity-30">{Math.round(cand.score)}%</span>
                      <div className="w-1.5 h-1.5 rounded-full" style={{ background: `hsla(${cand.score * 1.2}, 70%, 50%, 0.4)` }}></div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 mb-1">
                    <div className="candidate-path truncate opacity-40 text-[9px] max-w-[140px]">{path}</div>
                    {cand.relationship_path?.length > 1 && <div className="h-2 w-[1px] bg-white/10"></div>}
                    <ConnectionChain path={cand.relationship_path} />
                  </div>
                  
                  <ExplainabilityHierarchy breakdown={cand.score_breakdown} />
                </div>

                <div className="candidate-expand opacity-40 ml-2">
                  {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </div>
              </div>

              {isExpanded && (
                <div className="file-bubble-details animate-in slide-in-from-top-1 duration-200 pb-2">
                  <div className="px-3 flex items-center justify-end mb-2 gap-2">
                    <button 
                      className={`full-file-toggle ${activeSlicesCount === cand.slices?.length ? 'active' : ''}`}
                      onClick={(e) => { e.stopPropagation(); selectAllSlices(path); }}
                    >
                      Include All Fragments
                    </button>
                    <button 
                      className={`full-file-toggle ${isFullFile ? 'active' : ''}`}
                      onClick={(e) => { e.stopPropagation(); toggleFullFile(path); }}
                    >
                      {isFullFile ? 'Full File Enabled' : 'Include Full File'}
                    </button>
                  </div>
                  
                  {isEmpty && (
                    <div className="empty-slices-warning">
                      <AlertCircle size={10} />
                      <span>Warning: No surgical slices selected.</span>
                    </div>
                  )}

                  <div className="px-3 pb-2 space-y-2">
                    {isFullFile ? (
                      <div className="full-file-indicator">
                        <Zap size={10} className="text-purple-400" />
                        <span>Architectural pruning bypassed. Full context injected.</span>
                      </div>
                    ) : cand.slices && cand.slices.length > 0 ? (
                      cand.slices.map((slice, i) => (
                        <SliceCard 
                          key={i} 
                          path={path}
                          index={i}
                          slice={slice}
                          isSelected={sliceSelection[path]?.has(i) || false}
                          isAuto={autoSliceSelection[path]?.has(i) || false}
                          onToggle={() => toggleSlice(path, i)}
                        />
                      ))
                    ) : (
                      <div className="text-[10px] opacity-30 italic py-4 text-center">
                        No semantic slices available.
                      </div>
                    )}
                  </div>
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
