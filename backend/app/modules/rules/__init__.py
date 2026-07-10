"""Rules Engine context (docs/08-rules-engine.md).

A leaf module: other contexts call *into* it through the ``RuleSystem`` interface and the
registry; it never imports them. All system-specific data is opaque JSON validated by the
owning plugin — no game system is hardcoded into the core (enforced by import-linter).
"""
