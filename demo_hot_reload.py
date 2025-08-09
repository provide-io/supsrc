#!/usr/bin/env python3
"""
Demo script to prove hot reload functionality works.
This creates a test environment and demonstrates config hot reload.
"""

import asyncio
import tempfile
import time
from pathlib import Path

# Ensure we can import supsrc
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from supsrc.config.loader import load_config
from supsrc.runtime.orchestrator import WatchOrchestrator


async def main():
    print("🔥 Supsrc Hot Reload Demo")
    print("=" * 50)
    
    # Create temporary directory for demo
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create test repository
        repo_path = tmppath / "test-repo"
        repo_path.mkdir()
        (repo_path / "README.md").write_text("# Test Repository")
        
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, capture_output=True)
        
        # Create initial config
        config_path = tmppath / "supsrc.conf"
        config_content_v1 = f"""
[global]
log_level = "INFO"

[repositories.test-repo]
enabled = true
path = "{repo_path}"

[repositories.test-repo.rule]
type = "inactivity"
period = "30s"

[repositories.test-repo.repository]
engine = "supsrc.engines.git"
commit_message_template = "Version 1 commit"
"""
        config_path.write_text(config_content_v1)
        
        print(f"✅ Created test environment at: {tmppath}")
        print(f"✅ Config file at: {config_path}")
        print()
        
        # Start orchestrator
        shutdown_event = asyncio.Event()
        orchestrator = WatchOrchestrator(config_path, shutdown_event)
        
        # Create a task to modify config after 5 seconds
        async def modify_config_after_delay():
            await asyncio.sleep(5)
            print("\n🔄 Modifying config file...")
            
            config_content_v2 = f"""
[global]
log_level = "DEBUG"  # Changed from INFO

[repositories.test-repo]
enabled = true
path = "{repo_path}"

[repositories.test-repo.rule]
type = "inactivity"
period = "10s"  # Changed from 30s

[repositories.test-repo.repository]
engine = "supsrc.engines.git"
commit_message_template = "Version 2 commit - RELOADED!"

# Added new repository
[repositories.another-repo]
enabled = true
path = "{repo_path}"

[repositories.another-repo.rule]
type = "save_count"
count = 5

[repositories.another-repo.repository]
engine = "supsrc.engines.git"
"""
            config_path.write_text(config_content_v2)
            print("✅ Config file modified!")
            
        # Create a task to shutdown after 15 seconds
        async def shutdown_after_delay():
            await asyncio.sleep(15)
            print("\n🛑 Shutting down demo...")
            shutdown_event.set()
            
        # Start background tasks
        modify_task = asyncio.create_task(modify_config_after_delay())
        shutdown_task = asyncio.create_task(shutdown_after_delay())
        
        try:
            # Run orchestrator
            print("🚀 Starting orchestrator with hot reload enabled...")
            print("   - Config will be modified after 5 seconds")
            print("   - Watch for automatic reload message")
            print("   - Demo will end after 15 seconds")
            print()
            
            await orchestrator.run()
            
        except KeyboardInterrupt:
            print("\n⚠️  Demo interrupted by user")
            shutdown_event.set()
        finally:
            # Wait for tasks to complete
            await asyncio.gather(modify_task, shutdown_task, return_exceptions=True)
            
    print("\n✅ Demo completed!")


if __name__ == "__main__":
    asyncio.run(main())


# 🔥🔄✅