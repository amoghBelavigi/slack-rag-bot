"""
Alation MCP Client

Client for communicating with the Alation MCP server via Server-Sent Events (SSE).
Provides convenient access to Alation metadata tools for the RAG application.

This client abstracts the MCP communication layer and provides clean,
typed methods for accessing Alation metadata.

OPTIMIZED: Uses persistent session with connection reuse to reduce latency.
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)


class AlationMCPClient:
    """
    Client for the Alation MCP server.

    Connects to the MCP server running on localhost:8000 via SSE
    to access Alation metadata tools.

    OPTIMIZED: Maintains a persistent session to avoid connection overhead
    on each tool call.

    Usage:
        client = AlationMCPClient()
        data_sources = await client.list_data_sources()
        schemas = await client.list_schemas(data_source_id=123)
    """

    # Server endpoint (started by socket_mode.py)
    SERVER_URL = "http://localhost:8000/sse"
    
    # Session timeout - reconnect after this many seconds of inactivity
    SESSION_TIMEOUT = 300  # 5 minutes

    def __init__(self, server_url: Optional[str] = None):
        """
        Initialize the Alation MCP client.

        Args:
            server_url: Optional custom server URL (defaults to localhost:8000)
        """
        self.server_url = server_url or self.SERVER_URL
        self.tools_cache = None
        self._session = None
        self._session_context = None
        self._sse_context = None
        self._last_used = 0
        self._lock = asyncio.Lock()
        logger.info(f"Initialized AlationMCPClient with server: {self.server_url}")

    async def _ensure_session(self) -> ClientSession:
        """
        Ensure we have a valid persistent session.
        
        Creates a new session if none exists or if the current session
        has timed out. Uses a lock to prevent race conditions.
        
        Returns:
            Active ClientSession
        """
        async with self._lock:
            current_time = time.time()
            
            # Check if session needs refresh (timeout or doesn't exist)
            if (self._session is None or 
                current_time - self._last_used > self.SESSION_TIMEOUT):
                
                # Close existing session if any
                await self._close_session()
                
                # Create new session
                logger.info("Creating new persistent MCP session")
                try:
                    self._sse_context = sse_client(self.server_url)
                    read, write = await self._sse_context.__aenter__()
                    self._session_context = ClientSession(read, write)
                    self._session = await self._session_context.__aenter__()
                    await self._session.initialize()
                    logger.info("Persistent MCP session established")
                except Exception as e:
                    logger.error(f"Failed to create persistent session: {e}")
                    await self._close_session()
                    raise
            
            self._last_used = current_time
            return self._session
    
    async def _close_session(self):
        """Close the persistent session and cleanup resources."""
        if self._session_context:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error closing session context: {e}")
            self._session_context = None
            self._session = None
        
        if self._sse_context:
            try:
                await self._sse_context.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error closing SSE context: {e}")
            self._sse_context = None
    
    async def close(self):
        """Public method to close the client and cleanup resources."""
        await self._close_session()
        logger.info("AlationMCPClient closed")

    async def get_tools(self) -> List[Any]:
        """
        Fetch available tools from the MCP server.

        Tools are cached after first fetch for performance.
        Uses persistent session to avoid connection overhead.

        Returns:
            List of available tool definitions
        """
        if self.tools_cache:
            return self.tools_cache

        try:
            session = await self._ensure_session()
            result = await session.list_tools()
            self.tools_cache = result.tools
            logger.info(f"Loaded {len(result.tools)} tools from Alation MCP server")
            return result.tools

        except Exception as e:
            logger.error(f"Failed to connect to Alation MCP server: {e}")
            # Reset session on error to force reconnect on next call
            await self._close_session()
            return []

    async def call_tool(self, tool_name: str, tool_args: Optional[Dict] = None) -> str:
        """
        Public method to execute a tool on the MCP server.
        Uses persistent session for improved performance.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments to pass to the tool

        Returns:
            The tool's text output

        Raises:
            Exception: If tool execution fails
        """
        return await self._call_tool(tool_name, tool_args)

    async def _call_tool(self, tool_name: str, tool_args: Optional[Dict] = None) -> str:
        """
        Execute a tool on the MCP server using persistent session.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments to pass to the tool

        Returns:
            The tool's text output

        Raises:
            Exception: If tool execution fails
        """
        tool_args = tool_args or {}

        try:
            session = await self._ensure_session()
            result = await session.call_tool(tool_name, tool_args)
            return result.content[0].text

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            # Reset session on error to force reconnect on next call
            await self._close_session()
            raise

    # =========================================================================
    # Convenience Methods for Each Tool
    # =========================================================================

    async def list_data_sources(self) -> str:
        """
        List all available data sources in Alation.

        Returns:
            JSON formatted string with data source information
        """
        logger.info("Calling list_data_sources")
        return await self._call_tool("list_data_sources")

    async def list_schemas(self, data_source_id: int) -> str:
        """
        List all schemas in a specific data source.

        Args:
            data_source_id: The Alation data source ID

        Returns:
            JSON formatted string with schema information
        """
        logger.info(f"Calling list_schemas(data_source_id={data_source_id})")
        return await self._call_tool(
            "list_schemas",
            {"data_source_id": data_source_id}
        )

    async def list_tables(self, data_source_id: int, schema_name: str) -> str:
        """
        List all tables in a specific schema.

        Args:
            data_source_id: The Alation data source ID
            schema_name: Name of the schema

        Returns:
            JSON formatted string with table information
        """
        logger.info(
            f"Calling list_tables(data_source_id={data_source_id}, "
            f"schema_name={schema_name})"
        )
        return await self._call_tool(
            "list_tables",
            {
                "data_source_id": data_source_id,
                "schema_name": schema_name
            }
        )

    async def get_table_metadata(
        self,
        data_source_id: int,
        schema_name: str,
        table_name: str
    ) -> str:
        """
        Get detailed metadata for a specific table.

        Args:
            data_source_id: The Alation data source ID
            schema_name: Name of the schema
            table_name: Name of the table

        Returns:
            JSON formatted string with table metadata
        """
        logger.info(
            f"Calling get_table_metadata(data_source_id={data_source_id}, "
            f"schema_name={schema_name}, table_name={table_name})"
        )
        return await self._call_tool(
            "get_table_metadata",
            {
                "data_source_id": data_source_id,
                "schema_name": schema_name,
                "table_name": table_name
            }
        )

    async def get_column_metadata(
        self,
        data_source_id: int,
        schema_name: str,
        table_name: str
    ) -> str:
        """
        Get column definitions and metadata for a table.

        Args:
            data_source_id: The Alation data source ID
            schema_name: Name of the schema
            table_name: Name of the table

        Returns:
            JSON formatted string with column metadata
        """
        logger.info(
            f"Calling get_column_metadata(data_source_id={data_source_id}, "
            f"schema_name={schema_name}, table_name={table_name})"
        )
        return await self._call_tool(
            "get_column_metadata",
            {
                "data_source_id": data_source_id,
                "schema_name": schema_name,
                "table_name": table_name
            }
        )

    async def get_lineage(
        self,
        data_source_id: int,
        schema_name: str,
        table_name: str
    ) -> str:
        """
        Get data lineage for a table.

        Args:
            data_source_id: The Alation data source ID
            schema_name: Name of the schema
            table_name: Name of the table

        Returns:
            JSON formatted string with lineage information
        """
        logger.info(
            f"Calling get_lineage(data_source_id={data_source_id}, "
            f"schema_name={schema_name}, table_name={table_name})"
        )
        return await self._call_tool(
            "get_lineage",
            {
                "data_source_id": data_source_id,
                "schema_name": schema_name,
                "table_name": table_name
            }
        )


# =============================================================================
# Usage Example
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def demo():
        """Demonstrate Alation MCP client usage."""
        client = AlationMCPClient()

        # List all data sources
        print("=== Data Sources ===")
        data_sources = await client.list_data_sources()
        print(data_sources)

        # List schemas (example with data_source_id=1)
        print("\n=== Schemas ===")
        schemas = await client.list_schemas(data_source_id=1)
        print(schemas)

        # List tables (example)
        print("\n=== Tables ===")
        tables = await client.list_tables(data_source_id=1, schema_name="public")
        print(tables)

        # Get table metadata (example)
        print("\n=== Table Metadata ===")
        metadata = await client.get_table_metadata(
            data_source_id=1,
            schema_name="public",
            table_name="customers"
        )
        print(metadata)

        # Get column metadata (example)
        print("\n=== Column Metadata ===")
        columns = await client.get_column_metadata(
            data_source_id=1,
            schema_name="public",
            table_name="customers"
        )
        print(columns)

        # Get lineage (example)
        print("\n=== Lineage ===")
        lineage = await client.get_lineage(
            data_source_id=1,
            schema_name="public",
            table_name="customers"
        )
        print(lineage)

    # Run demo
    asyncio.run(demo())
