"""\u8bc6\u56fe\u5206\u6790\u5668\u6ce8\u518c\u8868 + \u4efb\u52a1\u76ee\u5f55\u81ea\u52a8\u53d1\u73b0.

\u76ee\u7684: \u8ba9\u6bcf\u4e2a\u4efb\u52a1\u628a\u81ea\u5df1\u7684\u8bc6\u56fe\u4ee3\u7801\u653e\u5728 *\u81ea\u5df1\u7684\u4efb\u52a1\u76ee\u5f55* ``vision.py`` \u91cc, \u901a\u8fc7
``@register("<analysisType>")`` \u767b\u8bb0, \u800c\u4e0d\u662f\u628a\u51fd\u6570\u5806\u8fdb\u5171\u4eab\u7684
``app/modules/uav/service.py``\u3002``service.handle_common_vision_upload`` \u53ea\u9700\u5148\u67e5\u8fd9\u5f20\u8868,
\u547d\u4e2d\u5c31\u8c03\u7528\u5bf9\u5e94\u4efb\u52a1\u7684 analyzer, \u5b9e\u73b0\u6309\u4efb\u52a1\u62c6\u5206\u3001\u907f\u514d\u5171\u4eab\u6587\u4ef6\u81a8\u80c0\u3002

\u53d1\u73b0\u673a\u5236
--------
:func:`ensure_task_analyzers_loaded` \u626b\u63cf ``examples/*/vision.py`` \u548c
case-local ``vision.py`` modules under ``examples/``, loaded by file path,
\u9010\u4e2a import \u2014\u2014 import \u65f6\u5404\u6a21\u5757\u7684 ``@register`` \u88c5\u9970\u5668\u5c31\u628a analyzer \u586b\u8fdb\u8868\u91cc\u3002
\u53ea\u52a0\u8f7d\u4e00\u6b21 (\u5e42\u7b49), \u5355\u4e2a\u4efb\u52a1\u6a21\u5757\u51fa\u9519\u53ea\u8df3\u8fc7\u5b83\u3001\u4e0d\u5f71\u54cd\u6574\u4f53\u3002

analyzer \u7ea6\u5b9a\u7b7e\u540d (\u7edf\u4e00\u5173\u952e\u5b57\u53c2\u6570, \u5b9e\u73b0\u8005\u7528 ``**kwargs`` \u5bb9\u9519)::

    async def analyzer(*, files, task_id, agent_id, agent_type, view_type,
                       step_index, subtask_index, current_height_m, metadata, **kwargs) -> dict
    # \u8fd4\u56de\u503c\u662f\u53ef\u76f4\u63a5\u4ea4\u7ed9 service \u7684 done() \u7684\u7ed3\u679c dict, \u5f62\u5982
    # {"status": "analyzed", "metadata": metadata, "result": {...}, ...}
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

_DISCOVERY_ROOTS = [REPO_ROOT / "examples"]

Analyzer = Callable[..., Awaitable[dict[str, Any]]]

_ANALYZERS: dict[str, Analyzer] = {}
_loaded = False


def register(analysis_type: str) -> Callable[[Analyzer], Analyzer]:
    """\u88c5\u9970\u5668: \u628a\u4e00\u4e2a analyzer \u6ce8\u518c\u5230\u7ed9\u5b9a analysisType (\u5927\u5c0f\u5199\u4e0d\u654f\u611f)\u3002"""

    key = str(analysis_type or "").strip().lower()
    if not key:
        raise ValueError("analysisType \u4e0d\u80fd\u4e3a\u7a7a")

    def decorator(fn: Analyzer) -> Analyzer:
        if key in _ANALYZERS and _ANALYZERS[key] is not fn:
            logger.warning("analysisType=%s \u5df2\u88ab\u6ce8\u518c, \u8986\u76d6\u4e3a %s", key, getattr(fn, "__name__", fn))
        _ANALYZERS[key] = fn
        return fn

    return decorator


def get_analyzer(analysis_type: str) -> Analyzer | None:
    return _ANALYZERS.get(str(analysis_type or "").strip().lower())


def registered_types() -> list[str]:
    return sorted(_ANALYZERS)


def _load_vision_module(path: Path, index: int) -> None:
    module_name = f"_task_vision_{index}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        logger.info("\u5df2\u52a0\u8f7d\u4efb\u52a1\u8bc6\u56fe\u6a21\u5757: %s", path)
    except Exception as exc:  
        logger.warning("\u52a0\u8f7d\u4efb\u52a1\u8bc6\u56fe\u6a21\u5757\u5931\u8d25, \u8df3\u8fc7: %s (%s)", path, exc)


def ensure_task_analyzers_loaded(*, force: bool = False) -> None:
    """\u5e42\u7b49\u5730\u53d1\u73b0\u5e76\u52a0\u8f7d\u6240\u6709\u4efb\u52a1\u76ee\u5f55\u7684 ``vision.py`` (\u9996\u6b21\u8c03\u7528\u65f6\u771f\u6b63\u626b\u63cf)\u3002"""

    global _loaded
    if _loaded and not force:
        return
    index = 0
    for root in _DISCOVERY_ROOTS:
        if not root.is_dir():
            continue
        for vision_path in sorted(root.glob("*/vision.py")):
            _load_vision_module(vision_path, index)
            index += 1
    _loaded = True
