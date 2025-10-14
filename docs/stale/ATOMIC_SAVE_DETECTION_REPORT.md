# Comprehensive Report: Atomic Save Detection with Scoring-Based Architecture

## Executive Summary
The project involves fixing atomic save operations bundling in the supsrc TUI event feed. Multiple file events (moved, deleted, created) for temporary files are appearing as separate entries instead of being bundled as a single "Updated" operation. The solution will implement a **scoring-based detection system** where all patterns are evaluated and the highest-scoring match wins, eliminating conflicts and making the system extensible.

## Problem Statement

### Original Issue
- **Symptom**: The supsrc TUI shows multiple event entries for a single atomic save operation
- **Example**: When VSCode saves `test_config_commands.py`, it shows:
  - `test_config_commands.py.tmp.84` moved
  - `test_config_commands.py.tmp.84` deleted
  - `test_config_commands.py` created
- **Expected**: Single entry showing `test_config_commands.py` updated

### Root Cause
Modern editors (VSCode, Sublime, etc.) use atomic save patterns involving temporary files to ensure data integrity. The file monitoring system wasn't recognizing these patterns as single operations due to conflicting detection patterns.

## Current Implementation Status

### 1. Architecture Overview

#### provide-foundation Library Structure
```
/REDACTED_ABS_PATH
├── __init__.py           # Exports main classes
├── detector.py           # Main OperationDetector class (RECENTLY REFACTORED)
├── types.py             # Data types (FileEvent, FileOperation, OperationType)
├── detectors/           # Specialized detector modules (NO LONGER USED after refactor)
│   ├── atomic.py       # AtomicOperationDetector (deprecated)
│   ├── batch.py        # BatchOperationDetector (deprecated)
│   ├── simple.py       # SimpleOperationDetector (deprecated)
│   └── temp.py         # TempPatternDetector (deprecated)
```

### 2. Recent Refactoring

The `detector.py` file was refactored to consolidate all detection logic into a single file. The detector classes in the `detectors/` subdirectory are no longer used. All detection methods are now in the main `OperationDetector` class.

#### Current Detection Flow (Lines 118-142 of detector.py)
```python
def _analyze_event_group(self, events: list[FileEvent]) -> FileOperation | None:
    """Analyze a group of events to detect an operation."""
    detectors = [
        self._detect_atomic_save,      # Tries all 5 patterns internally
        self._detect_safe_write,
        self._detect_rename_sequence,
        self._detect_batch_update,
        self._detect_backup_create,
        self._detect_simple_operation,
    ]

    best_operation = None
    best_confidence = 0.0

    for detector in detectors:
        operation = detector(events)
        if operation and operation.confidence > best_confidence:
            best_operation = operation
            best_confidence = operation.confidence

    return best_operation if best_confidence >= self.config.min_confidence else None
```

### 3. Current Atomic Save Patterns

The `_detect_atomic_save` method (lines 228-267) tries 5 patterns sequentially:

| Pattern | Description | Confidence | Example |
|---------|-------------|------------|---------|
| **Pattern 4** | VSCode: temp create→delete→real create | 0.95 | `.file.tmp.84` created → deleted → `file` created |
| **Pattern 1** | Direct rename: temp→final | 0.95 | `file.tmp` → renamed to `file` |
| **Pattern 5** | Same file replace | 0.90 | `file` deleted → `file` created |
| **Pattern 2** | Delete original + rename | 0.85 | `file` deleted → `file.tmp` renamed |
| **Pattern 3** | Overwrite pattern | 0.80 | `file.tmp` created → `file` modified |

## Proposed Scoring-Based Architecture

### Core Design Principles

1. **All Patterns Evaluated**: Every detector runs on every event group
2. **Multi-Dimensional Scoring**: Combine confidence, specificity, and recency
3. **No Early Exit**: Collect all matches, then select best
4. **Extensible**: New patterns can be added without affecting existing ones
5. **Debuggable**: Can log all candidate matches with scores

### Proposed Implementation Structure

```python
from dataclasses import dataclass
from enum import IntEnum

class PatternSpecificity(IntEnum):
    """Specificity levels for pattern matching."""
    EXACT_EDITOR_PATTERN = 100    # VSCode .tmp.84 pattern
    KNOWN_EDITOR_PATTERN = 90     # Vim .swp, IntelliJ ___jb_tmp___
    GENERIC_TEMP_PATTERN = 70     # Any .tmp file
    BEHAVIORAL_PATTERN = 50       # Based on timing/sequence
    FALLBACK_PATTERN = 30         # Generic file operation

@dataclass
class DetectorResult:
    """Result from a single detector with scoring information."""
    pattern_name: str              # e.g., "vscode_atomic_save"
    operation_type: OperationType  # e.g., OperationType.ATOMIC_SAVE
    confidence: float              # 0.0 to 1.0 (how sure we are)
    specificity: PatternSpecificity  # How specific the pattern is
    primary_path: Path             # The main file affected
    events: list[FileEvent]        # Events that matched
    description: str               # Human-readable description

    @property
    def combined_score(self) -> float:
        """Combined score for ranking matches."""
        # Specificity is more important than confidence
        return (self.specificity.value / 100.0) * 0.6 + self.confidence * 0.4

class ScoringOperationDetector:
    """New scoring-based operation detector."""

    def __init__(self, config: DetectorConfig | None = None):
        self.config = config or DetectorConfig()
        self.scorers = [
            VSCodeAtomicSaveScorer(),
            VimSaveScorer(),
            GenericAtomicSaveScorer(),
            SafeWriteScorer(),
            BatchOperationScorer(),
            SimpleOperationScorer(),
        ]

    def detect(self, events: list[FileEvent]) -> FileOperation | None:
        """Detect operations using scoring system."""
        if not events:
            return None

        # Collect all possible matches
        all_results: list[DetectorResult] = []

        for scorer in self.scorers:
            try:
                results = scorer.score(events)
                all_results.extend(results)
            except Exception as e:
                log.warning(f"Scorer {scorer.__class__.__name__} failed: {e}")

        if not all_results:
            return None

        # Sort by combined score (highest first)
        all_results.sort(key=lambda r: r.combined_score, reverse=True)

        # Log all candidates for debugging
        if log.isEnabledFor(logging.DEBUG):
            for i, result in enumerate(all_results[:5]):  # Top 5
                log.debug(
                    f"Candidate {i+1}: {result.pattern_name} "
                    f"(score={result.combined_score:.2f}, "
                    f"confidence={result.confidence:.2f}, "
                    f"specificity={result.specificity})"
                )

        # Select best match above threshold
        best = all_results[0]
        if best.confidence >= self.config.min_confidence:
            return self._create_operation(best)

        return None
```

### Specific Scorer Implementations

#### VSCode Atomic Save Scorer
```python
class VSCodeAtomicSaveScorer:
    """Scores VSCode-specific atomic save patterns."""

    def score(self, events: list[FileEvent]) -> list[DetectorResult]:
        results = []

        # Pattern: .file.tmp.XXXXX created → deleted → file created
        temp_creates = [e for e in events if e.event_type == "created"
                       and self._is_vscode_temp(e.path)]

        if temp_creates:
            # Look for the full VSCode pattern
            for temp_create in temp_creates:
                if self._find_vscode_pattern(temp_create, events):
                    results.append(DetectorResult(
                        pattern_name="vscode_atomic_save",
                        operation_type=OperationType.ATOMIC_SAVE,
                        confidence=0.95,
                        specificity=PatternSpecificity.EXACT_EDITOR_PATTERN,
                        primary_path=self._get_real_file_path(temp_create.path),
                        events=events,
                        description="VSCode atomic save operation"
                    ))

        return results

    def _is_vscode_temp(self, path: Path) -> bool:
        """Check if file matches VSCode temp pattern."""
        # Matches: .file.tmp.84, file.tmp.53TM2M, etc.
        return bool(re.match(r'\.?.*\.tmp\.\w+$', path.name))
```

#### Generic Atomic Save Scorer
```python
class GenericAtomicSaveScorer:
    """Scores generic atomic save patterns."""

    def score(self, events: list[FileEvent]) -> list[DetectorResult]:
        results = []

        # Pattern 1: Any temp file + final file modification
        if self._has_temp_and_modify(events):
            results.append(DetectorResult(
                pattern_name="generic_atomic_save",
                operation_type=OperationType.ATOMIC_SAVE,
                confidence=0.70,
                specificity=PatternSpecificity.GENERIC_TEMP_PATTERN,
                # ... other fields
            ))

        # Pattern 2: Delete + immediate recreate
        if self._has_delete_create_same_file(events):
            results.append(DetectorResult(
                pattern_name="delete_recreate_save",
                operation_type=OperationType.ATOMIC_SAVE,
                confidence=0.75,
                specificity=PatternSpecificity.BEHAVIORAL_PATTERN,
                # ... other fields
            ))

        return results
```

### Integration Points

#### 1. Update detector.py
Replace current `_analyze_event_group` method with scoring-based approach:
- Remove sequential detector calls
- Implement scorer classes
- Add scoring and selection logic

#### 2. Update types.py
Add new types for scoring system:
- `DetectorResult` dataclass
- `PatternSpecificity` enum
- Update `DetectorConfig` with scoring parameters

#### 3. Update buffer.py in supsrc
No changes needed - continues to use `OperationDetector` interface

## Implementation Plan

### Phase 1: Core Scoring Infrastructure
1. **Add scoring types** to `types.py`
   - DetectorResult dataclass
   - PatternSpecificity enum
   - Scoring configuration options

2. **Create base scorer class**
   ```python
   class BaseScorer(ABC):
       @abstractmethod
       def score(self, events: list[FileEvent]) -> list[DetectorResult]:
           """Return all possible matches with scores."""
           pass
   ```

3. **Implement scoring orchestrator** in `detector.py`
   - Collect results from all scorers
   - Rank by combined score
   - Select best match above threshold

### Phase 2: Implement Specific Scorers
1. **VSCodeAtomicSaveScorer** (highest priority)
   - Pattern: `.tmp.XXX` files
   - Specificity: 100
   - Confidence: 0.95

2. **VimSaveScorer**
   - Pattern: `.swp`, `.swo` files
   - Specificity: 90
   - Confidence: 0.90

3. **GenericAtomicSaveScorer**
   - Various temp patterns
   - Specificity: 50-70
   - Confidence: 0.70-0.85

4. **SimpleOperationScorer** (fallback)
   - Basic create/modify/delete
   - Specificity: 30
   - Confidence: 0.60-0.70

### Phase 3: Testing and Tuning
1. **Unit tests** for each scorer
2. **Integration tests** with real file operations
3. **TUI testing** with actual editor saves
4. **Tune scoring weights** based on results

## Testing Strategy

### Unit Tests
```python
def test_vscode_atomic_save_scores_highest():
    """VSCode pattern should score higher than generic."""
    events = [
        FileEvent(Path(".file.tmp.84"), "created", ...),
        FileEvent(Path(".file.tmp.84"), "deleted", ...),
        FileEvent(Path("file"), "created", ...)
    ]

    detector = ScoringOperationDetector()
    operation = detector.detect(events)

    assert operation.operation_type == OperationType.ATOMIC_SAVE
    assert "vscode" in operation.description.lower()
```

### Integration Tests
```python
def test_real_vscode_save(tmp_path):
    """Test with actual VSCode save operation."""
    # Simulate VSCode save pattern
    temp_file = tmp_path / ".test.tmp.123"
    real_file = tmp_path / "test.py"

    # Capture events
    with event_capture() as events:
        temp_file.write_text("content")
        temp_file.unlink()
        real_file.write_text("content")

    # Should detect as single atomic save
    operation = detector.detect(events)
    assert operation.operation_type == OperationType.ATOMIC_SAVE
```

## Configuration and Tuning

### Proposed Configuration Options
```python
@dataclass
class ScoringConfig:
    """Configuration for scoring-based detection."""

    # Scoring weights
    specificity_weight: float = 0.6  # How much specificity matters
    confidence_weight: float = 0.4   # How much confidence matters

    # Thresholds
    min_confidence: float = 0.6      # Minimum confidence to accept
    min_specificity: int = 30        # Minimum specificity level

    # Debugging
    log_all_candidates: bool = False # Log all scoring results
    max_candidates_to_log: int = 5   # How many to log

    # Performance
    max_scorers_parallel: int = 4    # Run scorers in parallel
    scorer_timeout_ms: int = 100     # Timeout per scorer
```

## Migration Path

### Step 1: Parallel Implementation
- Keep existing detection working
- Add scoring system alongside
- Compare results in debug mode

### Step 2: Gradual Rollout
- Enable scoring for specific patterns first
- Monitor logs for discrepancies
- Tune scores based on real usage

### Step 3: Full Migration
- Switch to scoring-only mode
- Remove old detection code
- Clean up deprecated detectors

## Benefits of Scoring Approach

### 1. **No Conflicts**
- All patterns evaluated independently
- Best match wins automatically
- No order dependencies

### 2. **Extensibility**
- Add new scorers without touching existing code
- Plugin architecture for editor-specific patterns
- Community can contribute scorers

### 3. **Debuggability**
- See all candidate matches
- Understand why specific pattern won
- Tune scores based on logs

### 4. **Performance**
- Scorers can run in parallel
- Cache pattern compilations
- Early exit for obvious matches

### 5. **Machine Learning Ready**
- Scores can be learned from user feedback
- Patterns can be discovered automatically
- Adaptive to user's specific editor

## Success Metrics

### Functional Success
- [ ] VSCode saves appear as single "Updated" entry
- [ ] Vim saves detected correctly
- [ ] IntelliJ saves detected correctly
- [ ] No false positives on build outputs

### Performance Metrics
- Detection time < 10ms for typical event group
- Memory usage < 1MB for pattern cache
- CPU usage negligible during monitoring

### Quality Metrics
- Test coverage > 90% for scorers
- Zero crashes in production
- Logging provides clear debugging info

## Summary

The scoring-based architecture solves the fundamental problem of conflicting detection patterns by evaluating all patterns and selecting the best match. This approach is more maintainable, extensible, and debuggable than the current first-match system.

The implementation involves creating scorer classes that return `DetectorResult` objects with confidence and specificity scores. The main detector combines these scores and selects the highest-scoring match above the confidence threshold.

This architecture supports adding editor-specific patterns without breaking existing detection, enables parallel evaluation for performance, and provides clear debugging through candidate logging.

The migration can be done gradually, maintaining backward compatibility while proving the new system works correctly. Once validated, the old detection code can be removed, leaving a clean, maintainable system.