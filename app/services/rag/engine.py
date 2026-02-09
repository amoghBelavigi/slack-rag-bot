"""
RAG Engine (Alation-Based)

Orchestrates the RAG pipeline using Alation MCP tools.
No vector store - all metadata comes from live Alation queries.

OPTIMIZED: Uses shared event loop to avoid repeated loop creation.
"""

import logging
from typing import List

from app.services.rag.generator import BedrockGenerator, get_event_loop
from app.services.rag.alation_client import AlationMCPClient
from app.models.schemas import RAGResponse

logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG engine using Alation MCP tools.

    This engine relies entirely on MCP tools for metadata access.
    The LLM uses tools to query Alation for enterprise metadata,
    including table descriptions, ownership, lineage, and governance.
    """

    def __init__(self):
        """Initialize the RAG engine."""
        self.generator = BedrockGenerator()
        self.mcp_client = AlationMCPClient()

    def answer(self, question: str, history: str = "") -> RAGResponse:
        """Generate an answer to a user's question.
        
        Args:
            question: The user's question
            history: Optional chat history for context
            
        Returns:
            RAGResponse containing the answer
        """
        logger.info(f"Answering question: {question}")
        
        # Get available tools from MCP server
        tools = self._get_tools()

        # Generate answer using Claude with Alation metadata tools
        answer_text = self.generator.generate(
            question=question,
            history=history,
            tools=tools,
            tool_executor=self.mcp_client
        )
        
        return RAGResponse(
            answer=answer_text,
            sources=[],  # No vector store sources
            question=question
        )
    
    def _get_tools(self) -> List:
        """Fetch available tools from the MCP server.
        
        Uses shared event loop to avoid repeated loop creation overhead.
        
        Returns:
            List of available tools, or empty list if fetch fails
        """
        try:
            loop = get_event_loop()
            return loop.run_until_complete(self.mcp_client.get_tools())
        except Exception as e:
            logger.error(f"Failed to get tools: {e}")
            return []


# Global singleton instance
rag_engine = RAGEngine()
