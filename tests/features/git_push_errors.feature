# Feature: Handling Git Push Errors
#   As a user whose network or Git remote might be unavailable or reject pushes,
#   I want supsrc to handle push failures gracefully after a successful commit,
#   So that the local commit is preserved and I am informed about the push failure.

@monitoring @git @errors @network
Feature: Handling Git Push Errors

  Background: Setup Git Repo with Auto-Push
    Given a directory structure for monitoring tests
    Given a clean Git repository exists at "watch_repos/repo-push-fail" with a configured mock remote "origin"
    Given a "supsrc.conf" file exists with:
      """
      [repositories.repo-push-fail]
      path = "watch_repos/repo-push-fail"
      enabled = true
      auto_push = true # Ensure push is attempted
      [repositories.repo-push-fail.trigger]
      type = "inactivity"
      period = "1s"
      """
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario Outline: Push Fails After Successful Commit
    Given the monitoring process is running
    And the mock remote "origin" for "repo-push-fail" is configured to fail the next push with "<failure_reason>"
    When a file "push_fail_change.txt" is created and saved in "watch_repos/repo-push-fail"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-push-fail] Inactivity trigger fired. Committing..."
    And the output should eventually contain "[repo-push-fail] Git commit successful. Hash: .*"
    And the output should eventually contain "[repo-push-fail] Auto-push enabled. Pushing changes..."
    And the output should eventually contain "[repo-push-fail] Error: Git push failed."
    And the output should contain details indicating "<expected_error_message_pattern>"
    And a commit should exist locally in the "repo-push-fail" Git history
    And the mock remote "origin" for "repo-push-fail" should NOT have received the commit
    And the process should continue monitoring "repo-push-fail"

    Examples:
      | failure_reason        | expected_error_message_pattern           | notes                      |
      | "Connection refused"  | "Connection refused\|Network is unreachable" | Network connectivity issue |
      | "Authentication failed" | "Authentication failed\|Permission denied" | Credential issue (mocked)  |
      | "Remote rejected"     | "failed to push some refs\|rejected"      | Force push required, etc.  |