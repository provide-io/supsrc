# File Quality Tools Integration Plan for supsrc

## Overview

This document outlines how supsrc can integrate `provide.foundation.file.quality` tools to measure and monitor the accuracy and performance of file operation detection.

## Current State

**What supsrc has:**
- ✅ Uses `OperationDetector` via `StreamingOperationHandler` (streaming.py:18)
- ✅ Has integration tests for VSCode atomic save pattern (test_vscode_atomic_save.py)
- ✅ Tests verify correctness (final file shown, not temp file)
- ❌ **No quality metrics** (accuracy, precision, recall, false positive/negative rates)

## Integration Approach: Add Quality Testing

### Option 1: Integration Tests with Quality Metrics (RECOMMENDED)

Add a new test file that measures detection quality for real-world patterns.

#### Example Test: `tests/integration/test_operation_detection_quality.py`

```python
"""Quality analysis tests for file operation detection in supsrc.

This module tests the accuracy and reliability of operation detection
for common editor patterns (VSCode, Vim, etc.) using Foundation's
quality analysis tools.
"""

from __future__ import annotations

import pytest
from provide.foundation.file.quality import (
    QualityAnalyzer,
    AnalysisMetric,
    OperationScenario,
    create_scenarios_from_patterns,
)
from provide.foundation.file.operations import DetectorConfig

from supsrc.events.buffer.streaming import StreamingOperationHandler


class TestOperationDetectionQuality:
    """Test the quality of operation detection in supsrc's event handling."""

    def test_vscode_atomic_save_detection_quality(self):
        """Test VSCode atomic save detection quality using standard scenarios."""
        # Create analyzer with supsrc's detector config
        detector_config = DetectorConfig(
            time_window_ms=500,
            min_confidence=0.7,
            temp_patterns=[
                r"\..*\.tmp\.\d+$",  # VSCode pattern
                r"~$",                # Backup files
                r"\.swp$",            # Vim swap
            ],
        )

        analyzer = QualityAnalyzer(
            detector=None  # Will use default, or pass custom detector
        )

        # Add standard scenarios (VSCode, Vim, batch operations)
        scenarios = create_scenarios_from_patterns()
        for scenario in scenarios:
            analyzer.add_scenario(scenario)

        # Run comprehensive analysis
        results = analyzer.run_analysis([
            AnalysisMetric.ACCURACY,
            AnalysisMetric.PRECISION,
            AnalysisMetric.RECALL,
            AnalysisMetric.F1_SCORE,
            AnalysisMetric.FALSE_POSITIVE_RATE,
            AnalysisMetric.FALSE_NEGATIVE_RATE,
            AnalysisMetric.DETECTION_TIME,
        ])

        # Assert quality thresholds
        assert results[AnalysisMetric.ACCURACY].value >= 0.95, \
            f"Detection accuracy below threshold: {results[AnalysisMetric.ACCURACY].value}"

        assert results[AnalysisMetric.PRECISION].value >= 0.90, \
            f"Precision too low: {results[AnalysisMetric.PRECISION].value}"

        assert results[AnalysisMetric.RECALL].value >= 0.90, \
            f"Recall too low: {results[AnalysisMetric.RECALL].value}"

        assert results[AnalysisMetric.FALSE_POSITIVE_RATE].value <= 0.05, \
            f"False positive rate too high: {results[AnalysisMetric.FALSE_POSITIVE_RATE].value}"

        # Generate and log report
        report = analyzer.generate_report(results)
        print("\n" + "=" * 80)
        print("OPERATION DETECTION QUALITY REPORT")
        print("=" * 80)
        print(report)

    def test_supsrc_custom_scenarios_quality(self):
        """Test detection quality with supsrc-specific scenarios."""
        analyzer = QualityAnalyzer()

        # Add custom supsrc scenario
        from provide.foundation.file.operations import FileEvent, FileEventType
        from pathlib import Path

        # Scenario: Multiple files saved in quick succession (batch operation)
        batch_scenario = OperationScenario(
            name="supsrc_batch_edit",
            description="Multiple Python files edited in quick succession",
            tags=["batch", "python", "supsrc"],
            events=[
                FileEvent(
                    path=Path("src/supsrc/runtime/orchestrator.py"),
                    event_type=FileEventType.MODIFIED,
                    timestamp=1000.0,
                    sequence=1,
                ),
                FileEvent(
                    path=Path("src/supsrc/events/processor.py"),
                    event_type=FileEventType.MODIFIED,
                    timestamp=1050.0,  # 50ms later
                    sequence=2,
                ),
                FileEvent(
                    path=Path("src/supsrc/config/models.py"),
                    event_type=FileEventType.MODIFIED,
                    timestamp=1100.0,  # Another 50ms
                    sequence=3,
                ),
            ],
            expected_operations=[
                {
                    "type": "batch_update",
                    "files": [
                        "src/supsrc/runtime/orchestrator.py",
                        "src/supsrc/events/processor.py",
                        "src/supsrc/config/models.py",
                    ],
                }
            ],
        )

        analyzer.add_scenario(batch_scenario)

        # Add standard scenarios too
        for scenario in create_scenarios_from_patterns():
            analyzer.add_scenario(scenario)

        # Run analysis
        results = analyzer.run_analysis([
            AnalysisMetric.ACCURACY,
            AnalysisMetric.F1_SCORE,
            AnalysisMetric.DETECTION_TIME,
        ])

        # Verify detection time is reasonable for real-time use
        detection_time_result = results[AnalysisMetric.DETECTION_TIME]
        avg_time_ms = detection_time_result.details["average_ms"]
        p95_time_ms = detection_time_result.details["p95_ms"]

        assert avg_time_ms < 10.0, \
            f"Average detection time too slow: {avg_time_ms}ms"

        assert p95_time_ms < 50.0, \
            f"P95 detection time too slow: {p95_time_ms}ms"

        print(f"\nPerformance metrics:")
        print(f"  Average detection time: {avg_time_ms:.2f}ms")
        print(f"  P95 detection time: {p95_time_ms:.2f}ms")

    @pytest.mark.benchmark
    def test_detection_performance_under_load(self):
        """Benchmark detection quality under high event load."""
        analyzer = QualityAnalyzer()

        # Create 100 scenarios (stress test)
        for i in range(100):
            scenario = OperationScenario(
                name=f"stress_test_{i}",
                description=f"Stress test scenario {i}",
                tags=["stress", "benchmark"],
                events=[
                    FileEvent(
                        path=Path(f"file_{i}.py"),
                        event_type=FileEventType.MODIFIED,
                        timestamp=1000.0 + (i * 10),
                        sequence=i,
                    )
                ],
                expected_operations=[
                    {"type": "simple_edit", "file": f"file_{i}.py"}
                ],
            )
            analyzer.add_scenario(scenario)

        # Measure quality under load
        results = analyzer.run_analysis([
            AnalysisMetric.DETECTION_TIME,
            AnalysisMetric.ACCURACY,
        ])

        # Performance should scale linearly, not degrade
        avg_time = results[AnalysisMetric.DETECTION_TIME].details["average_ms"]
        assert avg_time < 20.0, f"Detection degraded under load: {avg_time}ms"
```

---

### Option 2: CLI Command for Quality Reporting (NICE TO HAVE)

Add a quality analysis command to supsrc's CLI.

#### `src/supsrc/cli/quality_cmds.py`

```python
"""Quality analysis commands for operation detection."""

import click
from provide.foundation.file.quality import (
    QualityAnalyzer,
    AnalysisMetric,
    create_scenarios_from_patterns,
)
from provide.foundation.logger import get_logger

log = get_logger("cli.quality")


@click.group(name="quality")
def quality_group():
    """Analyze operation detection quality."""
    pass


@quality_group.command(name="analyze")
@click.option(
    "--metrics",
    "-m",
    multiple=True,
    type=click.Choice([
        "accuracy",
        "precision",
        "recall",
        "f1",
        "confidence",
        "time",
        "fpr",
        "fnr",
    ]),
    default=["accuracy", "precision", "recall", "f1"],
    help="Metrics to analyze (can specify multiple)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    help="Output format",
)
def analyze_quality(metrics: tuple[str, ...], format: str):
    """Analyze file operation detection quality.

    Runs quality analysis on standard editor patterns (VSCode, Vim, etc.)
    and reports detection accuracy metrics.

    Example:
        supsrc quality analyze --metrics accuracy --metrics precision
        supsrc quality analyze --format json
    """
    click.echo("Analyzing operation detection quality...")

    # Create analyzer
    analyzer = QualityAnalyzer()

    # Add standard scenarios
    scenarios = create_scenarios_from_patterns()
    for scenario in scenarios:
        analyzer.add_scenario(scenario)

    click.echo(f"Loaded {len(scenarios)} test scenarios")

    # Map CLI metrics to enum
    metric_map = {
        "accuracy": AnalysisMetric.ACCURACY,
        "precision": AnalysisMetric.PRECISION,
        "recall": AnalysisMetric.RECALL,
        "f1": AnalysisMetric.F1_SCORE,
        "confidence": AnalysisMetric.CONFIDENCE_DISTRIBUTION,
        "time": AnalysisMetric.DETECTION_TIME,
        "fpr": AnalysisMetric.FALSE_POSITIVE_RATE,
        "fnr": AnalysisMetric.FALSE_NEGATIVE_RATE,
    }

    analysis_metrics = [metric_map[m] for m in metrics]

    # Run analysis
    click.echo("Running analysis...")
    results = analyzer.run_analysis(analysis_metrics)

    # Generate report
    if format == "json":
        import json
        output = {
            metric.name: {
                "value": result.value,
                "details": result.details,
            }
            for metric, result in results.items()
        }
        click.echo(json.dumps(output, indent=2))
    elif format == "markdown":
        report = analyzer.generate_report(results)
        click.echo(f"```\n{report}\n```")
    else:
        report = analyzer.generate_report(results)
        click.echo("\n" + "=" * 80)
        click.echo(report)
        click.echo("=" * 80)

    # Exit with error if quality is below thresholds
    if AnalysisMetric.ACCURACY in results:
        if results[AnalysisMetric.ACCURACY].value < 0.90:
            click.secho(
                "\nWARNING: Detection accuracy below 90% threshold!",
                fg="yellow",
            )
            raise click.Exit(1)

    click.secho("\n✓ Quality analysis complete", fg="green")
```

**Usage:**
```bash
# Run quality analysis
uv run supsrc quality analyze

# Specific metrics
uv run supsrc quality analyze -m accuracy -m precision -m time

# JSON output for CI/CD
uv run supsrc quality analyze --format json
```

---

### Option 3: Continuous Quality Monitoring (ADVANCED)

Add quality metrics to CI/CD pipeline.

#### `.github/workflows/quality.yml`

```yaml
name: Operation Detection Quality

on: [push, pull_request]

jobs:
  quality-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"

      - name: Run quality analysis
        run: |
          uv run pytest tests/integration/test_operation_detection_quality.py -v

      - name: Generate quality report
        run: |
          uv run supsrc quality analyze --format markdown > quality-report.md

      - name: Upload quality report
        uses: actions/upload-artifact@v4
        with:
          name: quality-report
          path: quality-report.md
```

---

## Benefits for supsrc

### 1. Quantitative Quality Assurance
Current tests verify "it works" - quality tools add "how well does it work?"

**Metrics you'd get:**
- **Accuracy**: 95%+ detection correctness
- **Precision**: Low false positive rate for atomic saves
- **Recall**: Catching all VSCode/Vim patterns
- **Detection Time**: Average <10ms, P95 <50ms
- **False Positives**: <5% of detections are wrong

### 2. Regression Detection
Track quality metrics over time to catch detection regressions:

```python
def test_quality_regression():
    """Ensure quality doesn't degrade."""
    results = run_quality_analysis()

    # Historical baseline
    assert results[ACCURACY] >= 0.95  # Don't drop below 95%
    assert results[DETECTION_TIME] < 10.0  # Don't get slower
```

### 3. Editor Pattern Coverage
Verify detection works for all editor patterns:
- VSCode atomic saves ✓
- Vim with backup ✓
- Emacs auto-save ✓
- IntelliJ safe write ✓
- Batch operations ✓

### 4. Performance Validation
Ensure detection is fast enough for real-time use:
- Average detection time < 10ms
- P95 detection time < 50ms
- No degradation under load (100+ files)

---

## Implementation Roadmap

### Phase 1: Add Quality Tests (Low effort, high value)
1. Create `tests/integration/test_operation_detection_quality.py`
2. Use Foundation's `create_scenarios_from_patterns()`
3. Assert quality thresholds (accuracy ≥ 95%, precision ≥ 90%)
4. Run in CI/CD

### Phase 2: CLI Command (Medium effort)
1. Add `src/supsrc/cli/quality_cmds.py`
2. Register command in main CLI
3. Support text/json/markdown output
4. Document in CLI help

### Phase 3: Continuous Monitoring (Optional)
1. Track quality metrics over time
2. Store historical results
3. Alert on regressions
4. Dashboard visualization

---

## Quick Start Guide

### To use `file.quality` in supsrc:

1. **Import the tools:**
   ```python
   from provide.foundation.file.quality import (
       QualityAnalyzer,
       AnalysisMetric,
       create_scenarios_from_patterns,
   )
   ```

2. **Create analyzer with scenarios:**
   ```python
   analyzer = QualityAnalyzer()
   for scenario in create_scenarios_from_patterns():
       analyzer.add_scenario(scenario)
   ```

3. **Run analysis:**
   ```python
   results = analyzer.run_analysis([
       AnalysisMetric.ACCURACY,
       AnalysisMetric.PRECISION,
       AnalysisMetric.RECALL,
   ])
   ```

4. **Assert quality:**
   ```python
   assert results[AnalysisMetric.ACCURACY].value >= 0.95
   ```

### Where it fits:
- ✅ Integration tests - Measure detection quality for real patterns
- ✅ CLI commands - Provide quality reporting to developers
- ✅ CI/CD - Catch quality regressions automatically
- ✅ Performance benchmarks - Ensure detection is fast enough

---

## Summary

The file quality tools would give supsrc **quantitative confidence** that operation detection works correctly and efficiently for all editor patterns!

**Key Value Proposition:**
- Move from "does it work?" to "how well does it work?"
- Catch regressions before they reach production
- Validate performance under realistic load
- Ensure all editor patterns are correctly detected
