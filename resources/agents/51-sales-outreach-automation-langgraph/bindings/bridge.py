"""ABB binding for kaymen99/sales-outreach-automation-langgraph.

Upstream entrypoint (source under ``agent/`` is unchanged):

* ``main.py`` builds ``OutReachAutomation(lead_loader).app`` and invokes it with
  ``{"leads_ids": []}``.
* Nodes pull CRM leads, research LinkedIn/web/news, score, then draft outreach
  materials (report, email, interview script) and update the CRM.

Deployment boundary (no CRM / Google / LinkedIn / Serper):

* An in-memory lead loader supplies the single Case lead.
* Live scrapers and Google OAuth transports are replaced with Case-supplied or
  baked fixture research text so the native graph still runs end-to-end.
* ``invoke_llm`` is redirected to the OpenAI-compatible interceptor (DeepSeek
  rejects ``json_schema``; structured replies use ``json_object`` + Pydantic).
* Google Docs / Gmail are no-ops that report local-only URLs; nothing is sent.
"""

from __future__ import annotations

import json
import os
import re
import sys
import types
from pathlib import Path
from typing import Any


_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"
_CASE_CONTEXT: dict[str, Any] = {}


def _install_import_stubs() -> None:
    """Keep heavy optional stacks from loading before the graph imports."""

    stubs: dict[str, types.ModuleType] = {}

    def _ensure(name: str) -> types.ModuleType:
        if name in sys.modules and name.startswith(("googleapiclient", "google.", "chromadb", "langchain_chroma", "langchain_google", "hubspot", "pyairtable", "unstructured")):
            return sys.modules[name]
        mod = types.ModuleType(name)
        stubs[name] = mod
        sys.modules[name] = mod
        return mod

    for name in (
        "googleapiclient",
        "googleapiclient.discovery",
        "googleapiclient.http",
        "google.auth",
        "google.auth.transport",
        "google.auth.transport.requests",
        "google.oauth2",
        "google.oauth2.credentials",
        "google_auth_oauthlib",
        "google_auth_oauthlib.flow",
        "chromadb",
        "langchain_chroma",
        "langchain_google_genai",
        "hubspot",
        "hubspot.crm",
        "pyairtable",
        "unstructured",
        "unstructured.partition",
        "html2text",
        "bs4",
    ):
        _ensure(name)

    class _HTML2Text:
        def __init__(self):
            self.ignore_links = False
            self.ignore_images = True
            self.ignore_tables = True

        def handle(self, html):
            return str(html)

    sys.modules["html2text"].HTML2Text = _HTML2Text  # type: ignore[attr-defined]
    sys.modules["bs4"].BeautifulSoup = lambda *a, **k: types.SimpleNamespace(  # type: ignore[attr-defined]
        prettify=lambda: ""
    )

    class _Disabled:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Native dependency disabled in the ABB binding")

        def __call__(self, *args, **kwargs):
            raise RuntimeError("Native dependency disabled in the ABB binding")

        @classmethod
        def from_documents(cls, *args, **kwargs):
            raise RuntimeError("Native dependency disabled in the ABB binding")

    sys.modules["googleapiclient.discovery"].build = lambda *a, **k: object()  # type: ignore[attr-defined]
    sys.modules["googleapiclient.http"].MediaFileUpload = _Disabled  # type: ignore[attr-defined]
    sys.modules["google.auth.transport.requests"].Request = _Disabled  # type: ignore[attr-defined]
    sys.modules["google.oauth2.credentials"].Credentials = _Disabled  # type: ignore[attr-defined]
    sys.modules[
        "google.oauth2.credentials"
    ].Credentials.from_authorized_user_file = classmethod(  # type: ignore[attr-defined]
        lambda cls, *a, **k: None
    )
    sys.modules["google_auth_oauthlib.flow"].InstalledAppFlow = _Disabled  # type: ignore[attr-defined]
    sys.modules["langchain_chroma"].Chroma = _Disabled  # type: ignore[attr-defined]
    sys.modules["langchain_google_genai"].ChatGoogleGenerativeAI = _Disabled  # type: ignore[attr-defined]
    sys.modules["langchain_google_genai"].GoogleGenerativeAIEmbeddings = _Disabled  # type: ignore[attr-defined]


def _openai_chat_model():
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for ABB model interception")
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "deepseek-v4-pro"),
        temperature=0.1,
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


def _patched_invoke_llm(
    system_prompt,
    user_message,
    model="gemini-1.5-flash",
    llm_provider="google",
    response_format=None,
):
    """Replace Gemini/provider SDK calls with intercepted OpenAI-compatible chat."""

    del model, llm_provider
    llm = _openai_chat_model()
    if response_format is not None:
        schema = response_format.model_json_schema()
        bound = llm.bind(response_format={"type": "json_object"})
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{user_message}\n\nRespond with ONLY a JSON object that matches "
                    f"this JSON Schema:\n{json.dumps(schema)}"
                ),
            },
        ]
        response = bound.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return response_format.model_validate_json(content)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    response = llm.invoke(messages)
    content = response.content if hasattr(response, "content") else str(response)
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return content


class _InMemoryLeadLoader:
    """CRM stand-in that exposes exactly the Case-supplied lead."""

    available_statuses = ["NEW", "UNQUALIFIED", "ATTEMPTED_TO_CONTACT"]

    def __init__(self, record: dict[str, Any]):
        self._record = dict(record)
        self.updates: list[tuple[str, Any]] = []

    def fetch_records(self, status_filter="NEW"):
        del status_filter
        return [dict(self._record)]

    def update_record(self, lead_id, status_or_data):
        self.updates.append((lead_id, status_or_data))
        return {"id": lead_id, "updated": status_or_data}


class _NoGoogleDocsManager:
    def __init__(self):
        pass

    def add_document(self, content, doc_title, folder_name, make_shareable=False, folder_shareable=False, markdown=False):
        del content, markdown, folder_shareable
        doc_id = re.sub(r"[^a-zA-Z0-9]+", "-", doc_title).strip("-").lower() or "doc"
        folder = re.sub(r"[^a-zA-Z0-9]+", "-", folder_name).strip("-").lower() or "folder"
        document_url = f"https://docs.example.invalid/document/d/{doc_id}"
        return {
            "document_url": document_url,
            "shareable_url": f"{document_url}?share=1" if make_shareable else None,
            "folder_url": f"https://drive.example.invalid/folders/{folder}",
        }

    def get_document(self, doc_url):
        del doc_url
        return ""


class _NoGmailTools:
    def __init__(self):
        self.service = None

    def create_draft_email(self, recipient, subject, email_content):
        print(f"[ABB] Gmail unavailable; draft retained locally for {recipient}: {subject}")
        return {"id": "local-draft", "recipient": recipient, "subject": subject, "body": email_content}

    def send_email(self, recipient, subject, email_content):
        print(f"[ABB] Gmail unavailable; send skipped for {recipient}: {subject}")
        return None


def _default_fixture(lead: dict[str, Any]) -> dict[str, Any]:
    first = lead.get("First Name", "Alex")
    last = lead.get("Last Name", "Rivera")
    email = lead.get("Email", "alex.rivera@northwind-labs.example")
    company = lead.get("company_name") or email.split("@")[-1].split(".")[0].replace("-", " ").title()
    website = lead.get("company_website") or "https://northwind-labs.example"
    return {
        "lead_profile": (
            f"{first} {last} is Marketing Director at {company}. "
            f"Focus areas: AI-assisted content ops, demand generation, and CRM automation. "
            f"Based on publicly described role context for outreach preparation."
        ),
        "company_name": company,
        "company_website": website,
        "company_linkedin_url": f"https://www.linkedin.com/company/{company.lower().replace(' ', '-')}",
        "company_profile": (
            f"{company} sells B2B marketing software to mid-market teams. "
            f"Public materials emphasize content velocity and attribution gaps."
        ),
        "website_markdown": (
            f"# {company}\n\nWe help growth teams ship content faster.\n\n"
            f"Blog: {website}/blog\nYouTube: https://www.youtube.com/@{company.lower().replace(' ', '')}\n"
            f"Twitter: https://twitter.com/{company.lower().replace(' ', '')}\n"
            f"Facebook: https://facebook.com/{company.lower().replace(' ', '')}\n"
        ),
        "blog_markdown": (
            f"# {company} Blog\n\nRecent posts discuss AI drafting, editorial QA, and SEO ops. "
            f"Teams struggle with inconsistent brand voice across channels."
        ),
        "news": (
            f"{company} announced a Series B focused on AI marketing assistants. "
            f"Leadership cited manual content review as a bottleneck."
        ),
        "youtube_stats": (
            f"Channel for {company}: 12k subscribers, recent uploads on AI workflows and attribution."
        ),
        "case_study": (
            "ElevateAI helped Spark Retail cut content production cycle time by 40% "
            "using AI drafting plus human editorial review, while improving reply rates "
            "on personalized outreach sequences."
        ),
    }


def _parse_case_input(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (CRM record, research fixture) from text or JSON Case input."""

    payload: dict[str, Any]
    if isinstance(value, dict):
        payload = dict(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Lead brief must be a non-empty string or object.")
        try:
            loaded = json.loads(text)
            payload = loaded if isinstance(loaded, dict) else {"brief": text}
        except json.JSONDecodeError:
            payload = {"brief": text}
            # Prefer an embedded lead-brief JSON object when the Case wraps it in prose.
            embedded = re.search(r"Lead brief:\s*(\{.*?\})", text, flags=re.S)
            if embedded:
                try:
                    embedded_obj = json.loads(embedded.group(1))
                    if isinstance(embedded_obj, dict):
                        payload.update(embedded_obj)
                except json.JSONDecodeError:
                    pass
            briefing = re.search(
                r"Research briefing:\s*(.*?)(?:\n\nProduce |\n\nQuoted material:|\Z)",
                text,
                flags=re.S,
            )
            if briefing:
                payload["research_briefing"] = briefing.group(1).strip()
            email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
            if email_match and "email" not in payload:
                payload["email"] = email_match.group(0)
            name_match = re.search(
                r"(?:for|lead)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)",
                text,
            )
            if name_match and "first_name" not in payload and "name" not in payload:
                payload["first_name"] = name_match.group(1)
                payload["last_name"] = name_match.group(2)
    else:
        raise ValueError("Case input must be a string or JSON object describing one lead.")

    full_name = str(payload.get("name") or "").strip()
    if full_name and "first_name" not in payload and "First Name" not in payload:
        parts = full_name.split(None, 1)
        payload["first_name"] = parts[0]
        payload["last_name"] = parts[1] if len(parts) > 1 else "Lead"

    first = str(payload.get("first_name") or payload.get("First Name") or "Alex")
    last = str(payload.get("last_name") or payload.get("Last Name") or "Rivera")
    email = str(
        payload.get("email")
        or payload.get("Email")
        or "alex.rivera@northwind-labs.example"
    )
    company_name = payload.get("company_name") or payload.get("company")
    record = {
        "id": str(payload.get("id") or "lead-1"),
        "First Name": first,
        "Last Name": last,
        "Email": email,
        "Phone": str(payload.get("phone") or payload.get("Phone") or ""),
        "Address": str(payload.get("address") or payload.get("Address") or ""),
        "company_name": company_name,
        "company_website": payload.get("company_website"),
    }
    fixture = _default_fixture(record)
    for key in fixture:
        if key in payload and payload[key]:
            fixture[key] = str(payload[key])
    title = str(payload.get("title") or "").strip()
    context = str(payload.get("context") or "").strip()
    research_briefing = str(payload.get("research_briefing") or "").strip()
    brief_bits = []
    if payload.get("brief"):
        brief_bits.append(str(payload["brief"]))
    if title or context:
        brief_bits.append(
            f"Role/title: {title or 'n/a'}. Context: {context or 'n/a'}."
        )
    if research_briefing:
        fixture["company_profile"] = (
            f"{fixture['company_profile']}\n\nResearch briefing:\n{research_briefing}"
        )
        fixture["lead_profile"] = (
            f"{fixture['lead_profile']}\n\nResearch briefing:\n{research_briefing}"
        )
        fixture["news"] = research_briefing
    if brief_bits:
        fixture["lead_profile"] = (
            f"{fixture['lead_profile']}\n\nOperator brief:\n" + "\n".join(brief_bits)
        )
    return record, fixture


def _build_fixture_callables(fixture: dict[str, Any]):
    def _research_lead_on_linkedin(lead_name, lead_email):
        del lead_name, lead_email
        return (
            fixture["lead_profile"],
            fixture["company_name"],
            fixture["company_website"],
            fixture["company_linkedin_url"],
        )

    def _research_lead_company(company_linkedin_url):
        del company_linkedin_url
        return {"summary": fixture["company_profile"]}

    def _generate_company_profile(existing_profile, website_summary):
        return f"{existing_profile}\n\nWebsite summary:\n{website_summary}"

    def _scrape(url):
        url_l = (url or "").lower()
        if "blog" in url_l:
            return fixture["blog_markdown"]
        return fixture["website_markdown"]

    def _news(company):
        del company
        return fixture["news"]

    def _youtube(url):
        del url
        return fixture["youtube_stats"]

    def _case_study(description):
        del description
        return fixture["case_study"]

    return {
        "research_lead_on_linkedin": _research_lead_on_linkedin,
        "research_lead_company": _research_lead_company,
        "generate_company_profile": _generate_company_profile,
        "scrape": _scrape,
        "news": _news,
        "youtube": _youtube,
        "case_study": _case_study,
    }


def _apply_runtime_patches(fixture: dict[str, Any]) -> None:
    """Patch leaf modules first, then rebind names on ``src.nodes`` after import."""

    import src.tools.base.gmail_tools as gmail_mod
    import src.tools.base.markdown_scraper_tool as scrape_mod
    import src.tools.base.search_tools as search_mod
    import src.tools.company_research as company_mod
    import src.tools.google_docs_tools as docs_mod
    import src.tools.lead_research as lead_mod
    import src.tools.rag_tool as rag_mod
    import src.tools.youtube_tools as youtube_mod
    import src.utils as utils_mod

    calls = _build_fixture_callables(fixture)

    utils_mod.invoke_llm = _patched_invoke_llm
    docs_mod.GoogleDocsManager = _NoGoogleDocsManager
    gmail_mod.GmailTools = _NoGmailTools
    lead_mod.research_lead_on_linkedin = calls["research_lead_on_linkedin"]
    company_mod.research_lead_company = calls["research_lead_company"]
    company_mod.generate_company_profile = calls["generate_company_profile"]
    scrape_mod.scrape_website_to_markdown = calls["scrape"]
    search_mod.get_recent_news = calls["news"]
    search_mod.google_search = lambda query: [
        {"link": fixture["company_website"], "title": query}
    ]
    youtube_mod.get_youtube_stats = calls["youtube"]
    rag_mod.fetch_similar_case_study = calls["case_study"]

    # Import graph/nodes only after leaf patches exist for a cold import.
    from src.graph import OutReachAutomation  # noqa: F401
    import src.nodes as nodes_mod
    from src.state import Report

    nodes_mod.invoke_llm = _patched_invoke_llm
    nodes_mod.GoogleDocsManager = _NoGoogleDocsManager
    nodes_mod.GmailTools = _NoGmailTools
    nodes_mod.research_lead_on_linkedin = calls["research_lead_on_linkedin"]
    nodes_mod.research_lead_company = calls["research_lead_company"]
    nodes_mod.generate_company_profile = calls["generate_company_profile"]
    nodes_mod.scrape_website_to_markdown = calls["scrape"]
    nodes_mod.get_recent_news = calls["news"]
    nodes_mod.get_youtube_stats = calls["youtube"]
    nodes_mod.fetch_similar_case_study = calls["case_study"]

    def _analyze_blog_content(self, state):
        company_data = state["company_data"]
        blog_url = company_data.social_media_links.blog
        if not blog_url:
            return {"reports": []}
        blog_content = nodes_mod.scrape_website_to_markdown(blog_url)
        from src.prompts import BLOG_ANALYSIS_PROMPT

        content = nodes_mod.invoke_llm(
            system_prompt=BLOG_ANALYSIS_PROMPT.format(company_name=company_data.name),
            user_message=blog_content,
            model="gemini-1.5-flash",
        )
        return {
            "reports": [
                Report(title="Blog Analysis Report", content=content, is_markdown=True)
            ]
        }

    def _analyze_social_media_content(self, state):
        company_data = state["company_data"]
        youtube_url = company_data.social_media_links.youtube
        if not youtube_url:
            return {"company_data": company_data, "reports": []}
        from src.prompts import YOUTUBE_ANALYSIS_PROMPT

        youtube_data = nodes_mod.get_youtube_stats(youtube_url)
        insight = nodes_mod.invoke_llm(
            system_prompt=YOUTUBE_ANALYSIS_PROMPT.format(company_name=company_data.name),
            user_message=youtube_data,
            model="gemini-1.5-flash",
        )
        return {
            "company_data": company_data,
            "reports": [
                Report(title="Youtube Analysis Report", content=insight, is_markdown=True)
            ],
        }

    def _score_lead(state):
        from src.prompts import SCORE_LEAD_PROMPT
        from src.utils import get_report

        reports = state["reports"]
        global_research_report = get_report(reports, "Global Lead Analysis Report")
        raw = nodes_mod.invoke_llm(
            system_prompt=SCORE_LEAD_PROMPT,
            user_message=global_research_report,
            model="gemini-1.5-pro",
        )
        match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
        if not match:
            raise RuntimeError(f"Lead score was not numeric: {raw!r}")
        return {"lead_score": match.group(1)}

    def _update_crm(self, state):
        from src.utils import get_current_date

        # Upstream clears reports here; copy outreach text into state fields first
        # so the binding can still project a non-empty answer after the run ends.
        reports = state.get("reports") or []
        email = _report_content(reports, "Personalized Email")
        interview = _report_content(reports, "Interview Script")
        new_data = {
            "Status": "ATTEMPTED_TO_CONTACT",
            "Score": state["lead_score"],
            "Analysis Reports": state.get("reports_folder_link", ""),
            "Outreach Report": state.get("custom_outreach_report_link", ""),
            "Last Contacted": get_current_date(),
        }
        self.lead_loader.update_record(state["current_lead"].id, new_data)
        updates: dict[str, Any] = {
            "number_leads": state["number_leads"] - 1,
            "reports": [],
        }
        if email:
            updates["personalized_email"] = email
        if interview:
            updates["interview_script"] = interview
        return updates

    nodes_mod.OutReachAutomationNodes.analyze_blog_content = _analyze_blog_content
    nodes_mod.OutReachAutomationNodes.analyze_social_media_content = (
        _analyze_social_media_content
    )
    nodes_mod.OutReachAutomationNodes.score_lead = staticmethod(_score_lead)
    nodes_mod.OutReachAutomationNodes.update_CRM = _update_crm


def _report_content(reports, title: str) -> str:
    for report in reports or []:
        if getattr(report, "title", None) == title:
            return getattr(report, "content", "") or ""
    return ""


class SalesOutreachBinding:
    def __init__(self):
        self._closed = False
        self._loader: _InMemoryLeadLoader | None = None

    def invoke(self, value, config=None):
        if self._closed:
            raise RuntimeError("Sales outreach binding is closed.")
        if not _SOURCE_ROOT.is_dir():
            raise RuntimeError(f"Imported Agent source not found at {_SOURCE_ROOT}")

        record, fixture = _parse_case_input(value)
        global _CASE_CONTEXT
        _CASE_CONTEXT = {"record": record, "fixture": fixture}

        os.chdir(_SOURCE_ROOT)
        if str(_SOURCE_ROOT) not in sys.path:
            sys.path.insert(0, str(_SOURCE_ROOT))

        _install_import_stubs()
        _apply_runtime_patches(fixture)

        from src.graph import OutReachAutomation

        self._loader = _InMemoryLeadLoader(record)
        app = OutReachAutomation(self._loader).app
        run_config = dict(config or {})
        run_config.setdefault("recursion_limit", 1000)
        final_state = app.invoke({"leads_ids": [record["id"]]}, config=run_config)

        reports = final_state.get("reports") or []
        score = str(final_state.get("lead_score") or "")
        personalized = (
            str(final_state.get("personalized_email") or "").strip()
            or _report_content(reports, "Personalized Email")
        )
        interview = (
            str(final_state.get("interview_script") or "").strip()
            or _report_content(reports, "Interview Script")
        )
        try:
            score_value = float(score)
        except ValueError:
            score_value = 0.0
        parsed_lead = {
            "name": f"{record['First Name']} {record['Last Name']}".strip(),
            "email": record["Email"],
            "company": str(
                record.get("company_name") or fixture.get("company_name") or ""
            ),
            "phone": record.get("Phone") or "",
            "address": record.get("Address") or "",
            "lead_score": score,
            "qualified": score_value >= 7,
        }
        # Upstream only drafts outreach when score >= 7; surface that decision
        # instead of projecting an empty personalized_email. Also echo the
        # parsed lead fields so Cases that ask for JSON extraction still see them.
        if score_value < 7 and not personalized:
            personalized = (
                f"Lead not qualified (score {score or 'n/a'} < 7); "
                "no outreach email drafted. "
                "No live CRM is connected, so no CRM record was updated.\n\n"
                f"Parsed lead fields:\n{json.dumps(parsed_lead, ensure_ascii=False)}"
            )
        return {
            "personalized_email": personalized,
            "interview_script": interview,
            "lead_score": score,
            "parsed_lead": parsed_lead,
            "custom_outreach_report_link": final_state.get(
                "custom_outreach_report_link", ""
            ),
            "reports_folder_link": final_state.get("reports_folder_link", ""),
            "crm_updates": list(self._loader.updates),
        }

    def close(self):
        self._closed = True
        self._loader = None


def create_graph():
    """Return a fresh binding.

    Example input: a lead brief string, or
    ``{"first_name":"Alex","last_name":"Rivera","email":"alex@acme.example"}``.
    """

    return SalesOutreachBinding()
