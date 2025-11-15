#
# supsrc/timemachine/exceptions.py
#
"""
Custom exceptions for the Time Machine module.
"""


class TimeMachineError(Exception):
    """Base exception for all time machine errors."""

    pass


class CommitCreationError(TimeMachineError):
    """Failed to create a micro-commit."""

    pass


class SnapshotError(TimeMachineError):
    """Failed to create or manage a snapshot."""

    pass


class RestoreError(TimeMachineError):
    """Failed to restore a file from history."""

    pass


class IndexError(TimeMachineError):
    """Failed to build or query the timeline index."""

    pass


class ConfigurationError(TimeMachineError):
    """Invalid time machine configuration."""

    pass


class RefNameError(TimeMachineError):
    """Invalid Git ref name generated."""

    pass


class StorageError(TimeMachineError):
    """Storage-related error (disk full, quota exceeded, etc.)."""

    pass

# 🕰️ Time Machine
