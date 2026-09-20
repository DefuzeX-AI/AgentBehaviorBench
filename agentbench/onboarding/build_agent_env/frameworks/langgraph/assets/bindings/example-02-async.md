# Example 02: adapt current text to an asynchronous native graph

This is the complete existing Article Explainer binding, not pseudocode.
Prerequisites: the image installs `explainer` and its dependencies, the saved
manifest declares `binding="article_binding.py:create_graph"`,
`input_key="message"`, and NO output_key. Its existing source graph configuration
is `abb-langgraph.json`, graph ID `agent`. These names are Agent-specific.

Input example: `{"message": "Explain this excerpt: Photosynthesis converts light energy..."}`.
BBA may also wrap scalar text into that mapping. The wrapper validates the input,
converts it to a native user message, and forwards config to the original graph.
It returns the entire native state, including messages and active_agent; it does
not manufacture an answer. `close()` drops its graph reference and rejects future
invocations; it owns no separate database or client in this implementation.
The sync bridge must not be called from an already-running event loop.

Source snapshot: `resources/agents/09-article-explainer/bindings/article_binding.py`.

```python
"""Deliver a current excerpt/question to the unchanged native compiled swarm."""
import asyncio


def message_from_input(value):
    """Accept text or exactly {message: text}; reject unrepresented attachments."""
    if isinstance(value, dict):
        if set(value) != {'message'}:
            raise ValueError('Article Explainer accepts exactly one current message field')
        value = value['message']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Supply a non-empty current excerpt and question')
    return value


class ArticleExplainer:
    def __init__(self):
        self._app = None
        self._closed = False

    async def ainvoke(self, value, config=None):
        """Run native handoffs and return the entire native SwarmState.

        Args: value is current text or {message: text}; config is forwarded to
            the native graph, including real framework observation callbacks.
        Returns: Native state containing messages and active_agent, unchanged.
        No PDF or previous conversation is loaded or constructed by this binding.
        """
        message = message_from_input(value)
        if self._closed:
            raise RuntimeError('Article Explainer is closed')
        if self._app is None:
            from explainer.graph import app
            self._app = app
        return await self._app.ainvoke({'messages': [('user', message)]}, config=config)

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    def close(self):
        self._closed = True
        self._app = None


def create_graph():
    return ArticleExplainer()
```
