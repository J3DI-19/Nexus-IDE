import React from 'react';
import { FileCode, Copy } from 'lucide-react';

interface PromptPreviewProps {
  prompt: string;
  stats?: {
    files: number;
    context_lines: number;
    prompt_tokens: number;
  } | null;
  onCopy: () => void;
  onBack: () => void;
}

const PromptPreview: React.FC<PromptPreviewProps> = ({ prompt, stats, onCopy, onBack }) => {
  return (
    <div className="panel-section border-t border-white/5 pt-4">
      <div className="panel-title mb-2">
        <FileCode size={13} />
        <span>Generated Prompt</span>
      </div>

      {stats && (
        <div className="prompt-stats-row">
          <div className="prompt-stat">
            <span>{stats.files}</span>
            <small>Files</small>
          </div>
          <div className="prompt-stat">
            <span>{stats.context_lines}</span>
            <small>File Lines</small>
          </div>
          <div className="prompt-stat">
            <span>{stats.prompt_tokens}</span>
            <small>Est. Tokens</small>
          </div>
        </div>
      )}

      <div className="prompt-box max-h-[300px] mb-2">
        <pre className="text-[10px] leading-relaxed">{prompt}</pre>
      </div>

      <button
        className="btn btn-primary w-full flex justify-center items-center gap-2"
        onClick={onCopy}
      >
        <Copy size={14} />
        Copy to Clipboard
      </button>

      <button 
        className="btn w-full mt-2 opacity-60 hover:opacity-100"
        onClick={onBack}
      >
        Back to Review
      </button>
    </div>
  );
};

export default PromptPreview;
