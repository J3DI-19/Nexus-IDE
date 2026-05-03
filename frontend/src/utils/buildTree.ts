export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children?: FileNode[];
}

export const buildTree = (paths: string[]): FileNode[] => {
  const root: FileNode[] = [];

  paths.forEach((path) => {
    const parts = path.split('/');
    let currentLevel = root;

    parts.forEach((part, index) => {
      const isLast = index === parts.length - 1;
      const currentPath = parts.slice(0, index + 1).join('/');
      let existing = currentLevel.find((node) => node.name === part);

      if (!existing) {
        existing = {
          name: part,
          path: currentPath,
          type: isLast ? 'file' : 'folder',
          children: isLast ? undefined : [],
        };
        currentLevel.push(existing);
      }

      if (!isLast && existing.children) {
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
