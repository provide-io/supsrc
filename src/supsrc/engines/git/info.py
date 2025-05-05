#
# engines/git/info.py
#
"""
Data classes for Git-specific information.
"""

from typing import Optional
from attrs import define, field

@define(frozen=True, slots=True)
class GitRepoSummary:
    """Holds summary information about a Git repository's state."""
    is_empty: bool = False
    head_ref_name: Optional[str] = None # e.g., 'main', 'refs/heads/develop', 'UNBORN'
    head_commit_hash: Optional[str] = None # Full commit SHA
    head_commit_message_summary: Optional[str] = None # First line of commit message

# 🔼⚙️
