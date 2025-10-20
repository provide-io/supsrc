# supsrc/engines/git/base.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Implementation of the RepositoryEngine protocol using pygit2.


# Add Foundation resilience patterns for Git operations


# Use absolute imports
    CommitResult,
    PushResult,
    RepositoryEngine,
    RepoStatusResult,
    StageResult,
)

log = get_logger(__name__)


"""


class GitEngine(RepositoryEngine):
    """Implements RepositoryEngine using pygit2."""
