"""
Bedrock LLM Generator (Alation-Based)

Handles text generation using AWS Bedrock with Claude.
Supports tool use for fetching Alation enterprise metadata.

OPTIMIZED: Supports parallel tool execution for multiple tool calls.
"""

import json
import asyncio
import logging
from typing import List, Optional, Tuple

from app.core.config import bedrock_runtime
from app.services.rag.prompts import ALATION_RAG_PROMPT

logger = logging.getLogger(__name__)


# Shared event loop for async operations
_event_loop = None

def get_event_loop():
    """Get or create a shared event loop for async operations."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop


class BedrockGenerator:
    """Generate responses using AWS Bedrock Claude model.

    Uses MCP tools to fetch Alation enterprise metadata and answer questions
    about data assets, governance, lineage, and classifications.
    """
    
    def __init__(self, model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"):
        """Initialize the generator.
        
        Args:
            model_id: The Bedrock model ID to use
        """
        self.model_id = model_id
        self.client = bedrock_runtime

    def generate(
        self, 
        question: str, 
        history: str = "", 
        tools: Optional[List] = None, 
        tool_executor = None
    ) -> str:
        """Generate a response to a question.
        
        Args:
            question: The user's question
            history: Optional chat history
            tools: Optional list of MCP tools available
            tool_executor: Optional executor for calling tools
            
        Returns:
            The generated text response
        """
        # Build the prompt
        prompt = ALATION_RAG_PROMPT.format(history=history, question=question)
        messages = [{"role": "user", "content": prompt}]
        
        # Convert MCP tools to Claude tool format
        system_tools = self._format_tools(tools) if tools else []

        # Tool use loop - continues until model returns text (not tool call)
        while True:
            response_body = self._invoke_model(messages, system_tools)
            content = response_body["content"]
            
            # Add assistant response to message history
            messages.append({"role": "assistant", "content": content})

            # Check if model wants to use tools (may be multiple for parallel execution)
            tool_use_blocks = [c for c in content if c["type"] == "tool_use"]
            
            if tool_use_blocks and tool_executor:
                # Execute tools (in parallel if multiple) and add results to messages
                self._handle_tool_use_parallel(tool_use_blocks, tool_executor, messages)
            else:
                # No tool use - return the text response
                text_block = next(
                    (c for c in content if c["type"] == "text"), 
                    None
                )
                return text_block["text"] if text_block else ""
    
    def _format_tools(self, tools: List) -> List[dict]:
        """Convert MCP tools to Claude API format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            }
            for tool in tools
        ]
    
    def _invoke_model(self, messages: List[dict], tools: List[dict]) -> dict:
        """Invoke the Bedrock model."""
        body = {
            "messages": messages,
            "max_tokens": 2500,  # Increased for large metadata responses
            "anthropic_version": "bedrock-2023-05-31"
        }
        if tools:
            body["tools"] = tools

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body).encode("utf-8")
        )
        return json.loads(response.get("body").read())
    
    def _handle_tool_use_parallel(
        self, 
        tool_use_blocks: List[dict], 
        tool_executor, 
        messages: List[dict]
    ) -> None:
        """Execute multiple tools in parallel and add results to messages.
        
        OPTIMIZED: Uses asyncio.gather for parallel tool execution when
        Claude requests multiple tools at once.
        """
        loop = get_event_loop()
        
        async def execute_single_tool(block: dict) -> Tuple[str, str, str]:
            """Execute a single tool and return (id, name, result)."""
            tool_name = block["name"]
            tool_input = block["input"]
            tool_use_id = block["id"]
            
            try:
                logger.info(f"Executing tool: {tool_name}")
                result = await tool_executor.call_tool(tool_name, tool_input)
                logger.info(f"Tool Result ({tool_name}): {str(result)[:200]}...")
                return (tool_use_id, tool_name, str(result))
            except Exception as e:
                logger.error(f"Tool {tool_name} execution failed: {e}")
                return (tool_use_id, tool_name, f"Error executing tool: {str(e)}")
        
        async def execute_all_tools():
            """Execute all tools in parallel using asyncio.gather."""
            tasks = [execute_single_tool(block) for block in tool_use_blocks]
            return await asyncio.gather(*tasks)
        
        # Execute all tools in parallel
        if len(tool_use_blocks) > 1:
            logger.info(f"Executing {len(tool_use_blocks)} tools in parallel")
        
        results = loop.run_until_complete(execute_all_tools())
        
        # Build tool result content (all results in one message)
        tool_results_content = []
        for tool_use_id, tool_name, tool_result in results:
            tool_results_content.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": tool_result
            })
        
        # Add instruction text at the end
        tool_results_content.append({
            "type": "text",
            "text": (
                "The above are the results of the tool executions. "
                "Please present this FULL information to the user "
                "in a readable format (e.g. table or code block). "
                "Do not summarize."
            )
        })
        
        # Add all tool results to messages
        messages.append({
            "role": "user",
            "content": tool_results_content
        })
