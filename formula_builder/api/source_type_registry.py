# ═══════════════════════════════════════════════════════════════════════════
# FILE: formula_builder/api/source_type_registry.py
# Source Type Registry — Formula Builder v31 (Phase 1)
# ═══════════════════════════════════════════════════════════════════════════
"""Central registry for all data source types with auto-discovery from hooks.

MOTIVATION:
    Before v31, external apps had to monkey-patch into
    `data_source_registry._data_source_handlers` dict to add custom source types.
    This was fragile, had no metadata, and couldn't be validated.

    v31 introduces `SourceTypeRegistry` — a central singleton that:
      1. AUTO-DISCOVERS source types from `fb_source_types` in hooks.py
      2. STORES METADATA: label, description, config_schema, app, version
      3. VALIDATES source_config against JSON Schema before resolve
      4. SUPPORTS @register_source decorator (backward compatible)
      5. PROVIDES list_all() for admin UI / testing

ARCHITECTURE:
    ┌─ SourceTypeRegistry (singleton) ───────────────────────────┐
    │                                                            │
    │  _handlers: Dict[str, SourceTypeDefinition]                │
    │                                                            │
    │  ┌─ register(source_type, handler, **metadata)             │
    │  │   • Called by @register_source decorator                │
    │  │   • Called by _discover_from_hooks() at startup        │
    │  └────────────────────────────────────────────────────────│
    │                                                            │
    │  ┌─ _discover_from_hooks()                                │
    │  │   • Reads fb_source_types from all installed apps      │
    │  │   • Imports handler modules                            │
    │  │   • Registers with metadata from handler attributes     │
    │  └────────────────────────────────────────────────────────│
    │                                                            │
    │  ┌─ get_config_schema(source_type) → dict                 │
    │  │   • Returns JSON Schema for source_config validation    │
    │  └────────────────────────────────────────────────────────│
    │                                                            │
    │  ┌─ validate_source_config(source_type, config) → errors  │
    │  │   • Validates against config_schema                    │
    │  │   • Returns list of error messages (empty = valid)     │
    │  └────────────────────────────────────────────────────────│
    │                                                            │
    │  ┌─ list_all() → List[SourceTypeDefinition]               │
    │  │   • For admin UI: show all registered source types     │
    │  └────────────────────────────────────────────────────────│
    │                                                            │
    └────────────────────────────────────────────────────────────┘

USAGE (external app registering a handler):
    # In alumglass/hooks.py:
    fb_source_types = [
        "alumglass.fb_handlers.aluminum_price_composite",
        "alumglass.fb_handlers.glass_master_data",
    ]

    # In alumglass/fb_handlers.py:
    from formula_builder.api.source_type_registry import register_source

    @register_source("aluminum_price_composite",
        label="Aluminum Price (Composite Key)",
        description="Look up aluminum price by color, origin, thickness, surface",
        config_schema={...},
        app="alumglass",
        batchable=True,
        fingerprint_fn=lambda cfg: ...,
    )
    def _handle_aluminum_price(binding, doc, resolved_so_far):
        ...

USAGE (admin UI):
    from formula_builder.api.source_type_registry import SourceTypeRegistry
    registry = SourceTypeRegistry.get_instance()
    all_types = registry.list_all()
    # → [{source_type, label, description, app, batchable, config_schema}, ...]
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import frappe


# ═══════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SourceTypeDefinition:
    """Complete metadata for one registered source type."""

    source_type: str
    handler: Callable
    label: str = ""
    description: str = ""
    config_schema: dict = field(default_factory=dict)
    app: str = "formula_builder"
    version: str = "1.0"
    batchable: bool = False
    fingerprint_fn: Optional[Callable] = None
    # Transform metadata
    supports_transform: bool = False
    # Cache metadata
    supports_cache: bool = False
    default_cache_ttl: int = 0

    def to_dict(self) -> dict:
        """Serialize for API/UI (excludes the handler callable)."""
        return {
            "source_type": self.source_type,
            "label": self.label,
            "description": self.description,
            "config_schema": self.config_schema,
            "app": self.app,
            "version": self.version,
            "batchable": self.batchable,
            "supports_transform": self.supports_transform,
            "supports_cache": self.supports_cache,
            "default_cache_ttl": self.default_cache_ttl,
        }


# ═══════════════════════════════════════════════════════════════════════════
# JSON SCHEMA VALIDATION (lightweight, no jsonschema dependency)
# ═══════════════════════════════════════════════════════════════════════════

def _validate_against_schema(
    config: dict, schema: dict, path: str = ""
) -> List[str]:
    """Validate a config dict against a simple JSON Schema subset.

    Supports: type, required, properties, enum, minimum, maximum.
    Returns list of error messages (empty = valid).
    """
    errors: List[str] = []

    if not schema:
        return errors

    schema_type = schema.get("type", "object")

    if schema_type == "object":
        if not isinstance(config, dict):
            errors.append(f"{path}: expected object, got {type(config).__name__}")
            return errors

        # Required fields
        for req in schema.get("required", []):
            if req not in config or config[req] is None:
                errors.append(f"{path}.{req}: required field missing")

        # Properties
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if prop_name in config:
                child_path = f"{path}.{prop_name}" if path else prop_name
                errors += _validate_against_schema(
                    config[prop_name], prop_schema, child_path
                )

    elif schema_type == "string":
        if not isinstance(config, str):
            errors.append(f"{path}: expected string, got {type(config).__name__}")
        elif "enum" in schema and config not in schema["enum"]:
            errors.append(
                f"{path}: '{config}' not in allowed values: {schema['enum']}"
            )

    elif schema_type in ("number", "integer"):
        if not isinstance(config, (int, float)):
            errors.append(f"{path}: expected number, got {type(config).__name__}")
        else:
            if "minimum" in schema and config < schema["minimum"]:
                errors.append(
                    f"{path}: {config} < minimum {schema['minimum']}"
                )
            if "maximum" in schema and config > schema["maximum"]:
                errors.append(
                    f"{path}: {config} > maximum {schema['maximum']}"
                )

    elif schema_type == "array":
        if not isinstance(config, list):
            errors.append(f"{path}: expected array, got {type(config).__name__}")
        elif "items" in schema:
            for i, item in enumerate(config):
                child_path = f"{path}[{i}]"
                errors += _validate_against_schema(
                    item, schema["items"], child_path
                )

    elif schema_type == "boolean":
        if not isinstance(config, bool):
            errors.append(f"{path}: expected boolean, got {type(config).__name__}")

    return errors


# ═══════════════════════════════════════════════════════════════════════════
# SOURCE TYPE REGISTRY — singleton
# ═══════════════════════════════════════════════════════════════════════════

class SourceTypeRegistry:
    """Central registry for all data source type handlers.

    Singleton — use get_instance() to access.
    Auto-discovers from all installed apps on first access.
    """

    _instance: Optional[SourceTypeRegistry] = None

    def __init__(self):
        self._handlers: Dict[str, SourceTypeDefinition] = {}
        self._discovered: bool = False

    @classmethod
    def get_instance(cls) -> SourceTypeRegistry:
        """Get the singleton instance, auto-discovering on first call."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._discover_from_hooks()
            cls._instance._discovered = True
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    # ── Registration ─────────────────────────────────────────────────

    def register(
        self,
        source_type: str,
        handler: Callable,
        *,
        label: str = "",
        description: str = "",
        config_schema: Optional[dict] = None,
        app: str = "formula_builder",
        version: str = "1.0",
        batchable: bool = False,
        fingerprint_fn: Optional[Callable] = None,
        supports_transform: bool = False,
        supports_cache: bool = False,
        default_cache_ttl: int = 0,
    ) -> SourceTypeDefinition:
        """Register a source type handler with full metadata.

        Args:
            source_type: Unique identifier (e.g. "doctype_query").
            handler: The resolve function.
            label: Human-readable name.
            description: What this source does.
            config_schema: JSON Schema for source_config validation.
            app: Which app registered this.
            version: Handler version.
            batchable: Whether this handler supports batch resolution.
            fingerprint_fn: Function to compute batch grouping fingerprint.
            supports_transform: Whether transform config is supported.
            supports_cache: Whether per-source caching is supported.
            default_cache_ttl: Default cache TTL in seconds.

        Returns:
            SourceTypeDefinition that was registered.
        """
        definition = SourceTypeDefinition(
            source_type=source_type,
            handler=handler,
            label=label,
            description=description,
            config_schema=config_schema or {},
            app=app,
            version=version,
            batchable=batchable,
            fingerprint_fn=fingerprint_fn,
            supports_transform=supports_transform,
            supports_cache=supports_cache,
            default_cache_ttl=default_cache_ttl,
        )

        # Attach metadata back to the handler function for backward compat
        if batchable:
            handler.batchable = True
        if fingerprint_fn is not None:
            handler.fingerprint_fn = fingerprint_fn

        self._handlers[source_type] = definition

        # Also register in the legacy dict for backward compat
        try:
            from formula_builder.api.data_source_registry import (
                _data_source_handlers,
            )
            _data_source_handlers[source_type] = handler
        except ImportError:
            pass

        return definition

    # ── Lookup ───────────────────────────────────────────────────────

    def get(self, source_type: str) -> Optional[SourceTypeDefinition]:
        """Get full definition for a source type."""
        return self._handlers.get(source_type)

    def get_handler(self, source_type: str) -> Optional[Callable]:
        """Get just the handler function (backward compat)."""
        definition = self._handlers.get(source_type)
        return definition.handler if definition else None

    def has(self, source_type: str) -> bool:
        """Check if a source type is registered."""
        return source_type in self._handlers

    # ── Listing ──────────────────────────────────────────────────────

    def list_all(self) -> List[SourceTypeDefinition]:
        """Return all registered source types (for admin UI / API)."""
        return sorted(
            self._handlers.values(),
            key=lambda d: (d.app != "formula_builder", d.app, d.label),
        )

    def list_by_app(self, app: str) -> List[SourceTypeDefinition]:
        """Return source types registered by a specific app."""
        return [d for d in self._handlers.values() if d.app == app]

    def list_source_type_names(self) -> List[str]:
        """Return just the source_type identifiers."""
        return sorted(self._handlers.keys())

    # ── Config validation ────────────────────────────────────────────

    def get_config_schema(self, source_type: str) -> dict:
        """Return JSON Schema for a source type's source_config."""
        definition = self._handlers.get(source_type)
        return definition.config_schema if definition else {}

    def validate_source_config(
        self, source_type: str, source_config: dict
    ) -> List[str]:
        """Validate a source_config dict against its schema.

        Returns list of error messages (empty = valid).
        """
        definition = self._handlers.get(source_type)
        if not definition:
            return [f"Unknown source_type: '{source_type}'"]

        schema = definition.config_schema
        if not schema:
            return []  # No schema = always valid

        return _validate_against_schema(source_config, schema)

    def validate_binding_config(self, binding: dict) -> List[str]:
        """Validate a complete binding dict.

        Checks: source_type exists, source_config is valid JSON,
        source_config matches schema.
        """
        errors = []
        source_type = binding.get("source_type", "")

        if not source_type:
            errors.append("source_type is required")
            return errors

        if not self.has(source_type):
            errors.append(f"Unknown source_type: '{source_type}'")
            return errors

        # Parse source_config JSON
        cfg_raw = binding.get("source_config", "{}")
        if isinstance(cfg_raw, str):
            try:
                cfg = json.loads(cfg_raw)
            except json.JSONDecodeError as e:
                errors.append(f"source_config is not valid JSON: {e}")
                return errors
        else:
            cfg = cfg_raw if isinstance(cfg_raw, dict) else {}

        # Validate against schema
        schema_errors = self.validate_source_config(source_type, cfg)
        errors += schema_errors

        return errors

    # ── Auto-discovery ───────────────────────────────────────────────

    def _discover_from_hooks(self) -> None:
        """Auto-discover source types from all installed apps' hooks.py.

        Reads `fb_source_types` hook from each installed app.
        Each entry is a dotted path like:
            "alumglass.fb_handlers.aluminum_price_composite"

        The target module must call @register_source() at import time,
        which triggers self.register().
        """
        try:
            installed_apps = frappe.get_installed_apps()
        except Exception:
            installed_apps = []

        for app in installed_apps:
            try:
                hooks = frappe.get_hooks("fb_source_types", app_name=app)
            except Exception:
                hooks = []

            if not hooks:
                continue

            for handler_path in hooks:
                self._load_handler_from_path(handler_path, app)

    def _load_handler_from_path(self, path: str, app: str) -> None:
        """Import a handler from a dotted path.

        The module is expected to call @register_source() at import time,
        which will call self.register() with metadata.

        If the handler was registered without metadata (old style),
        enrich it with defaults from the import path.
        """
        if not path or "." not in path:
            frappe.log_error(
                f"fb_source_types: invalid handler path '{path}' in app '{app}'",
                "SourceTypeRegistry",
            )
            return

        # Split: "alumglass.fb_handlers.aluminum_price_composite"
        # → module="alumglass.fb_handlers", attr="aluminum_price_composite"
        parts = path.rsplit(".", 1)
        module_path = parts[0]
        attr_name = parts[1] if len(parts) > 1 else None

        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            frappe.log_error(
                f"fb_source_types: cannot import '{module_path}' ({e})",
                "SourceTypeRegistry",
            )
            return

        if attr_name and hasattr(module, attr_name):
            handler = getattr(module, attr_name)
            # If the handler was registered old-style (without metadata),
            # enrich with defaults from the path
            for st, definition in self._handlers.items():
                if definition.handler is handler and not definition.label:
                    definition.label = attr_name.replace("_", " ").title()
                    definition.app = app
                    definition.version = "1.0"
                    break

    # ── Debug / introspection ────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return registry statistics for debugging."""
        apps = {}
        for d in self._handlers.values():
            apps.setdefault(d.app, {"total": 0, "batchable": 0})
            apps[d.app]["total"] += 1
            if d.batchable:
                apps[d.app]["batchable"] += 1

        return {
            "total_source_types": len(self._handlers),
            "total_batchable": sum(
                1 for d in self._handlers.values() if d.batchable
            ),
            "by_app": apps,
        }


# ═══════════════════════════════════════════════════════════════════════════
# DECORATOR — unified registration API
# ═══════════════════════════════════════════════════════════════════════════

def register_source(
    source_type: str,
    *,
    label: str = "",
    description: str = "",
    config_schema: Optional[dict] = None,
    app: str = "formula_builder",
    version: str = "1.0",
    batchable: bool = False,
    fingerprint_fn: Optional[Callable] = None,
    supports_transform: bool = False,
    supports_cache: bool = False,
    default_cache_ttl: int = 0,
):
    """Decorator to register a data source handler with metadata.

    This is the SINGLE canonical way to register a source type.
    Works with SourceTypeRegistry auto-discovery from hooks.py.

    Args:
        source_type: Unique identifier.
        label: Human-readable name for UI.
        description: What this handler does.
        config_schema: JSON Schema dict for source_config validation.
        app: Name of the registering app.
        version: Handler version string.
        batchable: Whether handler supports batch resolution.
        fingerprint_fn: For batch grouping.
        supports_transform: Whether transform config is supported.
        supports_cache: Whether per-source caching is supported.
        default_cache_ttl: Default cache TTL if caching enabled.

    Example:
        @register_source("my_source",
            label="My Data Source",
            description="Fetches data from my custom doctype",
            config_schema={
                "type": "object",
                "required": ["doctype", "fieldname"],
                "properties": {
                    "doctype": {"type": "string"},
                    "fieldname": {"type": "string"},
                },
            },
            app="my_app",
            batchable=True,
        )
        def handle_my_source(binding, doc, resolved_so_far):
            ...
    """
    def decorator(func: Callable) -> Callable:
        # Register in SourceTypeRegistry (v31 — primary)
        try:
            registry = SourceTypeRegistry.get_instance()
            registry.register(
                source_type=source_type,
                handler=func,
                label=label or source_type.replace("_", " ").title(),
                description=description,
                config_schema=config_schema,
                app=app,
                version=version,
                batchable=batchable,
                fingerprint_fn=fingerprint_fn,
                supports_transform=supports_transform,
                supports_cache=supports_cache,
                default_cache_ttl=default_cache_ttl,
            )
        except Exception as e:
            frappe.log_error(
                f"SourceTypeRegistry.register('{source_type}') failed: {e}",
                "SourceTypeRegistry",
            )
            # Fallback: register in legacy dict
            from formula_builder.api.data_source_registry import (
                _data_source_handlers,
            )
            _data_source_handlers[source_type] = func

        # Also register in legacy dict for backward compat (immediate)
        try:
            from formula_builder.api.data_source_registry import (
                _data_source_handlers,
            )
            _data_source_handlers[source_type] = func
        except ImportError:
            pass

        # Set attributes on the function for backward compat
        func._fb_source_type = source_type
        func._fb_label = label

        return func

    return decorator


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS (for admin UI)
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def list_source_types() -> List[dict]:
    """API: List all registered source types for admin UI.

    Returns list of dicts with metadata (no handler functions).
    """
    registry = SourceTypeRegistry.get_instance()
    return [d.to_dict() for d in registry.list_all()]


@frappe.whitelist()
def get_source_type_schema(source_type: str) -> dict:
    """API: Get config_schema for a source type (for form generation)."""
    registry = SourceTypeRegistry.get_instance()
    definition = registry.get(source_type)
    if not definition:
        return {"error": f"Unknown source_type: '{source_type}'"}
    return {
        "source_type": source_type,
        "label": definition.label,
        "description": definition.description,
        "config_schema": definition.config_schema,
        "app": definition.app,
        "batchable": definition.batchable,
        "supports_transform": definition.supports_transform,
    }


@frappe.whitelist()
def validate_binding_source_config(source_type: str, source_config: str) -> dict:
    """API: Validate a source_config JSON against the source type's schema.

    Args:
        source_type: The source type identifier.
        source_config: JSON string of the config.

    Returns:
        {"valid": bool, "errors": [...]}
    """
    try:
        cfg = json.loads(source_config)
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"Invalid JSON: {e}"]}

    registry = SourceTypeRegistry.get_instance()
    errors = registry.validate_source_config(source_type, cfg)
    return {"valid": len(errors) == 0, "errors": errors}


@frappe.whitelist()
def get_registry_stats() -> dict:
    """API: Get SourceTypeRegistry statistics."""
    registry = SourceTypeRegistry.get_instance()
    return registry.get_stats()


@frappe.whitelist()
def test_data_source(source_type: str, source_config: str) -> dict:
    """API: Test a data source by resolving it with given config.

    Returns the resolved value or error.
    """
    registry = SourceTypeRegistry.get_instance()
    definition = registry.get(source_type)
    if not definition:
        return {"error": f"Unknown source_type: '{source_type}'"}

    try:
        cfg = json.loads(source_config)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}

    # Validate first
    errors = registry.validate_source_config(source_type, cfg)
    if errors:
        return {"error": "Validation failed", "validation_errors": errors}

    # Try to resolve
    binding = {
        "variable_name": "_test_",
        "source_type": source_type,
        "source_config": source_config,
        "data_type": "Float",
    }

    try:
        result = definition.handler(binding, doc=None, resolved_so_far={})
        return {
            "success": True,
            "value": result,
            "type": type(result).__name__,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": frappe.get_traceback(),
        }
