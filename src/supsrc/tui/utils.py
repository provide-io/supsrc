"""TUI utility functions and helpers."""

from datetime import datetime, UTC


def format_countdown(seconds_left: int | None) -> str:
    """Format countdown seconds into a readable display."""
    if seconds_left is None:
        return ""
    
    if seconds_left <= 0:
        return "Now"
    elif seconds_left < 60:
        return f"{seconds_left}s"
    else:
        minutes = seconds_left // 60
        secs = seconds_left % 60
        if secs > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{minutes}m"


def get_countdown_emoji(seconds_left: int | None) -> str:
    """Get an emoji representing the countdown state."""
    if seconds_left is None:
        return ""
    
    if seconds_left > 20:
        return "⏳"  # Hourglass
    elif seconds_left > 10:
        return "⏱️"  # Stopwatch
    elif seconds_left > 5:
        return "⚡"  # Lightning
    elif seconds_left > 3:
        return "🔥"  # Fire
    elif seconds_left > 1:
        return "✌️"  # Two fingers
    elif seconds_left == 1:
        return "☝️"  # One finger
    else:
        return "💥"  # Zero/trigger


def format_last_commit_time(last_change_time, threshold_hours=3):
    """Format last commit time as relative or absolute based on age."""
    if not last_change_time:
        return "Never"

    now = datetime.now(UTC)
    delta = now - last_change_time
    total_seconds = int(delta.total_seconds())

    # If older than threshold, show full date
    if delta.total_seconds() > (threshold_hours * 3600):
        return last_change_time.strftime("%Y-%m-%d %H:%M:%S")

    # Otherwise show relative time
    if total_seconds < 60:
        return f"{total_seconds}s ago"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes}m ago"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}h {minutes}m ago"
        else:
            return f"{hours}h ago"


class TimerManager:
    """Manages application timers with proper lifecycle handling."""

    def __init__(self, app):
        self.app = app
        self._timers = {}
        import structlog
        self._logger = structlog.get_logger("tui.timer_manager")

    def create_timer(self, name: str, interval: float, callback: callable, repeat: bool = True):
        """Create a new timer with proper tracking."""
        if name in self._timers:
            self.stop_timer(name)

        timer = self.app.set_interval(interval, callback, name=name)
        self._timers[name] = timer
        self._logger.debug("Timer created", name=name, interval=interval)
        return timer

    def stop_timer(self, name: str) -> bool:
        """Stop a specific timer."""
        if name not in self._timers:
            return False

        timer = self._timers[name]
        had_error = False
        try:
            # Check if the timer is active by inspecting its internal handle
            if hasattr(timer, "_Timer__handle") and timer._Timer__handle is not None:
                timer.stop()
        except Exception as e:
            self._logger.error("Error stopping timer", name=name, error=str(e))
            had_error = True
        finally:
            if name in self._timers:  # Re-check as timer.stop() might have already removed it
                del self._timers[name]
            self._logger.debug("Timer stopped or already inactive", name=name)
        
        return not had_error

    def stop_all_timers(self) -> None:
        """Stop all managed timers."""
        timer_names = list(self._timers.keys())
        self._logger.debug("Stopping all timers", count=len(timer_names))
        
        for name in timer_names:
            try:
                self.stop_timer(name)
            except Exception as e:
                self._logger.error("Error stopping timer during cleanup", name=name, error=str(e))
        
        # Clear any remaining timer references
        self._timers.clear()
        self._logger.debug("All timers stopped", count=len(timer_names))