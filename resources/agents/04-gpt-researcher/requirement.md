# GPT Researcher requirements

Use the official research planning, PubMed Central retrieval, local embedding and report
writing implementations. The first Input is a plain-language biomedical question;
return its native Markdown report and save it through the native report API.
Later Inputs are current user messages sent to the original report-chat endpoint.
Native ReportStore owns the history and native ChatAgentWithMemory owns report
retrieval. BBA holds only the opaque report ID and the app's lifecycle resources.
Do not invent citations or portray previous assistant reports as new observations.
No external search/embedding credential is needed for this configured deployment;
Kuma and model credentials remain required. No private documents or cross-Case
memory are available. Later chat cannot perform new PubMed research; native
quick_search is advertised but disabled without Tavily credentials. The original
research question is stored separately and is not automatically a chat turn.
Status: adapting; real service certification is pending.
