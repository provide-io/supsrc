#!/usr/bin/env python3
"""Test event logging in the TUI to debug event feed issues."""

import asyncio
import os
import sys
from pathlib import Path

# Set logging to DEBUG level before importing
os.environ["SUPSRC_LOG_LEVEL"] = "DEBUG"
os.environ["PYTHONPATH"] = "../provide-foundation/src:./workenv/wrkenv_darwin_arm64/lib/python3.11/site-packages:./src"

sys.path.insert(0, str(Path(__file__).parent / "src"))

from supsrc.config.loader import load_config
from supsrc.runtime.orchestrator import WatchOrchestrator


async def test_event_logging():
    """Test event emission and logging with DEBUG level."""
    print("🔍 Testing event logging with DEBUG level...")

    # Load config
    config_path = Path("/Users/tim/code/gh/provide-io/supsrc/examples/supsrc_test.conf")
    config = load_config(config_path)

    # Create shutdown event
    shutdown_event = asyncio.Event()

    # Create orchestrator
    orchestrator = WatchOrchestrator(config_path, shutdown_event)

    try:
        # Initialize orchestrator
        print("🚀 Initializing orchestrator...")
        await orchestrator.initialize()

        print("📊 Current repo states:")
        for repo_id, state in orchestrator.repo_states.items():
            print(f"  - {repo_id}: {state.status.name}")

        # Start monitoring for a short time
        print("👀 Starting monitoring for 5 seconds...")
        monitor_task = asyncio.create_task(orchestrator.run())

        # Wait for initialization
        await asyncio.sleep(1)

        # Create a test file to trigger events
        test_file = Path("/tmp/supsrc-example-repo1/event_test.txt")
        print(f"📝 Creating test file: {test_file}")
        test_file.write_text("Event test content")

        # Wait for events to be processed
        await asyncio.sleep(2)

        # Modify the file
        print("✏️ Modifying test file...")
        test_file.write_text("Modified event test content")

        # Wait for more events
        await asyncio.sleep(2)

        print("✅ Test completed successfully")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Shutdown
        print("🛑 Shutting down...")
        shutdown_event.set()
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(test_event_logging())