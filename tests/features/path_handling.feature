# Feature: Path Handling and Validation
#   As a user configuring supsrc,
#   I want the application to correctly interpret various path formats (tilde, relative, absolute) and validate their existence,
#   So that monitoring targets the correct directories.

@config @paths
Feature: Path Handling and Validation

  Background: Test Environment Setup
    Given a directory structure for path testing
    Given a directory exists at "~/supsrc_test_home/real_repo" # Simulating home dir expansion
    And a Git repository exists at "~/supsrc_test_home/real_repo"
    Given the current working directory is "/test_cwd"
    Given a directory exists at "/test_cwd/relative_repo"
    And a Git repository exists at "/test_cwd/relative_repo"
    Given a directory exists at "/absolute/path/repo"
    And a Git repository exists at "/absolute/path/repo"

  Scenario Outline: Loading Configuration with Different Valid Path Types
    Given a "supsrc.conf" file exists with content:
      """
      [repositories.test-repo]
      path = "<path_value>"
      enabled = true
      [repositories.test-repo.trigger]
      type = "manual"
      """
    When the user runs "supsrc --config supsrc.conf list-repos"
    Then the command should exit successfully
    And the output should contain "Repository ID: test-repo"
    And the output should contain "Path: <expected_expanded_path>"
    And the output should contain "Status: Enabled"

    Examples:
      | path_value               | expected_expanded_path          | notes                       |
      | ~/supsrc_test_home/real_repo | /REDACTED_ABS_PATH | Tilde expansion (mocked)    |
      | relative_repo            | /test_cwd/relative_repo         | Relative to CWD             |
      | /absolute/path/repo      | /absolute/path/repo             | Absolute path               |
      # | ../relative_repo_parent | /relative_repo_parent         | Relative parent (if exists) | # Add more complex relative paths if needed

  Scenario: Configuration Fails if Path Does Not Exist
    Given a "supsrc.conf" file exists with content:
      """
      [repositories.non-existent]
      path = "/path/that/does/not/exist"
      enabled = true
      [repositories.non-existent.trigger]
      type = "manual"
      """
    When the user runs "supsrc --config supsrc.conf validate" # Or 'watch'
    Then the command should exit with an error code
    And the error output should contain "Error: Configuration validation failed"
    And the error output should contain "Path does not exist or is not accessible: /path/that/does/not/exist" # Specific error message

  Scenario: Configuration Fails if Path is a File, Not a Directory
    Given a file exists at "/path/to/a_file.txt"
    Given a "supsrc.conf" file exists with content:
      """
      [repositories.path-is-file]
      path = "/path/to/a_file.txt"
      enabled = true
      [repositories.path-is-file.trigger]
      type = "manual"
      """
    When the user runs "supsrc --config supsrc.conf validate" # Or 'watch'
    Then the command should exit with an error code
    And the error output should contain "Error: Configuration validation failed"
    And the error output should contain "Path is not a directory: /path/to/a_file.txt" # Specific error message

  # Optional: Add scenario for permissions error if path exists but isn't readable/watchable