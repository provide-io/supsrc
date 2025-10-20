# supsrc/events/buffer/converters.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
"""
Event conversion utilities for transforming between different event formats.


    FileEvent,
    FileEventMetadata,
    OperationType,
)


log = get_logger("events.buffer.converters")


def convert_to_file_event(event: FileChangeEvent, sequence_counter: dict[str, int]) -> FileEvent:
    """Convert a FileChangeEvent to FileEvent for operation detection.

"""
