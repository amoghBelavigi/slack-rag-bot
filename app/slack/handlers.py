"""
Slack Event Handlers

This module contains the Slack event handlers for the MCP-based Metadata Assistant.
It handles both @mentions and direct messages.
"""

import logging
from app.core.config import app
from app.services.rag.engine import rag_engine

logger = logging.getLogger(__name__)


def handle_rag_request(event: dict, client, say) -> None:
    """Process a RAG request from a Slack message.
    
    This function:
    1. Extracts the question from the message
    2. Retrieves thread history for context (if in a thread)
    3. Adds a reaction to show processing
    4. Calls the RAG engine for an answer
    5. Replies in the thread
    
    Args:
        event: The Slack event dictionary
        client: The Slack WebClient instance
        say: Function to send messages back to Slack
    """
    question = event["text"]
    history = ""
    
    # Retrieve thread context if this message is in a thread
    if "thread_ts" in event:
        history = _get_thread_history(client, event)
    
    # Reply in thread if exists, or start new thread
    thread_ts = event.get("thread_ts") or event.get("ts")
    
    try:
        # React immediately to show we are working
        _add_processing_reaction(client, event)
        
        # Get answer from RAG engine
        response = rag_engine.answer(question, history)

        # Use client.chat_postMessage directly to guarantee thread reply
        # (say() can sometimes post as a top-level message)
        client.chat_postMessage(
            channel=event["channel"],
            text=response.answer,
            thread_ts=thread_ts
        )
        
    except Exception as e:
        logger.error(f"RAG Error: {e}", exc_info=True)
        client.chat_postMessage(
            channel=event["channel"],
            text="Sorry, I encountered an error while processing your request.",
            thread_ts=thread_ts
        )


def _get_thread_history(client, event: dict) -> str:
    """Retrieve and format thread history for context.
    
    Args:
        client: The Slack WebClient instance
        event: The Slack event dictionary
        
    Returns:
        Formatted string of the last 10 messages in the thread
    """
    try:
        replies = client.conversations_replies(
            channel=event["channel"],
            ts=event["thread_ts"]
        )
        messages = replies.get("messages", [])
        
        # Format history as User/Assistant dialogue
        history_lines = []
        for msg in messages:
            role = "Assistant" if "bot_id" in msg else "User"
            text = msg.get("text", "")
            history_lines.append(f"{role}: {text}")
        
        # Keep only last 10 messages to avoid context overflow
        history = "\n".join(history_lines[-10:])
        logger.info(f"Retrieved {len(messages)} messages from thread.")
        return history
        
    except Exception as e:
        logger.error(f"Error fetching thread history: {e}")
        return ""


def _add_processing_reaction(client, event: dict) -> None:
    """Add an 'eyes' reaction to show the bot is processing.
    
    Args:
        client: The Slack WebClient instance
        event: The Slack event dictionary
    """
    try:
        logger.info(f"Adding reaction 'eyes' to {event.get('ts')}")
        client.reactions_add(
            channel=event["channel"],
            timestamp=event["ts"],
            name="eyes"
        )
    except Exception as e:
        logger.error(f"Failed to add reaction: {e}")


@app.event("app_mention")
def handle_app_mention(event: dict, client, say) -> None:
    """Handle @mentions of the bot in channels."""
    handle_rag_request(event, client, say)


@app.event("message")
def handle_message(event: dict, client, say) -> None:
    """Handle direct messages to the bot."""
    if event.get("channel_type") == "im":
        handle_rag_request(event, client, say)


def register_slack_handlers() -> None:
    """Register all Slack event handlers.
    
    This function is called at startup to ensure handlers are registered.
    """
    logger.info("Slack event handlers registered.")
