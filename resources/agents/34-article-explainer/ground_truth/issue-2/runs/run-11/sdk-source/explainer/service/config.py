from dotenv import load_dotenv
import os
from langchain_ollama import ChatOllama
from langchain.chat_models import init_chat_model


def get_chat_model(model_name: str = "openai:gpt-4.1-mini"):
    """Returns a LangChain chat model initialized with the API key from the environment."""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        # This is the solution for the local setup, in case you want to host your model locally.
        return ChatOllama(
            model="qwen3:8b",
            base_url="http://localhost:11434"
        )

    return init_chat_model(model=model_name, api_key=api_key)