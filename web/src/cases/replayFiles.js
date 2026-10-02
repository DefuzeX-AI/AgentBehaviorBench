// Include deleted paths so their last observed change remains inspectable.
export function replayFiles(entries, changes, changedOnly = false) {
  const latest = new Map(changes.map(change => [change.path, change]));
  const nodes = new Map();
  function ensure(path) {
    if (!nodes.has(path)) nodes.set(path, { key: path, title: path.split('/').at(-1), children: [], isLeaf: false });
    return nodes.get(path);
  }
  for (const [path, entry] of entries) ensure(path).isLeaf = entry.type !== 'directory';
  for (const [path, change] of latest) {
    const node = ensure(path);
    node.isLeaf = (change.after || change.before)?.type !== 'directory';
    node.change = change.after == null ? 'D' : change.before == null ? 'A' : 'M';
  }
  const roots = [];
  for (const [path, node] of nodes) {
    const slash = path.lastIndexOf('/');
    if (slash < 0) roots.push(node);
    else ensure(path.slice(0, slash)).children.push(node);
  }
  function visit(branches) {
    return branches.map(node => {
      node.children = visit(node.children);
      node.changedCount = (node.change ? 1 : 0) + node.children.reduce((sum, child) => sum + child.changedCount, 0);
      return node;
    }).filter(node => !changedOnly || node.changedCount)
      .sort((a, b) => Number(a.isLeaf) - Number(b.isLeaf) || a.title.localeCompare(b.title));
  }
  return { tree: visit(roots), changedCount: latest.size };
}

export function parentDirectories(paths) {
  return [...new Set(paths.flatMap(path => {
    const parts = path.split('/');
    return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join('/'));
  }))];
}
