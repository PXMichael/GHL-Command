"""GHL Command for Hermes Agent.

Native GoHighLevel tools for Hermes Agent. Contacts, pipelines,
calendars, workflows, email and SMS sends directly from chat.
"""

from __future__ import annotations

import logging

try:  # package import (Hermes loader)
    from .tools import register_tools, TOOLSET
except ImportError:  # file import (pytest collection)
    from tools import register_tools, TOOLSET

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Plugin entry point, called by the Hermes plugin loader."""
    register_tools(ctx)
    logger.info("ghl-command: registered 12 GHL tools in toolset %s", TOOLSET)


__all__ = ["register", "register_tools", "TOOLSET"]
