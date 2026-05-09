import React, { useState, useRef, useEffect } from 'react';
import { ChevronRight, ChevronDown, Folder, FileText, FilePlus, FolderPlus, Edit2, Trash2 } from 'lucide-react';
import { FileNode } from '../utils/buildTree';

interface ExplorerProps {
  tree: FileNode[];
  selectedPath: string | null;
  dirtyPaths: Set<string>;
  onFileSelect: (path: string) => void;
  onCreateFile?: (path: string, isFolder: boolean) => void;
  onRename?: (oldPath: string, newPath: string) => void;
  onDelete?: (path: string) => void;
  onMove?: (sourcePath: string, destPath: string) => void;
}

const ExplorerNode: React.FC<{
  node: FileNode;
  level: number;
  selectedPath: string | null;
  dirtyPaths: Set<string>;
  onFileSelect: (path: string) => void;
  onCreateFile?: (path: string, isFolder: boolean) => void;
  onRename?: (oldPath: string, newPath: string) => void;
  onDelete?: (path: string) => void;
  onMove?: (sourcePath: string, destPath: string) => void;
}> = ({ node, level, selectedPath, dirtyPaths, onFileSelect, onCreateFile, onRename, onDelete, onMove }) => {

  const [isOpen, setIsOpen] = useState(level < 1);
  const [isHovered, setIsHovered] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(node.name);
  const [isCreating, setIsCreating] = useState<'file' | 'folder' | null>(null);
  const [createValue, setCreateValue] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  
  const inputRef = useRef<HTMLInputElement>(null);
  const createInputRef = useRef<HTMLInputElement>(null);

  const isSelected = selectedPath === node.path;
  const isDirty = node.type === 'file' && dirtyPaths.has(node.path);

  // Sync internal open state if tree changes and we are a parent of selected path
  useEffect(() => {
    if (selectedPath && selectedPath.startsWith(node.path + '/')) {
      setIsOpen(true);
    }
  }, [selectedPath, node.path]);

  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isRenaming]);

  useEffect(() => {
    if (isCreating && createInputRef.current) {
      createInputRef.current.focus();
    }
  }, [isCreating]);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isRenaming) return;

    if (node.type === 'folder') {
      setIsOpen(prev => !prev);
    } else {
      onFileSelect(node.path);
    }
  };

  const submitRename = () => {
    setIsRenaming(false);
    if (!renameValue.trim() || renameValue === node.name) {
      setRenameValue(node.name);
      return;
    }
    if (onRename) {
      const parentPath = node.path.substring(0, node.path.lastIndexOf('/'));
      const newPath = parentPath ? `${parentPath}/${renameValue}` : renameValue;
      onRename(node.path, newPath);
    }
  };

  const submitCreate = () => {
    if (!createValue.trim() || !isCreating) {
      setIsCreating(null);
      setCreateValue('');
      return;
    }
    if (onCreateFile) {
      const newPath = node.path ? `${node.path}/${createValue}` : createValue;
      onCreateFile(newPath, isCreating === 'folder');
    }
    setIsCreating(null);
    setCreateValue('');
    setIsOpen(true);
  };

  const handleDragStart = (e: React.DragEvent) => {
    e.stopPropagation();
    setIsDragging(true);
    e.dataTransfer.setData('application/x-nexus-path', node.path);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragEnd = () => {
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (node.type !== 'folder') return;
    
    // Attempt to read data to prevent invalid hover states.
    // Note: Chrome doesn't always allow reading data during dragover for security, 
    // but we can at least set drop effect.
    e.dataTransfer.dropEffect = 'move';
    if (!isDragOver) setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    
    if (node.type !== 'folder' || !onMove) return;

    const sourcePath = e.dataTransfer.getData('application/x-nexus-path');
    if (!sourcePath || sourcePath === node.path) return;

    // Prevent folder into itself or descendant (basic frontend check, backend handles strictly too)
    if (node.path.startsWith(sourcePath + '/')) return;
    
    // Prevent dropping into its own direct parent (no-op)
    const sourceParent = sourcePath.substring(0, sourcePath.lastIndexOf('/'));
    if (sourceParent === node.path) return;

    onMove(sourcePath, node.path);
  };

  return (
    <div className="explorer-node">

      {/* ROW */}
      <div
        draggable={true}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`explorer-item ${isSelected ? 'selected' : ''} ${isDragOver ? 'drag-over' : ''} ${isDragging ? 'dragging' : ''} ${isDirty ? 'dirty' : ''}`}
        style={{
          paddingLeft: `${level * 12 + 10}px`
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
        <div className="explorer-name flex-1 min-w-0 flex items-center pr-2">
          {isRenaming ? (
            <input
              ref={inputRef}
              className="explorer-inline-input"
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onBlur={submitRename}
              onKeyDown={e => {
                if (e.key === 'Enter') submitRename();
                if (e.key === 'Escape') {
                  setIsRenaming(false);
                  setRenameValue(node.name);
                }
              }}
              onClick={e => e.stopPropagation()}
            />
          ) : (
            <>
              <span className="truncate">{node.name}</span>
              {isDirty && <span className="explorer-dirty-indicator">●</span>}
            </>
          )}

          {isHovered && !isRenaming && (
            <div className="explorer-actions flex items-center gap-1 ml-auto" onClick={e => e.stopPropagation()}>
              {node.type === 'folder' && (
                <>
                  <button className="explorer-action-btn" onClick={() => { setIsCreating('file'); setCreateValue('untitled.txt'); }} title="New File">
                    <FilePlus size={12} />
                  </button>
                  <button className="explorer-action-btn" onClick={() => setIsCreating('folder')} title="New Folder">
                    <FolderPlus size={12} />
                  </button>
                </>
              )}
              <button className="explorer-action-btn" onClick={() => setIsRenaming(true)} title="Rename">
                <Edit2 size={12} />
              </button>
              <button className="explorer-action-btn delete" onClick={() => onDelete && onDelete(node.path)} title="Delete">
                <Trash2 size={12} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* children */}
      {node.type === 'folder' && (isOpen || isCreating) && (
        <div className="explorer-children">
          {isCreating && (
            <div 
              className="explorer-item"
              style={{ paddingLeft: `${(level + 1) * 12 + 10}px` }}
            >
              <div className="explorer-arrow"></div>
              <div className="explorer-icon">
                {isCreating === 'folder' ? <Folder size={14} /> : <FileText size={14} />}
              </div>
              <div className="explorer-name flex-1 min-w-0">
                <input
                  ref={createInputRef}
                  className="explorer-inline-input"
                  value={createValue}
                  placeholder={isCreating === 'folder' ? "Folder name..." : "File name..."}
                  onChange={e => setCreateValue(e.target.value)}
                  onBlur={submitCreate}
                  onKeyDown={e => {
                    if (e.key === 'Enter') submitCreate();
                    if (e.key === 'Escape') {
                      setIsCreating(null);
                      setCreateValue('');
                    }
                  }}
                />
              </div>
            </div>
          )}
          {Array.isArray(node.children) && node.children.map((child) => (
            <ExplorerNode
              key={child.path}
              node={child}
              level={level + 1}
              selectedPath={selectedPath}
              dirtyPaths={dirtyPaths}
              onFileSelect={onFileSelect}
              onCreateFile={onCreateFile}
              onRename={onRename}
              onDelete={onDelete}
              onMove={onMove}
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
  dirtyPaths,
  onFileSelect,
  onCreateFile,
  onRename,
  onDelete,
  onMove
}) => {
  const [isCreatingRoot, setIsCreatingRoot] = useState<'file' | 'folder' | null>(null);
  const [createRootValue, setCreateRootValue] = useState('');
  const [isRootDragOver, setIsRootDragOver] = useState(false);
  const createRootInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isCreatingRoot && createRootInputRef.current) {
      createRootInputRef.current.focus();
      if (isCreatingRoot === 'file') {
        createRootInputRef.current.select();
      }
    }
  }, [isCreatingRoot]);

  const submitCreateRoot = () => {
    if (!createRootValue.trim() || !isCreatingRoot) {
      setIsCreatingRoot(null);
      setCreateRootValue('');
      return;
    }
    if (onCreateFile) {
      onCreateFile(createRootValue, isCreatingRoot === 'folder');
    }
    setIsCreatingRoot(null);
    setCreateRootValue('');
  };

  const handleRootDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    if (!isRootDragOver) setIsRootDragOver(true);
  };

  const handleRootDragLeave = (e: React.DragEvent) => {
    e.stopPropagation();
    setIsRootDragOver(false);
  };

  const handleRootDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsRootDragOver(false);
    
    if (!onMove) return;

    const sourcePath = e.dataTransfer.getData('application/x-nexus-path');
    if (!sourcePath || !sourcePath.includes('/')) return; // Already at root

    onMove(sourcePath, ''); // Moving to root means dest is empty string
  };

  return (
    <div 
      className={`flex-1 flex flex-col h-full min-h-0 transition-colors ${isRootDragOver ? 'bg-white/5' : ''}`}
      onDragOver={handleRootDragOver}
      onDragLeave={handleRootDragLeave}
      onDrop={handleRootDrop}
    >
      {/* Root actions */}
      <div className="explorer-root-actions flex justify-end gap-2 px-2 py-1 border-b border-[var(--border-color)]">
        <button className="explorer-action-btn" onClick={() => { setIsCreatingRoot('file'); setCreateRootValue('untitled.txt'); }} title="New File at Root">
          <FilePlus size={13} />
        </button>
        <button className="explorer-action-btn" onClick={() => setIsCreatingRoot('folder')} title="New Folder at Root">
          <FolderPlus size={13} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isCreatingRoot && (
          <div className="explorer-item" style={{ paddingLeft: '10px' }}>
            <div className="explorer-arrow"></div>
            <div className="explorer-icon">
              {isCreatingRoot === 'folder' ? <Folder size={14} /> : <FileText size={14} />}
            </div>
            <div className="explorer-name flex-1 min-w-0">
              <input
                ref={createRootInputRef}
                className="explorer-inline-input"
                value={createRootValue}
                placeholder={isCreatingRoot === 'folder' ? "Folder name..." : "File name..."}
                onChange={e => setCreateRootValue(e.target.value)}
                onBlur={submitCreateRoot}
                onKeyDown={e => {
                  if (e.key === 'Enter') submitCreateRoot();
                  if (e.key === 'Escape') {
                    setIsCreatingRoot(null);
                    setCreateRootValue('');
                  }
                }}
              />
            </div>
          </div>
        )}
        {Array.isArray(tree) && tree.map((node) => (
          <ExplorerNode
            key={node.path}
            node={node}
            level={0}
            selectedPath={selectedPath}
            dirtyPaths={dirtyPaths}
            onFileSelect={onFileSelect}
            onCreateFile={onCreateFile}
            onRename={onRename}
            onDelete={onDelete}
            onMove={onMove}
          />
        ))}
      </div>
    </div>
  );
};

export default Explorer;
