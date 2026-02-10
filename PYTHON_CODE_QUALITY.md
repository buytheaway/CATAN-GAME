# Python Code Quality Improvements

## Issues Identified

### 1. Ambiguous Imports (34 instances)

Files with unresolved imports that need fixing:
- `app/dev_hand_overlay.py` - 2 unresolved imports
- `app/game_launcher.py` - 3 unresolved imports  
- `app/lobby_ui.py` - 3 unresolved imports
- `app/main_menu.py` - 4 unresolved imports
- `app/online_controller.py` - 2 unresolved imports
- `app/server_mp.py` - 9 unresolved imports
- `app/ui_v6.py` - 9 unresolved imports

**Root Cause**: These modules are trying to import from `app.rules_engine` which is an alias. The actual implementations are in `app.engine`.

**Fix Strategy**:
Replace all imports like:
```python
from app.rules_engine import GameState, build_game, ...
```

With:
```python
from app.engine import GameState, build_game, ...
```

### 2. Unreachable/Dead Code (7 files)

Files in `app/_legacy_next/` that are not used by any active module:
- `app/_legacy_next/base.py`
- `app/_legacy_next/board.py`
- `app/_legacy_next/client_cli.py`
- `app/_legacy_next/ports_bridge.py`
- `app/_legacy_next/runtime_patch.py`
- `app/_legacy_next/seafarers_stub.py`
- `app/expansions/` (entire directory)

**Action Items**:
1. ✅ They're already in `_legacy_next/` folder (separation done)
2. Consider archiving to a git-ignored archive folder if not needed
3. Or - if these are features to be implemented, move them to `app/engine/expansions/`

### 3. Type Hints

**Current State**: Minimal type hints in Python code

**Improvements Needed**:
- Add return type hints to all functions
- Add parameter type hints
- Use `from typing import ...` for complex types
- Use Python 3.10+ union syntax (`X | Y` instead of `Union[X, Y]`)

## Configuration Files Added

### 1. `mypy.ini` - Static Type Checking
Run type checking:
```bash
mypy app/
```

### 2. `setup.cfg` - Pytest Configuration
Run tests with coverage:
```bash
pytest
```

### 3. `.pylintrc` (Recommended)
```bash
pip install pylint
pylint app/
```

## Step-by-Step Fixes

### Step 1: Fix Import Aliases
Edit `app/rules_engine.py` - remove this file, it's redundant:
```python
# OLD - DELETE THIS FILE
from app.engine import (
    AchievementState,
    GameState,
    ...
)
__all__ = [...]
```

Replace all imports in other files:
```bash
# Find all files importing from app.rules_engine
grep -r "from app.rules_engine import" app/

# Replace them
find app -name "*.py" -type f -exec sed -i 's/from app\.rules_engine import/from app.engine import/g' {} \;
```

### Step 2: Clean Up Dead Code
```bash
# Archive legacy code
mkdir app/_archive
mv app/_legacy_next/* app/_archive/
mv app/expansions app/_archive/

# Or delete if repo cleanup is desired
rm -rf app/_legacy_next app/expansions
```

### Step 3: Add Type Hints

Example fix for `app/config.py`:

**Before**:
```python
class GameConfig:
    def __init__(self, mode, map_id, theme):
        self.mode = mode
        self.map_id = map_id
        self.theme = theme
```

**After**:
```python
from typing import Optional

class GameConfig:
    def __init__(self, mode: str, map_id: str, theme: str) -> None:
        self.mode: str = mode
        self.map_id: str = map_id
        self.theme: str = theme
```

### Step 4: Add py.typed Marker
```bash
touch app/py.typed
```

This marks the package as having inline type hints (PEP 561).

### Step 5: Run Quality Checks

```bash
# Type checking
mypy app/ --config-file=mypy.ini

# Linting
pylint app/ --max-line-length=120

# Testing with coverage
pytest --cov=app --cov-report=html

# Combined check
python -m pytest && mypy app/
```

## Recommendations

### High Priority
1. Fix import aliases (app.rules_engine → app.engine)
2. Add type hints to `app/engine/` modules
3. Clean up `_legacy_next/` folder

### Medium Priority  
1. Add return type hints to all functions
2. Add parameter type hints
3. Create type stubs for dynamic imports

### Nice to Have
1. Set up GitHub Actions CI/CD
2. Add code coverage badges
3. Add pre-commit hooks
4. Document public API

## Quality Checklist

- [ ] All imports use correct paths (app.engine, not app.rules_engine)
- [ ] No `any` types in type hints
- [ ] All public functions have docstrings
- [ ] All public functions have type hints
- [ ] `mypy` passes with 0 errors
- [ ] `pytest` passes with >80% coverage
- [ ] Dead code removed or archived
- [ ] `py.typed` marker exists

## Usage Examples

### Run Linting
```bash
cd /path/to/CATAN-GAME
black app/  # Auto-format
flake8 app/  # Check style
mypy app/  # Type check
```

### Run Tests
```bash
pytest tests/ -v --cov=app
```

### Pre-commit Hook
Create `.git/hooks/pre-commit`:
```bash
#!/bin/bash
mypy app/ && pytest tests/ --tb=short
```

## References

- [MyPy Documentation](https://mypy.readthedocs.io/)
- [PEP 484 - Type Hints](https://www.python.org/dev/peps/pep-0484/)
- [PEP 561 - Distributing Type Information](https://www.python.org/dev/peps/pep-0561/)
- [Pytest Documentation](https://docs.pytest.org/)
- [Black - Code Formatter](https://black.readthedocs.io/)
