from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pybox import AsyncLocalPyBoxManager, AsyncRemotePyBoxManager
from pydantic import BaseModel, DirectoryPath, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from tablegpt.agent import create_tablegpt_graph
from tablegpt.agent.file_reading import Stage

from .evaluatee import AbstractEvaluatee

if TYPE_CHECKING:
    from typing import Self

    from langchain_core.language_models import BaseLanguageModel
    from langchain_core.messages import BaseMessage
    from langgraph.graph.graph import CompiledGraph
    from pybox.base import BasePyBoxManager

logger = logging.getLogger(__name__)


class IpythonSettings(BaseModel):
    incluster: bool = False
    """Use kubernetes crd create kernel. if `incluster==true` load incluster config and create kernel CR as remote kernel"""
    gateway_url: HttpUrl | None = None
    env_file: str | None = None
    """Path to the environment file to use for the kernel."""


# TODO: this is also somehow a copy-paste from tablegpt-chat, with slight modifications
# Maybe we need to refactor that too?
class Settings(BaseSettings):
    """Application runtime settings.

    We give almost everything a default value, to make unittest easier.
    """

    model_config = SettingsConfigDict(env_nested_delimiter="__", extra="ignore")

    llm: dict[str, Any] = {}
    vlm: dict[str, Any] | None = None
    guard_llm: dict[str, Any] | None = None
    normalize_llm: dict[str, Any] | None = None
    """LLM used to normalize unstructured dataset"""

    data_vol: DirectoryPath = tempfile.gettempdir()
    """Data volume used to persist query results"""
    ipython_kernel: IpythonSettings = IpythonSettings()
    """Kubernetes Kernel Client settings"""
    error_trace_cleanup: bool = False
    """Enable trace cleanup to remove unnecessary error messages.
    This feature prunes the error trace to reduce the context length sent to the LLM, helping weaker models focus on the specific error line.
    When enabled, only a small context around the exact error line, along with a brief error description, is retained.
    While this is considered experimental, and some performance improvements have been observed, it may lead to information loss in certain situations.
    """


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=[".env"], _env_file_encoding="utf-8")


@lru_cache
def get_llm_instance() -> BaseLanguageModel:
    settings = get_settings()
    return ChatOpenAI(**settings.llm)


@lru_cache
def get_vlm_instance() -> BaseLanguageModel:
    settings = get_settings()
    if settings.vlm is None:
        return None
    return ChatOpenAI(**settings.vlm)


@lru_cache
def get_guard_llm_instance() -> BaseLanguageModel:
    settings = get_settings()
    if settings.guard_llm is None:
        return None
    return ChatOpenAI(**settings.guard_llm)


@lru_cache
def get_normalize_llm_instance() -> BaseLanguageModel:
    settings = get_settings()
    if settings.normalize_llm is None:
        return None
    return ChatOpenAI(**settings.normalize_llm)


@lru_cache
def get_pybox_manager() -> BasePyBoxManager:
    settings = get_settings()
    if (gateway_url := settings.ipython_kernel.gateway_url) is not None:
        import os

        # Clear default mask. Allow the kernel to read and write shared volumes.
        os.umask(000)
        return AsyncRemotePyBoxManager(
            host=str(gateway_url),
            env_file=settings.ipython_kernel.env_file,
        )
    return AsyncLocalPyBoxManager()


# TODO: a copy-paste from tablegpt-chat
# We need to refactor this and push it down to tablegpt-agent
class Attachment(TypedDict):
    filename: str
    mimetype: str
    size: int = 0


class TablegptEvaluatee(AbstractEvaluatee):
    def __init__(
        self,
        llm: BaseLanguageModel,
        pybox_manager: BasePyBoxManager,
        data_vol: str,
        *,
        error_trace_cleanup: bool = True,
        vlm: BaseLanguageModel | None = None,
        normalize_llm: BaseLanguageModel | None = None,
        guard_llm: BaseLanguageModel | None = None,
    ):
        self.llm = llm
        self.pybox_manager = pybox_manager
        self.session_id = f"eval-session-{uuid4().hex}"
        self.workdir = Path(data_vol, self.session_id)
        self.error_trace_cleanup = error_trace_cleanup
        self.vlm = vlm
        self.normalize_llm = normalize_llm
        self.guard_llm = guard_llm

    async def __aenter__(self):
        """Initialize the context resources."""
        logger.debug("Creating workdir: %s", self.workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

        logger.debug("Spawning kernel with session ID: %s", self.session_id)
        await self.pybox_manager.start(kernel_id=self.session_id, cwd=self.workdir)

        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Clean up the context resources."""
        logger.debug("Cleaning up worker resources...")
        logger.debug("Shutting down kernel: %s", self.session_id)
        await self.pybox_manager.shutdown(self.session_id)

        logger.debug("Removing workdir: %s", self.workdir)
        shutil.rmtree(self.workdir, ignore_errors=True)

        logger.debug("Worker resources cleaned up")

    async def _call(self, message: BaseMessage, **kwargs) -> list[BaseMessage]:  # noqa: ARG002
        checkpointer = MemorySaver()
        config = {
            "configurable": {"thread_id": self.session_id},
        }
        tablegpt_graph: CompiledGraph = create_tablegpt_graph(
            llm=self.llm,
            pybox_manager=self.pybox_manager,
            workdir=self.workdir,
            vlm=self.vlm,
            session_id=self.session_id,
            checkpointer=checkpointer,
            normalize_llm=self.normalize_llm,
            safety_llm=self.guard_llm,
            error_trace_cleanup=self.error_trace_cleanup,
        ).with_config(
            config=config,
        )
        parent_id = str(uuid4())
        attachments = [
            Attachment(filename=file, mimetype="text/csv") for file in message.additional_kwargs.get("attachments", [])
        ]
        attachment_msg = HumanMessage(
            content="",
            additional_kwargs={
                "parent_id": parent_id,
                "attachments": attachments,
                "var_name": "df",
            },
        )
        try:
            # file reading
            await tablegpt_graph.ainvoke(
                input={
                    "messages": [attachment_msg],
                    "parent_id": parent_id,
                    "entry_message": attachment_msg,
                    "processing_stage": Stage.UPLOADED,
                }
            )
            # data analysis
            state = await tablegpt_graph.ainvoke(
                input={
                    "parent_id": str(uuid4()),
                    "messages": [HumanMessage(content=message.content)],
                    "date": date.today(),  # noqa: DTZ011
                }
            )
            return state["messages"]
        except Exception as e:  # noqa: BLE001
            logger.warning("Tablegpt evaluatee execution failed: %s", str(e))
            checkpoint = await checkpointer.aget(config=config)
            return checkpoint["channel_values"].get("messages", [])

    @property
    def context(self):
        return {"workdir": self.workdir, "session_id": self.session_id}

    @classmethod
    def instance(cls) -> Self:
        settings = get_settings()
        return cls(
            llm=get_llm_instance(),
            pybox_manager=get_pybox_manager(),
            data_vol=settings.data_vol,
            error_trace_cleanup=settings.error_trace_cleanup,
            vlm=get_vlm_instance(),
            normalize_llm=get_normalize_llm_instance(),
            guard_llm=get_guard_llm_instance(),
        )
