# AI Data Science Team — Pandas Data Analyst (LangGraph)

Source: [business-science/ai-data-science-team](https://github.com/business-science/ai-data-science-team)
at `4ffeb7f38178aa250917f29b01355f8b89ba809e` (MIT), imported with `agentbench agent add`.
The committed `agent/` snapshot omits `img/` (README screenshots), `examples/` (notebooks),
`data/northwind.db` (24 MB, used only by the SQL apps) and a stray `.DS_Store` to keep the unit small;
no source file was changed. `agent add -b` (GLM build model) stopped with "OpenRouter returned an invalid structured
configuration", so `agent.toml`, `Dockerfile`, `requirement.md` and `bindings/bridge.py` are hand-written.

## What is deployed

The repository's **Pandas Data Analyst app** (`apps/pandas-data-analyst-app/app.py`): a
`PandasDataAnalyst` multi-agent (`ai_data_science_team/multiagents/pandas_data_analyst.py`) — routing
preprocessor → `DataWranglingAgent` (writes and executes a pandas function, with up to 3 fix retries)
→ optional `DataVisualizationAgent` (Plotly) → summary. Settings match the app:
`bypass_recommended_steps=True`, `n_samples=100`, `log=False`, `ChatOpenAI(model="gpt-4o-mini")`.

- The app asks the user to upload a CSV. This deployment pre-loads the repository's own
  `data/bike_sales_data.csv`, the dataset the app's "Example Questions" are written for.
- The Case Input is the chat question (`invoke_agent(user_instructions=..., data_raw=df)`).
- The app renders a table or a Plotly chart. The reply text carries the graph's summary message plus
  the wrangled table (first 40 rows, `DataFrame.to_string()`) or a summary of the chart (title, trace
  types, axis titles). The generated pandas/Plotly code, the Plotly JSON and chart errors are returned
  in extra output fields for evidence.
- `agent/abb-langgraph.json` is an added descriptor pointing at `make_pandas_data_analyst`; the upstream
  source is unchanged. `IPython` is installed in addition to `requirements.txt` because the package
  imports `IPython.display` without declaring it.

Excluded: the supervisor team (needs H2O / MLflow), SQL, EDA and data-loader agents, file upload,
chart rendering. Generated code runs in-process via upstream `exec` as in the app.

## Routes

Only the model route `POST api.openai.com /v1/chat/completions` (rewritten by ABB to the evaluated
provider). No tool egress.

## Deployment fixes (no upstream code change)

- `OPENBLAS_NUM_THREADS/OMP_NUM_THREADS/MKL_NUM_THREADS=1` and a one-line `.pth` start-up hook that pins
  the worker to one CPU (`os.sched_setaffinity`). Upstream runs generated code in a sandbox subprocess
  with a scrubbed environment and `RLIMIT_AS=512 MiB`; on a many-core host numpy's OpenBLAS sizes its
  buffers from all visible cores and aborts with "OpenBLAS error: Memory allocation still failed", so
  every wrangling attempt failed and the graph only answered "Workflow completed." The pinned CPU matches
  ABB's `--cpus=1` quota and is inherited by the sandbox child. (`launch.argv` cannot carry `taskset`:
  the KUMA overlay rewrites it.)
