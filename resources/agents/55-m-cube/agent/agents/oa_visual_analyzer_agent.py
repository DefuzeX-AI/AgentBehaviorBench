from __future__ import annotations

from typing import Any

from models.image_schemas import ImageAsset, PriorArtVisualReport

from .base_agent import BaseStructuredAgent


def run_prior_art_visual_analyzer(
    *,
    examiner_reasoning: str,
    application_images: list[ImageAsset],
    prior_art_images: list[ImageAsset],
    agent: BaseStructuredAgent[PriorArtVisualReport],
) -> PriorArtVisualReport:
    """
    Multimodal prior-art analyzer wrapper.
    Compares applicant drawings with cited prior-art drawings and outputs visual diff report.
    """
    if len(application_images) == 0 or len(prior_art_images) == 0:
        return PriorArtVisualReport(
            cited_figure_refs=[],
            diffs=[],
            conclusion="Visual comparison skipped because required images are missing.",
        )

    app_brief = [{"image_id": img.image_id, "caption_hint": img.caption_hint} for img in application_images]
    prior_brief = [{"image_id": img.image_id, "caption_hint": img.caption_hint} for img in prior_art_images]
    prompt = (
        "Compare drawings between this application and prior-art references.\n"
        "Focus on structural differences, physical connections, and cited figure arguments.\n"
        "Return valid JSON only.\n\n"
        f"[EXAMINER_REASONING]\n{examiner_reasoning}\n\n"
        f"[APPLICATION_IMAGE_METADATA]\n{app_brief}\n\n"
        f"[PRIOR_ART_IMAGE_METADATA]\n{prior_brief}"
    )
    context: dict[str, Any] = {
        "application_image_paths": [img.source_path for img in application_images],
        "prior_art_image_paths": [img.source_path for img in prior_art_images],
        "image_mime_types": [img.mime_type for img in application_images] + [img.mime_type for img in prior_art_images],
    }
    try:
        return agent.run_structured(prompt=prompt, output_model=PriorArtVisualReport, context=context)
    except Exception as exc:  # noqa: BLE001
        # Keep OA flow moving when provider-side vision input format is rejected.
        return PriorArtVisualReport(
            cited_figure_refs=[],
            diffs=[],
            conclusion=f"Visual comparison fallback to text-only mode due to vision request failure: {str(exc)}",
        )
