import { useMemo } from 'react';
import { ReactFlow, Background, Controls, MiniMap } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { executionGraph } from './graph.js';

export default function ExecutionGraph({ spans, onSelect }) {
  const graph = useMemo(() => executionGraph(spans), [spans]);
  return <div className="trajectory-canvas" aria-label="Live execution call graph">
    <ReactFlow nodes={graph.nodes} edges={graph.edges}
      defaultViewport={{ x: 40, y: 40, zoom: 1 }} minZoom={0.05}
      nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => onSelect(node.data.span)}>
      <Background /><Controls showInteractive={false} /><MiniMap pannable zoomable />
    </ReactFlow>
  </div>;
}
