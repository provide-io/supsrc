# Feature: .gitignore Integration
#   As a user of supsrc,
#   I want file changes matching patterns in the repository's .gitignore file to be ignored,
#   So that temporary files, build artifacts, or intentionally untracked files do not trigger commits.

@monitoring @gitignore
Feature: .gitignore Integration

  Background: Setup Git Repo with .gitignore
    Given a directory structure for monitoring tests
    Given a clean Git repository exists at "watch_repos/repo-ignore"
    Given a file ".gitignore" exists in "watch_repos/repo-ignore" with content:
      """
      # Ignore specific file
      ignored_file.log

      # Ignore directory
      build/

      # Ignore pattern
      *.tmp
      """
    Given a "supsrc.conf" file exists with:
      """
      [repositories.repo-ignore]
      path = "watch_repos/repo-ignore"
      enabled = true
      [repositories.repo-ignore.trigger]
      type = "inactivity"
      period = "1s"
      """
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Changes to Tracked Files Trigger Commit
    Given the monitoring process is running
    When a file "tracked_file.txt" is created and saved in "watch_repos/repo-ignore"
    Then the output should eventually contain "[repo-ignore] Change detected: .*tracked_file.txt"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-ignore] Inactivity trigger fired. Committing..."
    And a commit should exist in the "repo-ignore" Git history

  Scenario Outline: Changes to Ignored Files or Directories Do Not Trigger Commit
    Given the monitoring process is running
    When a file "<ignored_path>" is created and saved in "watch_repos/repo-ignore"
    Then the output should NOT contain "[repo-ignore] Change detected: .*<ignored_path>" # Should be filtered by watchdog/handler
    And after "2" seconds # Wait long enough to ensure no commit
    Then the output should NOT contain "[repo-ignore] Inactivity trigger fired. Committing..."
    And no new commit should exist in the "repo-ignore" Git history (beyond the initial one if created)

    Examples:
      | ignored_path           | notes                        |
      | ignored_file.log       | Specifically ignored file    |
      | build/output.bin       | File inside ignored directory|
      | temp_file.tmp          | File matching ignored pattern|
      | src/sub/another.tmp    | Pattern ignored in subdir    |
      # Also test modifications to existing ignored files