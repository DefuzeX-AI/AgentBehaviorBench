"""Automation monitoring and job submission routes for queue mode."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.hunt_store import load_hunt, now_iso
from api.routes import _hunts, request_hunt_cancel, _unique_leads_count
from api.security import require_api_access
from automation.job_queue import HuntJobQueue
from automation.metrics import collect_automation_metrics, collect_automation_status
from config.settings import get_settings
from emailing.store import EmailStore

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])
logger = logging.getLogger(__name__)


class AutomationJobRequest(BaseModel):
    website_url: str = ""
    description: str = ""
    product_keywords: list[str] = Field(default_factory=list)
    target_customer_profile: str = ""
    target_regions: list[str] = Field(default_factory=list)
    uploaded_file_ids: list[str] = Field(default_factory=list)
    target_lead_count: int = Field(default=200, ge=1, le=10000)
    max_rounds: int = Field(default=10, ge=1, le=50)
    min_new_leads_threshold: int = Field(default=5, ge=1, le=100)
    enable_email_craft: bool = False
    email_template_examples: list[str] = Field(default_factory=list)
    email_template_notes: str = ""


class AutomationJobContinueRequest(BaseModel):
    target_lead_count: int = Field(default=200, ge=1, le=10000)
    max_rounds: int = Field(default=10, ge=1, le=50)
    min_new_leads_threshold: int = Field(default=5, ge=1, le=100)
    enable_email_craft: bool = False
    email_template_examples: list[str] = Field(default_factory=list)
    email_template_notes: str = ""


def _queue() -> HuntJobQueue:
    settings = get_settings()
    queue = HuntJobQueue(settings.automation_queue_db_path)
    queue.init_db()
    return queue


def _email_store() -> EmailStore:
    settings = get_settings()
    store = EmailStore(settings.email_db_path)
    store.init_db()
    return store


def _lead_preview(leads: list[Any], limit: int = 20) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        company = str(lead.get("company_name", "") or "").strip()
        website = str(lead.get("website", "") or "").strip()
        country = str(lead.get("country", "") or "").strip()
        emails = [str(email).strip() for email in (lead.get("emails") or []) if str(email).strip()]
        key = (website or company or "|".join(emails)).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        preview.append(
            {
                "company_name": company,
                "website": website,
                "country": country,
                "emails": emails,
                "email_count": len(emails),
            }
        )
        if len(preview) >= limit:
            break
    return preview


def _email_sequence_preview(sequences: list[Any], limit: int = 10) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for sequence in sequences:
        if not isinstance(sequence, dict):
            continue
        lead = sequence.get("lead") if isinstance(sequence.get("lead"), dict) else {}
        targets: list[str] = []
        primary_target = sequence.get("target")
        if isinstance(primary_target, dict):
            primary_email = str(primary_target.get("target_email", "") or "").strip()
            if primary_email:
                targets.append(primary_email)
        raw_targets = sequence.get("targets")
        if isinstance(raw_targets, list):
            for target in raw_targets:
                if not isinstance(target, dict):
                    continue
                email = str(target.get("target_email", "") or "").strip()
                if email:
                    targets.append(email)
        deduped_targets = list(dict.fromkeys(targets))
        emails = sequence.get("emails") if isinstance(sequence.get("emails"), list) else []
        preview.append(
            {
                "company_name": str(lead.get("company_name", "") or ""),
                "website": str(lead.get("website", "") or ""),
                "target_emails": deduped_targets,
                "email_count": len(deduped_targets),
                "subjects": [
                    str(email.get("subject", "") or "")
                    for email in emails
                    if isinstance(email, dict)
                ],
            }
        )
        if len(preview) >= limit:
            break
    return preview


def _campaign_preview(hunt_id: str) -> dict[str, Any]:
    if not hunt_id:
        return {"campaign_count": 0, "sequence_count": 0, "target_emails": []}
    store = _email_store()
    campaigns = store.list_campaigns_for_hunt(hunt_id)
    sequences = []
    for item in campaigns:
        campaign = item.get("campaign") if isinstance(item, dict) else None
        campaign_id = str((campaign or {}).get("id", "") or "")
        if not campaign_id:
            continue
        sequences.extend(store.list_sequences_for_campaign(campaign_id))
    target_emails = list(
        dict.fromkeys(
            str(sequence.get("lead_email", "") or "").strip().lower()
            for sequence in sequences
            if str(sequence.get("lead_email", "") or "").strip()
        )
    )
    return {
        "campaign_count": len(campaigns),
        "sequence_count": len(sequences),
        "target_emails": target_emails[:100],
    }


def _serialize_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    template_seed = payload.get("template_seed") if isinstance(payload.get("template_seed"), dict) else {}
    hunt_id = str(job.get("last_hunt_id", "") or "")
    hunt = load_hunt(hunt_id) if hunt_id else None
    result = (hunt or {}).get("result") if isinstance((hunt or {}).get("result"), dict) else {}
    leads = result.get("leads") if isinstance(result.get("leads"), list) else []
    email_sequences = result.get("email_sequences") if isinstance(result.get("email_sequences"), list) else []
    campaign_summary = result.get("email_campaign_summary") if isinstance(result.get("email_campaign_summary"), dict) else {}
    leads_count = int((hunt or {}).get("leads_count", 0) or 0)
    if not leads_count and isinstance(leads, list):
        leads_count = _unique_leads_count(leads)
    email_sequences_count = int((hunt or {}).get("email_sequences_count", 0) or 0)
    if not email_sequences_count and isinstance(email_sequences, list):
        email_sequences_count = len(email_sequences)
    campaign_preview = _campaign_preview(hunt_id)
    return {
        "job_id": str(job.get("id", "") or ""),
        "status": str(job.get("status", "") or ""),
        "created_at": str(job.get("created_at", "") or ""),
        "updated_at": str(job.get("updated_at", "") or ""),
        "started_at": str(job.get("started_at", "") or ""),
        "finished_at": str(job.get("finished_at", "") or ""),
        "claimed_by": str(job.get("claimed_by", "") or ""),
        "attempt_count": int(job.get("attempt_count", 0) or 0),
        "last_error": str(job.get("last_error", "") or ""),
        "last_hunt_id": hunt_id,
        "progress_stage": str(job.get("progress_stage", "") or ""),
        "progress_message": str(job.get("progress_message", "") or ""),
        "template_seed_status": str(job.get("template_seed_status", "") or ""),
        "template_seed_source": str(job.get("template_seed_source", "") or ""),
        "template_seed": template_seed,
        "website_url": str(payload.get("website_url", "") or ""),
        "description": str(payload.get("description", "") or ""),
        "product_keywords": list(payload.get("product_keywords", []) or []),
        "target_regions": list(payload.get("target_regions", []) or []),
        "target_lead_count": int(payload.get("target_lead_count", 0) or 0),
        "enable_email_craft": bool(payload.get("enable_email_craft", False)),
        "hunt_status": str((hunt or {}).get("status", "") or ""),
        "hunt_stage": str((hunt or {}).get("current_stage", "") or ""),
        "hunt_error": str((hunt or {}).get("error", "") or ""),
        "leads_count": leads_count,
        "email_sequences_count": email_sequences_count,
        "lead_preview": _lead_preview(leads if isinstance(leads, list) else []),
        "email_sequence_preview": _email_sequence_preview(email_sequences if isinstance(email_sequences, list) else []),
        "campaign_summary": campaign_summary,
        "campaign_count": int(campaign_preview["campaign_count"]),
        "campaign_sequence_count": int(campaign_preview["sequence_count"]),
        "campaign_target_emails": list(campaign_preview["target_emails"]),
    }


@router.post("/jobs", dependencies=[Depends(require_api_access)])
async def create_automation_job(request: AutomationJobRequest):
    queue = _queue()
    job_id = queue.enqueue(request.model_dump(), now_iso=now_iso())
    logger.info(
        "[AutomationQueue] enqueued job=%s website=%s target_leads=%s email_craft=%s",
        job_id[:8],
        request.website_url or "-",
        request.target_lead_count,
        request.enable_email_craft,
    )
    job = queue.get(job_id)
    return _serialize_job(job or {"id": job_id, "payload": request.model_dump()})


@router.get("/jobs", dependencies=[Depends(require_api_access)])
async def list_automation_jobs(limit: int = Query(default=50, ge=1, le=200)):
    queue = _queue()
    return [_serialize_job(job) for job in queue.list_jobs(limit=limit)]


@router.get("/jobs/{job_id}", dependencies=[Depends(require_api_access)])
async def get_automation_job(job_id: str):
    queue = _queue()
    job = queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Automation job not found")
    return _serialize_job(job)


@router.get("/jobs/by-hunt/{hunt_id}", dependencies=[Depends(require_api_access)])
async def get_automation_job_by_hunt(hunt_id: str):
    queue = _queue()
    job = queue.get_by_hunt_id(hunt_id)
    if not job:
        raise HTTPException(status_code=404, detail="Automation job not found for hunt")
    return _serialize_job(job)


@router.post("/jobs/from-hunt/{hunt_id}", dependencies=[Depends(require_api_access)])
async def create_automation_job_from_hunt(hunt_id: str, request: AutomationJobContinueRequest):
    hunt = load_hunt(hunt_id)
    if not hunt:
        raise HTTPException(status_code=404, detail="Hunt not found")

    payload = hunt.get("payload") if isinstance(hunt.get("payload"), dict) else {}
    if not payload:
        raise HTTPException(status_code=422, detail="Hunt has no reusable payload")

    next_payload = {
        "website_url": str(payload.get("website_url", "") or ""),
        "description": str(payload.get("description", "") or ""),
        "product_keywords": list(payload.get("product_keywords", []) or []),
        "target_customer_profile": str(payload.get("target_customer_profile", "") or ""),
        "target_regions": list(payload.get("target_regions", []) or []),
        "uploaded_file_ids": list(payload.get("uploaded_file_ids", []) or []),
        "target_lead_count": int(request.target_lead_count),
        "max_rounds": int(request.max_rounds),
        "min_new_leads_threshold": int(request.min_new_leads_threshold),
        "enable_email_craft": bool(request.enable_email_craft),
        "email_template_examples": list(request.email_template_examples),
        "email_template_notes": str(request.email_template_notes or ""),
    }

    queue = _queue()
    job_id = queue.enqueue(next_payload, now_iso=now_iso())
    job = queue.get(job_id)
    return _serialize_job(job or {"id": job_id, "payload": next_payload})


@router.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_api_access)])
async def cancel_automation_job(job_id: str):
    queue = _queue()
    job = queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Automation job not found")
    queue.cancel(job_id, updated_at=now_iso())
    hunt_id = str(job.get("last_hunt_id", "") or "")
    if hunt_id:
        request_hunt_cancel(hunt_id, reason="Cancelled by user via automation job")
    logger.info("[AutomationQueue] cancelled job=%s", job_id[:8])
    updated = queue.get(job_id)
    return _serialize_job(updated or job)


@router.post("/jobs/{job_id}/retry", dependencies=[Depends(require_api_access)])
async def retry_automation_job(job_id: str):
    queue = _queue()
    job = queue.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Automation job not found")
    queue.retry_now(job_id, updated_at=now_iso())
    logger.info("[AutomationQueue] retried job=%s", job_id[:8])
    updated = queue.get(job_id)
    return _serialize_job(updated or job)


@router.get("/status", dependencies=[Depends(require_api_access)])
async def get_automation_status():
    return collect_automation_status(hunts=_hunts)


@router.get("/metrics", dependencies=[Depends(require_api_access)])
async def get_automation_metrics(hours: int = Query(default=24, ge=1, le=168)):
    return collect_automation_metrics(hours=hours, hunts=_hunts)


@router.get("/health", dependencies=[Depends(require_api_access)])
async def get_automation_health():
    status = collect_automation_status(hunts=_hunts)
    metrics = collect_automation_metrics(hours=2, hunts=_hunts)
    return {
        "status": "ok",
        "backlog_hunt_jobs": status["hunt_jobs"]["queued"],
        "backlog_email_messages": status["email_queue"]["pending"],
        "recent_failed_emails": metrics["emails"]["failed"],
    }
