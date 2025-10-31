#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Test to understand temp file emission in supsrc."""

import asyncio
from pathlib import Path
from unittest.mock import Mock

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


async def main():
    """Simulate VSCode atomic save pattern."""
    mock_callback = Mock()

    # Create buffer with smart mode (like supsrc uses)
    buffer = EventBuffer(
        window_ms=500,
        grouping_mode="smart",
        emit_callback=mock_callback,
    )

    # Simulate VSCode editing orchestrator.py
    temp_file = Path(".orchestrator.py.tmp")
    real_file = Path("orchestrator.py")
    repo_id = "test_repo"

    print("=== Simulating VSCode atomic save ===")

    # 1. Create temp file
    print(f"1. Creating temp file: {temp_file}")
    buffer.add_event(
        FileChangeEvent(
            description=f"File created: {temp_file.name}",
            repo_id=repo_id,
            file_path=temp_file,
            change_type="created",
        )
    )

    await asyncio.sleep(0.01)  # Small delay

    # 2. Modify temp file
    print(f"2. Modifying temp file: {temp_file}")
    buffer.add_event(
        FileChangeEvent(
            description=f"File modified: {temp_file.name}",
            repo_id=repo_id,
            file_path=temp_file,
            change_type="modified",
        )
    )

    await asyncio.sleep(0.01)  # Small delay

    # 3. Move temp to real file
    print(f"3. Moving {temp_file} -> {real_file}")
    buffer.add_event(
        FileChangeEvent(
            description=f"File moved: {temp_file.name} -> {real_file.name}",
            repo_id=repo_id,
            file_path=temp_file,
            change_type="moved",
            dest_path=real_file,
        )
    )

    # Wait for auto-flush
    print("\n=== Waiting for auto-flush (600ms) ===")
    await asyncio.sleep(0.6)

    print("\n=== Results ===")
    print(f"Callback call count: {mock_callback.call_count}")

    if mock_callback.call_count > 0:
        for i, call in enumerate(mock_callback.call_args_list):
            event = call[0][0]
            print(f"\nEmission {i + 1}:")
            print(f"  Operation type: {event.operation_type}")
            print(f"  File paths: {[str(p) for p in event.file_paths]}")
            print(f"  Primary change type: {event.primary_change_type}")
            print(f"  Event count: {event.event_count}")
    else:
        print("  NO EVENTS EMITTED!")

    # Also test single temp file modification
    print("\n\n=== Testing single temp file modification ===")
    mock_callback.reset_mock()

    buffer.add_event(
        FileChangeEvent(
            description=f"File modified: {temp_file.name}",
            repo_id=repo_id,
            file_path=temp_file,
            change_type="modified",
        )
    )

    await asyncio.sleep(0.6)

    print(f"Callback call count: {mock_callback.call_count}")
    if mock_callback.call_count > 0:
        event = mock_callback.call_args[0][0]
        print(f"  Operation type: {event.operation_type}")
        print(f"  File paths: {[str(p) for p in event.file_paths]}")
    else:
        print("  NO EVENTS EMITTED! (correct - temp file hidden)")


if __name__ == "__main__":
    asyncio.run(main())

# 🔼⚙️🔚
