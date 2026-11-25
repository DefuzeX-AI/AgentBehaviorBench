"""Full native BlogGenerator invocation with the caller's exact topic."""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, "/opt/agent/agent/backend")

def create_graph():
    os.environ.setdefault("VIBE_RUNTIME_DIR", str(Path.home() / "vibe-blog"))
    from services.llm.service import init_llm_service
    from services.blog_generator.services.search_service import init_search_service
    from services.blog_generator.generator import BlogGenerator
    settings = {"AI_PROVIDER_FORMAT": "openai", "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
        "TEXT_MODEL": "gpt-4o-mini"}
    llm = init_llm_service(settings)
    search = init_search_service(settings)
    generator = BlogGenerator(llm_client=llm, search_service=search)
    class NativeBlog:
        def invoke(self, inputs, config=None):
            text = inputs["message"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Expected nonempty text")
            result = generator.generate(topic=text)
            if not result.get("success"):
                raise RuntimeError(result.get("error") or "Native blog generation failed")
            if not result.get("markdown", "").strip():
                raise RuntimeError("Native graph returned without completed article; human input or task data may be required")
            return result
        async def ainvoke(self, inputs, config=None):
            return await asyncio.to_thread(self.invoke, inputs, config)
    return NativeBlog()
