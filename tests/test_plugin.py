"""Tests for px-ghl-bridge plugin registration."""

import sys
from pathlib import Path
import importlib.util

def test_registers_12_tools():
    plugin_dir = Path(__file__).resolve().parent.parent
    tools_path = plugin_dir / "tools.py"
    spec = importlib.util.spec_from_file_location("px_ghl_tools", tools_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    registered = []
    class FakeCtx:
        def register_tool(self, name, toolset, schema, handler, check_fn, emoji):
            registered.append(name)
            assert name == schema["name"]
    mod.register_tools(FakeCtx())
    assert len(registered) == 12
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
    assert set(registered) == expected

def test_default_location_constant():
    plugin_dir = Path(__file__).resolve().parent.parent
    tools_src = (plugin_dir / "tools.py").read_text(encoding="utf-8")
    assert "NvqL18HRoYJ29fAGdWSH" in tools_src
    assert "services.leadconnectorhq.com" in tools_src

def test_skill_host_rule():
    plugin_dir = Path(__file__).resolve().parent.parent
    tools_src = (plugin_dir / "tools.py").read_text(encoding="utf-8")
    # pit tokens must use leadconnector host, never rest.gohighlevel.com
    assert "rest.gohighlevel.com" not in tools_src
    assert "2021-07-28" in tools_src
