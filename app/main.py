"""
MCP-based Metadata Assistant - Main FastAPI Application

This module sets up the FastAPI application with Slack event routes.
Used when running the bot in HTTP mode (as opposed to Socket Mode).
"""

from fastapi import FastAPI
from app.slack.events import router as slack_router

# Initialize FastAPI application
app = FastAPI(
    title="MCP-based Metadata Assistant API",
    description="A Slack bot that answers questions using Alation enterprise metadata via MCP tools",
    version="1.0.0"
)

# Include Slack event handling routes
app.include_router(slack_router)
