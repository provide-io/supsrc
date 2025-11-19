#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Circuit breaker management commands for supsrc."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from provide.foundation.cli.decorators import logging_options
from provide.foundation.logger import get_logger
from structlog.typing import FilteringBoundLogger as StructLogger

from supsrc.config import load_config
from supsrc.state.file import StateFile
from supsrc.state.runtime import RepositoryStatus

log: StructLogger = get_logger(__name__)


@click.group(name="cb")
def circuit_breaker_cli():
    """Circuit breaker management commands."""


@circuit_breaker_cli.command(name="ack")
@click.argument("repo_id")
@click.option(
    "-c",
    "--config-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@logging_options
@click.pass_context
def acknowledge_circuit_breaker(
    ctx: click.Context,
    repo_id: str,
    config_path: Path,
    **kwargs,
):
    """Acknowledge and reset a triggered circuit breaker for a repository.

    REPO_ID: The repository identifier to acknowledge

    Example:
        supsrc cb ack my-repo
    """
    try:
        # Load configuration
        config = load_config(config_path)

        # Find repository config
        repo_config = None
        for repo in config.repositories:
            if repo.repo_id == repo_id:
                repo_config = repo
                break

        if not repo_config:
            click.echo(f"❌ Error: Repository '{repo_id}' not found in configuration", err=True)
            sys.exit(1)

        # Load state file
        state_file = StateFile(config.state_file_path)
        repo_state = state_file.load_repository_state(repo_id)

        if not repo_state:
            click.echo(f"⚠️  Warning: No state found for repository '{repo_id}'")
            click.echo("   (Circuit breaker may not be triggered)")
            sys.exit(0)

        # Check if circuit breaker is triggered
        if not repo_state.circuit_breaker_triggered:
            click.echo(f"✅ Repository '{repo_id}' circuit breaker is not triggered")
            sys.exit(0)

        # Display current state
        status_emoji = repo_state.display_status_emoji
        click.echo(f"\n{status_emoji} Circuit Breaker Status for '{repo_id}':")
        click.echo(f"   Status: {repo_state.status.name}")
        click.echo(f"   Reason: {repo_state.circuit_breaker_reason}")
        click.echo(f"   Files in window: {len(repo_state.bulk_change_files)}")

        # Reset circuit breaker
        repo_state.reset_circuit_breaker()
        repo_state.update_status(RepositoryStatus.IDLE)

        # Save state
        state_file.save_repository_state(repo_state)

        click.echo(f"\n✅ Circuit breaker acknowledged and reset for '{repo_id}'")
        click.echo("   Monitoring will resume on next file change")

    except FileNotFoundError as e:
        click.echo(f"❌ Error: Configuration file not found: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        log.exception("Failed to acknowledge circuit breaker", repo_id=repo_id)
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@circuit_breaker_cli.command(name="status")
@click.option(
    "-c",
    "--config-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
    default=Path("supsrc.conf"),
    show_default=True,
    envvar="SUPSRC_CONF",
    help="Path to the supsrc configuration file (env var SUPSRC_CONF).",
    show_envvar=True,
)
@logging_options
@click.pass_context
def circuit_breaker_status(ctx: click.Context, config_path: Path, **kwargs):
    """Show circuit breaker status for all repositories."""
    try:
        # Load configuration
        config = load_config(config_path)

        # Load state file
        state_file = StateFile(config.state_file_path)

        click.echo("\n🛡️  Circuit Breaker Status\n")

        any_triggered = False
        for repo in config.repositories:
            repo_state = state_file.load_repository_state(repo.repo_id)

            if not repo_state:
                continue

            if repo_state.circuit_breaker_triggered:
                any_triggered = True
                status_emoji = repo_state.display_status_emoji
                click.echo(f"{status_emoji} {repo.repo_id}:")
                click.echo(f"   Status: {repo_state.status.name}")
                click.echo(f"   Reason: {repo_state.circuit_breaker_reason}")
                click.echo(f"   Files: {len(repo_state.bulk_change_files)}")
                click.echo(f"   Action: supsrc cb ack {repo.repo_id}\n")

        if not any_triggered:
            click.echo("✅ No circuit breakers triggered\n")

    except FileNotFoundError as e:
        click.echo(f"❌ Error: Configuration file not found: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        log.exception("Failed to get circuit breaker status")
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


# 🔼⚙️🔚
