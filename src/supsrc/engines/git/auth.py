#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Git authentication and credentials handling for the GitEngine."""

from __future__ import annotations

from collections.abc import Callable
import getpass
from typing import TYPE_CHECKING, Any

from provide.foundation.logger import get_logger
import pygit2

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


class GitAuthHandler:
    """Handles Git authentication and credentials for repository operations."""

    def __init__(self) -> None:
        self._log = log.bind(handler_id=id(self))
        self._log.debug("GitAuthHandler initialized")

    def create_credentials_callback(
        self,
    ) -> Callable[[str, str | None, int], Any]:
        """Creates a credentials callback function for pygit2 operations."""

        def credentials_callback(url: str, username_from_url: str | None, allowed_types: int) -> Any:
            """Provides credentials to pygit2, attempting SSH agent first."""
            cred_log = self._log.bind(
                url=url, username_from_url=username_from_url, allowed_types=allowed_types
            )
            cred_log.debug("Credentials callback invoked")

            # 1. Try SSH Agent (KeypairFromAgent) if SSH key is allowed
            if allowed_types & pygit2.GIT_CREDENTIAL_SSH_KEY:
                try:
                    ssh_user = username_from_url or getpass.getuser()
                    cred_log.debug("Attempting SSH agent authentication", ssh_user=ssh_user)
                    credentials = pygit2.KeypairFromAgent(ssh_user)
                    cred_log.info("Using SSH agent credentials.")
                    return credentials
                except pygit2.GitError as e:
                    cred_log.debug("SSH agent authentication failed or not available", error=str(e))
                except Exception as e:
                    cred_log.error(
                        "Unexpected error during SSH agent auth attempt",
                        error=str(e),
                        exc_info=True,
                    )

            # 2. TODO: Add HTTPS Token/UserPass from Environment Variables
            # if allowed_types & pygit2.GIT_CREDENTIAL_USERPASS_PLAINTEXT:
            #    git_user = os.getenv("GIT_USERNAME")
            #    git_token = os.getenv("GIT_PASSWORD") # Treat as token
            #    if git_user and git_token:
            #        cred_log.info("Using User/Pass credentials from environment variables.")
            #        return pygit2.UserPass(git_user, git_token)
            #    else:
            #        cred_log.debug("GIT_USERNAME or GIT_PASSWORD env vars not set for UserPass.")

            cred_log.warning("No suitable credentials found or configured via callbacks.")
            return None

        return credentials_callback


# 🔼⚙️🔚
