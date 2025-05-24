# Feature: Basic CLI Interactions
#   As a user of the supsrc CLI,
#   I want basic command-line functionality like help and version information,
#   So that I can understand how to use the tool.

Feature: Basic CLI Interactions

  Scenario: Requesting Help Information
    When the user runs "supsrc --help"
    Then the command should exit successfully
    And the output should contain "Usage: supsrc [OPTIONS] COMMAND [ARGS]..."
    And the output should contain descriptions for options like "--config", "--version", "--help"
    And the output should contain descriptions for commands like "watch", "list-repos", "validate" # Assuming these commands

  Scenario: Requesting Version Information
    When the user runs "supsrc --version"
    Then the command should exit successfully
    And the output should match the pattern "supsrc version \d+\.\d+\.\d+" # Or your specific version format