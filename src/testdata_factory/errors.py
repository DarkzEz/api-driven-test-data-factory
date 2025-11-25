"""Domain-specific errors exposed to the CLI"""


class FactoryError(Exception):
    """Base class for expected operational fails"""


class ConfigurationError(FactoryError):
    """Raised when config is missing or invalid"""


class PublishError(FactoryError):
    """Raised when a generated batch can't be published safely"""
