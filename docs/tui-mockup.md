# supsrc TUI Mock-up

This document shows ASCII mock-ups of the Textual User Interface (TUI) for the `supsrc watch` command, illustrating the different contexts and display elements.

## Default 2-Pane View

This is the default view when `supsrc watch --tui` starts.

╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║ supsrc Watcher - (Press Ctrl+C to quit, Enter on repo for details, Esc to close details)                                                                                       ║
╠════════════╤═════════════════════╤════════════════════╤═══════════════════════╤══════════════════════════════════╤═══════════════════════════════════════════════════════════╣
║ Status     │ Repository          │ Last Change        │ Rule                  │ Current Action                   │ Last Commit / Message                                     ║
╠════════════╪═════════════════════╪════════════════════╪═══════════════════════╪══════════════════════════════════╪═══════════════════════════════════════════════════════════╣
║ 🧼 Idle    │ bfiles              │ 2025-05-22 19:53:10│ ⏳ Inactivity (30s)   │                                  │ 857c48b - Automated commit                            ║
║ ✏️ Changed  │ pyvider             │ 2025-05-22 19:54:05│ ⏳ Inactivity (60s)   │                                  │ b056b2d - Feature X                                   ║
║ 😴 Waiting │ pyvider-telemetry   │ 2025-05-22 19:52:00│ ⏳ (00:17)            │                                  │ 9d8b8e7 - Initial setup                               ║
║ 🔄 Acting  │ pyvider-rpcplugin   │ 2025-05-22 19:50:00│ ⏳ Inactivity (30s)   │ Committing... [|||     ] 30%    │ 57da4b3 - Refactor utils                              ║
║ ✅ Success │ pyvider-core        │ 2025-05-22 19:45:30│ ⚙️ Default            │ Push complete                    │ 9127805 - Add new module                              ║
║ 🚫 Skipped │ pyvider-cty         │ 2025-05-22 19:40:00│ ⏳ Inactivity (30s)   │ Skipped (no changes)             │ 53260ee - Update deps                                 ║
║ ❌ Error   │ pyvider-schema      │ 2025-05-22 19:35:15│ ⏳ Inactivity (30s)   │ Error: Merge conflict            │ 8dfaef6 - Fix typo                                    ║
╠════════════╧═════════════════════╧════════════════════╧═══════════════════════╧══════════════════════════════════╧═══════════════════════════════════════════════════════════╣
║ Global Event Log                                                                                                                                                             ║
╟──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╢
║ [INFO] Orchestrator starting up...                                                                                                                                           ║
║ [DEBUG] bfiles: Change detected: README.md                                                                                                                                   ║
║ [INFO] pyvider-rpcplugin: Staging changes...                                                                                                                                 ║
║ [WARNING] pyvider-schema: Failed to commit: Merge conflict detected.                                                                                                         ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝

## 3-Pane View (Repository Detail)

Activated by pressing "Enter" on a repository in the table above.

╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║ supsrc Watcher - (Press Ctrl+C to quit, Enter on repo for details, Esc to close details)                                                                                       ║
╠════════════╤═════════════════════╤════════════════════╤═══════════════════════╤══════════════════════════════════╤═══════════════════════════════════════════════════════════╣
║ Status     │ Repository          │ Last Change        │ Rule                  │ Current Action                   │ Last Commit / Message                                     ║
╠════════════╪═════════════════════╪════════════════════╪═══════════════════════╪══════════════════════════════════╪═══════════════════════════════════════════════════════════╣
║ 😴 Waiting │ pyvider-telemetry   │ 2025-05-22 19:52:00│ ⏳ (00:12)            │                                  │ 9d8b8e7 - Initial setup                               ║
║ ... (other repositories) ...                                                                                                                                                 ║
╠════════════╧═════════════════════╧════════════════════╧═══════════════════════╧══════════════════════════════════╧═══════════════════════════════════════════════════════════╣
║ Details for: pyvider-telemetry                                                                                                                                               ║
╟──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╢
║ Commit History / Specific Logs:                                                                                                                                              ║
║ - 2025-05-22 19:52:00: Change detected: main.py                                                                                                                              ║
║ - 2025-05-22 19:50:30: Commit abc1234 - Refactor data processing                                                                                                             ║
║ - 2025-05-22 19:45:00: Push successful to origin/main                                                                                                                        ║
╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
║ Global Event Log                                                                                                                                                             ║
╟──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╢
║ [DEBUG] pyvider-telemetry: Inactivity timer started (30s).                                                                                                                   ║
║ [INFO] bfiles: Commit successful: newhash0 - Update README.md                                                                                                                ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝

## Column Explanations (Updated):

*   **Status:** Emoji indicating the overall current state of the repository (e.g., ✏️, 😴, 🔄, ✅, ❌).
*   **Repository:** The name/ID of the repository.
*   **Last Change:** Timestamp of the most recent file event or significant state update.
*   **Rule:**
    *   Shows an emoji for the rule type (e.g., ⏳ for Inactivity).
    *   Shows a dynamic indicator (e.g., countdown like `(00:17)` or status like `(3/5 files)` or `Active`).
*   **Current Action:**
    *   Describes the ongoing long-running action (e.g., "Staging...", "Committing...", "Pushing...").
    *   May include a textual progress bar (e.g., `[|||---] 50%`) if progress data is available.
    *   Shows completion or error status briefly after an action.
*   **Last Commit / Message:** Short hash and summary of the last successful commit for that repository.

## Rule Emojis and Dynamic Indicators

1.  **Inactivity Rule:**
    *   **Emoji:** ⏳
    *   **Dynamic Indicator (when waiting):** Countdown timer, e.g., `(00:17)` decreasing.
    *   **Dynamic Indicator (when idle/configured):** Static period, e.g., `Inactivity (30s)`.
    *   **Dynamic Indicator (when evaluating):** "Checking..."

2.  **FileCount Rule (Example for a potential future rule type):**
    *   **Emoji:** 🗂️
    *   **Dynamic Indicator (when active):** File count progress, e.g., `(3/5 files)`.

3.  **Default/Other Rules:**
    *   **Emoji:** ⚙️
    *   **Dynamic Indicator:** Rule type name or "Active".
