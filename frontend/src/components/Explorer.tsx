import React, { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, FileText } from 'lucide-react';
import { FileNode } from '../utils/buildTree';

interface ExplorerProps {
  tree: FileNode[];
  selectedPath: string | null;
  onFileSelect: (path: string) => void;
}

const ExplorerNode: React.FC<{
  node: FileNode;
  level: number;
  selectedPath: string | null;
  onFileSelect: (path: string) => void;
}> = ({ node, level, selectedPath, onFileSelect }) => {

  const [isOpen, setIsOpen] = useState(level < 1);
  const isSelected = selectedPath === node.path;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();

    if (node.type === 'folder') {
      setIsOpen(prev => !prev);
    } else {
      onFileSelect(node.path);
    }
  };

  return (
    <div className="explorer-node">

      {/* ROW */}
      <div
        onClick={handleClick}
        className={`explorer-item ${isSelected ? 'selected' : ''}`}
        style={{
          paddingLeft: `${level * 14 + 12}px`
        }}
      >
        {/* arrow */}
        <div className="explorer-arrow">
          {node.type === 'folder' && (
            isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />
          )}
        </div>

        {/* icon */}
        <div className="explorer-icon">
          {node.type === 'folder'
            ? <Folder size={14} />
            : <FileText size={14} />
          }
        </div>

        {/* name */}
        <div className="explorer-name">
          {node.name}
        </div>
      </div>

      {/* children */}
      {node.type === 'folder' && isOpen && node.children && (
        <div className="explorer-children">
          {node.children.map((child) => (
            <ExplorerNode
              key={child.path}
              node={child}
              level={level + 1}
              selectedPath={selectedPath}
              onFileSelect={onFileSelect}
            />
          ))}
        </div>
      )}

    </div>
  );
};

const Explorer: React.FC<ExplorerProps> = ({
  tree,
  selectedPath,
  onFileSelect
}) => {
  return (
    <div className="h-full overflow-y-auto pb-16">
      {tree.map((node) => (
        <ExplorerNode
          key={node.path}
          node={node}
          level={0}
          selectedPath={selectedPath}
          onFileSelect={onFileSelect}
        />
      ))}
    </div>
  );
};

export default Explorer;