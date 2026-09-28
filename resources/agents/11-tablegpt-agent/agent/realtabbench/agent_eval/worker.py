from __future__ import annotations

import asyncio
import json
import logging
import traceback
from typing import TYPE_CHECKING, Any

import aiofiles
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from .evaluator import create_evaluator_runnable
from .evaluator.prompt import DEFAULT_CRITERIA_WITH_REFERENCE_ANSWER, DEFAULT_CRITERIA_WITHOUT_REFERENCE_ANSWER

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage
    from tqdm.asyncio import tqdm

    from .evaluatee import AbstractEvaluatee

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        queue: asyncio.Queue,
        evaluatee: AbstractEvaluatee,
        stop_event: asyncio.Event | None = None,
        pbar: tqdm | None = None,
        evaluator_config: dict[str, Any] | None = None,
        eval_run_output_file: str = "eval-result.jsonl",
    ) -> None:
        self.queue = queue
        self.evaluatee = evaluatee
        self.stop_event = stop_event
        self.pbar = pbar
        self.evaluator_config = evaluator_config if evaluator_config else {}
        self.eval_run_output_file = eval_run_output_file

    async def run(self) -> None:
        logger.info("Worker started")
        async with self.evaluatee:
            while self.stop_event is None or not self.stop_event.is_set():
                try:
                    sample = self.queue.get_nowait()
                    executor = EvalExecutor(self.evaluatee, self.evaluator_config, self.eval_run_output_file)
                    await executor.run(sample)
                    if self.pbar is not None:
                        self.pbar.update(1)
                except asyncio.QueueEmpty:
                    # No more tasks in the queue, quit current worker
                    logger.info("Worker finished")
                    break
                except Exception:
                    logger.exception("Worker encountered an error")
                    # Set the stop event to cancel other workers
                    if self.stop_event is not None:
                        self.stop_event.set()
                    break


class EvalExecutor:
    def __init__(
        self,
        evaluatee: AbstractEvaluatee,
        evaluator_config: dict[str, Any],
        eval_run_output_file: str = "eval-result.jsonl",
    ) -> None:
        self.evaluator = create_evaluator_runnable(ChatOpenAI(**evaluator_config))
        self.evaluatee = evaluatee
        self.eval_run_output_file = eval_run_output_file

    async def run(self, sample: BaseMessage) -> None:
        """Run the evaluation workflow.
        Usually a evaluatee runnable will be executed, followed by a evaluator runnable.

        Args:
            sample (BaseMessage): Evaluation sample.
        """
        logger.debug("Evaluating sample: %s", sample)
        criteria = (
            sample.additional_kwargs.get("criteria")
            if sample.additional_kwargs.get("criteria")
            else (
                DEFAULT_CRITERIA_WITH_REFERENCE_ANSWER
                if sample.additional_kwargs.get("expected_output")
                else DEFAULT_CRITERIA_WITHOUT_REFERENCE_ANSWER
            )
        )
        reference_answer = sample.additional_kwargs.get("expected_output")
        redlines = sample.additional_kwargs.get("redlines", [])

        eval_result = {
            "input": sample.content,
            "reference_answer": reference_answer,
            "evaluatee_answer": "",
            "criteria": criteria,
            "redlines": redlines,
        }

        try:
            eval_result["messages"] = await self.evaluatee(sample)
        except Exception:
            logger.exception(
                "Evaluation Workflow failed, item: %s, context: %s",
                sample,
                self.evaluatee.context,
            )
            eval_result["messages"] = []
            # We treat any exception in agent invocation as a bad case
            eval_result["evaluation"] = {
                "score": 0,
                "explaination": traceback.format_exc(),
            }

        try:
            if not eval_result["messages"]:
                raise ValueError(  # noqa: TRY301, TRY003
                    "Evaluatee did not generate any messages."  # noqa: EM101
                    "Ensure the Evaluatee is implemented correctly and returns a valid response."
                )

            if not isinstance(eval_result["messages"][-1], AIMessage):
                raise TypeError(  # noqa: TRY301, TRY003
                    f"The final message in the output from Evaluatee is of type '{type(eval_result["messages"][-1]).__name__}', "  # noqa: EM102
                    "but it must be an instance of 'AIMessage'. Please verify the Evaluatee implementation."
                )

            evaluatee_answer = eval_result["messages"][-1].content
            eval_result["evaluatee_answer"] = evaluatee_answer
            eval_result["evaluation"] = await self.evaluator.ainvoke(
                input={
                    "question": sample.content,
                    "reference_answer": reference_answer,
                    "answer": evaluatee_answer,
                    "criteria": criteria,
                    "redlines": redlines,
                },
            )
        except Exception:
            logger.exception(
                "Evaluator invocation failed, item: %s, context: %s",
                sample,
                self.evaluatee.context,
            )
            # We treat any exception in evaluator invocation as a bad case
            eval_result["evaluation"] = {
                "score": 0,
                "explaination": traceback.format_exc(),
            }

        eval_result["messages"] = [message.model_dump() for message in eval_result["messages"]]

        async with aiofiles.open(self.eval_run_output_file, mode="a") as f:
            await f.write(json.dumps(eval_result, ensure_ascii=False) + "\n")
