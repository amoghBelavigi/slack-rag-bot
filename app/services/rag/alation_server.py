"""
Alation MCP Server

Model Context Protocol (MCP) server that exposes Alation metadata to LLMs.
Provides clean, stable tools for querying enterprise metadata without
exposing Alation API complexity.

Core Principles:
- Alation is the single source of truth
- Read-only operations
- No hallucination - explicit "unknown" for missing data
- Graceful error handling
- No data persistence (in-memory cache only)

Tools Provided:
1. list_data_sources - List all available data sources
2. list_schemas - List schemas in a data source
3. list_tables - List tables in a schema
4. get_table_metadata - Get detailed table metadata
5. get_column_metadata - Get column definitions and classifications
6. get_lineage - Get upstream/downstream lineage
"""

import os
import json
import logging
from typing import Dict, Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from app.services.rag.alation_adapter import AlationAPIAdapter

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP service
mcp = FastMCP("Alation Metadata")

# Initialize Alation API adapter
alation = AlationAPIAdapter(
    base_url=os.getenv("ALATION_BASE_URL"),
    api_token=os.getenv("ALATION_API_TOKEN"),
    user_id=os.getenv("ALATION_USER_ID"),
    cache_enabled=True
)


def format_response(data: Any, error_msg: str = None) -> str:
    """
    Format response for LLM consumption.

    Args:
        data: Response data (list, dict, or primitive)
        error_msg: Optional error message

    Returns:
        JSON formatted string or error message
    """
    if error_msg:
        return f"Error: {error_msg}"

    if data is None:
        return "No data available"

    # Format as clean JSON
    try:
        return json.dumps(data, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to format response: {e}")
        return str(data)


# =============================================================================
# Tool 1: list_data_sources
# =============================================================================

@mcp.tool()
def list_data_sources() -> str:
    """
    List all available data sources in Alation.

    Returns structured information about each data source including:
    - data_source_id: Unique identifier
    - name: Display name
    - type: Database type (snowflake, redshift, postgresql, etc.)
    - description: Human-readable description

    Returns:
        JSON formatted list of data sources
    """
    try:
        logger.info("Tool invoked: list_data_sources")
        data_sources = alation.list_data_sources()

        if not data_sources:
            return format_response(None, "No data sources found or access denied")

        return format_response(data_sources)

    except Exception as e:
        logger.error(f"list_data_sources failed: {e}")
        return format_response(None, f"Failed to retrieve data sources: {str(e)}")


# =============================================================================
# Tool 2: list_schemas
# =============================================================================

@mcp.tool()
def list_schemas(data_source_id: int) -> str:
    """
    List all schemas in a specific data source.

    Args:
        data_source_id: The Alation data source ID (from list_data_sources)

    Returns:
        JSON formatted list of schemas with:
        - schema_name: Name of the schema
        - schema_description: Description if available, "unknown" otherwise

    Example:
        list_schemas(data_source_id=123)
    """
    try:
        logger.info(f"Tool invoked: list_schemas(data_source_id={data_source_id})")

        if not isinstance(data_source_id, int):
            return format_response(None, "data_source_id must be an integer")

        schemas = alation.list_schemas(data_source_id)

        if not schemas:
            return format_response(
                None,
                f"No schemas found for data source {data_source_id} or access denied"
            )

        return format_response(schemas)

    except Exception as e:
        logger.error(f"list_schemas failed: {e}")
        return format_response(None, f"Failed to retrieve schemas: {str(e)}")


# =============================================================================
# Tool 3: list_tables
# =============================================================================

@mcp.tool()
def list_tables(data_source_id: int, schema_name: str) -> str:
    """
    List all tables in a specific schema.

    Args:
        data_source_id: The Alation data source ID
        schema_name: Name of the schema

    Returns:
        JSON formatted list of tables with:
        - table_name: Name of the table
        - table_type: Type (TABLE, VIEW, etc.)
        - row_count: Number of rows if available, "unknown" otherwise
        - popularity: Usage signals if available, "unknown" otherwise

    Example:
        list_tables(data_source_id=123, schema_name="public")
    """
    try:
        logger.info(
            f"Tool invoked: list_tables(data_source_id={data_source_id}, "
            f"schema_name={schema_name})"
        )

        if not isinstance(data_source_id, int):
            return format_response(None, "data_source_id must be an integer")

        if not schema_name:
            return format_response(None, "schema_name is required")

        tables = alation.list_tables(data_source_id, schema_name)

        if not tables:
            return format_response(
                None,
                f"No tables found in {schema_name} or access denied"
            )

        return format_response(tables)

    except Exception as e:
        logger.error(f"list_tables failed: {e}")
        return format_response(None, f"Failed to retrieve tables: {str(e)}")


# =============================================================================
# Tool 4: get_table_metadata
# =============================================================================

@mcp.tool()
def get_table_metadata(
    data_source_id: int,
    schema_name: str,
    table_name: str
) -> str:
    """
    Get detailed metadata for a specific table.

    Provides comprehensive table information including ownership,
    governance status, and usage context.

    Args:
        data_source_id: The Alation data source ID
        schema_name: Name of the schema
        table_name: Name of the table

    Returns:
        JSON formatted metadata including:
        - table_name: Name of the table
        - table_description: Business description or "unknown"
        - owner: Table owner or "unknown"
        - steward: Data steward or "unknown"
        - certification: Trust certification status or "unknown"
        - trust_status: Endorsement status or "unknown"
        - last_updated: Last modification timestamp or "unknown"
        - sample_queries: Example queries or "unknown"

    Example:
        get_table_metadata(
            data_source_id=123,
            schema_name="public",
            table_name="customers"
        )
    """
    try:
        logger.info(
            f"Tool invoked: get_table_metadata(data_source_id={data_source_id}, "
            f"schema_name={schema_name}, table_name={table_name})"
        )

        if not isinstance(data_source_id, int):
            return format_response(None, "data_source_id must be an integer")

        if not schema_name or not table_name:
            return format_response(None, "schema_name and table_name are required")

        metadata = alation.get_table_metadata(data_source_id, schema_name, table_name)

        if not metadata:
            return format_response(
                None,
                f"Table {schema_name}.{table_name} not found or access denied"
            )

        return format_response(metadata)

    except Exception as e:
        logger.error(f"get_table_metadata failed: {e}")
        return format_response(None, f"Failed to retrieve table metadata: {str(e)}")


# =============================================================================
# Tool 5: get_column_metadata
# =============================================================================

@mcp.tool()
def get_column_metadata(
    data_source_id: int,
    schema_name: str,
    table_name: str
) -> str:
    """
    Get column definitions and metadata for a table.

    Provides detailed column information including data types,
    descriptions, and data classifications.

    Args:
        data_source_id: The Alation data source ID
        schema_name: Name of the schema
        table_name: Name of the table

    Returns:
        JSON formatted list of columns with:
        - column_name: Name of the column
        - data_type: SQL data type
        - description: Column description or "unknown"
        - nullable: Whether column accepts NULL values or "unknown"
        - classification: Data classification tags (PII, PHI, etc.) or "unknown"

    Example:
        get_column_metadata(
            data_source_id=123,
            schema_name="public",
            table_name="customers"
        )
    """
    try:
        logger.info(
            f"Tool invoked: get_column_metadata(data_source_id={data_source_id}, "
            f"schema_name={schema_name}, table_name={table_name})"
        )

        if not isinstance(data_source_id, int):
            return format_response(None, "data_source_id must be an integer")

        if not schema_name or not table_name:
            return format_response(None, "schema_name and table_name are required")

        columns = alation.get_column_metadata(data_source_id, schema_name, table_name)

        if not columns:
            return format_response(
                None,
                f"No columns found for {schema_name}.{table_name} or access denied"
            )

        return format_response(columns)

    except Exception as e:
        logger.error(f"get_column_metadata failed: {e}")
        return format_response(None, f"Failed to retrieve column metadata: {str(e)}")


# =============================================================================
# Tool 6: get_lineage
# =============================================================================

@mcp.tool()
def get_lineage(
    data_source_id: int,
    schema_name: str,
    table_name: str
) -> str:
    """
    Get data lineage for a table.

    Provides upstream and downstream dependencies to understand
    data flow and transformation context.

    Args:
        data_source_id: The Alation data source ID
        schema_name: Name of the schema
        table_name: Name of the table

    Returns:
        JSON formatted lineage information with:
        - upstream_tables: List of source tables or "unknown"
        - downstream_tables: List of dependent tables or "unknown"
        - transformation_context: SQL or transformation logic if available, "unknown" otherwise

    Note:
        Lineage data may not be available for all tables. Missing lineage
        is explicitly marked as "unknown" rather than inferred.

    Example:
        get_lineage(
            data_source_id=123,
            schema_name="public",
            table_name="customer_summary"
        )
    """
    try:
        logger.info(
            f"Tool invoked: get_lineage(data_source_id={data_source_id}, "
            f"schema_name={schema_name}, table_name={table_name})"
        )

        if not isinstance(data_source_id, int):
            return format_response(None, "data_source_id must be an integer")

        if not schema_name or not table_name:
            return format_response(None, "schema_name and table_name are required")

        lineage = alation.get_lineage(data_source_id, schema_name, table_name)

        if not lineage:
            return format_response(
                None,
                f"Lineage not available for {schema_name}.{table_name}"
            )

        return format_response(lineage)

    except Exception as e:
        logger.error(f"get_lineage failed: {e}")
        return format_response(None, f"Failed to retrieve lineage: {str(e)}")


# =============================================================================
# Server Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Alation MCP Server on port 8000")
    logger.info(f"Connected to Alation instance: {os.getenv('ALATION_BASE_URL')}")

    # Run the SSE server on port 8000
    # This is started automatically by socket_mode.py
    uvicorn.run(mcp.sse_app, host="0.0.0.0", port=8000)
