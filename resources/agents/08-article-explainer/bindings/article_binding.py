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
