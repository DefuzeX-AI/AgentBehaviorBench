import { useEffect, useRef, useState } from 'react';

export default function useFileChangeAnimation(snapshots, ready) {
  const seen = useRef(null);
  const [animated, setAnimated] = useState(new Set());
  useEffect(() => {
    if (!ready) return;
    const ids = new Set(snapshots.flatMap(snapshot => snapshot.changes.map(change => change.id)));
    const arrived = seen.current ? new Set([...ids].filter(id => !seen.current.has(id))) : new Set();
    seen.current = ids;
    setAnimated(arrived);
    if (arrived.size) {
      const timer = setTimeout(() => setAnimated(new Set()), 900);
      return () => clearTimeout(timer);
    }
  }, [snapshots, ready]);
  return animated;
}
