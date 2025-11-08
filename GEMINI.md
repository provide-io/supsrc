# Supsrc Project Context for Gemini AI

This document provides comprehensive context for the Gemini AI assistant when working with the `supsrc` project.

## Project Overview

The `supsrc` project is a component within the larger `provide-io` monorepo. It is an automated Git commit/push utility based on filesystem events and rules. Its core purpose is to enable Python developers to create infrastructure-as-code components without dealing with the complexity of the Terraform plugin protocol, leveraging the `pyvider` framework.

## Core Components

The `provide-io` monorepo contains several core components, with `supsrc` being one of them. Other related components include:
*   **`pyvider`**: The main framework for building Terraform providers in Python.
*   **`pyvider-rpcplugin`**: A high-performance, type-safe RPC plugin framework for Python.
*   **`pyvider-cty`**: A Python implementation of Terraform's type system.
*   **`pyvider-hcl`**: A library for parsing and generating HCL (HashiCorp Configuration Language).
*   **`pyvider-telemetry`**: A library for structured logging and telemetry.
*   **`tofusoup`**: A testing and conformance suite for providers.
*   **`flavor`**: An optional packaging system for distributing providers as binaries.
*   **`wrknv`**: A development environment management tool.

## Configuration Files

### `supsrc.toml`

The `supsrc.toml` file is the primary configuration file for `supsrc` projects. It defines:
*   Repository monitoring settings.
*   Rules for triggering actions (e.g., auto-commits).
*   Integration with various engines (e.g., Git).

When starting a new session or analyzing a `supsrc` project, you should be aware of the presence and contents of `supsrc.toml` as it dictates the project's behavior.

## Building and Running

The `supsrc` project can be built and tested using a combination of `hatch`, `setuptools`, `pytest`, and `ruff`. The `scripts` directory contains a number of useful scripts for managing the monorepo.

### Key Commands:
*   `supsrc --help`: Displays the `supsrc` CLI help.
*   `wrknv status`: Checks tool versions.
*   `pytest`: Runs tests.
*   `deactivate`: Exits the development environment.
*   `uv sync`: Activates the development environment.

## Development Conventions

*   **Coding Style**: The code is formatted with `ruff format` and linted with `ruff check`.
*   **Testing**: The projects are tested with `pytest`.
*   **Type Checking**: Type checking is done with `mypy` and `pyre`.
*   **Dependencies**: Dependencies are managed with `uv` and specified in the `pyproject.toml` files.
*   **Virtual Environments**: The projects are developed in virtual environments, which can be managed with `wrknv`.

---
*This document is intended for the Gemini AI assistant.*