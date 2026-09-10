# Wangyi Agent 模型统计（2026-09-09）

范围：`/Users/anthonyyao/Desktop/wangsong_project/ABB/wangyi/agents` 下全部 175 个 `runtime/meta.json` 对应的 Agent：tested 20，untested 155。

## 统计口径

这里保存的是运行适配包与留档，并非 175 份完整上游源码。默认模型从 Python AST 的 SPEC.model 提取（包括环境变量未设置时的默认值）；补充声明来自 model/llm 参数、赋值和 meta.json 的 fixed_env。注释、README 和 suites 中的 Judge 调用不计入模型声明。

历史观测限定为每个 Agent 的 `runtime/.smoke/raw-spans.json` 中 chat/completion 类 span 的模型字段，排除仅含模型标签的根 span。158 个 Agent 有该文件，其中 56 个记录了可提取的 LLM 模型；119 个没有这种证据（17 个无文件，102 个文件内无符合条件的模型记录）。**没有记录不表示没有调用。**

这些 trace 是插桩上报，可能由适配器赋值；不是网关实际转发的证明。模型名称原样保留，不代表确认其当前可用性。client imports 仅统计 runtime Python 的直接 import，不覆盖镜像内依赖、动态导入、生成代码或上游源码。

## 适配包默认模型

| SPEC.model 的默认声明 | Agent 数 |
| --- | ---: |
| `deepseek/deepseek-v4-flash` | 168 |
| `deepseek-v4-flash` | 2 |
| `openai:deepseek/deepseek-v4-flash` | 2 |
| `openrouter/deepseek/deepseek-v4-flash` | 1 |
| 未提取到 SPEC.model 字面量 | 2 |

上述四种名称都属于 DeepSeek 默认声明，共 **173** 个。两个例外是 009 agent-service-toolkit 和 010 Agentic-Bug-Hunter。010 的 fixed_env 指定 `qwen2.5:7b`，其 patch 另有 `qwen3:8b`、`qwen2.5:32b`；009 历史 smoke 的模型字段为 `fake`。

默认值会被环境配置或运行时替换覆盖，不能理解为 173 个 Agent 的历史调用都使用该模型。

## 历史 smoke 请求模型

按 Agent 去重；本次每个有模型记录的 Agent 仅出现一种请求模型。

| 记录值 | Agent 数 |
| --- | ---: |
| `deepseek-chat` | 23 |
| `glm-5.3-flash` | 17 |
| `deepseek/deepseek-v4-flash` | 9 |
| `deepseek-v4-flash` | 2 |
| `openai:deepseek-chat` | 2 |
| `fake` | 1 |
| `qwen2.5:7b` | 1 |
| `openrouter/deepseek-chat` | 1 |

合并 DeepSeek 名称前缀后：DeepSeek **37**，GLM **17**，Qwen **1**，fake **1**，其余 **119** 缺少本口径下的模型证据。

历史响应模型：`deepseek-v4-flash` 28 个；`glm-5.3-flash` 12 个；`deepseek-chat` 2 个；`deepseek/deepseek-v4-flash` 2 个；`fake` 1 个；`qwen2.5:7b` 1 个；`openai:deepseek-chat` 1 个。请求与响应名称不必相同。

## 客户端线索（不是全量 SDK 使用率）

| Python runtime 直接导入 | Agent 数 |
| --- | ---: |
| `langchain_openai` | 15 |
| `ollama` | 3 |
| `langchain_google_genai` | 2 |
| `langchain_ollama` | 1 |
| `openai` | 1 |
| `langchain_anthropic` | 1 |

Agent 可同时出现多个客户端。其余项目可能在 Docker 基础镜像里的上游代码发起调用，不能归为“不使用 LLM”。

Company 015 的适配脚本明确把 ChatGoogleGenerativeAI 和 ChatOpenAI 替换为统一模型调用，所以不能依据此目录的 DeepSeek trace 判断 Company 原生只用 DeepSeek。029 的 Anthropic 客户端也被替换。005 存在 `openai:gpt-5.6-sol`，062 存在 `gpt-3.5-turbo` 的代码声明，但声明不等于最终调用。014 的 `text-embedding-3-small` 是 embedding，不计为生成模型。

## 证据限制

- 32 个 Agent 的 smoke provider 字段包含 `fake`。这些 provider 标签不可信作真实出口证据；因此不据此统计 OpenRouter 覆盖率。
- 没有读取 .env 或任何凭据内容；仅静态读取运行代码/元数据和归档 smoke 模型标签。
- 没有启动 Agent，没有调用模型，没有下载上游项目。
- [JSON 明细](wangyi-llm-inventory.json) 保存每个 Agent 的模型集合、span 次数和最多前三条声明/导入定位样本。

## 全部 Agent 明细

| ID | Agent（链接至运行入口） | 目录分类 | 适配包默认模型 | smoke 请求模型 | 直接导入客户端 |
| --- | --- | --- | --- | --- | --- |
| 001 | [001_TauricResearch__TradingAgents](../../../wangyi/agents/untested/001_TauricResearch__TradingAgents/runtime/entrypoint.py) | untested | deepseek-v4-flash | deepseek-v4-flash | 未直接导入所扫描客户端 |
| 002 | [002_bytedance__deer-flow](../../../wangyi/agents/tested/002_bytedance__deer-flow/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | glm-5.3-flash | langchain_openai |
| 003 | [003_assafelovic__gpt-researcher](../../../wangyi/agents/untested/003_assafelovic__gpt-researcher/runtime/entrypoint.py) | untested | openai:deepseek/deepseek-v4-flash | openai:deepseek-chat | 未直接导入所扫描客户端 |
| 004 | [004_langchain-ai__deepagents](../../../wangyi/agents/untested/004_langchain-ai__deepagents/runtime/entrypoint.py) | untested | openai:deepseek/deepseek-v4-flash | openai:deepseek-chat | langchain_google_genai |
| 005 | [005_langchain-ai__open-swe](../../../wangyi/agents/tested/005_langchain-ai__open-swe/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | langchain_openai |
| 006 | [006_xerrors__Yuxi](../../../wangyi/agents/tested/006_xerrors__Yuxi/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | langchain_openai |
| 007 | [007_PurpleAILAB__Decepticon](../../../wangyi/agents/untested/007_PurpleAILAB__Decepticon/runtime/entrypoint.py) | untested | openrouter/deepseek/deepseek-v4-flash | openrouter/deepseek-chat | langchain_openai |
| 008 | [008_EvoScientist__EvoScientist](../../../wangyi/agents/tested/008_EvoScientist__EvoScientist/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 009 | [009_JoshuaC215__agent-service-toolkit](../../../wangyi/agents/tested/009_JoshuaC215__agent-service-toolkit/runtime/entrypoint.py) | tested | 未提取到 | fake | 未直接导入所扫描客户端 |
| 010 | [010_Awarexone__Agentic-Bug-Hunter](../../../wangyi/agents/tested/010_Awarexone__Agentic-Bug-Hunter/runtime/entrypoint.py) | tested | 未提取到 | qwen2.5:7b | langchain_ollama, ollama |
| 011 | [011_simonlin1212__TradingAgents-astock](../../../wangyi/agents/untested/011_simonlin1212__TradingAgents-astock/runtime/entrypoint.py) | untested | deepseek-v4-flash | deepseek-v4-flash | 未直接导入所扫描客户端 |
| 012 | [012_wassim249__fastapi-langgraph-agent-production-ready-template](../../../wangyi/agents/tested/012_wassim249__fastapi-langgraph-agent-production-ready-template/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_openai |
| 013 | [013_beenuar__AiSOC](../../../wangyi/agents/tested/013_beenuar__AiSOC/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 014 | [014_1517005260__graph-rag-agent](../../../wangyi/agents/tested/014_1517005260__graph-rag-agent/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 015 | [015_guy-hartstein__company-research-agent](../../../wangyi/agents/tested/015_guy-hartstein__company-research-agent/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_google_genai, langchain_openai |
| 016 | [016_ai-christianson__RA.Aid](../../../wangyi/agents/tested/016_ai-christianson__RA.Aid/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 017 | [017_olaxbt__ai-market-maker](../../../wangyi/agents/tested/017_olaxbt__ai-market-maker/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 018 | [018_zi-yue-1129__DATAGEN](../../../wangyi/agents/tested/018_zi-yue-1129__DATAGEN/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | langchain_openai |
| 019 | [019_ginlix-ai__LangAlpha](../../../wangyi/agents/tested/019_ginlix-ai__LangAlpha/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_openai |
| 020 | [020_ShenSeanChen__waku-agent](../../../wangyi/agents/tested/020_ShenSeanChen__waku-agent/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | 未直接导入所扫描客户端 |
| 021 | [021_rotemweiss57__gpt-newspaper](../../../wangyi/agents/untested/021_rotemweiss57__gpt-newspaper/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_openai |
| 022 | [022_darwin-lau__langmanus](../../../wangyi/agents/untested/022_darwin-lau__langmanus/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 023 | [023_rcortx__kiwiq](../../../wangyi/agents/untested/023_rcortx__kiwiq/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 024 | [024_SalesforceAIResearch__enterprise-deep-research](../../../wangyi/agents/untested/024_SalesforceAIResearch__enterprise-deep-research/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 026 | [026_test-zeus-ai__testzeus-hercules](../../../wangyi/agents/untested/026_test-zeus-ai__testzeus-hercules/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 027 | [027_EuniAI__Prometheus](../../../wangyi/agents/untested/027_EuniAI__Prometheus/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 028 | [028_Fullive-AI__Anima](../../../wangyi/agents/untested/028_Fullive-AI__Anima/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 029 | [029_hrithikkoduri__WebRover](../../../wangyi/agents/untested/029_hrithikkoduri__WebRover/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_anthropic, langchain_openai |
| 030 | [030_mikekelly__AgentK](../../../wangyi/agents/untested/030_mikekelly__AgentK/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 031 | [031_FareedKhan-dev__production-grade-agentic-system](../../../wangyi/agents/untested/031_FareedKhan-dev__production-grade-agentic-system/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 032 | [032_XD-MHLOO__Osintgraph](../../../wangyi/agents/untested/032_XD-MHLOO__Osintgraph/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 033 | [033_zamalali__DeepGit](../../../wangyi/agents/untested/033_zamalali__DeepGit/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 034 | [034_Pan-Chera__Multi-Agent-CAD](../../../wangyi/agents/untested/034_Pan-Chera__Multi-Agent-CAD/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 035 | [035_lc2panda__alphastream](../../../wangyi/agents/untested/035_lc2panda__alphastream/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 036 | [036_cuga-project__cuga-agent](../../../wangyi/agents/untested/036_cuga-project__cuga-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 037 | [037_NVIDIA-AI-Blueprints__aiq](../../../wangyi/agents/untested/037_NVIDIA-AI-Blueprints__aiq/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 038 | [038_icey1287__SuperMew](../../../wangyi/agents/untested/038_icey1287__SuperMew/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 039 | [039_langchain-ai__react-agent](../../../wangyi/agents/tested/039_langchain-ai__react-agent/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_openai, ollama, openai |
| 040 | [040_nirbar1985__ai-travel-agent](../../../wangyi/agents/untested/040_nirbar1985__ai-travel-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 041 | [041_vinay-gatech__stocks-insights-ai-agent](../../../wangyi/agents/tested/041_vinay-gatech__stocks-insights-ai-agent/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 042 | [042_Chen-zexi__open-ptc-agent](../../../wangyi/agents/untested/042_Chen-zexi__open-ptc-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 043 | [043_isoftstone-data-intelligence-ai__efflux-backend](../../../wangyi/agents/untested/043_isoftstone-data-intelligence-ai__efflux-backend/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 044 | [044_braincrew-lab__langgraph-mcp-agents](../../../wangyi/agents/untested/044_braincrew-lab__langgraph-mcp-agents/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 045 | [045_stophobia__deerflow2.0-enhanced](../../../wangyi/agents/untested/045_stophobia__deerflow2.0-enhanced/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 046 | [046_Westlake-AGI-Lab__AppAgentX](../../../wangyi/agents/untested/046_Westlake-AGI-Lab__AppAgentX/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 047 | [047_nuglifeleoji__Options-Analytics-Agent](../../../wangyi/agents/untested/047_nuglifeleoji__Options-Analytics-Agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 048 | [048_langtalks__swe-agent](../../../wangyi/agents/untested/048_langtalks__swe-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 049 | [049_tablegpt__tablegpt-agent](../../../wangyi/agents/untested/049_tablegpt__tablegpt-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 050 | [050_zhongyu09__openchatbi](../../../wangyi/agents/untested/050_zhongyu09__openchatbi/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 051 | [051_51bitquant__ai-hedge-fund-crypto](../../../wangyi/agents/untested/051_51bitquant__ai-hedge-fund-crypto/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 052 | [052_wassim249__YT-Navigator](../../../wangyi/agents/untested/052_wassim249__YT-Navigator/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 053 | [053_esxr__langgraph-mcp](../../../wangyi/agents/untested/053_esxr__langgraph-mcp/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 054 | [054_NicholasGoh__fastapi-mcp-langgraph-template](../../../wangyi/agents/untested/054_NicholasGoh__fastapi-mcp-langgraph-template/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 055 | [055_psyray__oasis](../../../wangyi/agents/untested/055_psyray__oasis/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 056 | [056_bcefghj__multi-agent-ecommerce-system](../../../wangyi/agents/untested/056_bcefghj__multi-agent-ecommerce-system/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 057 | [057_vibesurf-ai__VibeSurf](../../../wangyi/agents/untested/057_vibesurf-ai__VibeSurf/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 058 | [058_NanGePlus__LangGraphChatBot](../../../wangyi/agents/untested/058_NanGePlus__LangGraphChatBot/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 059 | [059_SponsioLabs__Sponsio](../../../wangyi/agents/untested/059_SponsioLabs__Sponsio/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 060 | [060_Tswoen__Paper-Agent](../../../wangyi/agents/untested/060_Tswoen__Paper-Agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 061 | [061_brainqub3__jar3d_meta_expert](../../../wangyi/agents/untested/061_brainqub3__jar3d_meta_expert/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 062 | [062_john-adeojo__graph_websearch_agent](../../../wangyi/agents/tested/062_john-adeojo__graph_websearch_agent/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | langchain_openai |
| 063 | [063_Arvo-AI__aurora](../../../wangyi/agents/untested/063_Arvo-AI__aurora/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 064 | [064_skygazer42__GustoBot](../../../wangyi/agents/untested/064_skygazer42__GustoBot/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 065 | [065_togethercomputer__open_deep_research](../../../wangyi/agents/untested/065_togethercomputer__open_deep_research/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 066 | [066_Xeron2000__openOii](../../../wangyi/agents/untested/066_Xeron2000__openOii/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 067 | [067_amanv1906__GENAI-CareerAssistant-Multiagent](../../../wangyi/agents/untested/067_amanv1906__GENAI-CareerAssistant-Multiagent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 068 | [068_kaymen99__sales-outreach-automation-langgraph](../../../wangyi/agents/untested/068_kaymen99__sales-outreach-automation-langgraph/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 069 | [069_bcefghj__smart-cs-multi-agent](../../../wangyi/agents/untested/069_bcefghj__smart-cs-multi-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 070 | [070_NVlabs__SpatialClaw](../../../wangyi/agents/untested/070_NVlabs__SpatialClaw/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 071 | [071_cnunescoelho__kiroku](../../../wangyi/agents/untested/071_cnunescoelho__kiroku/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 072 | [072_NVIDIA-AI-IOT__remembr](../../../wangyi/agents/untested/072_NVIDIA-AI-IOT__remembr/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 073 | [073_CronusL-1141__AI-company](../../../wangyi/agents/untested/073_CronusL-1141__AI-company/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 074 | [074_EthanXiang777__circuit-framework](../../../wangyi/agents/untested/074_EthanXiang777__circuit-framework/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 075 | [075_GoogleCloudPlatform__cymbal-air-toolbox-demo](../../../wangyi/agents/untested/075_GoogleCloudPlatform__cymbal-air-toolbox-demo/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 076 | [076_ivebotunac__PrimoAgent](../../../wangyi/agents/untested/076_ivebotunac__PrimoAgent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 077 | [077_Negai-ai__AgentClaw](../../../wangyi/agents/untested/077_Negai-ai__AgentClaw/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 078 | [078_lhh737__LangChain-ReAct-Agent](../../../wangyi/agents/untested/078_lhh737__LangChain-ReAct-Agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 079 | [079_didilili__shopkeeper-agent](../../../wangyi/agents/untested/079_didilili__shopkeeper-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 080 | [080_kmeanskaran__stock-agent-ops](../../../wangyi/agents/untested/080_kmeanskaran__stock-agent-ops/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 081 | [081_jd-opensource__JoySafeter](../../../wangyi/agents/untested/081_jd-opensource__JoySafeter/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 082 | [082_liangdabiao__langgraph_multi-agent-rag-customer-support](../../../wangyi/agents/tested/082_liangdabiao__langgraph_multi-agent-rag-customer-support/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 083 | [083_hwchase17__langchain-streamlit-template](../../../wangyi/agents/untested/083_hwchase17__langchain-streamlit-template/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 084 | [084_yolo-hyl__medical-rag](../../../wangyi/agents/untested/084_yolo-hyl__medical-rag/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 085 | [085_dhruvsinghal09__Adaptive-Rag](../../../wangyi/agents/untested/085_dhruvsinghal09__Adaptive-Rag/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 086 | [086_HKUSTDial__DeepFund](../../../wangyi/agents/untested/086_HKUSTDial__DeepFund/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 087 | [087_langchain-ai__new-langgraph-project](../../../wangyi/agents/untested/087_langchain-ai__new-langgraph-project/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 088 | [088_goruck__home-generative-agent](../../../wangyi/agents/untested/088_goruck__home-generative-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 089 | [089_jarrycyx__openlens-ai](../../../wangyi/agents/untested/089_jarrycyx__openlens-ai/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 090 | [090_NVIDIA-AI-Blueprints__ai-virtual-assistant](../../../wangyi/agents/untested/090_NVIDIA-AI-Blueprints__ai-virtual-assistant/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 091 | [091_quarqlabs__argus](../../../wangyi/agents/tested/091_quarqlabs__argus/runtime/entrypoint.py) | tested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 092 | [092_kaymen99__langgraph-email-automation](../../../wangyi/agents/untested/092_kaymen99__langgraph-email-automation/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 093 | [093_SecurityClaw__SecurityClaw](../../../wangyi/agents/untested/093_SecurityClaw__SecurityClaw/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 094 | [094_Lyra-stellAI__BYO-LLM-WIKI](../../../wangyi/agents/untested/094_Lyra-stellAI__BYO-LLM-WIKI/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 095 | [095_artnoage__Podcast](../../../wangyi/agents/untested/095_artnoage__Podcast/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 096 | [096_lingxi-agent__Lingxi](../../../wangyi/agents/untested/096_lingxi-agent__Lingxi/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 097 | [097_mfmezger__conversational-agent-langchain](../../../wangyi/agents/untested/097_mfmezger__conversational-agent-langchain/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 098 | [098_tyxben__AI_novel](../../../wangyi/agents/untested/098_tyxben__AI_novel/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 099 | [099_bernatsampera__event-deep-research](../../../wangyi/agents/untested/099_bernatsampera__event-deep-research/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 100 | [100_Y-Research-SBU__PosterGen](../../../wangyi/agents/untested/100_Y-Research-SBU__PosterGen/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 101 | [101_datawhalechina__vibe-blog](../../../wangyi/agents/untested/101_datawhalechina__vibe-blog/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 102 | [102_huygiatrng__AlpacaTradingAgent](../../../wangyi/agents/untested/102_huygiatrng__AlpacaTradingAgent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 103 | [103_KodyKendall__LlamaBot](../../../wangyi/agents/untested/103_KodyKendall__LlamaBot/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 104 | [104_billy-enrizky__openbrowser-ai](../../../wangyi/agents/untested/104_billy-enrizky__openbrowser-ai/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 105 | [105_lgesuellip__langgraph-whatsapp-agent](../../../wangyi/agents/untested/105_lgesuellip__langgraph-whatsapp-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 106 | [106_NVIDIA-AI-Blueprints__vulnerability-analysis](../../../wangyi/agents/untested/106_NVIDIA-AI-Blueprints__vulnerability-analysis/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 107 | [107_wshobson__financial-chat](../../../wangyi/agents/untested/107_wshobson__financial-chat/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 108 | [108_nicoladisabato__MultiAgenticRAG](../../../wangyi/agents/untested/108_nicoladisabato__MultiAgenticRAG/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 109 | [109_eosho__langchain_data_agent](../../../wangyi/agents/untested/109_eosho__langchain_data_agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 110 | [110_growgraph__ontocast](../../../wangyi/agents/untested/110_growgraph__ontocast/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 111 | [111_louisgthier__decompai](../../../wangyi/agents/untested/111_louisgthier__decompai/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 112 | [112_Gen-Future__ExcelMind](../../../wangyi/agents/untested/112_Gen-Future__ExcelMind/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 113 | [113_jamwithai__observable-job-agent](../../../wangyi/agents/untested/113_jamwithai__observable-job-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 114 | [114_Nachoeigu__agentic-customer-service-medical-clinic](../../../wangyi/agents/untested/114_Nachoeigu__agentic-customer-service-medical-clinic/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 115 | [115_kulkarnirohit123__cra-agent](../../../wangyi/agents/untested/115_kulkarnirohit123__cra-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 116 | [116_Yanyutin753__LambChat](../../../wangyi/agents/untested/116_Yanyutin753__LambChat/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 117 | [117_Yonom__assistant-ui-langgraph-fastapi](../../../wangyi/agents/untested/117_Yonom__assistant-ui-langgraph-fastapi/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 118 | [118_HezaoHezao__poirot](../../../wangyi/agents/untested/118_HezaoHezao__poirot/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 119 | [119_fzn0x__watchtower](../../../wangyi/agents/untested/119_fzn0x__watchtower/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 120 | [120_jank__curiosity](../../../wangyi/agents/untested/120_jank__curiosity/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 121 | [121_yycyyv__M-Cube](../../../wangyi/agents/untested/121_yycyyv__M-Cube/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 122 | [122_muratcankoylan__readwren](../../../wangyi/agents/untested/122_muratcankoylan__readwren/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 123 | [123_guangshu100__BidMaster-Pro](../../../wangyi/agents/untested/123_guangshu100__BidMaster-Pro/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 124 | [124_tavily-ai__meeting-prep-agent](../../../wangyi/agents/untested/124_tavily-ai__meeting-prep-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 125 | [125_ZhangJinHaHaHa__FinchainAgent](../../../wangyi/agents/untested/125_ZhangJinHaHaHa__FinchainAgent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 126 | [126_tevslin__meeting-reporter](../../../wangyi/agents/untested/126_tevslin__meeting-reporter/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 127 | [127_ai-forever__giga_agent](../../../wangyi/agents/untested/127_ai-forever__giga_agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 128 | [128_duartecaldascardoso__article-explainer](../../../wangyi/agents/untested/128_duartecaldascardoso__article-explainer/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_openai |
| 129 | [129_chatchat-space__LangGraph-Chatchat](../../../wangyi/agents/untested/129_chatchat-space__LangGraph-Chatchat/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 130 | [130_didilili__deepsearch-agents](../../../wangyi/agents/untested/130_didilili__deepsearch-agents/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 131 | [131_OS3Lab__agent4kdump](../../../wangyi/agents/untested/131_OS3Lab__agent4kdump/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 132 | [132_akamai__patchdiff-ai](../../../wangyi/agents/untested/132_akamai__patchdiff-ai/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 133 | [133_tarun7r__deep-research-agent](../../../wangyi/agents/untested/133_tarun7r__deep-research-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 134 | [134_kaymen99__personal-ai-assistant](../../../wangyi/agents/untested/134_kaymen99__personal-ai-assistant/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 135 | [135_skygazer42__Weaver](../../../wangyi/agents/untested/135_skygazer42__Weaver/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 136 | [136_Yourdaylight__stock_datasource](../../../wangyi/agents/untested/136_Yourdaylight__stock_datasource/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 137 | [137_GU-Cryptography__anykb](../../../wangyi/agents/untested/137_GU-Cryptography__anykb/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 138 | [138_YUHAO-corn__manufacturing-agents](../../../wangyi/agents/untested/138_YUHAO-corn__manufacturing-agents/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 139 | [139_EYamanS__texel-studio](../../../wangyi/agents/untested/139_EYamanS__texel-studio/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 140 | [140_Y-Research-SBU__TimeSeriesScientist](../../../wangyi/agents/untested/140_Y-Research-SBU__TimeSeriesScientist/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek/deepseek-v4-flash | langchain_openai |
| 141 | [141_FeiCoder__BreadFree-Simu](../../../wangyi/agents/untested/141_FeiCoder__BreadFree-Simu/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 142 | [142_CopilotKit__scene-creator-copilot](../../../wangyi/agents/untested/142_CopilotKit__scene-creator-copilot/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 143 | [143_FareedKhan-dev__scalable-rag-pipeline](../../../wangyi/agents/untested/143_FareedKhan-dev__scalable-rag-pipeline/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 144 | [144_kaymen99__Upwork-AI-jobs-applier](../../../wangyi/agents/untested/144_kaymen99__Upwork-AI-jobs-applier/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 145 | [145_kargarisaac__telegram_link_summarizer_agent](../../../wangyi/agents/untested/145_kargarisaac__telegram_link_summarizer_agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 146 | [146_xiongQvQ__AI_Find_Customer](../../../wangyi/agents/untested/146_xiongQvQ__AI_Find_Customer/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 147 | [147_itshyao__proxyless-llm-websearch](../../../wangyi/agents/untested/147_itshyao__proxyless-llm-websearch/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 148 | [148_langchain-ai__langgraph-fullstack-python](../../../wangyi/agents/untested/148_langchain-ai__langgraph-fullstack-python/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 149 | [149_123-qw-as__Beacon](../../../wangyi/agents/untested/149_123-qw-as__Beacon/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 150 | [150_BjornMelin__docmind-ai-llm](../../../wangyi/agents/untested/150_BjornMelin__docmind-ai-llm/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 151 | [151_iblameandrew__open-deepthink](../../../wangyi/agents/untested/151_iblameandrew__open-deepthink/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 152 | [152_argonne-lcf__ChemGraph](../../../wangyi/agents/untested/152_argonne-lcf__ChemGraph/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 153 | [153_Ganador1__FenixAI_tradingBot](../../../wangyi/agents/untested/153_Ganador1__FenixAI_tradingBot/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 154 | [154_EricHong123__B-agent](../../../wangyi/agents/untested/154_EricHong123__B-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 155 | [155_hwchase17__autoresearch-agents](../../../wangyi/agents/untested/155_hwchase17__autoresearch-agents/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 156 | [156_leonzzz435__garmin-ai-coach](../../../wangyi/agents/untested/156_leonzzz435__garmin-ai-coach/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 157 | [157_kevin333353__jobsmith](../../../wangyi/agents/untested/157_kevin333353__jobsmith/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 158 | [158_neopen__story-shot-agent](../../../wangyi/agents/untested/158_neopen__story-shot-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 159 | [159_bamboo-moon__zhisaotong-Agent](../../../wangyi/agents/untested/159_bamboo-moon__zhisaotong-Agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | glm-5.3-flash | 未直接导入所扫描客户端 |
| 160 | [160_Neon549__Alpha_stock](../../../wangyi/agents/untested/160_Neon549__Alpha_stock/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 161 | [161_waseens__deep-search-pro](../../../wangyi/agents/untested/161_waseens__deep-search-pro/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 162 | [162_colossus-lab__openarg_backend](../../../wangyi/agents/untested/162_colossus-lab__openarg_backend/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 163 | [163_NVIDIA-AI-Blueprints__biomedical-aiq-research-agent](../../../wangyi/agents/untested/163_NVIDIA-AI-Blueprints__biomedical-aiq-research-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 164 | [164_kaymen99__local-rag-researcher-deepseek](../../../wangyi/agents/untested/164_kaymen99__local-rag-researcher-deepseek/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | langchain_openai, ollama |
| 165 | [165_ro-anderson__multi-agent-rag-customer-support](../../../wangyi/agents/untested/165_ro-anderson__multi-agent-rag-customer-support/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | deepseek-chat | 未直接导入所扫描客户端 |
| 166 | [166_twanew__OmniWriter](../../../wangyi/agents/untested/166_twanew__OmniWriter/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 167 | [167_IatomicreactorI__CSGOTrading](../../../wangyi/agents/untested/167_IatomicreactorI__CSGOTrading/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 168 | [168_jaguarliuu__xunlong](../../../wangyi/agents/untested/168_jaguarliuu__xunlong/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 169 | [169_Eldergenix__Plato-Scientific-Research-Autonomous-Agent](../../../wangyi/agents/untested/169_Eldergenix__Plato-Scientific-Research-Autonomous-Agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 170 | [170_bcefghj__medical-multi-agent-system](../../../wangyi/agents/untested/170_bcefghj__medical-multi-agent-system/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 171 | [171_agruai__company-research-agent](../../../wangyi/agents/untested/171_agruai__company-research-agent/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 172 | [172_seanlxh__Air-Lingjing](../../../wangyi/agents/untested/172_seanlxh__Air-Lingjing/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 173 | [173_shodan1q__zeroapp](../../../wangyi/agents/untested/173_shodan1q__zeroapp/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 174 | [174_bcefghj__agent-knowledge-hub](../../../wangyi/agents/untested/174_bcefghj__agent-knowledge-hub/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 175 | [175_KRATSZ__LabScript-AI](../../../wangyi/agents/untested/175_KRATSZ__LabScript-AI/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |
| 176 | [176_ljxpython__ai-agent-platform](../../../wangyi/agents/untested/176_ljxpython__ai-agent-platform/runtime/entrypoint.py) | untested | deepseek/deepseek-v4-flash | 未记录 | 未直接导入所扫描客户端 |

## 对 ABB 拦截设计的含义

该目录足以证明应覆盖 OpenAI 兼容客户端、Google 客户端、Anthropic 客户端和 Ollama，但不足以枚举原生 REST/gRPC、stream、模型能力的完整矩阵。下一步必须检查对应上游源码/镜像中的实际模型调用及传输，不能用统一改写后的 smoke 测试代替原生协议验收。

