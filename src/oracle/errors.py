class OracleError(Exception):
    """Base exception for oracle integrations."""


class OracleConfigurationError(OracleError):
    """Raised when oracle configuration is invalid."""


class OracleDependencyError(OracleError):
    """Raised when an optional dependency for an oracle provider is missing."""


class OracleReadError(OracleError):
    """Raised when reading from an oracle provider fails."""
