from __future__ import annotations

import json
from typing import Any

from models.image_schemas import DrawingMap, ImageAsset

from .base_agent import BaseStructuredAgent


def run_drawing_analyzer(
    *,
    disclosure_text: str,
    disclosure_images: list[ImageAsset],
    agent: BaseStructuredAgent[DrawingMap],
) -> DrawingMap:
    """
    Multimodal drawing analyzer wrapper.
    Returns structured DrawingMap that can be consumed by downstream spec writer node.
    """
    if len(disclosure_images) == 0:
        return DrawingMap(
            figures=[],
            overall_notes="No disclosure images were provided. Drawing analysis skipped.",
            warnings=["no_disclosure_images"],
        )

    image_brief = [
        {
            "image_id": img.image_id,
            "page_index": img.page_index,
            "caption_hint": img.caption_hint,
            "mime_type": img.mime_type,
        }
        for img in disclosure_images
    ]
    # Keep context concise to reduce truncation risk for long disclosure text.
    disclosure_excerpt = disclosure_text[:8000]
    prompt = (
        "You are an expert patent drawing analyzer. Analyze the provided disclosure drawings and build a comprehensive, structured drawing map.\n"
        "The drawings may be mechanical diagrams, system block diagrams, software flowcharts, circuit diagrams, or UI mockups.\n\n"
        "TASKS:\n"
        "1. FIGURE CLASSIFICATION: For each figure, explicitly identify its type (e.g., 'Flowchart', 'Block Diagram', 'Mechanical View', 'Circuit Diagram', 'UI Mockup', 'Data Graph').\n"
        "2. ADAPTIVE ELEMENT EXTRACTION:\n"
        "   - For Mechanical/Apparatus: Extract reference numerals and physical part names.\n"
        "   - For Flowcharts: Extract step numbers (e.g., S101, Step 1) and the corresponding step action/description.\n"
        "   - For System/Block Diagrams: Extract module names, component labels, and database/server nodes.\n"
        "3. RELATIONSHIP & FLOW MAPPING:\n"
        "   - Describe how the extracted elements interact. This could be physical attachment, data flow direction, electrical connection, or the logical execution sequence of method steps.\n"
        "4. OVERALL UNDERSTANDING: Provide a concise 1-2 sentence summary explaining the core technical concept illustrated in the figure.\n\n"
        "### JSON SAFETY RULES:\n"
        "1. Output a single valid JSON object only.\n"
        "2. Do NOT wrap output with markdown code fences.\n"
        "3. Do NOT include explanatory text before/after JSON.\n"
        "4. Ensure all keys/strings use double quotes in valid JSON format.\n\n"
        "Return valid JSON only, strictly matching the required schema.\n\n"
        f"[DISCLOSURE_TEXT_EXCERPT]\n{disclosure_excerpt}\n\n"
        f"[IMAGE_METADATA_JSON]\n{json.dumps(image_brief, ensure_ascii=False)}"
    )
    context: dict[str, Any] = {
        "image_paths": [img.source_path for img in disclosure_images],
        "image_mime_types": [img.mime_type for img in disclosure_images],
    }
    try:
        return agent.run_structured(prompt=prompt, output_model=DrawingMap, context=context)
    except Exception as exc:  # noqa: BLE001
        # Degrade gracefully when provider-side vision format compatibility fails.
        return DrawingMap(
            figures=[],
            overall_notes="Drawing analyzer fallback to text-only mode due to vision request failure.",
            warnings=[f"vision_request_failed: {str(exc)}"],
        )
