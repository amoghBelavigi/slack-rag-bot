"""
MCP-based Metadata Assistant - Socket Mode Entry Point

This is the main entry point for running the Slack bot in Socket Mode.
Socket Mode allows the bot to receive events via WebSocket instead of HTTP webhooks.

Usage:
    python -m app.socket_mode
"""

import logging
import subprocess
import sys
import os

from app.core.config import app, settings
from slack_bolt.adapter.socket_mode import SocketModeHandler
from app.slack.handlers import register_slack_handlers

logger = logging.getLogger(__name__)


def start_mcp_server():
    """Start the MCP (Model Context Protocol) server as a subprocess.

    The MCP server provides Alation metadata tools that the assistant can use
    to fetch enterprise metadata from the Alation catalog.

    Returns:
        subprocess.Popen: The running MCP server process
    """
    logger.info("Starting Alation MCP Server as module")
    return subprocess.Popen([sys.executable, "-m", "app.services.rag.alation_server"])


def main():
    """Main entry point for the MCP-based Metadata Assistant."""
    # Start the MCP Server (Alation) as a subprocess
    mcp_process = start_mcp_server()
    
    try:
        # Register Slack event handlers
        register_slack_handlers()
        
        logger.info("⚡️ Starting MCP-based Metadata Assistant in Socket Mode...")
        handler = SocketModeHandler(app, settings.SLACK_APP_TOKEN)
        handler.start()
    finally:
        # Ensure MCP server is stopped when bot exits
        logger.info("Stopping MCP Server...")
        mcp_process.terminate()
        mcp_process.wait()


if __name__ == "__main__":
    main()
