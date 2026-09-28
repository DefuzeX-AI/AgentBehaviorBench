from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import aiofiles
from langchain_core.messages import HumanMessage
from tqdm.asyncio import tqdm
from traitlets import import_item

from .evaluatee import AbstractEvaluatee
from .worker import Worker

if TYPE_CHECKING:
    from agent_eval.config import EvalSettings
    from langchain_core.messages import BaseMessage


logger = logging.getLogger(__name__)

# TODO: make this configurable, and we can continue running after an error
eval_run_output_file = f"eval_run_{datetime.datetime.now(tz=datetime.UTC).strftime('%Y%m%d_%H%M%S')}.jsonl"


class Runner:
    """Evaluation task runner.

    config(config.EvalSettings): evaluation configuration.
    """

    def __init__(self, config: EvalSettings) -> None:
        """Initialize the Evaluation runner with the given configuration.

        Args:
            config (dict): Configuration dictionary for the Evaluation.
        """
        self.config = config
        self.evaluatee_class = import_item(config.evaluatee_class)
        if not issubclass(self.evaluatee_class, AbstractEvaluatee):
            raise TypeError(f"{config.evaluatee_class} is not a subclass of AbstractEvaluatee")  # noqa: TRY003, EM102

    async def run(self, stop_event: asyncio.Event) -> None:
        """Gather evaluation samples and run the evaluation process, in parallel."""
        logger.info("Gathering evaluation samples...")
        queue = asyncio.Queue()
        await enqueue_samples(queue, self.config.datasets, self.config.num_repetitions)
        total_samples = queue.qsize()
        logger.info("Gathered %s samples for evaluation", total_samples)

        with tqdm(total=total_samples, desc="Evaluation samples") as pbar:
            try:
                eval_tasks = [
                    asyncio.create_task(
                        Worker(
                            queue,
                            self.evaluatee_class.instance(),
                            stop_event,
                            pbar,
                            self.config.evaluator,
                            eval_run_output_file,
                        ).run(),
                        name=f"worker-{i}",
                    )
                    for i in range(self.config.max_concurrency)
                ]
                # Ensure all consumers exit
                await asyncio.gather(*eval_tasks, return_exceptions=True)
            except Exception:
                logger.exception("Error in evaluator")
            finally:
                logger.info("Shutting down evaluator...")


async def enqueue_samples(queue: asyncio.Queue, dataset_configs: list[dict], num_repetitions: int = 1) -> None:
    """Reads datasets from the provided configurations, constructs samples, and enqueues them for processing.

    Args:
        queue (asyncio.Queue): The queue to which the samples will be added.
        dataset_configs (list[dict]): A list of dataset configurations, each containing a 'name' key pointing to the dataset file.
        num_repetitions (int, optional): The number of times each sample should be repeated in the queue. Defaults to 1.
    """
    for dataset_config in dataset_configs:
        logger.debug("Gathering samples from dataset: %s...", dataset_config.name)

        async with aiofiles.open(dataset_config.name) as f:
            content = await f.read()
            dataset = json.loads(content)
        _samples = construct_samples(dataset)
        logger.debug(
            "Gathered %d samples from dataset %s",
            len(_samples),
            dataset_config.name,
        )
        for sample in _samples:
            # Repeat each sample for `num_repetitions` times.
            for _ in range(num_repetitions):
                await queue.put(sample)


def construct_samples(dataset: list[dict[str, Any]]) -> list[BaseMessage]:
    """Constructs a list of samples from the dataset, filtering out archived items and adding metadata.

    Args:
        dataset (list[dict[str, Any]]): The dataset containing items with 'status', 'attachments', and 'expected_output' keys.

    Returns:
        list[BaseMessage]: A list of `HumanMessage` objects, each containing the item's input and associated metadata (e.g., attachments, expected output, and evaluation criteria).
    """
    # Filter out archived samples
    active_samples = [sample for sample in dataset if sample["status"] != "ARCHIVED"]

    # Construct samples with additional metadata
    return [HumanMessage(content=sample.pop("input"), additional_kwargs=sample) for sample in active_samples]
