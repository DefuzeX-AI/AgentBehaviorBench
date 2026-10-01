import { useMemo } from 'react';
import { ReactFlow, Background, Controls, Handle, Position, BaseEdge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { formatTime } from '../cases/timelineModel.js';
import { topologyPositions } from './model.js';
import './topology.css';

const labels = { case: 'Runtime', agent: 'Agent', llm: 'LLM', tool: 'Tool', http: 'HTTP', sdk_wait: 'SDK / Judge', generation: 'Generation' };
const countLabel = item => `${item.count} ${item.kind === 'case' ? (item.count === 1 ? 'run' : 'runs') : (item.count === 1 ? 'call' : 'calls')}`;
const elapsed = item => `${formatTime(item.duration_ms)}${item.unfinished ? ' +' : ''}`;

function Participant({ data }) {
  return <div className={`topology-participant topology-${data.kind}${data.failed ? ' topology-failed' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <small>{labels[data.kind]}</small><strong>{data.title}</strong>
    {data.model && <span className="topology-model">{data.model}</span>}
    <div className="topology-metrics"><span>{countLabel(data)}</span><b>{elapsed(data)}</b></div>
    <small>Summed span time{data.missing ? ` · ${data.missing} unmeasured` : ''}</small>
    {(data.failed > 0 || data.unfinished > 0) && <span className="topology-state">{[data.failed && `${data.failed} failed`, data.unfinished && `${data.unfinished} unfinished`].filter(Boolean).join(' · ')}</span>}
    <Handle type="source" position={Position.Right} />
  </div>;
}

function SelfCall({ sourceX, sourceY, targetX, targetY, ...props }) {
  const top = Math.min(sourceY, targetY) - 115;
  return <BaseEdge {...props} path={`M ${sourceX},${sourceY} C ${sourceX + 75},${sourceY} ${sourceX + 75},${top} ${sourceX},${top} L ${targetX},${top} C ${targetX - 75},${top} ${targetX - 75},${targetY} ${targetX},${targetY}`}
    labelX={(sourceX + targetX) / 2} labelY={top} />;
}
const nodeTypes = { participant: Participant }, edgeTypes = { selfCall: SelfCall };

export default function TopologyDiagram({ graph, onSelect, selectedId }) {
  const positions = useMemo(() => topologyPositions(graph.nodes, graph.edges), [graph]);
  const keyboardOpen = id => ({ onKeyDown: event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); onSelect(id); }
  } });
  const nodes = graph.nodes.map(node => ({ id: node.id, type: 'participant', position: positions.get(node.id), data: node,
    ariaRole: 'button', domAttributes: keyboardOpen(node.id),
    selected: selectedId === node.id, ariaLabel: `${node.title}, ${countLabel(node)}, ${elapsed(node)} summed span time. Open recorded calls.` }));
  const edges = graph.edges.map(edge => ({ ...edge, type: edge.source === edge.target ? 'selfCall' : 'smoothstep',
    ariaRole: 'button', domAttributes: keyboardOpen(edge.id),
    selected: selectedId === edge.id, label: `${countLabel(edge)} · ${elapsed(edge)}${edge.missing ? ` · ${edge.missing} unmeasured` : ''}`,
    ariaLabel: `${edge.title}, ${edge.count} calls. Open recorded calls.`,
    markerEnd: { type: 'arrowclosed', color: edge.failed ? '#b4544b' : '#648773' },
    style: { stroke: edge.failed ? '#b4544b' : '#648773', strokeWidth: 1.7 },
    labelStyle: { fill: '#3f5b4b', fontSize: 11 }, labelBgStyle: { fill: '#fff' },
    labelBgPadding: [7, 5], labelBgBorderRadius: 4, interactionWidth: 24 }));
  return <section className="topology-diagram" aria-label="Execution topology">
    <div className="topology-heading"><strong>Topology</strong><span>{nodes.length} participants · {edges.length} recorded connections</span></div>
    <p>Repeated calls are grouped by participant. Select a node or connection for its recorded calls. Times are summed span durations, not wall-clock elapsed time.</p>
    {!nodes.length ? <p>No recorded execution participants in this scope. Preparation details remain available in Sequence and Waterfall.</p>
      : <div className="topology-canvas"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
        fitView fitViewOptions={{ padding: 0.2, maxZoom: 1 }} minZoom={0.15} maxZoom={1.8}
        nodesDraggable={false} nodesConnectable={false} edgesFocusable deleteKeyCode={null}
        onNodeClick={(_, node) => onSelect(node.id)} onEdgeClick={(_, edge) => onSelect(edge.id)}>
        <Background color="#dfe8e2" gap={24} /><Controls showInteractive={false} />
      </ReactFlow></div>}
    <p>Connections follow recorded parent calls, including intervening framework steps. Unlinked participants stay unconnected. SDK submit / wait includes client-observed waiting; it is not Judge compute time.</p>
  </section>;
}
