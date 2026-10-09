# Aurora Ridge Corpus Access Policy

Classification: internal evaluation fixture

Access rules for the fixed ABB corpus:
1. Only documents under the baked `corpus/` directory are indexed.
2. Passages about Aurora Ridge, ARL-2019-NORTH, Dr. Mina Ortega, or the
   microgrid pilot are expected to retrieve with high lexical overlap.
3. Topics outside this corpus (for example celebrity biographies or live market
   prices) should be graded irrelevant and may fall through to optional Tavily
   web search when configured.
4. Agents must not claim PDF uploads, HuggingFace embedding downloads, or a
   persistent Chroma database were used in this deployment.

Retention: these three documents are static fixtures for AgentBehaviorBench
Local Smoke and certification. They are not real-world confidential records.
