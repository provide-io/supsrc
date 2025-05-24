# Feature: Configuration Defaults and Overrides
#   As a user configuring supsrc,
#   I want global defaults to apply unless specifically overridden in a repository's config,
#   So that I can maintain consistency while allowing specific exceptions.

@config
Feature: Configuration Defaults and Overrides

  Background: Base Setup
    Given a directory structure for testing configuration
    Given a clean Git repository exists at "repos/proj-defaults"
    Given a file "defaults.conf" exists with:
      """
      [global]
      log_level = "INFO"
      default_commit_message = "Global Commit Default"
      default_auto_push = true # Global default is TRUE

      [repositories]
      [repositories.repo-using-defaults]
      path = "repos/proj-defaults"
      enabled = true
      [repositories.repo-using-defaults.trigger]
      type = "inactivity"
      period = "1s"
      # Implicitly uses global message and auto_push = true

      [repositories.repo-override-push]
      path = "repos/proj-defaults"
      enabled = true
      auto_push = false # Override auto_push
      [repositories.repo-override-push.trigger]
      type = "inactivity"
      period = "1s"
      # Implicitly uses global message

      [repositories.repo-override-message]
      path = "repos/proj-defaults"
      enabled = true
      commit_message = "Specific Message" # Override message
      [repositories.repo-override-message.trigger]
      type = "inactivity"
      period = "1s"
      # Implicitly uses global auto_push = true
      """

  Scenario: Repository Inherits Global Auto-Push and Commit Message
    Given a valid "supsrc.conf" reusing "[repositories.repo-using-defaults]" from "defaults.conf"
    And the mock remote "origin" for "repo-using-defaults" is configured
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner
    And a file "change1.txt" is created and saved in "repos/proj-defaults"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-using-defaults] Git commit successful"
    And the output should eventually contain "[repo-using-defaults] Auto-push enabled. Pushing changes..." # Because global default is true
    And a commit should exist in the "repo-using-defaults" Git history with message "Global Commit Default"

  Scenario: Repository Overrides Global Auto-Push (to False)
    Given a valid "supsrc.conf" reusing "[repositories.repo-override-push]" from "defaults.conf"
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner
    And a file "change2.txt" is created and saved in "repos/proj-defaults"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-override-push] Git commit successful"
    And the output should NOT contain "[repo-override-push] Auto-push enabled. Pushing changes..." # Because override is false
    And a commit should exist in the "repo-override-push" Git history with message "Global Commit Default"

  Scenario: Repository Overrides Global Commit Message
    Given a valid "supsrc.conf" reusing "[repositories.repo-override-message]" from "defaults.conf"
    And the mock remote "origin" for "repo-override-message" is configured
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner
    And a file "change3.txt" is created and saved in "repos/proj-defaults"
    And after "1.5" seconds
    Then the output should eventually contain "[repo-override-message] Git commit successful"
    And the output should eventually contain "[repo-override-message] Auto-push enabled. Pushing changes..." # Because global default is true
    And a commit should exist in the "repo-override-message" Git history with message "Specific Message"