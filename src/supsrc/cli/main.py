# supsrc/cli/main.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
"""
Main CLI entry point for supsrc using Click.
Properly dogfoods provide-foundation's CLI framework.




try:
    __version__ = version("supsrc")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

log: StructLogger = get_logger(__name__)


def _initialize_logging(cli_context: CLIContext) -> None:
    """Initialize Foundation logging from CLIContext.

"""
