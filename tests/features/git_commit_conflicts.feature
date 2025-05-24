# Feature: Handling Git Commit Conflicts
#   As a user whose repository might enter a conflicted state,
#   I want supsrc to detect this state and avoid attempting automatic commits that would fail,
#   So that the conflicted state is not worsened and I am notified appropriately.

@monitoring @git @errors
Feature: Handling Git Commit Conflicts

  Background: Setup Git Repo in Conflicted State
    Given a directory structure for monitoring tests
    Given a Git repository exists at "watch_repos/repo-conflict"
    # Test setup needs to create a merge conflict state in the working dir
    And the repository "watch_repos/repo-conflict" is put into a merge conflict state on file "conflict.txt"
    Given a "supsrc.conf" file exists with:
      """
      [repositories.repo-conflict]
      path = "watch_repos/repo-conflict"
      enabled = true
      [repositories.repo-conflict.trigger]
      type = "inactivity"
      period = "1s"
      """
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Changes Are Detected but Commit Fails Due to Conflicts
    Given the monitoring process is running
    # Modify a non-conflicted file to trigger the inactivity timer
    When a file "another_file.txt" is created and saved in "watch_repos/repo-conflict"
    Then the output should eventually contain "[repo-conflict] Change detected: .*another_file.txt"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-conflict] Inactivity trigger fired. Committing..."
    # Git add . might stage the non-conflicted file, but commit will fail
    And the output should eventually contain "[repo-conflict] Error: Git commit failed."
    And the output should contain details indicating unmerged paths or conflicts # Check for Git error output
    And no new commit should exist in the "repo-conflict" Git history
    And the repository "watch_repos/repo-conflict" should remain in a conflicted state
    And the process should continue monitoring "repo-conflict"