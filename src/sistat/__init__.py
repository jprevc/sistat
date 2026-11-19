"""Python client for SiStat, the database of the Statistical Office of Slovenia (SURS)."""

from .client import Client, table_id
from .errors import APIError, QueryError, SiStatError
from .pxweb import TableInfo, TableMetadata, Variable

__all__ = ["APIError", "Client", "QueryError", "SiStatError", "TableInfo", "TableMetadata", "Variable", "table_id"]
__version__ = "0.1.0"
