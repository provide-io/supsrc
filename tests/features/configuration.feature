# Feature: Configuration File Handling
#   As a user of the supsrc CLI,
#   I want the application to correctly load, validate, and report on my configuration file,
#   So that I can ensure my monitoring setup is correct and understandable.

@config
Feature: Configuration File Handling

  Background: Base Setup
    Given a directory structure for testing configuration

  Scenario: Loading a Valid Configuration for Watching
    Given a valid "supsrc.conf" file exists with the following content:
      """
      [global]
      log_level = "INFO"
      default_commit_message = "Test commit: {{timestamp}}"
      default_auto_push = false

      [repositories]
      [repositories.proj-a]
      path = "repos/proj-a"
      enabled = true
      [repositories.proj-a.trigger]
      type = "manual"
      """
    And a valid Git repository exists at "repos/proj-a"
    # The 'watch' command implicitly validates the config on startup
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner # Requires test runner magic
    Then the output should eventually contain "Configuration loaded successfully"
    And the output should eventually contain "Monitoring repository: proj-a"
    # Cleanup step would stop the non-blocking process

  Scenario: Validating a Configuration File Explicitly
    Given a valid "supsrc.conf" file exists with the content from "Loading a Valid Configuration"
    When the user runs "supsrc --config supsrc.conf validate"
    Then the command should exit successfully
    And the output should contain "Configuration file 'supsrc.conf' is valid."

  Scenario: Attempting to Load a Non-Existent Configuration File
    When the user runs "supsrc --config non_existent.conf watch"
    Then the command should exit with an error code
    And the error output should contain "Error: Configuration file not found at 'non_existent.conf'"

  Scenario: Attempting to Load an Invalid TOML Configuration File
    Given a file "invalid_toml.conf" exists with the content:
      """
      [global]
      log_level = "INFO"
      default_commit_message = "Missing quote ->
      """
    When the user runs "supsrc --config invalid_toml.conf watch"
    Then the command should exit with an error code
    And the error output should contain "Error: Failed to parse TOML configuration"
    And the error output should indicate a parsing error near "Missing quote"

  Scenario: Attempting to Load a Configuration with Schema Validation Errors
    Given a file "invalid_schema.conf" exists with the content:
      """
      [global]
      log_level = "INFO"

      [repositories]
      [repositories.proj-c]
      # Missing 'path' which is required
      enabled = true
      [repositories.proj-c.trigger]
      type = "inactivity"
      # Missing 'period' for inactivity trigger
      """
    When the user runs "supsrc --config invalid_schema.conf watch"
    Then the command should exit with an error code
    And the error output should contain "Error: Configuration validation failed"
    # Specific error depends on cattrs/validation implementation
    And the error output should indicate that 'path' is missing for repository 'proj-c'
    And the error output should indicate that 'period' is missing for the inactivity trigger in 'proj-c'

  Scenario: Listing Configured Repositories
    Given a valid "supsrc.conf" file exists with the following content:
      """
      [global]
      log_level = "DEBUG"

      [repositories]
      [repositories.proj-alpha]
      path = "~/dev/proj-alpha" # Assuming home expansion works
      enabled = true
      auto_push = true
      [repositories.proj-alpha.trigger]
      type = "inactivity"
      period = "5m"

      [repositories.util-beta]
      path = "/var/libs/util-beta"
      enabled = false # Should still be listed but marked disabled
      [repositories.util-beta.trigger]
      type = "save_count"
      count = 3
      """
    When the user runs "supsrc --config supsrc.conf list-repos"
    Then the command should exit successfully
    And the output should contain "Repository ID: proj-alpha"
    And the output should contain "Path: ~/dev/proj-alpha" # Or the expanded path
    And the output should contain "Status: Enabled"
    And the output should contain "Trigger: inactivity (period: 5m)"
    And the output should contain "Auto-push: True"
    And the output should contain "Repository ID: util-beta"
    And the output should contain "Path: /var/libs/util-beta"
    And the output should contain "Status: Disabled"
    And the output should contain "Trigger: save_count (count: 3)"
    And the output should contain "Auto-push: <default>" # Or the actual default value if printed