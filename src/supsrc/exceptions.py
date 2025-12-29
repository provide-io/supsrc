#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Supsrc exceptions using Foundation's error system."""

from provide.foundation.errors import FoundationError
from provide.foundation.errors.config import ConfigurationError as BaseConfigurationError


class SupsrcError(FoundationError):
    """Base class for all supsrc application specific errors."""



# Configuration exceptions - these now inherit from Foundation's config errors
class ConfigurationError(BaseConfigurationError, SupsrcError):
    """Configuration-related errors using Foundation's error system."""



class ConfigFileNotFoundError(ConfigurationError, FileNotFoundError):
    """Configuration file not found."""



class ConfigParsingError(ConfigurationError):
    """Configuration file parsing errors."""



class ConfigValidationError(ConfigurationError):
    """Configuration validation errors."""



class PathValidationError(ConfigValidationError):
    """Path validation errors."""



class DurationValidationError(ConfigValidationError):
    """Duration validation errors."""



# Monitoring exceptions
class MonitoringError(SupsrcError):
    """Base class for monitoring-related errors."""



class MonitoringSetupError(MonitoringError):
    """Monitoring setup errors."""



# Export all exceptions for backward compatibility
__all__ = [
    "ConfigFileNotFoundError",
    "ConfigParsingError",
    "ConfigValidationError",
    "ConfigurationError",
    "DurationValidationError",
    "MonitoringError",
    "MonitoringSetupError",
    "PathValidationError",
    "SupsrcError",
]

# 🔼⚙️🔚
