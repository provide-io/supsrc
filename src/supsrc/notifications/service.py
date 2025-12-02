#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Desktop notification service for supsrc using system notification tools."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from enum import Enum, auto
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger

if TYPE_CHECKING:
    from supsrc.config.models import NotificationConfig

log = get_logger(__name__)


class NotificationType(Enum):
    """Types of notifications that can be sent."""

    COMMIT_SUCCESS = auto()
    PUSH_SUCCESS = auto()
    PUSH_FAILURE = auto()
    CIRCUIT_BREAKER = auto()
    CONFLICT_DETECTED = auto()
    ERROR = auto()
    INFO = auto()


# Notification type icons and urgency levels
NOTIFICATION_ICONS = {
    NotificationType.COMMIT_SUCCESS: "✅",
    NotificationType.PUSH_SUCCESS: "🚀",
    NotificationType.PUSH_FAILURE: "⚠️",
    NotificationType.CIRCUIT_BREAKER: "🛑",
    NotificationType.CONFLICT_DETECTED: "⚔️",
    NotificationType.ERROR: "❌",
    NotificationType.INFO: "💬",
}


class NotificationService:
    """Service for sending desktop notifications using system tools."""

    def __init__(self, config: NotificationConfig | None = None) -> None:
        """Initialize the notification service.

        Args:
            config: Optional notification configuration
        """
        self._enabled = config.enabled if config else False
        self._config = config
        self._log = log.bind(service="notifications")
        self._notifier = self._detect_notifier()
        self._log.debug(
            "Notification service initialized",
            enabled=self._enabled,
            notifier=self._notifier,
        )

    def _detect_notifier(self) -> str | None:
        """Detect available notification tool on the system."""
        if sys.platform == "darwin":
            # macOS - use osascript
            if shutil.which("osascript"):
                return "osascript"
        elif sys.platform.startswith("linux"):
            # Linux - prefer notify-send, then zenity
            if shutil.which("notify-send"):
                return "notify-send"
            if shutil.which("zenity"):
                return "zenity"
        elif sys.platform == "win32":
            # Windows - PowerShell toast notifications
            if shutil.which("powershell"):
                return "powershell"

        self._log.warning("No notification tool found on system")
        return None

    @property
    def enabled(self) -> bool:
        """Check if notifications are enabled and available."""
        return self._enabled and self._notifier is not None

    def enable(self) -> None:
        """Enable notifications."""
        self._enabled = True

    def disable(self) -> None:
        """Disable notifications."""
        self._enabled = False

    async def notify(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        repo_id: str | None = None,
    ) -> bool:
        """Send a desktop notification.

        Args:
            title: Notification title
            message: Notification body
            notification_type: Type of notification for icon/urgency
            repo_id: Optional repository ID for context

        Returns:
            True if notification was sent successfully
        """
        if not self.enabled:
            return False

        # Check if this notification type is enabled in config
        if self._config and not self._should_notify(notification_type):
            return False

        icon = NOTIFICATION_ICONS.get(notification_type, "📢")
        full_title = f"{icon} Supsrc: {title}"

        if repo_id:
            message = f"[{repo_id}] {message}"

        self._log.debug(
            "Sending notification",
            title=title,
            type=notification_type.name,
            repo_id=repo_id,
        )

        try:
            return await self._send_notification(full_title, message, notification_type)
        except Exception as e:
            self._log.warning("Failed to send notification", error=str(e))
            return False

    def _should_notify(self, notification_type: NotificationType) -> bool:
        """Check if a notification type is enabled in config."""
        if not self._config:
            return True

        # Map notification types to config options
        type_config_map = {
            NotificationType.COMMIT_SUCCESS: self._config.on_commit,
            NotificationType.PUSH_SUCCESS: self._config.on_push,
            NotificationType.PUSH_FAILURE: self._config.on_error,
            NotificationType.CIRCUIT_BREAKER: self._config.on_circuit_breaker,
            NotificationType.CONFLICT_DETECTED: self._config.on_conflict,
            NotificationType.ERROR: self._config.on_error,
            NotificationType.INFO: True,  # Always allow INFO
        }
        return type_config_map.get(notification_type, True)

    async def _send_notification(self, title: str, message: str, notification_type: NotificationType) -> bool:
        """Send notification using detected system tool."""
        if not self._notifier:
            return False

        try:
            if self._notifier == "osascript":
                return await self._send_macos_notification(title, message)
            elif self._notifier == "notify-send":
                return await self._send_linux_notification(title, message, notification_type)
            elif self._notifier == "zenity":
                return await self._send_zenity_notification(title, message)
            elif self._notifier == "powershell":
                return await self._send_windows_notification(title, message)
        except Exception as e:
            self._log.error("Notification send failed", error=str(e), notifier=self._notifier)
            return False

        return False

    async def _send_macos_notification(self, title: str, message: str) -> bool:
        """Send notification on macOS using osascript."""
        # Escape double quotes in title and message
        title = title.replace('"', '\\"')
        message = message.replace('"', '\\"')

        script = f'display notification "{message}" with title "{title}"'
        proc = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            script,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    async def _send_linux_notification(
        self, title: str, message: str, notification_type: NotificationType
    ) -> bool:
        """Send notification on Linux using notify-send."""
        # Map notification types to urgency levels
        urgency_map = {
            NotificationType.ERROR: "critical",
            NotificationType.CIRCUIT_BREAKER: "critical",
            NotificationType.CONFLICT_DETECTED: "critical",
            NotificationType.PUSH_FAILURE: "normal",
            NotificationType.COMMIT_SUCCESS: "low",
            NotificationType.PUSH_SUCCESS: "low",
            NotificationType.INFO: "low",
        }
        urgency = urgency_map.get(notification_type, "normal")

        proc = await asyncio.create_subprocess_exec(
            "notify-send",
            "--urgency",
            urgency,
            "--app-name",
            "Supsrc",
            title,
            message,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    async def _send_zenity_notification(self, title: str, message: str) -> bool:
        """Send notification on Linux using zenity as fallback."""
        proc = await asyncio.create_subprocess_exec(
            "zenity",
            "--notification",
            f"--text={title}: {message}",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    async def _send_windows_notification(self, title: str, message: str) -> bool:
        """Send notification on Windows using PowerShell toast notification."""
        # Escape single quotes
        title = title.replace("'", "''")
        message = message.replace("'", "''")

        script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
        $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template)
        $texts = $xml.GetElementsByTagName('text')
        $texts[0].AppendChild($xml.CreateTextNode('{title}')) | Out-Null
        $texts[1].AppendChild($xml.CreateTextNode('{message}')) | Out-Null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Supsrc').Show($toast)
        """

        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-Command",
            script,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    # Convenience methods for common notification types
    async def notify_commit(self, repo_id: str, commit_hash: str, files_count: int) -> bool:
        """Notify about a successful commit."""
        return await self.notify(
            "Commit Successful",
            f"Committed {files_count} files ({commit_hash[:7]})",
            NotificationType.COMMIT_SUCCESS,
            repo_id,
        )

    async def notify_push(self, repo_id: str, branch: str) -> bool:
        """Notify about a successful push."""
        return await self.notify(
            "Push Successful",
            f"Pushed to {branch}",
            NotificationType.PUSH_SUCCESS,
            repo_id,
        )

    async def notify_push_failure(self, repo_id: str, reason: str) -> bool:
        """Notify about a push failure."""
        return await self.notify(
            "Push Failed",
            reason,
            NotificationType.PUSH_FAILURE,
            repo_id,
        )

    async def notify_circuit_breaker(self, repo_id: str, reason: str) -> bool:
        """Notify about a circuit breaker trigger."""
        return await self.notify(
            "Circuit Breaker Triggered",
            reason,
            NotificationType.CIRCUIT_BREAKER,
            repo_id,
        )

    async def notify_conflict(self, repo_id: str, conflict_count: int) -> bool:
        """Notify about detected conflicts."""
        return await self.notify(
            "Conflicts Detected",
            f"{conflict_count} conflict(s) found - manual resolution required",
            NotificationType.CONFLICT_DETECTED,
            repo_id,
        )

    async def notify_error(self, repo_id: str, error_message: str) -> bool:
        """Notify about an error."""
        return await self.notify(
            "Error",
            error_message,
            NotificationType.ERROR,
            repo_id,
        )


# 🔼⚙️🔚
