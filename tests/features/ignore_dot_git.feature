# Feature: Ignoring .git Directory Changes
#   As a user of supsrc,
#   I want changes occurring inside the .git directory (e.g., index locking, object writing) to be explicitly ignored,
#   So that internal Git operations do not trigger spurious commits.

@monitoring @core
Feature: Ignoring .git Directory Changes

  Background: Setup Git Repo
    Given a directory structure for monitoring tests
    Given a clean Git repository exists at "watch_repos/repo-dotgit"
    Given a "supsrc.conf" file exists with:
      """
      [repositories.repo-dotgit]
      path = "watch_repos/repo-dotgit"
      enabled = true
      [repositories.repo-dotgit.trigger]
      type = "inactivity"
      period = "1s"
      """
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Internal Git File Changes Are Ignored
    Given the monitoring process is running
    # Simulate internal git operations (e.g., writing to index, refs, objects)
    # This might require specific file system events mocking if watchdog filters perfectly,
    # or simply writing files directly into the .git dir for testing the handler logic.
    When a file ".git/index.lock" is created in "watch_repos/repo-dotgit"
    And a file ".git/objects/info/tmp_file" is created in "watch_repos/repo-dotgit"
    And a file ".git/logs/refs/heads/main" is modified in "watch_repos/repo-dotgit"
    Then the output should NOT contain "[repo-dotgit] Change detected: .*\.git.*" # Ensure no logs for .git changes
    And after "2" seconds
    Then the output should NOT contain "[repo-dotgit] Inactivity trigger fired. Committing..."
    And no new commit should exist in the "repo-dotgit" Git history

  Scenario: Changes Outside .git Still Trigger Commit
    Given the monitoring process is running
    When a file "tracked_file.txt" is created and saved in "watch_repos/repo-dotgit"
    Then the output should eventually contain "[repo-dotgit] Change detected: .*tracked_file.txt"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-dotgit] Inactivity trigger fired. Committing..."
    And a commit should exist in the "repo-dotgit" Git history