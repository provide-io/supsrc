# Feature: Handling Large Number of Repositories
#   As a user monitoring many projects,
#   I want supsrc to handle a configuration file with a large number of repositories efficiently,
#   So that startup time is reasonable and monitoring remains responsive.

@config @performance
Feature: Handling Large Number of Repositories

  Background: Setup Many Repos
    Given a directory structure for performance testing
    # Create a large number of mock repositories (e.g., 50-100)
    # This setup might be slow and should perhaps be tagged for optional runs
    Given "100" mock Git repositories exist under "many_repos/repo_" prefix
    # Generate a large config file programmatically
    Given a "large_config.conf" file is generated monitoring all "100" repositories under "many_repos/" with manual triggers

  Scenario: Loading and Validating a Large Configuration
    # Measure startup time indirectly or focus on success/failure
    When the user runs "supsrc --config large_config.conf validate"
    Then the command should exit successfully within "10" seconds # Set a reasonable timeout
    And the output should contain "Configuration file 'large_config.conf' is valid."

  Scenario: Starting Monitoring for Many Repositories
    When the user runs "supsrc --config large_config.conf watch" in a non-blocking manner
    # Check that monitoring starts for all enabled repos without excessive delay
    Then the output should eventually contain "Monitoring repository: repo_0" # Check first
    And the output should eventually contain "Monitoring repository: repo_99" # Check last
    And the process should remain running
    # Optionally, add checks for resource usage if feasible in testing framework
    # Cleanup step to stop the non-blocking process