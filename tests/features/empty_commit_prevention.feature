# Feature: Empty Commit Prevention
#   As a user running supsrc watch,
#   I want the tool to avoid making a commit if there are no actual changes staged (e.g., after saving a file with no content change),
#   So that my Git history is not cluttered with empty commits.

@monitoring @git
Feature: Empty Commit Prevention

  Background: Setup Git Repo
    Given a directory structure for monitoring tests
    Given a Git repository exists at "watch_repos/repo-empty" with an initial commit containing "existing_file.txt"
    Given a "supsrc.conf" file exists with:
      """
      [repositories.repo-empty]
      path = "watch_repos/repo-empty"
      enabled = true
      [repositories.repo-empty.trigger]
      type = "inactivity"
      period = "1s"
      """
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Saving File Without Actual Changes Does Not Commit
    Given the monitoring process is running
    # Simulate a save event without changing file content (e.g., touch, or IDE save on unmodified file)
    When the file "watch_repos/repo-empty/existing_file.txt" is saved without modification
    Then the output should eventually contain "[repo-empty] Change detected: .*existing_file.txt"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-empty] Inactivity trigger fired. Committing..."
    # Check for a specific message indicating nothing to commit
    And the output should eventually contain "[repo-empty] No changes detected by git status. Skipping commit." # Or similar log
    And the output should NOT contain "[repo-empty] Git commit successful"
    And no new commit should exist in the "repo-empty" Git history

  Scenario: Saving File With Changes Still Commits
    Given the monitoring process is running
    When the file "watch_repos/repo-empty/existing_file.txt" is modified with new content and saved
    Then the output should eventually contain "[repo-empty] Change detected: .*existing_file.txt"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-empty] Inactivity trigger fired. Committing..."
    And the output should eventually contain "[repo-empty] Git commit successful"
    And a new commit should exist in the "repo-empty" Git history