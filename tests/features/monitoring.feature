# Feature: Core Repository Monitoring and Actions
#   As a user running the supsrc CLI 'watch' command,
#   I want the tool to monitor configured repositories for file changes,
#   And automatically perform Git actions (commit, push) based on defined triggers,
#   So that my work is saved and synchronized automatically.

@monitoring @core
Feature: Core Repository Monitoring and Actions

  Background: Base Monitoring Setup
    Given a directory structure for monitoring tests
    And a base "supsrc.conf" file for monitoring exists with:
      """
      [global]
      log_level = "DEBUG" # Use DEBUG for testing visibility
      default_commit_message = "supsrc auto: {{timestamp}} [{{trigger_type}}]"
      default_auto_push = false

      [repositories]
      # Repo A: Inactivity trigger, no auto-push
      [repositories.repo-a]
      path = "watch_repos/repo-a"
      enabled = true
      [repositories.repo-a.trigger]
      type = "inactivity"
      period = "1s" # Short period for testing

      # Repo B: Save count trigger, with auto-push
      [repositories.repo-b]
      path = "watch_repos/repo-b"
      enabled = true
      auto_push = true
      commit_message = "Repo-B save sync: {{save_count}} saves"
      [repositories.repo-b.trigger]
      type = "save_count"
      count = 2 # Commit after 2 saves

      # Repo C: Manual trigger
      [repositories.repo-c]
      path = "watch_repos/repo-c"
      enabled = true
      [repositories.repo-c.trigger]
      type = "manual"

      # Repo D: Configured but disabled
      [repositories.repo-d]
      path = "watch_repos/repo-d"
      enabled = false
      [repositories.repo-d.trigger]
      type = "inactivity"
      period = "1m"
      """
    And a clean Git repository exists at "watch_repos/repo-a"
    And a clean Git repository exists at "watch_repos/repo-b" with a configured mock remote "origin"
    And a clean Git repository exists at "watch_repos/repo-c"
    And a directory exists at "watch_repos/repo-d" (may or may not be git repo)
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Initial Monitoring Status Output
    # Given steps from Background execute
    Then the output should eventually contain "Monitoring repository: repo-a (Trigger: inactivity, Period: 1s, AutoPush: False)"
    And the output should eventually contain "Monitoring repository: repo-b (Trigger: save_count, Count: 2, AutoPush: True)"
    And the output should eventually contain "Monitoring repository: repo-c (Trigger: manual, AutoPush: False)"
    And the output should NOT contain "Monitoring repository: repo-d" # Because it's disabled
    And the process should remain running

  Scenario: Inactivity Trigger Fires Commit (No Push)
    # Given steps from Background execute
    Given the monitoring process is running
    When a file "new_file.txt" is created and saved in "watch_repos/repo-a"
    Then the output should eventually contain "[repo-a] Change detected: .*new_file.txt" # Match event details
    And after "1.5" seconds # Allow slightly more than the 1s period
    Then the output should eventually contain "[repo-a] Inactivity trigger fired. Committing..."
    And the output should eventually contain "[repo-a] Git commit successful. Hash: .*" # Match commit hash output
    And the output should NOT contain "[repo-a] Pushing changes..."
    And a commit should exist in the "repo-a" Git history matching message pattern "supsrc auto: .* \[inactivity]"
    And the "repo-a" Git working directory should be clean

  Scenario: Save Count Trigger Fires Commit and Push
    # Given steps from Background execute
    Given the monitoring process is running
    When a file "file1.txt" is created and saved in "watch_repos/repo-b" # Save 1
    Then the output should eventually contain "[repo-b] Change detected: .*file1.txt (Save 1/2)"
    When a file "file2.txt" is created and saved in "watch_repos/repo-b" # Save 2
    Then the output should eventually contain "[repo-b] Change detected: .*file2.txt (Save 2/2)"
    And the output should eventually contain "[repo-b] Save count trigger fired. Committing..."
    And the output should eventually contain "[repo-b] Git commit successful. Hash: .*"
    And the output should eventually contain "[repo-b] Auto-push enabled. Pushing changes..."
    And the output should eventually contain "[repo-b] Git push successful." # Assuming mock remote works
    And a commit should exist in the "repo-b" Git history matching message "Repo-B save sync: 2 saves"
    And the mock remote "origin" for "repo-b" should have received the commit
    And the "repo-b" Git working directory should be clean

  Scenario: Manual Trigger Detects Change but Does Not Commit
    # Given steps from Background execute
    Given the monitoring process is running
    When a file "manual_change.md" is created and saved in "watch_repos/repo-c"
    Then the output should eventually contain "[repo-c] Change detected: .*manual_change.md"
    And after "2" seconds # Wait long enough to ensure no commit happens
    Then the output should NOT contain "[repo-c] .* trigger fired. Committing..."
    And no new commit should exist in the "repo-c" Git history

  Scenario: Handling Git Commit Failure
    # Given steps from Background execute
    Given the monitoring process is running
    And the next 'git commit' operation in "watch_repos/repo-a" is configured to fail # Test setup magic
    When a file "fail_commit.txt" is created and saved in "watch_repos/repo-a"
    Then the output should eventually contain "[repo-a] Change detected: .*fail_commit.txt"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-a] Inactivity trigger fired. Committing..."
    And the output should eventually contain "[repo-a] Error: Git commit failed." # Generic error
    And the output should contain details about the commit failure # Specific error message if possible
    And the "repo-a" Git working directory should still contain uncommitted changes
    And the process should continue monitoring "repo-a" # Ensure resilience

  Scenario: Handling Git Push Failure
    # Given steps from Background execute
    Given the monitoring process is running
    And the mock remote "origin" for "repo-b" is configured to reject the next push # Test setup magic
    When a file "file_push_fail1.txt" is created and saved in "watch_repos/repo-b" # Save 1
    And a file "file_push_fail2.txt" is created and saved in "watch_repos/repo-b" # Save 2
    Then the output should eventually contain "[repo-b] Save count trigger fired. Committing..."
    And the output should eventually contain "[repo-b] Git commit successful. Hash: .*"
    And the output should eventually contain "[repo-b] Auto-push enabled. Pushing changes..."
    And the output should eventually contain "[repo-b] Error: Git push failed." # Generic error
    And the output should contain details about the push failure # Specific error message if possible
    And a commit should exist in the "repo-b" Git history matching message "Repo-B save sync: 2 saves"
    And the mock remote "origin" for "repo-b" should NOT have received the commit
    And the process should continue monitoring "repo-b" # Ensure resilience

  # Remember to add a step/hook to stop the non-blocking process after each scenario