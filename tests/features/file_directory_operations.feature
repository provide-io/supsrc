# Feature: File and Directory Operations Handling
#   As a user managing files within a monitored repository,
#   I want supsrc to correctly detect changes resulting from file/directory moves, renames, and deletions,
#   So that the repository state is accurately captured.

@monitoring @filesystem
Feature: File and Directory Operations Handling

  Background: Setup Git Repo
    Given a directory structure for monitoring tests
    Given a Git repository exists at "watch_repos/repo-ops" with an initial commit containing "file_to_move.txt" and "dir_to_rename/"
    Given a "supsrc.conf" file exists with:
      """
      [repositories.repo-ops]
      path = "watch_repos/repo-ops"
      enabled = true
      [repositories.repo-ops.trigger]
      type = "inactivity"
      period = "1s"
      """
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Moving a File Triggers Commit
    Given the monitoring process is running
    When the file "watch_repos/repo-ops/file_to_move.txt" is moved to "watch_repos/repo-ops/moved_file.txt"
    # Depending on watchdog/OS, this might appear as delete + create or a specific move event
    Then the output should eventually contain "[repo-ops] Change detected: .*" # Should detect the move/delete/create
    And after "1.5" seconds
    Then the output should eventually contain "[repo-ops] Inactivity trigger fired. Committing..."
    And a commit should exist in the "repo-ops" Git history reflecting the file move

  Scenario: Renaming a Directory Triggers Commit
    Given the monitoring process is running
    When the directory "watch_repos/repo-ops/dir_to_rename" is renamed to "watch_repos/repo-ops/renamed_dir"
    Then the output should eventually contain "[repo-ops] Change detected: .*"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-ops] Inactivity trigger fired. Committing..."
    And a commit should exist in the "repo-ops" Git history reflecting the directory rename

  Scenario: Deleting a File Triggers Commit
    Given the monitoring process is running
    And a file "file_to_delete.txt" is created and committed in "watch_repos/repo-ops"
    When the file "watch_repos/repo-ops/file_to_delete.txt" is deleted
    Then the output should eventually contain "[repo-ops] Change detected: .*file_to_delete.txt" # Or similar event
    And after "1.5" seconds
    Then the output should eventually contain "[repo-ops] Inactivity trigger fired. Committing..."
    And a commit should exist in the "repo-ops" Git history reflecting the file deletion