#!/usr/bin/env python3
"""
Quick test to verify the statistics fix is working without running the full TUI.
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from supsrc.engines.git import GitEngine
from supsrc.state import RepositoryState
from supsrc.config import GlobalConfig


async def test_statistics_loading():
    """Test that statistics are properly loaded from git status."""

    # Create a git engine
    engine = GitEngine()

    # Create a repository state
    repo_state = RepositoryState(repo_id="test_repo")

    # Create minimal config
    global_config = GlobalConfig()
    repo_config = {}

    # Get the current working directory (this is a git repo)
    working_dir = Path.cwd()

    print(f"Testing statistics loading for: {working_dir}")

    try:
        # Get status (this should populate statistics)
        status_result = await engine.get_status(
            repo_state, repo_config, global_config, working_dir
        )

        if status_result.success:
            print("✅ Status retrieved successfully")
            print(f"   Total files: {status_result.total_files}")
            print(f"   Changed files: {status_result.changed_files}")
            print(f"   Added files: {status_result.added_files}")
            print(f"   Modified files: {status_result.modified_files}")
            print(f"   Deleted files: {status_result.deleted_files}")
            print(f"   Current branch: {status_result.current_branch}")
            print(f"   Is clean: {status_result.is_clean}")

            # Test manual statistics copying (like in action_handler)
            repo_state.total_files = status_result.total_files or 0
            repo_state.changed_files = status_result.changed_files or 0
            repo_state.added_files = status_result.added_files or 0
            repo_state.deleted_files = status_result.deleted_files or 0
            repo_state.modified_files = status_result.modified_files or 0
            repo_state.has_uncommitted_changes = not status_result.is_clean
            repo_state.current_branch = status_result.current_branch

            print("\n✅ Statistics copied to repository state:")
            print(f"   repo_state.total_files: {repo_state.total_files}")
            print(f"   repo_state.changed_files: {repo_state.changed_files}")
            print(f"   repo_state.current_branch: {repo_state.current_branch}")
            print(f"   repo_state.has_uncommitted_changes: {repo_state.has_uncommitted_changes}")

        else:
            print(f"❌ Status retrieval failed: {status_result.message}")

        # Test git summary loading
        summary = await engine.get_summary(working_dir)
        print(f"\n✅ Git summary retrieved:")
        print(f"   Head ref: {summary.head_ref_name}")
        print(f"   Head commit hash: {summary.head_commit_hash}")
        print(f"   Head commit message: {summary.head_commit_message_summary}")
        print(f"   Head commit timestamp: {getattr(summary, 'head_commit_timestamp', 'Not available')}")

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Testing repository statistics loading...")
    asyncio.run(test_statistics_loading())