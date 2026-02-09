"""
Alation API Adapter

Thin abstraction layer for Alation REST APIs.
Handles authentication, error handling, and response mapping.
Provides clean interface for MCP server without exposing API complexity.

Key principles:
- Read-only operations
- Explicit handling of missing data (no hallucination)
- Graceful degradation on API failures
- Simple in-memory caching for performance
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with TTL."""
    data: Any
    expires_at: datetime


class AlationAPIAdapter:
    """
    Adapter for Alation REST API.

    Provides clean, typed methods for accessing Alation metadata.
    All responses are read-only. Missing data is explicitly marked as "unknown".
    """

    # Cache TTL in seconds
    CACHE_TTL = 300  # 5 minutes

    def __init__(
        self,
        base_url: str,
        api_token: str,
        user_id: Optional[str] = None,
        cache_enabled: bool = True
    ):
        """
        Initialize Alation API adapter.

        Args:
            base_url: Alation instance URL (e.g., https://company.alation.com)
            api_token: Alation API access token
            user_id: Optional user ID for user-context operations
            cache_enabled: Enable in-memory caching
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.user_id = user_id
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, CacheEntry] = {}
        
        # OPTIMIZED: Dedicated cache for table ID lookups (used by column & lineage queries)
        self._table_id_cache: Dict[str, int] = {}

        # Configure session with retry logic
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic and auth headers."""
        session = requests.Session()

        # Retry strategy for transient failures
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]  # Only retry GET requests
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set auth headers
        session.headers.update({
            "TOKEN": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

        return session

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Retrieve item from cache if valid."""
        if not self.cache_enabled:
            return None

        entry = self._cache.get(key)
        if entry and datetime.now() < entry.expires_at:
            logger.debug(f"Cache hit for key: {key}")
            return entry.data

        # Remove expired entry
        if entry:
            del self._cache[key]

        return None

    def _set_in_cache(self, key: str, data: Any) -> None:
        """Store item in cache with TTL."""
        if not self.cache_enabled:
            return

        expires_at = datetime.now() + timedelta(seconds=self.CACHE_TTL)
        self._cache[key] = CacheEntry(data=data, expires_at=expires_at)
        logger.debug(f"Cache set for key: {key}")

    def _api_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        cache_key: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Make API request to Alation.

        Args:
            endpoint: API endpoint path (e.g., '/integration/v1/datasource/')
            params: Query parameters
            cache_key: Optional cache key for result

        Returns:
            API response data or None on failure
        """
        # Check cache first
        if cache_key:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        url = f"{self.base_url}{endpoint}"

        try:
            logger.info(f"Alation API request: {endpoint}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Cache successful response
            if cache_key:
                self._set_in_cache(cache_key, data)

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Resource not found: {endpoint}")
                return None
            elif e.response.status_code == 403:
                logger.error(f"Access denied to {endpoint} - check user permissions")
                return None
            else:
                logger.error(f"HTTP error {e.response.status_code}: {endpoint}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {str(e)}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error for {endpoint}: {str(e)}")
            return None

    # =========================================================================
    # Data Source Operations
    # =========================================================================

    def list_data_sources(self) -> List[Dict[str, Any]]:
        """
        List all accessible data sources.

        Returns:
            List of data sources with id, name, type, description
        """
        data = self._api_request(
            '/integration/v1/datasource/',
            cache_key='data_sources'
        )

        if not data:
            logger.warning("Failed to retrieve data sources from Alation")
            return []

        # Map to clean response format
        data_sources = []
        for ds in data:
            data_sources.append({
                'data_source_id': ds.get('id'),
                'name': ds.get('title', 'unknown'),
                'type': ds.get('dbtype', 'unknown'),
                'description': ds.get('description', 'unknown')
            })

        return data_sources

    def get_data_source(self, data_source_id: int) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific data source.

        Args:
            data_source_id: Alation data source ID

        Returns:
            Data source details or None
        """
        data = self._api_request(
            f'/integration/v1/datasource/{data_source_id}/',
            cache_key=f'ds_{data_source_id}'
        )

        if not data:
            return None

        return {
            'data_source_id': data.get('id'),
            'name': data.get('title', 'unknown'),
            'type': data.get('dbtype', 'unknown'),
            'description': data.get('description', 'unknown'),
            'uri': data.get('uri', 'unknown')
        }

    # =========================================================================
    # Schema Operations
    # =========================================================================

    def list_schemas(self, data_source_id: int) -> List[Dict[str, Any]]:
        """
        List schemas in a data source.

        Args:
            data_source_id: Alation data source ID

        Returns:
            List of schemas with name and description
        """
        # Alation API endpoint for schemas
        data = self._api_request(
            '/integration/v2/schema/',
            params={'ds_id': data_source_id},
            cache_key=f'schemas_{data_source_id}'
        )

        if not data:
            logger.warning(f"No schemas found for data source {data_source_id}")
            return []

        schemas = []
        for schema in data:
            schemas.append({
                'schema_name': schema.get('name', 'unknown'),
                'schema_description': schema.get('description', 'unknown')
            })

        return schemas

    # =========================================================================
    # Table Operations
    # =========================================================================

    def list_tables(
        self,
        data_source_id: int,
        schema_name: str
    ) -> List[Dict[str, Any]]:
        """
        List tables in a schema.

        Args:
            data_source_id: Alation data source ID
            schema_name: Schema name

        Returns:
            List of tables with metadata
        """
        data = self._api_request(
            '/integration/v2/table/',
            params={
                'ds_id': data_source_id,
                'schema_name': schema_name
            },
            cache_key=f'tables_{data_source_id}_{schema_name}'
        )

        if not data:
            logger.warning(f"No tables found for {data_source_id}.{schema_name}")
            return []

        tables = []
        for table in data:
            tables.append({
                'table_name': table.get('name', 'unknown'),
                'table_type': table.get('table_type', 'unknown'),
                'row_count': table.get('number_of_rows', 'unknown'),
                'popularity': table.get('popularity', 'unknown')
            })

        return tables

    def get_table_metadata(
        self,
        data_source_id: int,
        schema_name: str,
        table_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed metadata for a specific table.

        Args:
            data_source_id: Alation data source ID
            schema_name: Schema name
            table_name: Table name

        Returns:
            Table metadata including description, owner, certification, etc.
        """
        # Get table by qualified name
        data = self._api_request(
            '/integration/v2/table/',
            params={
                'ds_id': data_source_id,
                'schema_name': schema_name,
                'name': table_name
            },
            cache_key=f'table_meta_{data_source_id}_{schema_name}_{table_name}'
        )

        if not data or len(data) == 0:
            logger.warning(f"Table not found: {data_source_id}.{schema_name}.{table_name}")
            return None

        # Alation returns list, take first match
        table = data[0]

        return {
            'table_name': table.get('name', 'unknown'),
            'table_description': table.get('description', 'unknown'),
            'owner': table.get('owner', 'unknown'),
            'steward': table.get('steward', 'unknown'),
            'certification': table.get('trust_flags', {}).get('certification', 'unknown'),
            'trust_status': table.get('trust_flags', {}).get('endorsement', 'unknown'),
            'last_updated': table.get('ts_updated', 'unknown'),
            'sample_queries': table.get('sample_queries', []) or 'unknown'
        }

    # =========================================================================
    # Table ID Lookup (OPTIMIZED with dedicated cache)
    # =========================================================================

    def _get_table_id(
        self,
        data_source_id: int,
        schema_name: str,
        table_name: str
    ) -> Optional[int]:
        """
        Get table ID with dedicated caching.
        
        OPTIMIZED: This method is called by both get_column_metadata and get_lineage.
        The table ID is cached separately to avoid redundant API calls when both
        methods are called for the same table.

        Args:
            data_source_id: Alation data source ID
            schema_name: Schema name
            table_name: Table name

        Returns:
            Table ID or None if not found
        """
        cache_key = f"{data_source_id}_{schema_name}_{table_name}"
        
        # Check dedicated table ID cache first
        if cache_key in self._table_id_cache:
            logger.debug(f"Table ID cache hit: {cache_key}")
            return self._table_id_cache[cache_key]
        
        # Fetch from API
        table_data = self._api_request(
            '/integration/v2/table/',
            params={
                'ds_id': data_source_id,
                'schema_name': schema_name,
                'name': table_name
            }
        )

        if not table_data or len(table_data) == 0:
            logger.warning(f"Table not found: {schema_name}.{table_name}")
            return None

        table_id = table_data[0].get('id')
        if table_id:
            # Cache for future use
            self._table_id_cache[cache_key] = table_id
            logger.info(f"Cached table_id={table_id} for {schema_name}.{table_name}")
        
        return table_id

    # =========================================================================
    # Column Operations
    # =========================================================================

    def get_column_metadata(
        self,
        data_source_id: int,
        schema_name: str,
        table_name: str
    ) -> List[Dict[str, Any]]:
        """
        Get column metadata for a table.

        Tries multiple API endpoints to maximize compatibility:
        1. Integration API v2 with ds_id filter
        2. Catalog API with table_id
        3. Integration API v2 with qualified table name

        Args:
            data_source_id: Alation data source ID
            schema_name: Schema name
            table_name: Table name

        Returns:
            List of column metadata including types, descriptions, classifications
        """
        # Get table ID using cached lookup
        table_id = self._get_table_id(data_source_id, schema_name, table_name)
        
        if not table_id:
            logger.warning(f"Cannot get columns - table not found: {schema_name}.{table_name}")
            return []

        columns = []
        
        # Approach 1: Try Integration API v2 with ds_id and qualified table name
        qualified_table_name = f"{schema_name}.{table_name}"
        logger.info(f"Trying Integration API for columns: {qualified_table_name}")
        
        data = self._api_request(
            '/integration/v2/column/',
            params={
                'ds_id': data_source_id,
                'table_name': qualified_table_name
            }
        )
        
        if data and len(data) > 0:
            logger.info(f"Integration API returned {len(data)} columns")
            for col in data:
                columns.append({
                    'column_name': col.get('name', 'unknown'),
                    'data_type': col.get('column_type', col.get('data_type', 'unknown')),
                    'description': col.get('description', 'unknown'),
                    'nullable': col.get('nullable', 'unknown'),
                    'classification': col.get('flags', []) or 'unknown'
                })
            return columns
        
        # Approach 2: Try Catalog API with table_id
        logger.info(f"Trying Catalog API for columns with table_id={table_id}")
        
        data = self._api_request(
            '/catalog/column/',
            params={
                'table_id': table_id
            },
            cache_key=f'columns_{data_source_id}_{schema_name}_{table_name}'
        )

        if data and len(data) > 0:
            logger.info(f"Catalog API returned {len(data)} columns")
            for col in data:
                columns.append({
                    'column_name': col.get('name', 'unknown'),
                    'data_type': col.get('data_type', col.get('column_type', 'unknown')),
                    'description': col.get('description', 'unknown'),
                    'nullable': col.get('nullable', 'unknown'),
                    'classification': col.get('custom_fields', []) or 'unknown'
                })
            return columns
        
        # Approach 3: Try fetching table object which may include columns
        logger.info(f"Trying to get columns from table object")
        
        table_data = self._api_request(
            f'/catalog/table/{table_id}/'
        )
        
        if table_data and 'columns' in table_data:
            cols = table_data.get('columns', [])
            logger.info(f"Table object contains {len(cols)} columns")
            for col in cols:
                columns.append({
                    'column_name': col.get('name', 'unknown'),
                    'data_type': col.get('data_type', col.get('column_type', 'unknown')),
                    'description': col.get('description', 'unknown'),
                    'nullable': col.get('nullable', 'unknown'),
                    'classification': col.get('custom_fields', []) or 'unknown'
                })
            return columns

        logger.warning(f"No columns found for {schema_name}.{table_name} after trying all API approaches")
        return []

    # =========================================================================
    # Lineage Operations
    # =========================================================================

    def get_lineage(
        self,
        data_source_id: int,
        schema_name: str,
        table_name: str
    ) -> Dict[str, Any]:
        """
        Get lineage for a table.

        Args:
            data_source_id: Alation data source ID
            schema_name: Schema name
            table_name: Table name

        Returns:
            Lineage information with upstream and downstream tables
        """
        # Get table ID using cached lookup (OPTIMIZED)
        table_id = self._get_table_id(data_source_id, schema_name, table_name)

        if not table_id:
            logger.warning(f"Cannot get lineage - table not found: {table_name}")
            return {
                'upstream_tables': 'unknown',
                'downstream_tables': 'unknown',
                'transformation_context': 'unknown'
            }

        # Get lineage using lineage API
        lineage_data = self._api_request(
            f'/integration/v2/lineage/',
            params={'oid': table_id, 'otype': 'table'},
            cache_key=f'lineage_{data_source_id}_{schema_name}_{table_name}'
        )

        if not lineage_data:
            logger.warning(f"Lineage data not available for {table_name}")
            return {
                'upstream_tables': 'unknown',
                'downstream_tables': 'unknown',
                'transformation_context': 'unknown'
            }

        # Parse lineage response
        upstream = lineage_data.get('upstream', [])
        downstream = lineage_data.get('downstream', [])

        return {
            'upstream_tables': [u.get('key', 'unknown') for u in upstream] if upstream else 'unknown',
            'downstream_tables': [d.get('key', 'unknown') for d in downstream] if downstream else 'unknown',
            'transformation_context': lineage_data.get('sql', 'unknown')
        }

    def clear_cache(self) -> None:
        """Clear all cached data including table ID cache."""
        self._cache.clear()
        self._table_id_cache.clear()
        logger.info("All caches cleared")
