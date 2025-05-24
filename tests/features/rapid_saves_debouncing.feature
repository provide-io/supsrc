# Feature: Handling Rapid File Saves (Debouncing)
#   As a user saving files frequently (e.g., IDE auto-save),
#   I want supsrc to debounce these rapid changes for inactivity triggers,
#   So that only one commit occurs after a period of actual inactivity, not one per save.

@monitoring @timing
Feature: Handling Rapid File Saves (Debouncing)

  Background: Setup Git Repo with Inactivity Trigger
    Given a directory structure for monitoring tests
    Given a clean Git repository exists at "watch_repos/repo-debounce"
    Given a "supsrc.conf" file exists with:
      """
      [repositories.repo-debounce]
      path = "watch_repos/repo-debounce"
      enabled = true
      [repositories.repo-debounce.trigger]
      type = "inactivity"
      # Use a slightly longer period to observe debouncing
      period = "2s"
      """
    # Requires time mocking capabilities (e.g., freezegun)
    Given time is frozen at "2024-05-01 12:00:00"
    When the user runs "supsrc --config supsrc.conf watch" in a non-blocking manner

  Scenario: Multiple Saves Within Inactivity Period Result in One Commit
    Given the monitoring process is running
    When time advances by "0.1" seconds # 12:00:00.1
    And a file "rapid_save.txt" is created and saved in "watch_repos/repo-debounce"
    Then the output should eventually contain "[repo-debounce] Change detected: .*rapid_save.txt"
    # Timer should start for 2s, ending at 12:00:02.1

    When time advances by "1.0" seconds # 12:00:01.1 (within the 2s window)
    And the file "rapid_save.txt" is modified and saved again in "watch_repos/repo-debounce"
    Then the output should eventually contain "[repo-debounce] Change detected: .*rapid_save.txt"
    # Timer should reset for 2s, now ending at 12:00:03.1

    When time advances by "1.0" seconds # 12:00:02.1 (still within the new 2s window)
    And the file "rapid_save.txt" is modified and saved again in "watch_repos/repo-debounce"
    Then the output should eventually contain "[repo-debounce] Change detected: .*rapid_save.txt"
    # Timer should reset again for 2s, now ending at 12:00:04.1

    # Now let time pass beyond the last timer reset + period
    When time advances by "2.5" seconds # 12:00:04.6 (past the 12:00:04.1 trigger time)
    Then the output should eventually contain "[repo-debounce] Inactivity trigger fired. Committing..."
    And the output should eventually contain "[repo-debounce] Git commit successful"
    # Crucially, verify only *one* commit happened despite multiple saves
    And exactly "1" new commit should exist in the "repo-debounce" Git history