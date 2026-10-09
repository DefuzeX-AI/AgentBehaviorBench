"""流式对话 - 使用 LangChain ReAct Agent"""

import json
from typing import Any, AsyncGenerator, Dict

from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from .config import get_config
from .excel_loader import get_loader
from .knowledge_base import get_knowledge_base, format_knowledge_context
from .tools import ALL_TOOLS


class CustomJSONEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，处理 Pandas/Numpy 类型"""
    
    def default(self, obj):
        # 处理 Pandas Timestamp
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        # 处理 numpy 类型
        if hasattr(obj, 'item'):
            return obj.item()
        # 处理 numpy 数组
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        # 处理 pandas NaT
        if str(obj) == 'NaT':
            return None
        # 处理 pandas NA
        if str(obj) == '<NA>':
            return None
        return super().default(obj)


def json_dumps(obj, **kwargs):
    """使用自定义编码器的 JSON 序列化函数"""
    return json.dumps(obj, cls=CustomJSONEncoder, **kwargs)


SYSTEM_PROMPT = """你是一个专业的 Excel 数据分析助手。

## 当前 Excel 信息
{excel_summary}

## 相关知识参考
{knowledge_context}

## 工作原则
1. 根据用户问题，判断是否需要使用工具
2. 如需工具，调用合适的工具获取数据
3. 工具调用成功后，根据结果回答用户问题
4. **最终回答直接给出结论和分析**，不要描述"我使用了xx工具"或"我进行了xx操作"等内部过程
5. 回答语气友好，使用中文，并给出自己的一些数据分析建议
6. 如果有相关知识参考，请遵循其中的规则和建议
"""


def get_llm():
    """获取 LLM 实例"""
    config = get_config()
    provider = config.model.get_active_provider()
    return ChatOpenAI(
        model=provider.model_name,
        api_key=provider.api_key,
        base_url=provider.base_url if provider.base_url else None,
        temperature=provider.temperature,
        max_tokens=provider.max_tokens,
    )


async def stream_chat(message: str, history: list = None) -> AsyncGenerator[Dict[str, Any], None]:
    """执行对话 - 使用 LangChain ReAct Agent
    
    Args:
        message: 当前用户消息
        history: 历史对话列表，每项为 {"role": "user"|"assistant", "content": "..."}
    """
    loader = get_loader()
    
    if not loader.is_loaded:
        yield {"type": "error", "content": "请先上传 Excel 文件"}
        return
    
    try:
        excel_summary = loader.get_summary()
        llm = get_llm()
        
        # 主对话开始
        yield {"type": "thinking", "content": "正在规划解答..."}
        
        # 检索相关知识
        knowledge_context = "暂无相关知识参考。"
        kb = get_knowledge_base()
        if kb:
            try:
                stats = kb.get_stats()
                print(f"[知识库] 状态: {stats['total_entries']} 条知识")
                relevant_knowledge = kb.search(query=message)
                print(f"[知识库] 检索到 {len(relevant_knowledge)} 条相关知识")
                if relevant_knowledge:
                    knowledge_context = format_knowledge_context(relevant_knowledge)
                    yield {"type": "thinking", "content": f"找到 {len(relevant_knowledge)} 条相关知识参考..."}
            except Exception as e:
                print(f"[知识库检索] 警告: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("[知识库] 未启用或初始化失败")
        
        # 构建系统提示
        system_prompt = SYSTEM_PROMPT.format(
            excel_summary=excel_summary,
            knowledge_context=knowledge_context
        )
        
        # 获取当前活跃表信息
        active_table_info = loader.get_active_table_info()
        current_table_name = active_table_info.filename if active_table_info else "未知表"
        
        # 创建 ReAct Agent
        agent = create_react_agent(llm, ALL_TOOLS)
        
        # 构建消息 - 包含历史对话
        current_message = f"[当前操作表: {current_table_name}] {message}"
        messages = [SystemMessage(content=system_prompt)]
        
        # 添加历史对话
        if history:
            from langchain_core.messages import AIMessage
            for msg in history:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg.get("content", "")))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg.get("content", "")))
        
        # 添加当前用户消息
        messages.append(HumanMessage(content=current_message))
        
        # 使用 stream_mode="messages" 获取真正的流式输出
        thinking_content = ""
        final_content = ""
        tool_call_yielded = False
        thinking_done_sent = False
        
        # 累积工具调用信息
        # 按 index 累积 args（因为大部分 args chunks 没有 id，只有 index）
        # 按 id 记录工具名称（因为带 id 的 chunks 有 name）
        tool_names_by_id = {}  # id -> name
        args_by_index = {}  # index -> args_str
        tool_call_order = []  # 记录工具调用的顺序 [(id, index), ...]
        yielded_tool_ids = set()
        
        async for chunk in agent.astream(
            {"messages": messages},
            stream_mode="messages"
        ):
            # chunk 是一个 tuple: (message, metadata)
            if isinstance(chunk, tuple) and len(chunk) >= 2:
                msg, metadata = chunk[0], chunk[1]
                
                # 处理 AIMessageChunk (LLM 输出)
                if isinstance(msg, AIMessageChunk):
                    content = msg.content if hasattr(msg, 'content') else ""
                    tool_call_chunks = getattr(msg, 'tool_call_chunks', [])
                    
                    # 累积工具调用的 chunks
                    if tool_call_chunks:
                        for tcc in tool_call_chunks:
                            tc_id = tcc.get("id")
                            tc_name = tcc.get("name", "")
                            tc_args = tcc.get("args", "")
                            tc_index = tcc.get("index", 0)
                            
                            # 如果有新的工具 id 出现（带 name），记录下来
                            if tc_id and tc_name:
                                if tc_id not in tool_names_by_id:
                                    tool_call_order.append((tc_id, tc_index))
                                    if not thinking_done_sent:
                                        yield {"type": "thinking_done"}
                                        thinking_done_sent = True
                                tool_names_by_id[tc_id] = tc_name
                            
                            # 累积 args（按 index）
                            if tc_args:
                                if tc_index not in args_by_index:
                                    args_by_index[tc_index] = ""
                                args_by_index[tc_index] += tc_args
                    
                    # 如果有文本内容
                    if content:
                        if tool_call_yielded:
                            # 工具调用后的内容是最终回答
                            final_content += content
                            yield {"type": "token", "content": content}
                        else:
                            # 工具调用前的内容是思考过程
                            thinking_content += content
                            yield {"type": "thinking", "content": thinking_content}
                
                # 处理 ToolMessage (工具结果) - 此时工具调用已完成，args 已完整
                elif isinstance(msg, ToolMessage):
                    tool_call_id = msg.tool_call_id if hasattr(msg, 'tool_call_id') else None
                    tool_name = msg.name if hasattr(msg, 'name') else "tool"
                    tool_content = msg.content
                    
                    # 在发送 tool_result 之前，先发送对应的 tool_call
                    if tool_call_id and tool_call_id not in yielded_tool_ids:
                        yielded_tool_ids.add(tool_call_id)
                        tool_call_yielded = True
                        
                        # 找到这个工具调用的 index
                        tc_index = 0
                        for (tid, idx) in tool_call_order:
                            if tid == tool_call_id:
                                tc_index = idx
                                break
                        
                        # 从 args_by_index 获取 args
                        args_str = args_by_index.get(tc_index, "{}")
                        
                        # 解析 args - 注意可能累积了多个 JSON 对象
                        try:
                            # 尝试直接解析
                            args = json.loads(args_str)
                        except json.JSONDecodeError:
                            # 如果失败，可能是多个 JSON 对象连在一起，取最后一个完整的
                            # 或者尝试找到第一个完整的 JSON
                            try:
                                # 找到最后一个 { 开始的 JSON
                                last_brace = args_str.rfind('{"')
                                if last_brace >= 0:
                                    args = json.loads(args_str[last_brace:])
                                else:
                                    args = {"raw": args_str}
                            except:
                                args = {"raw": args_str}
                        
                        # 获取工具名称
                        tc_name = tool_names_by_id.get(tool_call_id, tool_name)
                        
                        yield {
                            "type": "tool_call",
                            "name": tc_name,
                            "args": args,
                        }
                        
                        # 清除已处理的 args，为下一个工具调用准备
                        if tc_index in args_by_index:
                            del args_by_index[tc_index]
                    
                    # 发送工具结果
                    try:
                        result = json.loads(tool_content)
                    except:
                        result = {"result": tool_content}
                    
                    yield {
                        "type": "tool_result",
                        "name": tool_name,
                        "result": result,
                    }
        
        # 流式结束
        if not tool_call_yielded and thinking_content:
            # 没有工具调用，thinking_content 就是最终回答
            if not thinking_done_sent:
                yield {"type": "thinking_done"}
            yield {"type": "clear_thinking"}
            yield {"type": "token", "content": thinking_content}
            yield {"type": "done", "content": thinking_content}
        elif final_content:
            yield {"type": "done", "content": final_content}
        else:
            yield {"type": "done", "content": ""}
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield {"type": "thinking_done"}
        yield {"type": "error", "content": f"处理出错: {str(e)}"}
