"""Official KUMA and the existing Agent worker, in one container process."""
import argparse
import asyncio
import json
import os
import platform
from pathlib import Path
from uuid import uuid4
from importlib.metadata import version
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.input_binding import validate_input_contract
from .runner import drive_run
from .configuration import request_options, api_key
from .compatibility import run_case
from agentbench.runtime.agentcontainer.session import AgentSession


async def execute(root, output, settings=None):
    # 这里进入容器内的评测流程，root 是 Agent 根目录，output 是产物目录，settings 是任务配置
    # 导入官方 Kuma SDK、证据采集工具和实际调用 Agent 的函数
    from kuma import create_run, DEFAULT_BASE_URL
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from agentbench.runtime.agentcontainer.worker import execute as invoke_agent, configure_trust
    from agentbench.runtime.agentcontainer.config import tomllib



    
    # 准备产物保存工具，并把 OpenTelemetry 采集的证据接给 Kuma SDK
    files = Artifacts(output)
    provider = TracerProvider(resource=Resource.create({'service.name': 'abb-evaluation'}))
    capture = configure_trace_evidence(provider)
    
    # 读取容器里的 Agent 配置，取得 Agent ID、框架等信息
    with (root / 'agent.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    # SDK Run 尚未创建，先准备供后续 Agent 调用复用的会话对象
    run = None
    agent_session = AgentSession()
    settings = dict(settings or {})
    try:
        # 仅校验逐轮原样输入契约；历史与记忆由 Agent 自己维护
        validate_input_contract(root / 'evaluation/input-contract.json')
        configure_trust()
        # 先保存当前进程、SDK 版本和初始任务状态，方便我们查看进度
        credential, credential_source = api_key(os.environ)
        files.save('process.json', {'pid': os.getpid(), 'container': platform.node(), 'mode': 'official',
                   'sdk': 'kuma', 'sdk_version': version('kuma-defuzex'), 'agent_id': manifest['agent_id'],
                   'sdk_base_url': DEFAULT_BASE_URL,
                   'api_key_source': credential_source,
                   'source': manifest.get('source'), 'repo': str(root / 'agent')})
        files.save('manifest.json', {'phase': 'case_generation', 'judge': 'pending'})

        # 组装 SDK 参数，包括仓库路径、对话步数上限、密钥、trace 证据和等待时间
        options = dict(repo_path=root / 'agent',
                       max_steps=settings.get('max_steps'), 
                       allow_local=False, track_files=False, 
                       save_local=True,

                       api_key=credential, trace_evidence=capture,
                       **request_options(settings.get('sdk_request_options')))

        
        if settings.get('mode') == 'generate':
            # 生成模式：根据 Agent profile 批量生成并保存 Case，这个分支不调用 Agent 回答
            from .generation import generate_collection
            # Generation reads the Agent profile; reuse rejects it, so the profile
            # belongs only to this branch.
            collection = generate_collection(
                create_run, count=settings['count'], files=files, repo=root / 'agent',
                case_indices=settings.get('case_indices'), allow_partial=settings.get('allow_partial', False),
                options=dict(options, agent_profile_path=root / 'evaluation/profile.md'))
            complete = not collection['failures'] and not collection['unattempted_indices']
            files.save('manifest.json', {'phase': 'batch_generated' if complete else 'batch_partial',
                                        'count': len(collection['cases']),
                                        'failed_count': len(collection['failures']),
                                        'unattempted_indices': collection['unattempted_indices']})
            # Case 批量生成完成就结束，不进入下面的 Case 执行流程
            return 0 if complete else 1
        
        # 执行模式必须提供已经保存的 Case 文件
        if settings.get('case_artifact') is None:
            raise ValueError('Evaluation requires a prepared Case artifact; generation belongs to batch preparation')
        # The SDK reuses a Case only from a saved artifact file inside the Run repository,
        # and rejects a Profile or strategy alongside it: the Case is already decided.
        # 从已有 Case 创建本次 SDK Run，不重新生成 Case
        run = create_run(case_path=settings['case_artifact'], **options)


        # Current SDK has no public Case accessor. Keep this version-sensitive
        # snapshot in the KUMA boundary; never manufacture an official Case ID.
        # 保存 SDK 实际加载的 Case，供宿主检查
        case = run_case(run)
        files.save('case.json', case)
        from agentbench.sdk.common.case_identity import case_content_sha256
        # 对照宿主指定的 Case ID 和内容摘要，确认没有执行错 Case
        fingerprint = case_content_sha256(case)
        expected = settings['expected_case']
        matched = run.case_id == expected['case_id'] and fingerprint == expected['content_sha256']
        files.save('case-selection.json', {'case_id': run.case_id, 'content_sha256': fingerprint,
                                          'expected_case': expected,
                                          'status': 'accepted' if matched else 'rejected'})
        if not matched:
            raise ValueError('SDK Case does not match the prepared identity; no Agent steps were executed')
        # 记录 Case 事件，这里沿用 case_generated 事件名，实际加载的是已有 Case
        from agentbench.observe.store import TraceStore
        TraceStore(output / 'sdk.jsonl', run.run_id, source='sdk').record(
            'case_generated', case_id=run.case_id, artifact='case.json')

        
        async def invoke(payload, folder, shared_provider):
            # 每轮调用同一个 Agent 会话，payload 仅包含当前 Input
            # shared_provider 是同一套 trace 采集对象
            request = folder / 'request.json'
            invocation_id = uuid4().hex
            observed_input = json.loads((folder / 'input.json').read_text())
            # 写下本轮调用请求，带上 Case、Input 和会话身份
            files.save(str(request.relative_to(output)), {
                'schema': 'abb.invocation.v1', 'run_id': invocation_id, 'session_id': run.run_id,
                'observation_context': {key: observed_input[key] for key in ('case_id', 'input_id') if isinstance(observed_input.get(key), str)},
                'agent_id': manifest['agent_id'], 'framework': manifest['framework'], 'input': payload})
            # 这里真正执行 Agent 的回答逻辑，并等待本轮调用结束
            await invoke_agent(root, request, folder, provider=shared_provider, session=agent_session)
            # 读取 Agent 写出的结果，交回上层对话流程
            return json.loads((folder / 'result.json').read_text())
        # 这里开始驱动整个 Case：取输入、调用上面的 invoke、提交输出并接收 Judge 报告
        summary = await drive_run(run, invoke, output, provider=provider, repo_path=root / 'agent')
        # 判断执行和证据是否完整，这里的退出码不判断 Judge 是否给出 pass
        return 0 if (summary['judge'] == 'received' and summary['otel'] == 'complete'
                     and summary['evidence'] == 'captured'
                     and summary['execution'] == 'succeeded') else 1
    except Exception as exc:
        # 出错时保存错误信息，并用退出码 1 通知宿主
        files.save('error.json', {'phase': 'case_generation' if run is None else 'evaluation',
                   'type': type(exc).__name__, 'message': str(exc), 'code': getattr(exc, 'code', None),
                   'retryable': getattr(exc, 'retryable', None), 'client_request_id': getattr(exc, 'client_request_id', None),
                   'request_id': getattr(exc, 'request_id', None)})
        return 1
    finally:
        # 无论成功还是失败，都关闭 Agent 会话并保存会话状态
        try:
            await agent_session.aclose()
        finally:
            files.save('session.json', agent_session.snapshot())
            # SDK Run 还停在等待输入或提交的阶段时，取消未完成的 Run
            if run is not None and run.state in ('ready', 'input_delivered'):
                run.cancel()
            # 最后刷新 trace 并关闭采集器
            provider.force_flush()
            provider.shutdown()


def main():
    # 容器进程先进入这里，读取 Agent 路径、产物路径和任务配置文件路径
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-root', type=Path, default=Path('/opt/agent'))
    parser.add_argument('--output', type=Path, default=Path('/run/abb-output'))
    parser.add_argument('--settings', type=Path, default=Path('/run/abb-input/evaluation.json'))
    args = parser.parse_args()
    # 从宿主挂载进来的 evaluation.json 读取生成或执行模式等配置
    settings = json.loads(args.settings.read_text()) if args.settings.is_file() else {}
    # 启动异步执行流程，并把它的退出码返回给进程入口
    return asyncio.run(execute(args.agent_root, args.output, settings))


if __name__ == '__main__':
    # Docker 执行 python -m agentbench.sdk.plugin.kuma.worker 时，从这里调用 main
    raise SystemExit(main())
