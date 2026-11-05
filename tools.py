"""GHL Command for Hermes Agent.

Native tools for GoHighLevel CRM operations: contacts, pipelines, calendars,
workflows, email and SMS sends directly from chat.

API host is services.leadconnectorhq.com (the only host that accepts pit-
Private Integration Tokens) with Version header 2021-07-28. Auth goes
through Hermes secrets via agent.secret_scope.get_secret, never os.environ
directly, so profile multiplexing is respected (catalog rule 11).

Default location falls back to the configured GHL_LOCATION_ID unless
GHL_LOCATION_ID is set or a location_id argument is passed.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TOOLSET = "ghl-command"
GHL_BASE = "https://services.leadconnectorhq.com"
DEFAULT_LOCATION = "NvqL18HRoYJ29fAGdWSH"


def tool_error(message: str) -> str:
    """Tool error envelope (same JSON shape as core)."""
    return json.dumps({"error": str(message)}, ensure_ascii=False)


def _get_config() -> tuple[str, str]:
    """Return (token, location) via Hermes secret scope.

    Falls back to DEFAULT_LOCATION when GHL_LOCATION_ID is unset.
    """
    from agent.secret_scope import get_secret

    token = get_secret("GHL_API_KEY", "") or ""
    location = get_secret("GHL_LOCATION_ID", "") or ""
    if not location:
        location = DEFAULT_LOCATION
    return token, location


def _get_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Version": "2021-07-28",
        "Accept": "application/json",
        "User-Agent": "curl/8.5.0",
    }


def _api(
    method: str,
    path: str,
    location_id: Optional[str] = None,
    query: Optional[Dict[str, str]] = None,
    body: Optional[Any] = None,
    timeout: float = 20,
):
    """One GHL REST call. Raises on HTTP error, returns parsed JSON."""
    token, default_loc = _get_config()
    if not token:
        raise RuntimeError(
            "GHL_API_KEY is not set. Add it via Hermes secrets. " "Private Integration Token (pit-...) is required."
        )
    loc = location_id or default_loc
    url = GHL_BASE + path
    # Always include locationId as query for list endpoints when not in body
    params = dict(query or {})
    if loc and "locationId" not in params and "location_id" not in params:
        # Only add for endpoints that accept it; safe to pass always, GHL ignores extra on some routes
        # but we keep it for clarity. POST /contacts/search needs it in body instead.
        if path.startswith("/contacts/search"):
            pass
        else:
            params["locationId"] = loc
    if params:
        qs = urllib.parse.urlencode(params, doseq=True)
        url = url + ("&" if "?" in url else "?") + qs
    data_bytes = None
    if body is not None:
        data_bytes = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data_bytes, method=method.upper(), headers=_get_headers(token)
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {"raw": raw.decode("utf-8", errors="ignore")}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        # Keep GHL error body visible for debugging (token vs location vs scope)
        raise RuntimeError(f"GHL API {method} {path} failed {e.code}: {raw[:2000]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"GHL network error for {path}: {e.reason}")


def _resolve_location(args: dict) -> str:
    token, default_loc = _get_config()
    return (args.get("location_id") or args.get("locationId") or default_loc or "").strip()


def _compact_contact(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": c.get("id"),
        "firstName": c.get("firstName"),
        "lastName": c.get("lastName"),
        "email": c.get("email"),
        "phone": c.get("phone"),
        "tags": c.get("tags"),
        "companyName": c.get("companyName"),
        "dateAdded": c.get("dateAdded"),
    }


def _dispatch(fn, log_name: str, fail_msg: str) -> str:
    try:
        result = fn()
        # fn already returns dict; wrap as {"result": ...}
        return json.dumps({"result": result}, ensure_ascii=False)
    except Exception as e:
        logger.error("%s error: %s", log_name, e)
        return tool_error(f"{fail_msg}: {e}")


def _check_ghl_available() -> bool:
    """Tool is only available when token is set."""
    try:
        token, _ = _get_config()
        return bool(token)
    except Exception:
        return False


# --- Handlers ---

def _handle_list_contacts(args: dict, **kw) -> str:
    loc = _resolve_location(args)
    limit = args.get("limit", 20)
    def run():
        res = _api("GET", "/contacts/", location_id=loc, query={"limit": str(limit), "page": str(args.get("page", 1))})
        contacts = res.get("contacts") or res.get("data") or []
        return {"location_id": loc, "count": len(contacts), "contacts": [_compact_contact(c) for c in contacts], "meta": res.get("meta")}
    return _dispatch(run, "ghl_list_contacts", "Failed to list contacts")


def _handle_search_contacts(args: dict, **kw) -> str:
    loc = _resolve_location(args)
    query = (args.get("query") or args.get("email") or "").strip()
    if not query:
        return tool_error("Missing required parameter: query (email or name)")
    page_limit = args.get("pageLimit") or args.get("limit", 20)
    def run():
        body = {"locationId": loc, "query": query, "pageLimit": int(page_limit)}
        # GHL search supports POST with query and pageLimit
        res = _api("POST", "/contacts/search", location_id=loc, body=body)
        contacts = res.get("contacts") or res.get("data") or []
        return {"location_id": loc, "count": len(contacts), "contacts": [_compact_contact(c) for c in contacts]}
    return _dispatch(run, "ghl_search_contacts", "Failed to search contacts")


def _handle_create_contact(args: dict, **kw) -> str:
    loc = _resolve_location(args)
    first = args.get("firstName") or args.get("first_name")
    email = args.get("email")
    phone = args.get("phone")
    if not first and not email and not phone:
        return tool_error("Missing required parameters: firstName, email or phone")
    def run():
        body = {"locationId": loc}
        for key in ["firstName", "lastName", "email", "phone", "tags", "companyName", "address", "source"]:
            if args.get(key):
                body[key] = args[key]
        # Accept tags as string or list
        if isinstance(body.get("tags"), str):
            body["tags"] = [t.strip() for t in body["tags"].split(",") if t.strip()]
        res = _api("POST", "/contacts/", location_id=loc, body=body)
        contact = res.get("contact") or res.get("data") or res
        return {"location_id": loc, "contact": _compact_contact(contact) if isinstance(contact, dict) else contact}
    return _dispatch(run, "ghl_create_contact", "Failed to create contact")


def _handle_update_contact(args: dict, **kw) -> str:
    contact_id = args.get("contact_id") or args.get("contactId")
    if not contact_id:
        return tool_error("Missing required parameter: contact_id")
    def run():
        body = {}
        for key in ["firstName", "lastName", "email", "phone", "tags", "companyName", "address"]:
            if args.get(key) is not None:
                body[key] = args[key]
        if isinstance(body.get("tags"), str):
            body["tags"] = [t.strip() for t in body["tags"].split(",") if t.strip()]
        if not body:
            return {"error": "No fields to update", "contact_id": contact_id}
        # IMPORTANT: contact update must NOT include locationId (returns 422)
        res = _api("PUT", f"/contacts/{contact_id}", body=body)
        contact = res.get("contact") or res
        return {"contact_id": contact_id, "contact": _compact_contact(contact) if isinstance(contact, dict) else contact}
    return _dispatch(run, "ghl_update_contact", "Failed to update contact")


def _handle_delete_contact(args: dict, **kw) -> str:
    contact_id = args.get("contact_id") or args.get("contactId")
    if not contact_id:
        return tool_error("Missing required parameter: contact_id")
    loc = _resolve_location(args)
    def run():
        res = _api("DELETE", f"/contacts/{contact_id}", location_id=loc)
        return {"contact_id": contact_id, "location_id": loc, "result": res}
    return _dispatch(run, "ghl_delete_contact", "Failed to delete contact")


def _handle_send_sms(args: dict, **kw) -> str:
    contact_id = args.get("contact_id") or args.get("contactId")
    message = args.get("message") or args.get("body")
    phone = args.get("phone") or args.get("to")
    if not message:
        return tool_error("Missing required parameter: message")
    if not contact_id and not phone:
        return tool_error("Missing required parameter: contact_id or phone")
    loc = _resolve_location(args)
    def run():
        body = {"locationId": loc, "contactId": contact_id, "type": "SMS", "message": message}
        if phone and not contact_id:
            body["phone"] = phone
        # GHL conversations/messages POST
        res = _api("POST", "/conversations/messages", location_id=loc, body=body)
        return {"location_id": loc, "contact_id": contact_id, "phone": phone, "message_id": res.get("id") or res.get("messageId"), "raw": res}
    return _dispatch(run, "ghl_send_sms", "Failed to send SMS")


def _handle_send_email(args: dict, **kw) -> str:
    contact_id = args.get("contact_id") or args.get("contactId")
    email = args.get("email") or args.get("to")
    subject = args.get("subject") or "Message from Pursuing X"
    html = args.get("html") or args.get("htmlBody") or args.get("body") or args.get("message")
    if not html:
        return tool_error("Missing required parameter: html (email body)")
    if not contact_id and not email:
        return tool_error("Missing required parameter: contact_id or email")
    loc = _resolve_location(args)
    def run():
        body = {"locationId": loc, "contactId": contact_id, "type": "Email", "subject": subject, "htmlBody": html}
        if email and not contact_id:
            body["email"] = email
        res = _api("POST", "/conversations/messages", location_id=loc, body=body)
        return {"location_id": loc, "contact_id": contact_id, "email": email, "subject": subject, "message_id": res.get("id") or res.get("messageId"), "raw": res}
    return _dispatch(run, "ghl_send_email", "Failed to send email")


def _handle_list_pipelines(args: dict, **kw) -> str:
    loc = _resolve_location(args)
    def run():
        res = _api("GET", "/opportunities/pipelines", location_id=loc)
        pipelines = res.get("pipelines") or res.get("data") or res
        # Normalize pipeline summaries
        summaries = []
        if isinstance(pipelines, list):
            for p in pipelines:
                summaries.append({"id": p.get("id"), "name": p.get("name"), "stages": p.get("stages")})
        else:
            summaries = pipelines
        return {"location_id": loc, "pipelines": summaries, "raw_count": len(pipelines) if isinstance(pipelines, list) else None}
    return _dispatch(run, "ghl_list_pipelines", "Failed to list pipelines")


def _handle_search_opportunities(args: dict, **kw) -> str:
    loc = _resolve_location(args)
    def run():
        query = {"locationId": loc, "limit": str(args.get("limit", 20))}
        if args.get("pipeline_id"):
            query["pipeline_id"] = args["pipeline_id"]
        if args.get("contact_id"):
            query["contact_id"] = args["contact_id"]
        res = _api("GET", "/opportunities/search", location_id=loc, query=query)
        opps = res.get("opportunities") or res.get("data") or []
        return {"location_id": loc, "count": len(opps), "opportunities": opps}
    return _dispatch(run, "ghl_search_opportunities", "Failed to search opportunities")


def _handle_move_opportunity(args: dict, **kw) -> str:
    opp_id = args.get("opportunity_id") or args.get("opportunityId")
    if not opp_id:
        return tool_error("Missing required parameter: opportunity_id")
    def run():
        body = {}
        # Accept stage_id or status
        if args.get("stage_id"):
            body["stageId"] = args["stage_id"]
        if args.get("stage"):
            body["stageId"] = args["stage"]
        if args.get("status"):
            body["status"] = args["status"]
        if not body:
            return {"error": "Provide stage_id or status", "opportunity_id": opp_id}
        res = _api("PUT", f"/opportunities/{opp_id}", body=body)
        return {"opportunity_id": opp_id, "result": res}
    return _dispatch(run, "ghl_move_opportunity", "Failed to move opportunity")


def _handle_list_workflows(args: dict, **kw) -> str:
    loc = _resolve_location(args)
    def run():
        res = _api("GET", "/workflows/", location_id=loc)
        workflows = res.get("workflows") or res.get("data") or res
        if isinstance(workflows, list):
            summarized = [{"id": w.get("id"), "name": w.get("name"), "isActive": w.get("isActive")} for w in workflows]
        else:
            summarized = workflows
        return {"location_id": loc, "workflows": summarized}
    return _dispatch(run, "ghl_list_workflows", "Failed to list workflows")


def _handle_enroll_workflow(args: dict, **kw) -> str:
    contact_id = args.get("contact_id") or args.get("contactId")
    workflow_id = args.get("workflow_id") or args.get("workflowId")
    if not contact_id or not workflow_id:
        return tool_error("Missing required parameters: contact_id and workflow_id")
    def run():
        # Exact singular endpoint: POST /contacts/{contactId}/workflow/{workflowId} with {}
        res = _api("POST", f"/contacts/{contact_id}/workflow/{workflow_id}", body={})
        return {"contact_id": contact_id, "workflow_id": workflow_id, "result": res}
    return _dispatch(run, "ghl_enroll_workflow", "Failed to enroll in workflow")


# --- Schemas ---

GHL_LIST_CONTACTS_SCHEMA = {
    "name": "ghl_list_contacts",
    "description": "List GoHighLevel contacts for a location. Uses location_id or the configured default (Pursuing X Agency).",
    "parameters": {
        "type": "object",
        "properties": {
            "location_id": {"type": "string", "description": "Optional location ID. Defaults to PX Agency."},
            "limit": {"type": "integer", "description": "How many to return. Default 20."},
            "page": {"type": "integer", "description": "Page number. Default 1."},
        },
        "required": [],
    },
}

GHL_SEARCH_CONTACTS_SCHEMA = {
    "name": "ghl_search_contacts",
    "description": "Search GoHighLevel contacts by email or name. Use POST /contacts/search with query and pageLimit.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Email or name to search for."},
            "location_id": {"type": "string", "description": "Optional location ID."},
            "pageLimit": {"type": "integer", "description": "How many to return. Default 20."},
        },
        "required": ["query"],
    },
}

GHL_CREATE_CONTACT_SCHEMA = {
    "name": "ghl_create_contact",
    "description": "Create a GoHighLevel contact. Include locationId plus firstName, email or phone.",
    "parameters": {
        "type": "object",
        "properties": {
            "firstName": {"type": "string"},
            "lastName": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "tags": {"type": "string", "description": "Comma separated tags."},
            "companyName": {"type": "string"},
            "location_id": {"type": "string"},
        },
        "required": [],
    },
}

GHL_UPDATE_CONTACT_SCHEMA = {
    "name": "ghl_update_contact",
    "description": "Update a GoHighLevel contact. Do not include locationId in the body (returns 422).",
    "parameters": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "firstName": {"type": "string"},
            "lastName": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "tags": {"type": "string", "description": "Comma separated tags."},
            "companyName": {"type": "string"},
        },
        "required": ["contact_id"],
    },
}

GHL_DELETE_CONTACT_SCHEMA = {
    "name": "ghl_delete_contact",
    "description": "Delete a GoHighLevel contact by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "location_id": {"type": "string"},
        },
        "required": ["contact_id"],
    },
}

GHL_SEND_SMS_SCHEMA = {
    "name": "ghl_send_sms",
    "description": "Send an SMS via GoHighLevel conversations. Provide contact_id or phone plus message.",
    "parameters": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "phone": {"type": "string"},
            "message": {"type": "string"},
            "location_id": {"type": "string"},
        },
        "required": ["message"],
    },
}

GHL_SEND_EMAIL_SCHEMA = {
    "name": "ghl_send_email",
    "description": "Send an email via GoHighLevel conversations. Provide contact_id or email plus html body.",
    "parameters": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "email": {"type": "string"},
            "subject": {"type": "string"},
            "html": {"type": "string", "description": "HTML email body or plain text."},
            "location_id": {"type": "string"},
        },
        "required": ["html"],
    },
}

GHL_LIST_PIPELINES_SCHEMA = {
    "name": "ghl_list_pipelines",
    "description": "List GoHighLevel pipelines for a location.",
    "parameters": {
        "type": "object",
        "properties": {
            "location_id": {"type": "string"},
        },
        "required": [],
    },
}

GHL_SEARCH_OPPORTUNITIES_SCHEMA = {
    "name": "ghl_search_opportunities",
    "description": "Search GoHighLevel opportunities or pipeline deals.",
    "parameters": {
        "type": "object",
        "properties": {
            "location_id": {"type": "string"},
            "pipeline_id": {"type": "string"},
            "contact_id": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": [],
    },
}

GHL_MOVE_OPPORTUNITY_SCHEMA = {
    "name": "ghl_move_opportunity",
    "description": "Move an opportunity to a new pipeline stage. Provide opportunity_id plus stage_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "opportunity_id": {"type": "string"},
            "stage_id": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["opportunity_id"],
    },
}

GHL_LIST_WORKFLOWS_SCHEMA = {
    "name": "ghl_list_workflows",
    "description": "List GoHighLevel workflows for a location.",
    "parameters": {
        "type": "object",
        "properties": {
            "location_id": {"type": "string"},
        },
        "required": [],
    },
}

GHL_ENROLL_WORKFLOW_SCHEMA = {
    "name": "ghl_enroll_workflow",
    "description": "Enroll a contact into a GoHighLevel workflow. Uses POST /contacts/{contactId}/workflow/{workflowId} with {}.",
    "parameters": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "workflow_id": {"type": "string"},
        },
        "required": ["contact_id", "workflow_id"],
    },
}


TOOLS = (
    (GHL_LIST_CONTACTS_SCHEMA, _handle_list_contacts),
    (GHL_SEARCH_CONTACTS_SCHEMA, _handle_search_contacts),
    (GHL_CREATE_CONTACT_SCHEMA, _handle_create_contact),
    (GHL_UPDATE_CONTACT_SCHEMA, _handle_update_contact),
    (GHL_DELETE_CONTACT_SCHEMA, _handle_delete_contact),
    (GHL_SEND_SMS_SCHEMA, _handle_send_sms),
    (GHL_SEND_EMAIL_SCHEMA, _handle_send_email),
    (GHL_LIST_PIPELINES_SCHEMA, _handle_list_pipelines),
    (GHL_SEARCH_OPPORTUNITIES_SCHEMA, _handle_search_opportunities),
    (GHL_MOVE_OPPORTUNITY_SCHEMA, _handle_move_opportunity),
    (GHL_LIST_WORKFLOWS_SCHEMA, _handle_list_workflows),
    (GHL_ENROLL_WORKFLOW_SCHEMA, _handle_enroll_workflow),
)


def register_tools(ctx) -> None:
    """Register all GoHighLevel tools in the px-ghl-bridge toolset via the plugin API."""
    for schema, handler in TOOLS:
        ctx.register_tool(
            name=schema["name"],
            toolset=TOOLSET,
            schema=schema,
            handler=handler,
            check_fn=_check_ghl_available,
            emoji="📈",
        )
