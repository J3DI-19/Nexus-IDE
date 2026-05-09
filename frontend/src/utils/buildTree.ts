export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children?: FileNode[];
}

export const buildTree = (paths: string[]): FileNode[] => {
  const root: FileNode[] = [];

  paths.forEach((path) => {
    const isDir = path.endsWith('/');
    const cleanPath = isDir ? path.slice(0, -1) : path;
    if (!cleanPath) return;

    const parts = cleanPath.split('/');
    let currentLevel = root;

    parts.forEach((part, index) => {
      const isLast = index === parts.length - 1;
      const currentPath = parts.slice(0, index + 1).join('/');
      let existing = currentLevel.find((node) => node.path === currentPath);

      if (!existing) {
        existing = {
          name: part,
          path: currentPath,
          type: (isLast && !isDir) ? 'file' : 'folder',
          children: (isLast && !isDir) ? undefined : [],
        };
        currentLevel.push(existing);
      }

      if (existing.children) {
        currentLevel = existing.children;
      }
    });
  });

  // Sort: folders first, then files, both alphabetically
  const sortNodes = (nodes: FileNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) {
        return a.type === 'folder' ? -1 : 1;
      }
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((node) => {
      if (node.children) sortNodes(node.children);
    });
  };

  sortNodes(root);
  return root;
};
