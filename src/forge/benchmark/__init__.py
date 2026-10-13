"""Phase 0 pilot benchmark: versioned tasks, B0/B1/F-legacy conditions, deterministic L0
checks, hashed manifests, and file + PostgreSQL persistence.

Protocol: ``docs/benchmark/pilot-protocol.md``. Results are always interpreted as
``INCONCLUSIVE``; deterministic checks do not measure overall prompt quality.
"""

PROTOCOL_ID = "forge-pilot"
PROTOCOL_VERSION = "1"
INTERPRETATION = "INCONCLUSIVE"
