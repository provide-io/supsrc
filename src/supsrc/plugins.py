#
# supsrc/plugins.py **Conceptual**
#

import importlib
from importlib.metadata import entry_points
from typing import Protocol, TypeVar

T = TypeVar("T", bound=Protocol)

_plugin_cache: dict[str, Any] = {} # Simple cache

def load_plugin(plugin_type_str: str, expected_protocol: type[T]) -> T:
    """
    Loads a plugin based on its type string (e.g., 'supsrc.rules.inactivity',
    'plugin:my_rule', 'local:my_module.MyClass').

    Checks if the loaded class implements the expected_protocol.
    """
    if plugin_type_str in _plugin_cache:
        instance = _plugin_cache[plugin_type_str]
        if isinstance(instance, expected_protocol): # Check protocol conformance
             return instance
        else:
             # Handle error: cached item doesn't match protocol
             raise TypeError(f"Cached plugin '{plugin_type_str}' does not match protocol {expected_protocol.__name__}")


    if plugin_type_str.startswith("supsrc."):
        # Built-in plugin (convention)
        module_path, class_name = plugin_type_str.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Could not load built-in plugin: {plugin_type_str}") from e

    elif plugin_type_str.startswith("plugin:"):
        # Entry point plugin
        ep_name = plugin_type_str[len("plugin:"):]
        try:
            # Assuming entry point group names like 'supsrc.rules', 'supsrc.conversions', 'supsrc.repository_engines'
            group_name = f"supsrc.{expected_protocol.__name__.lower()}s" # Heuristic, might need refinement
            eps = entry_points(group=group_name)
            plugin_class = eps[ep_name].load()
        except (KeyError, Exception) as e: # Catch broader load errors
            raise ImportError(f"Could not find or load plugin entry point '{ep_name}' in group '{group_name}'") from e

    elif plugin_type_str.startswith("local:"):
        # Local module.Class plugin
        path_str = plugin_type_str[len("local:"):]
        module_path, class_name = path_str.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Could not load local plugin: {path_str}") from e
    else:
        raise ValueError(f"Invalid plugin type format: {plugin_type_str}")

    # Instantiate the plugin (assuming plugins are classes needing instantiation)
    # If plugins are simple functions, adjust this logic.
    try:
         instance = plugin_class()
    except Exception as e:
         raise RuntimeError(f"Failed to instantiate plugin '{plugin_type_str}'") from e


    # Check protocol conformance *after* instantiation
    if not isinstance(instance, expected_protocol):
        raise TypeError(f"Plugin '{plugin_type_str}' does not implement protocol {expected_protocol.__name__}")

    _plugin_cache[plugin_type_str] = instance # Cache the instance
    return instance

# 🔼⚙️
