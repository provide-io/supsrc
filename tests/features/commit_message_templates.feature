# Feature: Commit Message Template Handling
#   As a user configuring supsrc,
#   I want to define custom commit message templates with placeholders,
#   So that my automated commits have meaningful and context-rich messages.

@config @commit
Feature: Commit Message Template Handling

  Background: Base Setup
    Given a directory structure for testing configuration
    Given a clean Git repository exists at "repos/proj-msg"
    Given a file "base_config_msg.conf" exists with:
      """
      [global]
      log_level = "INFO"
      default_commit_message = "Global default: {{timestamp}}"
      default_auto_push = false

      [repositories]
      [repositories.repo-defaults]
      path = "repos/proj-msg"
      enabled = true
      [repositories.repo-defaults.trigger]
      type = "inactivity"
      period = "1s"

      [repositories.repo-custom]
      path = "repos/proj-msg" # Can reuse repo for testing different configs
      enabled = true
      commit_message = "Custom: {{trigger_type}} at {{timestamp}} saves={{save_count}} host={{hostname}}"
      [repositories.repo-custom.trigger]
      type = "save_count"
      count = 1
      """

  Scenario: Commit using Global Default Template (Inactivity Trigger)
    Given a valid "supsrc.conf" reusing "[repositories.repo-defaults]" from "base_config_msg.conf"
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner
    And a file "change_default.txt" is created and saved in "repos/proj-msg"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-defaults] Git commit successful"
    And a commit should exist in the "repo-defaults" Git history matching message pattern "Global default: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*"

  Scenario: Commit using Custom Repo-Specific Template (Save Count Trigger)
    Given a valid "supsrc.conf" reusing "[repositories.repo-custom]" from "base_config_msg.conf"
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner
    And a file "change_custom.txt" is created and saved in "repos/proj-msg" # Save 1
    Then the output should eventually contain "[repo-custom] Git commit successful"
    And a commit should exist in the "repo-custom" Git history matching message pattern "Custom: save_count at .* saves=1 host=.*"
    # Note: {{hostname}} requires mocking/injection in tests

  Scenario: Using Non-Existent Placeholder in Template (Should likely default or warn)
    Given a valid "supsrc.conf" with a repository configured with commit_message = "Bad: {{non_existent_placeholder}}"
    And trigger type "inactivity" with period "1s"
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner
    And a file "change_bad_placeholder.txt" is created and saved in the repo
    And after "1.5" seconds
    Then the output should eventually contain "Git commit successful"
    # Behavior depends on implementation: could be literal, empty string, or raise warning/error earlier
    And a commit should exist in the repo history with message "Bad: {{non_existent_placeholder}}" # Or adjusted based on chosen behavior
    # And the output should contain a warning about the unknown placeholder "non_existent_placeholder" (optional but good UX)