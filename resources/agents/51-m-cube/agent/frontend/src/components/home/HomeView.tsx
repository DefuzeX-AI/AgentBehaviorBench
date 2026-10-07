import React from "react";

type WorkflowItem = {
  id: string;
  title: string;
  agent: string;
  capability: string;
  status: string;
};

export default function HomeView() {
  const workflows: WorkflowItem[] = [
    {
      id: "01",
      title: "说明书撰写",
      agent: "AGENT_INVENTOR & AGENT_ATTORNEY",
      capability:
        "基于技术交底书进行原子级特征拆解和附图分析，通过多智能体协作撰写权利要求和说明书，并提供交底书可溯源性检查和逻辑审查。",
      status: "READY",
    },
    {
      id: "02",
      title: "OA (审查意见) 答复",
      agent: "AGENT_RED_TEAM & AGENT_DEFENDER",
      capability:
        "深度解析审查意见，分析本案与对比文件，根据审查意见确定修改策略以及挖掘说明书后备特征，并进行特征核验，最终生成《意见陈述书》与A33合规替换页。",
      status: "READY",
    },
    {
      id: "03",
      title: "专利对比",
      agent: "AGENT_ANALYST",
      capability:
        "分析本案与对比文件图文，进行特征和连接关系的比对，输出本案专利的新颖性/创造性风险分级和后续修改建议。",
      status: "READY",
    },
    {
      id: "04",
      title: "专利润色",
      agent: "AGENT_LINGUIST_LEGAL",
      capability:
        "针对申请文件进行重构，排查权利要求中的前序词不清、缺少引用基础、非技术特征等形式缺陷，并对修改后的文件进行逻辑审查。",
      status: "READY",
    },
  ];

  return (
    <div className="w-full max-w-5xl mx-auto pb-32 font-sans text-gray-800 animate-fade-in-up pt-12">
      <div className="border-b border-gray-200 pb-16 mb-20">
        <div className="flex items-center gap-4 mb-6">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight">M-Cube</h1>
        </div>

        <p className="text-[16.5px] leading-[1.9] text-gray-800 max-w-4xl text-justify font-serif">
          M-Cube是一个多维推演、多模态解析、多重核验的多智能体协同专利撰写助手，底层依托 LangGraph 编排多智能体，通过引入多个
          AI Agents进行多思维步骤的思考，在不同阶段根据专利文件文字和附图的多模态信息完成各项功能，
          包括专利撰写、OA答复、专利对比和专利润色，并在过程中引入多重核验，包括说明书支撑、对比文件图文核验等逻辑核验，形成
          技术方案自洽、权利要求稳固、附图与文字互证的专利文件输出。
        </p>
      </div>

      <div className="space-y-4 mb-24">
        <h3 className="text-xl font-bold text-gray-900 tracking-wide uppercase mb-8">核心功能</h3>

        <div className="border-t border-gray-200">
          {workflows.map((flow) => (
            <div key={flow.id} className="flex flex-col md:flex-row md:items-start py-10 border-b border-gray-200 group">
              <div className="w-full md:w-5/12 mb-6 md:mb-0 pr-8">
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-[16px] font-mono font-bold text-gray-400 group-hover:text-gray-900 transition-colors">
                    {flow.id}
                  </span>
                  <h4 className="text-[20px] font-bold text-gray-900">{flow.title}</h4>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <span className="text-[13px] text-emerald-700 font-bold uppercase tracking-wider">● {flow.status}</span>
                </div>
              </div>

              <div className="w-full md:w-7/12 pl-0 md:pl-8 md:border-l border-gray-200">
                <div className="text-[15.5px] leading-[1.8] text-gray-800 text-justify">
                  <strong className="text-gray-900 block mb-2">功能：</strong>
                  {flow.capability}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
