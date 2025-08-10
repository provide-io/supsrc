#
# tests/unit/test_cty_models.py
#
"""
Test CTY type system integration for supsrc models.
"""

import pytest
from datetime import timedelta
from pathlib import Path

from supsrc.models.cty_types import (
    RepositoryStateCty,
    SupsrcConfigCty,
    MonitoringRuleCty,
    validate_duration,
    validate_path,
    CtyValidationError
)


class TestRepositoryStateCty:
    """Test repository state with CTY types."""
    
    def test_create_valid_state(self):
        """Test creating a valid repository state."""
        state = RepositoryStateCty({
            "repo_id": "test-repo",
            "status": "idle",
            "changes": {
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "total_size": 0
            },
            "timers": {},
            "metrics": {
                "save_count": 0,
                "commit_count": 0,
                "avg_commit_time": "0s"
            }
        })
        
        assert state.repo_id == "test-repo"
        assert state.status == "idle"
        assert state.changes.total_size == 0
        assert state.metrics.save_count == 0
    
    def test_invalid_status_raises(self):
        """Test that invalid status raises validation error."""
        with pytest.raises(CtyValidationError) as exc_info:
            RepositoryStateCty({
                "repo_id": "test-repo",
                "status": "invalid_status",  # Not in enum
                "changes": {
                    "staged": [],
                    "unstaged": [],
                    "untracked": [],
                    "total_size": 0
                },
                "timers": {},
                "metrics": {
                    "save_count": 0,
                    "commit_count": 0,
                    "avg_commit_time": "0s"
                }
            })
        
        assert "invalid_status" in str(exc_info.value)
        assert "must be one of" in str(exc_info.value)
    
    def test_negative_metrics_raises(self):
        """Test that negative metrics raise validation error."""
        with pytest.raises(CtyValidationError) as exc_info:
            RepositoryStateCty({
                "repo_id": "test-repo",
                "status": "idle",
                "changes": {
                    "staged": [],
                    "unstaged": [],
                    "untracked": [],
                    "total_size": -100  # Negative size
                },
                "timers": {},
                "metrics": {
                    "save_count": -5,  # Negative count
                    "commit_count": 0,
                    "avg_commit_time": "0s"
                }
            })
        
        assert "must be >= 0" in str(exc_info.value)
    
    def test_duration_parsing(self):
        """Test duration string parsing."""
        state = RepositoryStateCty({
            "repo_id": "test-repo",
            "status": "idle",
            "changes": {
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "total_size": 0
            },
            "timers": {
                "inactivity": "5m30s",
                "debounce": "1s"
            },
            "metrics": {
                "save_count": 0,
                "commit_count": 0,
                "avg_commit_time": "2.5s"
            }
        })
        
        # Durations should be parsed to timedelta
        assert state.timers["inactivity"] == timedelta(minutes=5, seconds=30)
        assert state.timers["debounce"] == timedelta(seconds=1)
        assert state.metrics.avg_commit_time == timedelta(seconds=2.5)
    
    def test_path_list_validation(self):
        """Test path list validation."""
        state = RepositoryStateCty({
            "repo_id": "test-repo",
            "status": "changed",
            "changes": {
                "staged": ["/path/to/file.py", "relative/path.js"],
                "unstaged": ["another/file.go"],
                "untracked": [".env", "*.log"],
                "total_size": 1024
            },
            "timers": {},
            "metrics": {
                "save_count": 1,
                "commit_count": 0,
                "avg_commit_time": "0s"
            }
        })
        
        # Paths should be converted to Path objects
        assert all(isinstance(p, Path) for p in state.changes.staged)
        assert state.changes.staged[0] == Path("/path/to/file.py")
        assert len(state.changes.untracked) == 2
    
    def test_sensitive_data_marking(self):
        """Test sensitive data is marked properly."""
        state = RepositoryStateCty({
            "repo_id": "test-repo",
            "status": "idle",
            "changes": {
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "total_size": 0
            },
            "timers": {},
            "metrics": {
                "save_count": 0,
                "commit_count": 0,
                "avg_commit_time": "0s"
            },
            "sensitive_data": "secret_token_123"
        })
        
        # Sensitive data should be marked
        assert hasattr(state.sensitive_data, "__cty_marks__")
        assert "sensitive" in state.sensitive_data.__cty_marks__
        
        # Should not appear in string representation
        assert "secret_token_123" not in str(state)
        assert "[SENSITIVE]" in str(state) or "***" in str(state)


class TestSupsrcConfigCty:
    """Test supsrc configuration with CTY types."""
    
    def test_minimal_config(self):
        """Test minimal valid configuration."""
        config = SupsrcConfigCty({
            "global": {},
            "repositories": {}
        })
        
        # Defaults should be applied
        assert config.global_.log_level == "INFO"
        assert config.global_.default_commit_message == "🔼⚙️ auto-commit"
        assert len(config.repositories) == 0
    
    def test_full_repository_config(self):
        """Test full repository configuration."""
        config = SupsrcConfigCty({
            "global": {
                "log_level": "DEBUG"
            },
            "repositories": {
                "my-repo": {
                    "enabled": True,
                    "path": "/REDACTED_ABS_PATH",
                    "rule": {
                        "type": "inactivity",
                        "period": "5m"
                    },
                    "monitoring": {
                        "interval": "30s",
                        "ignore_patterns": ["*.log", "*.tmp", ".git/**"],
                        "max_file_size": 50
                    }
                }
            }
        })
        
        assert config.global_.log_level == "DEBUG"
        assert "my-repo" in config.repositories
        
        repo = config.repositories["my-repo"]
        assert repo.enabled is True
        assert repo.path == Path("/REDACTED_ABS_PATH")
        assert repo.monitoring.interval == timedelta(seconds=30)
        assert len(repo.monitoring.ignore_patterns) == 3
        assert repo.monitoring.max_file_size == 50  # MB
    
    def test_invalid_log_level_raises(self):
        """Test invalid log level raises error."""
        with pytest.raises(CtyValidationError) as exc_info:
            SupsrcConfigCty({
                "global": {
                    "log_level": "TRACE"  # Not in enum
                },
                "repositories": {}
            })
        
        assert "TRACE" in str(exc_info.value)
        assert "must be one of" in str(exc_info.value)
    
    def test_path_validation(self):
        """Test path existence validation."""
        with pytest.raises(CtyValidationError) as exc_info:
            SupsrcConfigCty({
                "global": {},
                "repositories": {
                    "test": {
                        "path": "/definitely/does/not/exist/path"
                    }
                }
            })
        
        assert "does not exist" in str(exc_info.value)
    
    def test_duration_constraints(self):
        """Test duration min/max constraints."""
        # Too short interval
        with pytest.raises(CtyValidationError) as exc_info:
            SupsrcConfigCty({
                "global": {},
                "repositories": {
                    "test": {
                        "path": "/tmp",
                        "monitoring": {
                            "interval": "0.5s"  # Less than 1s minimum
                        }
                    }
                }
            })
        
        assert "must be >= 1s" in str(exc_info.value)
        
        # Too long interval
        with pytest.raises(CtyValidationError) as exc_info:
            SupsrcConfigCty({
                "global": {},
                "repositories": {
                    "test": {
                        "path": "/tmp",
                        "monitoring": {
                            "interval": "2h"  # More than 1h maximum
                        }
                    }
                }
            })
        
        assert "must be <= 1h" in str(exc_info.value)
    
    def test_template_string_validation(self):
        """Test template string validation."""
        config = SupsrcConfigCty({
            "global": {
                "default_commit_message": "{{repo_id}}: {{change_summary}}"
            },
            "repositories": {}
        })
        
        # Should parse template variables
        assert "{{repo_id}}" in config.global_.default_commit_message
        assert config.global_.default_commit_message.is_template
    
    def test_dynamic_rule_types(self):
        """Test dynamic rule type handling."""
        config = SupsrcConfigCty({
            "global": {},
            "repositories": {
                "repo1": {
                    "path": "/tmp",
                    "rule": {
                        "type": "inactivity",
                        "period": "5m"
                    }
                },
                "repo2": {
                    "path": "/tmp",
                    "rule": {
                        "type": "save_count",
                        "count": 10
                    }
                }
            }
        })
        
        # Different rule types should be handled
        assert config.repositories["repo1"].rule.type == "inactivity"
        assert config.repositories["repo1"].rule.period == timedelta(minutes=5)
        assert config.repositories["repo2"].rule.type == "save_count"
        assert config.repositories["repo2"].rule.count == 10


class TestMonitoringRuleCty:
    """Test monitoring rule CTY types."""
    
    def test_inactivity_rule(self):
        """Test inactivity rule configuration."""
        rule = MonitoringRuleCty({
            "name": "auto-commit-idle",
            "type": "inactivity",
            "enabled": True,
            "conditions": {
                "period": "5m",
                "reset_on_focus": True
            },
            "actions": [
                {
                    "type": "commit",
                    "config": {
                        "message": "Auto-commit after inactivity"
                    }
                }
            ]
        })
        
        assert rule.name == "auto-commit-idle"
        assert rule.type == "inactivity"
        assert rule.conditions.period == timedelta(minutes=5)
        assert len(rule.actions) == 1
        assert rule.actions[0].type == "commit"
    
    def test_pattern_rule(self):
        """Test pattern-based rule configuration."""
        rule = MonitoringRuleCty({
            "name": "watch-configs",
            "type": "pattern",
            "conditions": {
                "files": ["*.json", "*.yaml", "*.toml"],
                "content_regex": "version\\s*=\\s*[\"']([^\"']+)[\"']",
                "size_threshold": 1048576  # 1MB in bytes
            },
            "actions": [
                {
                    "type": "notify",
                    "config": {
                        "message": "Configuration file changed"
                    }
                },
                {
                    "type": "analyze",
                    "config": {
                        "check_syntax": True
                    }
                }
            ]
        })
        
        assert rule.type == "pattern"
        assert len(rule.conditions.files) == 3
        assert rule.conditions.size_threshold == 1048576
        assert len(rule.actions) == 2
    
    def test_action_validation(self):
        """Test action type validation."""
        with pytest.raises(CtyValidationError) as exc_info:
            MonitoringRuleCty({
                "name": "bad-action",
                "type": "inactivity",
                "conditions": {"period": "5m"},
                "actions": [
                    {
                        "type": "invalid_action",  # Not in enum
                        "config": {}
                    }
                ]
            })
        
        assert "invalid_action" in str(exc_info.value)
        assert "must be one of" in str(exc_info.value)


class TestCtyHelperFunctions:
    """Test CTY helper functions."""
    
    def test_validate_duration(self):
        """Test duration validation function."""
        # Valid durations
        assert validate_duration("5s") == timedelta(seconds=5)
        assert validate_duration("1m30s") == timedelta(minutes=1, seconds=30)
        assert validate_duration("2h") == timedelta(hours=2)
        assert validate_duration("1h30m45s") == timedelta(hours=1, minutes=30, seconds=45)
        
        # Invalid durations
        with pytest.raises(ValueError):
            validate_duration("invalid")
        
        with pytest.raises(ValueError):
            validate_duration("5x")
        
        with pytest.raises(ValueError):
            validate_duration("-5s")  # Negative duration
    
    def test_validate_path(self):
        """Test path validation function."""
        # Valid paths
        assert validate_path("/tmp") == Path("/tmp")
        assert validate_path("~") == Path.home()
        assert validate_path(".") == Path.cwd()
        
        # Expanduser
        assert validate_path("~/test") == Path.home() / "test"
        
        # Non-existent path (should not raise by default)
        result = validate_path("/does/not/exist", must_exist=False)
        assert result == Path("/does/not/exist")
        
        # Must exist validation
        with pytest.raises(ValueError) as exc_info:
            validate_path("/does/not/exist", must_exist=True)
        
        assert "does not exist" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])