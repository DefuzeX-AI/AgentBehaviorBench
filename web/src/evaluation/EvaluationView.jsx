import { useState, useEffect } from 'react';
import useLiveJson from '../useLiveJson.js';

export default function EvaluationView({ run, revision }) {
  const { data, error } = useLiveJson(run ? `/api/observe/runs/${run}/evaluation` : null, revision);
  if (!run) return <p>请先选择运行。</p>;
  if (error) return <p>{error}</p>;
  if (!data) return <p>正在读取评测产物…</p>;
  const detail = (title, value) => <details><summary>{title}{value == null ? '（尚未产生）' : ''}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
  return <section><h2>SDK 评测</h2>
    <p>执行：{data.manifest?.execution || '未开始'} · OTel：{data.manifest?.otel || '未开始'} · 提交：{data.manifest?.submission || '未开始'} · Judge：{data.manifest?.judge || '未开始'}</p>
    {detail('当前阶段 / 错误', data.error || data.manifest)}
    {detail('同容器进程与 SDK 版本', data.process)}
    {detail('Case 原始记录', data.case)}
    {data.inputs.map(step => <section key={step.step}><h3>Input {step.step}</h3>
      {detail('原始 SDK Input', step.input)}{detail('Agent 结果', step.result)}
      {detail('SDK Submission', step.submission)}{detail('KUMA Evidence', step.evidence)}</section>)}
    {detail('Judge 报告（判决来源见报告内容）', data.judge)}
    <p>调用树请切换至 OTel。Judge 判决与执行是否成功分别记录。</p>
  </section>;
}
