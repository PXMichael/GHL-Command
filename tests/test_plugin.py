"""Tests for the ghl-command plugin registration, approval gate, and id handling."""

import importlib.util
from pathlib import Path

import pytest


def _load():
    """Load tools.py by file path, not as a package import."""
    plugin_dir = Path(__file__).resolve().parent.parent
    tools_path = plugin_dir / "tools.py"
    spec = importlib.util.spec_from_file_location("px_ghl_tools", tools_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _src():
    return (Path(__file__).resolve().parent.parent / "tools.py").read_text(encoding="utf-8")


class FakeCtx:
    def __init__(self):
        self.registered = []
        self.hooks = {}

    def register_tool(self, name, toolset, schema, handler, check_fn, emoji):
        self.registered.append(name)
        assert name == schema["name"]

    def register_hook(self, name, handler):
        self.hooks[name] = handler


def test_registers_12_tools():
    mod = _load()
    ctx = FakeCtx()
    mod.register_tools(ctx)
    expected = {
        "ghl_list_contacts",
        "ghl_search_contacts",
        "ghl_create_contact",
        "ghl_update_contact",
        "ghl_delete_contact",
        "ghl_send_sms",
        "ghl_send_email",
        "ghl_list_pipelines",
        "ghl_search_opportunities",
        "ghl_move_opportunity",
        "ghl_list_workflows",
        "ghl_enroll_workflow",
    }
    assert set(ctx.registered) == expected
    assert len(ctx.registered) == 12


def test_registers_pre_tool_call_hook():
    mod = _load()
    ctx = FakeCtx()
    mod.register_tools(ctx)
    assert "pre_tool_call" in ctx.hooks
    assert ctx.hooks["pre_tool_call"] is mod.pre_tool_call


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("ghl_delete_contact", {"contact_id": "abc123"}),
        ("ghl_send_sms", {"contact_id": "abc123", "message": "hi there"}),
        ("ghl_send_email", {"email": "a@b.com", "subject": "Hello"}),
        ("ghl_enroll_workflow", {"contact_id": "abc123", "workflow_id": "wf9"}),
    ],
)
def test_approval_hook_gates_outbound_tools(tool_name, args):
    mod = _load()
    verdict = mod.pre_tool_call(tool_name=tool_name, args=args)
    assert isinstance(verdict, dict)
    assert verdict["action"] == "approve"
    assert verdict["rule_key"] == "ghl-command:" + tool_name
    assert tool_name in verdict["message"]


@pytest.mark.parametrize(
    "tool_name",
    [
        "ghl_list_contacts",
        "ghl_search_contacts",
        "ghl_create_contact",
        "ghl_update_contact",
        "ghl_list_pipelines",
        "ghl_search_opportunities",
        "ghl_move_opportunity",
        "ghl_list_workflows",
    ],
)
def test_approval_hook_ignores_read_tools(tool_name):
    mod = _load()
    assert mod.pre_tool_call(tool_name=tool_name, args={}) is None


def test_approval_message_names_the_target():
    mod = _load()
    v = mod.pre_tool_call(
        tool_name="ghl_send_sms", args={"contact_id": "c1", "message": "Your replay is ready"}
    )
    assert "c1" in v["message"]
    assert "Your replay is ready" in v["message"]


@pytest.mark.parametrize(
    "bad",
    [
        "../../admin",
        "abc/def",
        "abc?x=1",
        "abc#frag",
        "abc def",
        "abc%2f",
        "",
        None,
        "a" * 200 + "/x",
    ],
)
def test_safe_id_rejects_bad_values(bad):
    mod = _load()
    with pytest.raises(ValueError):
        mod._safe_id(bad, "contact_id")


@pytest.mark.parametrize("good", ["abc123", "ABC-123_xyz", "6Xy9Q2mNpL"])
def test_safe_id_accepts_clean_values(good):
    mod = _load()
    assert mod._safe_id(good, "contact_id") == good


def test_no_raw_id_in_url_paths():
    """Every interpolated path segment must go through _safe_id."""
    src = _src()
    assert 'f"/contacts/{contact_id}"' not in src
    assert 'f"/opportunities/{opp_id}"' not in src
    assert 'f"/contacts/{contact_id}/workflow/{workflow_id}"' not in src


def test_user_agent_is_honest():
    """No spoofed curl UA, and the real UA names the plugin and its repo."""
    src = _src()
    assert "curl/8.5.0" not in src
    assert "ghl-command/" in src
    assert "https://github.com/PXMichael/GHL-Command" in src


def test_no_hardcoded_location():
    """A public plugin must never ship a default location id."""
    src = _src()
    assert "NvqL18HRoYJ29fAGdWSH" not in src
    assert "DEFAULT_LOCATION" not in src
    assert "services.leadconnectorhq.com" in src


def test_skill_host_rule():
    src = _src()
    # pit tokens must use leadconnector host, never rest.gohighlevel.com
    assert "rest.gohighlevel.com" not in src
    assert "2021-07-28" in src
