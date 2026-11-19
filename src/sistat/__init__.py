"""Python client for SiStat, the database of the Statistical Office of Slovenia (SURS)."""

from pxweb import APIError, PxWebError, QueryError, TableInfo, TableMetadata, Variable

from .client import Client, table_id

__all__ = ["APIError", "Client", "PxWebError", "QueryError", "TableInfo", "TableMetadata", "Variable", "table_id"]
__version__ = "0.2.0"
