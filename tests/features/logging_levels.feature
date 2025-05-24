# Feature: Logging Verbosity and Levels
#   As a user running supsrc,
#   I want to control the logging verbosity via the configuration file,
#   So that I can see appropriate levels of detail for debugging or normal operation.

@config @logging
Feature: Logging Verbosity and Levels

  Background: Setup Basic Repo
    Given a directory structure for testing configuration
    Given a clean Git repository exists at "repos/proj-log"

  Scenario Outline: Different Log Levels Affect Output Detail
    Given a "supsrc.conf" file exists with:
      """
      [global]
      log_level = "<log_level>" # Set the level for this scenario

      [repositories.repo-log]
      path = "repos/proj-log"
      enabled = true
      [repositories.repo-log.trigger]
      type = "inactivity"
      period = "1s"
      """
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner
    And a file "log_change.txt" is created and saved in "repos/proj-log"
    And after "1.5" seconds # Allow commit to happen

    # Check for presence/absence of messages based on level
    Then the output "<debug_presence>" contain "DEBUG.*Initializing watcher for repo-log" # Example DEBUG message
    And the output should contain "INFO.*Monitoring repository: repo-log" # Example INFO message
    And the output should contain "INFO.*\[repo-log] Change detected: .*log_change.txt" # Example INFO message
    And the output should contain "INFO.*\[repo-log] Inactivity trigger fired. Committing..." # Example INFO message
    And the output should contain "INFO.*\[repo-log] Git commit successful" # Example INFO message

    # Simulate an error condition if needed to test WARNING/ERROR logs
    # Given the next 'git commit' operation in "repos/proj-log" is configured to fail
    # When ... trigger commit ...
    # Then the output "<error_presence>" contain "ERROR.*\[repo-log] Error: Git commit failed."

    Examples:
      | log_level | debug_presence | error_presence | notes                           |
      | DEBUG     | should         | should         | Shows DEBUG, INFO, ERROR        |
      | INFO      | should not     | should         | Shows INFO, ERROR (no DEBUG)    |
      | WARNING   | should not     | should         | Shows WARNING, ERROR (not INFO) | # Assuming commit failure is ERROR
      | ERROR     | should not     | should         | Shows only ERROR                |

  # Cleanup step to stop the non-blocking process