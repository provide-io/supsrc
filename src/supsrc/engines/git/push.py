#
# engines/git/push.py
#
"""
Git push logic using pygit2.
"""

from pathlib import Path
import pygit2 # type: ignore[import-untyped]
import structlog

from supsrc.protocols import PushResult
from .runner import run_pygit2_async
from .errors import GitPushError, GitRemoteError, GitAuthenticationError

log = structlog.get_logger("engines.git.push")

# Note: Handling complex authentication (SSH keys with passphrases, HTTPS tokens)
# often requires more setup, potentially using pygit2 Callbacks or external helpers.
# This implementation assumes simple cases (e.g., SSH agent, credential helper).

class GitCallbacks(pygit2.RemoteCallbacks): # type: ignore[misc] # pygit2 stubs might be incomplete
    """Handles callbacks for remote operations, e.g., credentials."""
    def __init__(self, cred_type: str | None = None, user: str | None = None, key_path: str | None = None):
        super().__init__()
        # Simplistic example - real world needs more robust credential handling
        self._cred_type = cred_type # e.g., 'ssh_key', 'userpass'
        self._user = user
        self._key_path = key_path
        self._attempts = 0

    def credentials(self, url: str, username_from_url: str | None, allowed_types: int) -> pygit2.Cred | None:
        self._attempts += 1
        log.debug("Credentials callback invoked", url=url, username_from_url=username_from_url, allowed_types=allowed_types, attempt=self._attempts)

        # Example: SSH Key Authentication (if public key path is known)
        if allowed_types & pygit2.GIT_CREDENTIAL_SSH_KEY:
            # This assumes the key is usable without a passphrase or via an agent
            # For keys with passphrases, more complex logic is needed.
            ssh_pub_key = self._key_path + ".pub" if self._key_path else None
            ssh_priv_key = self._key_path if self._key_path else None
            user = self._user or username_from_url or "git" # Default SSH user
            log.debug("Attempting SSH key authentication", user=user, pubkey=ssh_pub_key)
            try:
                # Passphrase would be the 4th arg if needed
                return pygit2.Keypair(user, ssh_pub_key, ssh_priv_key, "")
            except Exception as e:
                 log.error("Failed to create SSH Keypair credential", error=str(e))
                 # Fall through to other methods or fail

        # Example: User/Password (less secure, avoid if possible)
        if allowed_types & pygit2.GIT_CREDENTIAL_USERPASS_PLAINTEXT:
             log.warning("Attempting USERPASS_PLAINTEXT authentication (less secure)")
             # Need to securely get username/password (e.g., from config, keyring)
             # Placeholder:
             # return pygit2.UserPass("my_user", "my_password")
             pass # Fall through

        # TODO: Implement other credential types if needed (e.g., GIT_CREDENTIAL_DEFAULT)
        log.error("No suitable credential method found or configured.", allowed_types=allowed_types)
        return None # Returning None will likely cause the operation to fail

    # You can override other callbacks like 'transfer_progress', 'update_tips', etc.
    # def update_tips(self, refname, old_oid, new_oid):
    #     log.debug("Push update", ref=refname, old=str(old_oid), new=str(new_oid))

    # def transfer_progress(self, stats):
    #     log.debug(f"Push progress: {stats.indexed_objects}/{stats.total_objects}")


async def perform_git_push(
    repo: pygit2.Repository,
    working_dir: Path,
    remote_name: str,
    branch_name: str,
    config: dict, # Engine config
) -> PushResult:
    """
    Performs a Git push using pygit2 asynchronously.

    Args:
        repo: An initialized pygit2.Repository object.
        working_dir: The repository's working directory path.
        remote_name: The name of the remote to push to (e.g., 'origin').
        branch_name: The name of the local branch to push.
        config: The engine-specific configuration dictionary (for potential creds).

    Returns:
        PushResult indicating success or failure.
    """
    log.debug(f"Attempting git push", repo_path=str(working_dir), remote=remote_name, branch=branch_name)

    try:
        # Find the remote
        try:
            remote = await run_pygit2_async(repo.remotes.__getitem__, remote_name)
        except KeyError:
            raise GitRemoteError(f"Remote '{remote_name}' not found.", repo_path=str(working_dir))
        except IndexError: # Sometimes pygit2 raises this instead of KeyError
             raise GitRemoteError(f"Remote '{remote_name}' not found (IndexError).", repo_path=str(working_dir))

        log.debug("Found remote", remote_name=remote.name, remote_url=remote.url)

        # Prepare callbacks (e.g., for authentication)
        # TODO: Enhance credential handling based on config
        callbacks = GitCallbacks()

        # Construct the refspec (e.g., 'refs/heads/main:refs/heads/main')
        local_ref = f"refs/heads/{branch_name}"
        remote_ref = local_ref # Push to the same branch name on the remote by default

        # Check if the local ref exists
        try:
             _ = await run_pygit2_async(repo.references.get, local_ref)
        except KeyError:
             raise GitPushError(f"Local branch '{branch_name}' (ref: {local_ref}) not found.", repo_path=str(working_dir))

        refspec = f"{local_ref}:{remote_ref}"
        log.debug("Using refspec for push", refspec=refspec)

        # Perform the push operation
        # The push call itself is blocking
        push_result_details = await run_pygit2_async(remote.push, [refspec], callbacks=callbacks)

        # push() doesn't raise exceptions on common push failures (like rejection),
        # but might on network errors or severe issues. It returns None on success.
        # We need to check callbacks or potentially parse output if more detail is needed,
        # but for now, assume success if no exception was raised.
        # Note: pygit2 push result interpretation is subtle. A non-exception doesn't
        # *guarantee* the remote accepted the push (e.g., non-fast-forward rejection
        # might not raise an exception but fail silently without callback checks).
        # For MVP, we'll assume no exception means success.

        log.info("Push command executed.", repo_path=str(working_dir), remote=remote_name, branch=branch_name)
        # A more robust check would involve inspecting callback status if implemented.

        return PushResult(success=True, message="Push command executed successfully.")

    except pygit2.GitError as e:
        # Try to interpret common GitErrors
        err_msg = str(e)
        log.error("GitError during push", repo_path=str(working_dir), error=err_msg, exc_info=True)
        if "authenticat" in err_msg.lower():
             raise GitAuthenticationError(f"Push failed: {err_msg}", repo_path=str(working_dir), details=e) from e
        # Add more specific error checks if needed (e.g., for network errors)
        raise GitPushError(f"Push failed: {err_msg}", repo_path=str(working_dir), details=e) from e
    except Exception as e:
        # Catch other potential errors
        log.error("Failed to perform push", repo_path=str(working_dir), error=str(e), exc_info=True)
        if isinstance(e, GitPushError): raise # Re-raise if already specific type
        raise GitPushError(f"Push failed unexpectedly: {e}", repo_path=str(working_dir), details=e) from e

# 🔼⚙️
