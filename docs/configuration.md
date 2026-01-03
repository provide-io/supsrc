# Configuration Guide

This guide provides comprehensive documentation for configuring supsrc through the `supsrc.conf` file and environment variables.

## Configuration File (`supsrc.conf`)

Create a file named `supsrc.conf` (or specify another path using `-c`). Here's a complete example:

```toml
# Example supsrc.conf

# Global settings (can be overridden by environment variables like SUPSRC_LOG_LEVEL)
[global]
log_level = "INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Define repositories to monitor
[repositories]

  # Unique identifier for this repository monitoring task
  [repositories.my-project]
    # Path to the Git repository (use '~' for home directory)
    path = "~/dev/my-project"
    # Set to false to temporarily disable monitoring for this repo
    enabled = true

    # Define the rule that triggers actions
    [repositories.my-project.rule]
      # Trigger after 5 minutes of inactivity
      type = "supsrc.rules.inactivity" # Built-in rule type
      period = "5m" # Format: XhYmZs (e.g., "30s", "10m", "1h5m")

      # --- OR ---
      # Trigger after every 10 save events
      # type = "supsrc.rules.save_count"
      # count = 10

      # --- OR ---
      # Disable automatic triggers (requires external mechanism if actions are needed)
      # type = "supsrc.rules.manual"

    # Configure the repository engine (currently only Git)
    [repositories.my-project.repository]
      type = "supsrc.engines.git" # Must be specified

      # --- Git Engine Specific Options ---
      # Automatically push after successful commit? (Default: false)
      auto_push = true
      # Remote to push to (Default: 'origin')
      remote = "origin"
      # Branch to push (Default: uses the current checked-out branch)
      # branch = "main"
      # Commit message template (Go template syntax)
      # Available placeholders: {{timestamp}}, {{repo_id}}, {{save_count}}, {{change_summary}}
      commit_message_template = "feat: Auto-sync changes at {{timestamp}}\n\n{{change_summary}}"

  [repositories.another-repo]
    path = "/path/to/another/repo"
    enabled = true
    [repositories.another-repo.rule]
      type = "supsrc.rules.inactivity"
      period = "30s"
    [repositories.another-repo.repository]
      type = "supsrc.engines.git"
      auto_push = false # Keep commits local for this one
```

## Environment Variable Overrides

The following environment variables can override configuration settings:

*   `SUPSRC_CONF`: Path to the configuration file.
*   `SUPSRC_LOG_LEVEL`: Sets the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
*   `SUPSRC_LOG_FILE`: Path to write JSON logs to a file.
*   `SUPSRC_JSON_LOGS`: Set to `true`, `1`, `yes`, or `on` to output console logs as JSON.

## LLM Configuration (Optional)

`supsrc` can use Large Language Models (LLMs) to automate tasks like generating commit messages, reviewing changes for obvious errors, and analyzing test failures. This requires the `supsrc[llm]` extra to be installed.

To enable LLM features for a specific repository, add an `[repositories.<repo_id>.llm]` section to your `supsrc.conf`.

```toml
# In your supsrc.conf file...

[repositories.my-llm-project]
  path = "~/dev/my-llm-project"
  enabled = true
  [repositories.my-llm-project.rule]
    type = "supsrc.rules.inactivity"
    period = "2m"
  [repositories.my-llm-project.repository]
    type = "supsrc.engines.git"
    auto_push = true

  # --- LLM Configuration Section ---
  [repositories.my-llm-project.llm]
    # Enable LLM features for this repo
    enabled = true

    # --- Provider Setup ---
    # Choose your LLM provider: "gemini" or "ollama"
    provider = "gemini"
    # Specify the model to use
    model = "gemini-1.5-flash" # For Gemini
    # model = "llama3" # Example for Ollama

    # (For Gemini) Specify the environment variable containing your API key
    api_key_env_var = "GEMINI_API_KEY"

    # --- Feature Flags ---
    # Automatically generate the commit message subject line
    generate_commit_message = true
    # Use Conventional Commits format for the generated message
    use_conventional_commit = true
    # Perform a quick review of changes and veto the commit on critical issues (e.g., secrets)
    review_changes = true
    # Run a test command before committing
    run_tests = true
    # If tests fail, use the LLM to analyze the failure output
    analyze_test_failures = true

    # --- Additional Settings ---
    # Specify the command to run for tests. If not set, supsrc tries to infer it.
    test_command = "pytest"
```

### LLM Provider Details

#### Gemini (`provider = "gemini"`)

*   Uses the Google Gemini API.
*   Requires an API key. By default, it looks for the key in the `GEMINI_API_KEY` environment variable. You can change the variable name with `api_key_env_var`.
*   **Setup:**
    1.  Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
    2.  Set the environment variable: `export GEMINI_API_KEY="your-api-key-here"`

#### Ollama (`provider = "ollama"`)

*   Connects to a local [Ollama](https://ollama.ai/) instance.
*   Does not require an API key.
*   **Setup:**
    1.  Install and run Ollama on your machine.
    2.  Pull a model you want to use, e.g., `ollama pull llama3`.
    3.  Set `provider = "ollama"` and `model = "llama3"` (or your chosen model) in the config.

## Rules Explained

The `[repositories.*.rule]` section defines when `supsrc` should trigger its actions (stage, commit, push).

### Inactivity Rule

**Type:** `supsrc.rules.inactivity`

Triggers when no filesystem changes have been detected in the repository for the duration specified by `period`.

**Configuration:**
```toml
[repositories.my-repo.rule]
  type = "supsrc.rules.inactivity"
  period = "5m"  # Duration: XhYmZs format (e.g., "30s", "5m", "1h")
```

**Examples:**
- `"30s"` - 30 seconds
- `"5m"` - 5 minutes
- `"1h5m"` - 1 hour and 5 minutes

### Save Count Rule

**Type:** `supsrc.rules.save_count`

Triggers when the number of detected save events reaches the specified `count`. The count resets after a successful action sequence.

**Configuration:**
```toml
[repositories.my-repo.rule]
  type = "supsrc.rules.save_count"
  count = 10  # Positive integer
```

**Use Cases:**
- Checkpoint every N file modifications
- Create commits at specific intervals of work

### Manual Rule

**Type:** `supsrc.rules.manual`

Disables automatic triggering by `supsrc`. Actions would need to be initiated externally if this rule is used (primarily for testing or advanced scenarios).

**Configuration:**
```toml
[repositories.my-repo.rule]
  type = "supsrc.rules.manual"
```

## Engines

`supsrc` uses engines to interact with different types of repositories.

### Git Engine

**Type:** `supsrc.engines.git`

The primary engine for interacting with Git repositories.

**Features:**
*   Uses the `pygit2` library
*   Supports status checks
*   Staging (respecting `.gitignore`)
*   Committing
*   Pushing

**Configuration Options:**

```toml
[repositories.my-repo.repository]
  type = "supsrc.engines.git"

  # Automatically push after successful commit (default: false)
  auto_push = true

  # Remote to push to (default: 'origin')
  remote = "origin"

  # Branch to push (default: current checked-out branch)
  branch = "main"

  # Commit message template (Go template syntax)
  # Available placeholders: {{timestamp}}, {{repo_id}}, {{save_count}}, {{change_summary}}
  commit_message_template = "feat: Auto-sync changes at {{timestamp}}\n\n{{change_summary}}"
```

### Git Engine Authentication

The Git engine currently supports:

#### 1. SSH Agent

For SSH-based remote URLs (e.g., `git@github.com:...`):
- `supsrc` will attempt to use `pygit2.KeypairFromAgent` to authenticate via a running SSH agent
- Ensure your agent is running and the correct key is loaded

**Setup:**
```bash
# Start SSH agent
eval "$(ssh-agent -s)"

# Add your SSH key
ssh-add ~/.ssh/id_rsa
```

#### 2. HTTPS (Environment Variables)

For HTTPS URLs (e.g., `https://github.com/...`):
- `supsrc` will look for the following environment variables:
    *   `GIT_USERNAME`: Your Git username.
    *   `GIT_PASSWORD`: Your Git password **or preferably a Personal Access Token (PAT)**.

**Setup:**
```bash
export GIT_USERNAME="your-username"
export GIT_PASSWORD="your-token-or-password"
```

> **Security Note:** Storing credentials directly is generally discouraged. Using an SSH agent or short-lived tokens is recommended.

## Textual TUI (Optional)

If installed (`uv tool install 'supsrc[tui]'`) and run with `supsrc sui`, a terminal user interface provides:

*   A live-updating table showing the status, last change time, save count, and errors for each monitored repository.
*   A scrolling log view displaying messages from `supsrc`.

**Running the TUI:**
```bash
# Interactive dashboard
supsrc sui

# With custom config
supsrc sui -c /path/to/config.toml
```

**TUI Features:**
- Real-time repository status
- Live log streaming
- Save count tracking
- Error notifications
- Keyboard navigation

## Configuration Validation

Validate and display your configuration:

```bash
# Show current configuration
supsrc config show

# Show configuration from specific file
supsrc config show -c path/to/config.toml
```

This command displays:
- Loaded configuration values
- Environment variable overrides
- Repository monitoring settings
- Rule configurations
- Engine settings

## Best Practices

1. **Start with simple rules**: Use inactivity rules with reasonable periods (e.g., 5-10 minutes)
2. **Test auto_push carefully**: Consider starting with `auto_push = false` until you're confident
3. **Use descriptive repo_ids**: Name repositories clearly in the configuration
4. **Leverage commit templates**: Customize commit messages with placeholders
5. **Monitor logs**: Use DEBUG level logging during setup to troubleshoot
6. **Secure credentials**: Prefer SSH agent over environment variables for authentication
7. **Use .gitignore**: Ensure your repositories have proper `.gitignore` files to avoid committing unwanted files
