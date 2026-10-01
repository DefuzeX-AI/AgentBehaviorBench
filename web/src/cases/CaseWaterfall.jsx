import { useEffect, useRef } from 'react';
import { Button, Space, Typography } from 'antd';
import { DataSet, Timeline } from 'vis-timeline/standalone';
import 'vis-timeline/styles/vis-timeline-graph2d.css';
import { formatTime } from './timelineModel.js';
const { Text } = Typography;
const plain = value => { const node = document.createElement('span'); node.textContent = value; return node; };
const colorKind = kind => ['agent', 'execution', 'llm', 'tool', 'build', 'wait', 'sdk_wait', 'cleanup'].includes(kind) ? kind : 'runtime';

export default function Waterfall({ model, onSelect }) {
  const element = useRef(null), chart = useRef(null), sets = useRef(null), initialized = useRef(false);
  const autoFit = useRef(true);
  const select = useRef(onSelect);
  select.current = onSelect;
  useEffect(() => {
    const items = new DataSet(), groups = new DataSet();
    sets.current = { items, groups };
    chart.current = new Timeline(element.current, items, groups, {
      editable: false, stack: false, showCurrentTime: false, orientation: 'top',
      zoomMin: 1, zoomKey: 'ctrlKey', maxHeight: 600, verticalScroll: true,
      groupOrder: 'order', margin: { item: 7, axis: 8 },
      format: { minorLabels: date => formatTime(date.valueOf()), majorLabels: () => 'Elapsed from first recorded stage' },
      template: item => plain(item?.content || ''), groupTemplate: group => plain(group?.content || ''),
    });
    chart.current.on('select', event => select.current(event.items[0] || null));
    chart.current.on('rangechanged', event => { if (event.byUser) autoFit.current = false; });
    return () => { chart.current.destroy(); chart.current = null; initialized.current = false; };
  }, []);
  useEffect(() => {
    if (!chart.current || model.start == null) return;
    const { items, groups } = sets.current;
    const ids = new Set(model.rows.map(row => row.id));
    items.remove(items.getIds().filter(id => !ids.has(id)));
    groups.remove(groups.getIds().filter(id => !ids.has(id)));
    groups.update(model.rows.map((row, order) => ({ id: row.id, content: row.name, order, treeLevel: row.depth,
      ...(row.childIds.length ? { nestedGroups: row.childIds } : {}), ...(!groups.get(row.id) ? { showNested: row.depth < 3 } : {}) })));
    items.update(model.rows.map(row => ({ id: row.id, group: row.id,
      start: row.start_ms - model.start, end: Math.max(row.start_ms + 0.01, row.end_ms) - model.start,
      type: 'range', content: `${formatTime(row.duration_ms)}${row.status === 'running' ? ' · running' : ''}`,
      className: `timing-${colorKind(row.kind)} timing-status-${row.status}` })));
    if (!initialized.current || autoFit.current) { chart.current.setWindow(-10, Math.max(100, model.end - model.start) * 1.04, { animation: false }); initialized.current = true; }
  }, [model]);
  return <><Space wrap><Button onClick={() => { autoFit.current = true; chart.current?.fit({ animation: false }); }}>Fit all stages</Button>
    <Text type="secondary">Drag to pan · Ctrl + scroll to zoom · expand stage names</Text></Space>
    <div ref={element} className="timing-chart" aria-label="Execution duration waterfall" /></>;
}
