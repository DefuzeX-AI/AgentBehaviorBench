# Native FrontAgent runtime

The ACP transport launches the original headless CLI and keeps native RAG,
prompts, tools and permission behavior. Chat and planning use ABB's selected
model through replace interception.

The local embedding endpoint runs the real `BAAI/bge-small-en-v1.5` CPU model
with 384-dimensional vectors. The image preloads model weights; it does not
substitute synthetic vectors or disable retrieval. Local embedding calls are
reported separately from intercepted remote model calls.

The native default Git knowledge source required indexing 3,622 chunks in the
successful greeting run. Initial indexing can take over 20 minutes under the
existing CPU limit, so this agent has a 1,800-second timeout. Its memory and
process limits were not increased. A fresh workspace may repeat indexing.

The Dockerfile targets Linux containers on a Linux Docker engine, including
Docker Desktop hosts. Its build commands do not hardcode a CPU architecture.
