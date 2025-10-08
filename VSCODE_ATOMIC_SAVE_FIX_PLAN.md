# VSCode Atomic Save Fix - Complete Plan

## Problem Statement

**Issue 1: VSCode Temp File Pattern Bug**
- VSCode creates temp files like `.orchestrator.py.tmp.84` during atomic saves
- supsrc's TUI displays `.orchestrator.py` (with leading dot) instead of `orchestrator.py`
- The leading `.` is part of VSCode's temp pattern, not the actual filename

**Issue 2: Package Installation/Build Problem**
- provide-foundation source code has NEW architecture with `detectors/orchestrator.py`
- Package builds with OLD architecture (`detector.py`) without callback support
- This causes runtime error: `TypeError: OperationDetector.__init__() got an unexpected keyword argument 'on_operation_complete'`

## Status Summary

### ✅ COMPLETED: VSCode Pattern Detection Fix

**Files Modified:**
1. `provide-foundation/src/provide/foundation/file/operations/detectors/helpers.py`
   - Fixed `extract_base_name()` to handle VSCode pattern: `.file.tmp.XX` → `file`
   - Enhanced `is_temp_file()` with explicit VSCode pattern detection

2. `provide-foundation/tests/file/file_operations_fixtures.py`
   - Fixed VSCode simulator to use realistic pattern: `.{filename}.tmp.{random_id}`

3. `provide-foundation/tests/file/test_vscode_temp_pattern.py` (NEW)
   - 12 test cases for VSCode pattern edge cases

4. `supsrc/tests/integration/test_vscode_atomic_save.py` (NEW)
   - 5 integration tests for EventBuffer with VSCode patterns

5. `provide-foundation/VERSION`
   - Bumped to `0.0.31`

**Verification:**
```bash
cd /Users/tim/code/gh/provide-io/provide-foundation
python3 -c "
from pathlib import Path
from src.provide.foundation.file.operations.detectors.helpers import extract_base_name, is_temp_file

# Test cases
assert is_temp_file(Path('.orchestrator.py.tmp.84')) == True
assert extract_base_name(Path('.orchestrator.py.tmp.84')) == 'orchestrator.py'
print('✅ VSCode pattern detection works correctly')
"
```

### ❌ BLOCKED: Package Installation Issue

**Root Cause:**
- The editable install (`uv pip install -e`) is not properly including the `detectors/` subdirectory
- Python is still loading old `detector.py` file instead of new `detectors/orchestrator.py`
- The `pyproject.toml` build configuration is missing explicit package discovery

**Current State:**
```
Source code structure (CORRECT):
provide-foundation/src/provide/foundation/file/operations/
├── __init__.py           # Imports from detectors.orchestrator
├── detectors/
│   ├── __init__.py       # Exports OperationDetector
│   ├── orchestrator.py   # Has on_operation_complete parameter ✅
│   ├── helpers.py        # Fixed VSCode pattern ✅
│   └── ...
├── types.py
└── utils.py

Installed package (WRONG):
.venv/lib/python3.11/site-packages/provide/foundation/file/operations/
├── __init__.py           # Imports from detector (OLD)
├── detector.py           # Missing on_operation_complete parameter ❌
├── types.py
└── utils.py
# detectors/ directory is MISSING!
```

## Complete Fix Plan

### Phase 1: Fix Package Build Configuration

**Step 1.1: Update pyproject.toml**
```toml
# In provide-foundation/pyproject.toml

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["provide.foundation", "provide.foundation.file.operations.detectors"]
# OR
[tool.setuptools.packages.find]
where = ["src"]
include = ["provide*"]
namespaces = false
```

**Step 1.2: Verify package includes detectors/**
```bash
cd /Users/tim/code/gh/provide-io/provide-foundation

# Build the package
uv build

# Check what's in the wheel
unzip -l dist/provide_foundation-0.0.31-py3-none-any.whl | grep operations
# Should see:
#   provide/foundation/file/operations/detectors/__init__.py
#   provide/foundation/file/operations/detectors/orchestrator.py
#   provide/foundation/file/operations/detectors/helpers.py
#   etc.
```

**Step 1.3: Clean Install in supsrc**
```bash
cd /Users/tim/code/gh/provide-io/supsrc

# Remove everything
rm -rf .venv/lib/python3.11/site-packages/provide*
rm -rf .venv/lib/python3.11/site-packages/__editable__*

# Reinstall
uv pip install -e '../provide-foundation[all]'

# Verify correct structure
ls -la .venv/lib/python3.11/site-packages/provide/foundation/file/operations/
# Should show detectors/ directory
```

### Phase 2: Alternative Fix - Use MANIFEST.in

If pyproject.toml approach doesn't work:

**Step 2.1: Create MANIFEST.in**
```bash
cd /Users/tim/code/gh/provide-io/provide-foundation
cat > MANIFEST.in << 'EOF'
recursive-include src/provide/foundation/file/operations/detectors *.py
include src/provide/foundation/file/operations/detectors/__init__.py
EOF
```

**Step 2.2: Add to pyproject.toml**
```toml
[tool.setuptools]
include-package-data = true
```

### Phase 3: Verification Checklist

**3.1 Check Package Structure**
```bash
cd /Users/tim/code/gh/provide-io/supsrc

# Check detectors directory exists
test -d .venv/lib/python3.11/site-packages/provide/foundation/file/operations/detectors && echo "✅ detectors/ exists" || echo "❌ detectors/ missing"

# Check orchestrator.py exists
test -f .venv/lib/python3.11/site-packages/provide/foundation/file/operations/detectors/orchestrator.py && echo "✅ orchestrator.py exists" || echo "❌ orchestrator.py missing"

# Check old detector.py is gone
test ! -f .venv/lib/python3.11/site-packages/provide/foundation/file/operations/detector.py && echo "✅ old detector.py removed" || echo "❌ old detector.py still present"
```

**3.2 Check OperationDetector Signature**
```bash
cd /Users/tim/code/gh/provide-io/supsrc

uv run python -c "
from provide.foundation.file.operations import OperationDetector
import inspect

sig = inspect.signature(OperationDetector.__init__)
params = list(sig.parameters.keys())

print(f'Module: {OperationDetector.__module__}')
print(f'File: {inspect.getfile(OperationDetector)}')
print(f'Parameters: {params}')

# Should be: ['self', 'config', 'on_operation_complete']
assert 'on_operation_complete' in params, '❌ on_operation_complete parameter missing'
print('✅ OperationDetector has on_operation_complete parameter')
"
```

**3.3 Test VSCode Pattern Detection**
```bash
cd /Users/tim/code/gh/provide-io/supsrc

uv run python -c "
from pathlib import Path
from provide.foundation.file.operations.detectors.helpers import extract_base_name, is_temp_file

test_cases = [
    (Path('.orchestrator.py.tmp.84'), 'orchestrator.py'),
    (Path('.test.txt.tmp.123'), 'test.txt'),
    (Path('.config.json.tmp.abc'), 'config.json'),
]

for temp_file, expected in test_cases:
    assert is_temp_file(temp_file), f'❌ {temp_file} not detected as temp'
    result = extract_base_name(temp_file)
    assert result == expected, f'❌ {temp_file} → {result}, expected {expected}'

print('✅ All VSCode pattern tests pass')
"
```

**3.4 Run test_temp_emission.py**
```bash
cd /Users/tim/code/gh/provide-io/supsrc
uv run python test_temp_emission.py

# Expected output:
# === Simulating VSCode atomic save ===
# 1. Creating temp file: .orchestrator.py.tmp
# 2. Modifying temp file: .orchestrator.py.tmp
# 3. Moving to final: orchestrator.py
#
# === Waiting for emission (smart mode) ===
#
# === Results ===
# ✅ Event emitted!
# ✅ Final file: orchestrator.py  # ← Should NOT have leading dot!
```

**3.5 Run provide-foundation Tests**
```bash
cd /Users/tim/code/gh/provide-io/provide-foundation
uv run pytest tests/file/test_vscode_temp_pattern.py -v

# Should pass all 12+ tests
```

**3.6 Run supsrc Integration Tests**
```bash
cd /Users/tim/code/gh/provide-io/supsrc
uv run pytest tests/integration/test_vscode_atomic_save.py -v

# Should pass all 5 tests
```

### Phase 4: Final Integration Test

**4.1 Test with Real supsrc TUI**
```bash
cd /Users/tim/code/gh/provide-io/supsrc
uv run supsrc sui

# In TUI:
# 1. Watch a repo
# 2. Edit a file in VSCode
# 3. Save (CMD+S)
# 4. Check TUI event display
#
# Expected: Should show "orchestrator.py" NOT ".orchestrator.py"
```

## Troubleshooting Guide

### Issue: detectors/ directory still missing after install

**Solution 1: Check source directory**
```bash
cd /Users/tim/code/gh/provide-io/provide-foundation
ls -la src/provide/foundation/file/operations/detectors/
# If missing, the source code is corrupted. Re-pull from git.
```

**Solution 2: Force clean build**
```bash
cd /Users/tim/code/gh/provide-io/provide-foundation
rm -rf dist/ build/ *.egg-info src/*.egg-info
rm -rf .venv/lib/python3.11/site-packages/provide*

cd /Users/tim/code/gh/provide-io/supsrc
rm -rf .venv/lib/python3.11/site-packages/provide*
uv pip install --force-reinstall --no-cache-dir -e '../provide-foundation[all]'
```

**Solution 3: Manual verification of wheel contents**
```bash
cd /Users/tim/code/gh/provide-io/provide-foundation
uv build
python -m zipfile -l dist/*.whl | grep "operations/detectors"
# Should show multiple files in detectors/
```

### Issue: Circular import error

**Symptom:**
```
ImportError: cannot import name 'get_hub' from partially initialized module
```

**Solution:**
This indicates the detectors registry is being loaded during module initialization. Check:
```bash
# Verify the __init__.py import order
cat src/provide/foundation/file/operations/detectors/__init__.py
# The _auto_register_builtin_detectors() should only log, not import foundation.hub
```

### Issue: Still loading old detector.py

**Solution:**
```bash
cd /Users/tim/code/gh/provide-io/supsrc

# Find all detector.py files
find .venv -name "detector.py" -type f

# Remove them all
find .venv -name "detector.py" -type f -delete

# Clear Python cache
find .venv -name "*.pyc" -delete
find .venv -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# Reinstall
uv pip uninstall provide-foundation
uv pip install -e '../provide-foundation[all]'
```

## Success Criteria

- [ ] `detectors/` directory exists in installed package
- [ ] `OperationDetector.__init__` has `on_operation_complete` parameter
- [ ] `extract_base_name('.file.tmp.84')` returns `'file'` (not `'.file'`)
- [ ] `is_temp_file('.file.tmp.84')` returns `True`
- [ ] test_temp_emission.py runs without errors
- [ ] test_temp_emission.py shows `orchestrator.py` (not `.orchestrator.py`)
- [ ] provide-foundation tests pass
- [ ] supsrc integration tests pass
- [ ] Real TUI shows correct filenames after VSCode save

## Files Modified Summary

### provide-foundation
- `src/provide/foundation/file/operations/detectors/helpers.py` - Fixed VSCode pattern
- `tests/file/file_operations_fixtures.py` - Fixed simulator
- `tests/file/test_vscode_temp_pattern.py` - NEW comprehensive tests
- `VERSION` - Bumped to 0.0.31
- `pyproject.toml` - Need to fix package discovery (TO DO)

### supsrc
- `tests/integration/test_vscode_atomic_save.py` - NEW integration tests
- `pyproject.toml` - Already updated to require provide-foundation>=0.0.0.dev3

## Next Steps

1. Fix pyproject.toml build configuration in provide-foundation
2. Verify wheel contains detectors/ directory
3. Clean install in supsrc
4. Run all verification steps
5. Test with real TUI
6. Commit changes and publish provide-foundation v0.0.31

## Context for LLM

When resuming this work:
1. The VSCode pattern detection logic is **already fixed** in the source code
2. The tests are **already written** and will pass once package installation works
3. The **only** remaining issue is the package build/installation
4. DO NOT modify helpers.py or the detection logic - they are correct
5. FOCUS ONLY on making `uv pip install -e` include the `detectors/` directory
6. The old `detector.py` file should not exist in the source code - if it does, delete it

## Key Insights

- VSCode uses `.filename.ext.tmp.XXXX` pattern (leading dot is part of temp name)
- The detectors architecture uses a registry-based system with priority ordering
- OperationDetector needs `on_operation_complete` callback for streaming mode
- EventBuffer in supsrc uses smart mode which requires the callback API
- The package must use setuptools backend for proper subdirectory inclusion
