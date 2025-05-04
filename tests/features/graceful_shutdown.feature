# Feature: Graceful Shutdown
#   As a user running supsrc watch,
#   I want to be able to stop the monitoring process cleanly using Ctrl+C (SIGINT),
#   So that resources are released properly and no data is corrupted.

@cli @lifecycle
Feature: Graceful Shutdown

  Background: Setup Monitoring
    Given a directory structure for monitoring tests
    Given a clean Git repository exists at "watch_repos/repo-shutdown"
    Given a "supsrc.conf" file exists configuring "watch_repos/repo-shutdown"
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Stopping the Watcher with SIGINT (Ctrl+C)
    Given the monitoring process is running
    And the output should eventually contain "Monitoring repository: repo-shutdown"
    When the user sends a SIGINT signal to the running process
    # Check for specific shutdown messages
    Then the output should eventually contain "Received shutdown signal. Cleaning up..." # Or similar message
    And the output should eventually contain "Stopping watcher for repo-shutdown"
    And the output should eventually contain "supsrc exiting."
    And the process should exit gracefully # Check exit code, often 0 or specific signal code
    # Add checks if specific cleanup actions are expected (e.g., removing lock files)