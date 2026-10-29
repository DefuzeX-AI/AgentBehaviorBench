# Ranked hypotheses before intervention

1. The query loop consumes tool_call_complete without yielding it. Prediction: yielding the original event alone will populate native session assistant toolCalls and remove the second-request orphan tool results.
2. The session reconstruction independently discards received tool calls. Prediction: yielding the event alone will not restore valid history; persisted assistant toolCalls will remain missing or malformed.
3. The OpenAI-compatible serialization strips otherwise-correct session tool calls. Prediction: persisted state will contain toolCalls while the outgoing request omits tool_calls, before or after the query change.

The baseline completed prompt 1, then the first model request for prompt 2 received real provider HTTP 400 for orphan tool messages. The intervention changes only one source line in the first location. No synthetic model replies, mocked tools, or fault injection are used.
