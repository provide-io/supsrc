#
# engines/git/runner.py
#
"""
Async helper for executing blocking pygit2 operations in a thread pool.
"""

import asyncio
from typing import Callable, TypeVar, Any
import functools

import structlog

from .errors import GitEngineError # Import base error for wrapping

log = structlog.get_logger("engines.git.runner")

T = TypeVar("T")

async def run_pygit2_async(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Runs a potentially blocking pygit2 function asynchronously using asyncio.to_thread.

    Args:
        func: The pygit2 function or method to call.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The result of the pygit2 function call.

    Raises:
        GitEngineError: Wraps exceptions raised by the pygit2 function.
    """
    func_name = getattr(func, '__name__', repr(func))
    log.debug("Running pygit2 function via thread", func_name=func_name, args_len=len(args), kwargs_keys=list(kwargs.keys()))

    # functools.partial is used to pass args/kwargs to the function executed by to_thread
    # See: https://docs.python.org/3/library/asyncio-eventloop.html#executing-code-in-thread-or-process-pools
    try:
        # Wrap the potentially blocking call in asyncio.to_thread
        # This requires Python 3.9+
        # For 3.8 or lower, loop.run_in_executor(None, partial(func, *args, **kwargs)) would be needed.
        # Assuming Python 3.11+ based on project setup.
        partial_func = functools.partial(func, *args, **kwargs)
        result = await asyncio.to_thread(partial_func)
        log.debug("pygit2 function completed successfully", func_name=func_name)
        return result
    except Exception as e:
        # Catch specific pygit2 errors if needed, otherwise wrap general exceptions
        log.error("Error executing pygit2 function in thread", func_name=func_name, error=str(e), exc_info=True)
        # Wrap the exception in our custom GitEngineError
        raise GitEngineError(f"Error in '{func_name}': {e}", details=e) from e

# 🔼⚙️
