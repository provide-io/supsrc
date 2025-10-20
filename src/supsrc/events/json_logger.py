# supsrc/events/json_logger.py
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
"""
JSON event logger for persisting events to structured log files.




if TYPE_CHECKING:

    pass
log = get_logger("events.json_logger")


@attrs.define
class JSONEventLogger:
    """Logs events to a JSON file with structured format.

"""
