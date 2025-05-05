#
# supsrc/engines/git/runner.py
#
"""
Runs potentially blocking pygit2 functions in a separate thread using asyncio.to_thread.
"""

import asyncio
import functools
from typing import Callable, Any, Coroutine, TypeVar
import structlog
import pygit2 # For exception type checking

# Import specific Git exceptions
from .exceptions import GitCommandError

log = structlog.get_logger("engines.git.runner")

T = TypeVar("T") # Generic type variable for return value

async def run_pygit2_func(func: Callable[..., T], *args: Any, **kwargs: Any) -> Coroutine[Any, Any, T]:
    """
    Runs a pygit2 function in a thread pool to avoid blocking the asyncio loop.

    Handles potential GitErrors and wraps them.

    Args:
        func: The pygit2 function or method to call.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The result of the pygit2 function call.

    Raises:
        GitCommandError: If the pygit2 function raises a GitError.
        Exception: For other unexpected errors during execution.
    """
    func_name = getattr(func, "__name__", str(func))
    log.debug(
        "Running pygit2 function via thread",
        func_name=func_name,
        args_len=len(args),
        kwargs_keys=list(kwargs.keys()),
    )
    try:
        # functools.partial ensures args/kwargs are correctly passed to func
        # when called by asyncio.to_thread's internal executor.
        bound_func = functools.partial(func, *args, **kwargs)
        result = await asyncio.to_thread(bound_func)
        log.debug("pygit2 function completed successfully", func_name=func_name)
        return result
    except pygit2.GitError as e:
        log.error("pygit2 function failed", func_name=func_name, error=str(e), exc_info=False) # Keep log cleaner
        # Wrap the GitError in our custom exception
        raise GitCommandError(f"Git operation '{func_name}' failed", details=e) from e
    except Exception as e:
        # Catch other potential exceptions during thread execution
        log.exception("Unexpected error running pygit2 function in thread", func_name=func_name)
        raise # Re-raise other exceptions

# 🔼⚙️
