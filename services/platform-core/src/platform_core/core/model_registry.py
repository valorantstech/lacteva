"""The complete model registry (CI-001).

`Base.metadata` only knows about tables whose module has been imported. That
makes metadata completeness an *import-order* property, and this platform has
now been bitten by it twice:

1. `migrations/env.py` lost its model imports to a linter autofix, and the
   next autogenerate proposed dropping every table (found in BAK-001).
2. The backup CLI imported only its own models, so a "successful" backup
   captured **one table and three rows** while reporting success (found here,
   in CI-001, by running the CLI against a real seeded database).

Both had the same shape: a process read `Base.metadata` without having caused
every model module to be imported, and nothing complained.

This module is the single answer. `import_all_models()` is a **function call**,
not a bare import, so no linter can remove it as unused and no future refactor
can quietly shrink it. Anything that reads `Base.metadata` for a
whole-schema purpose — migrations, backup, classification — calls it first.

Projection models are included deliberately: they register at consumer
discovery rather than at import, which is exactly how they were missed once
before (SEC-001's RLS coverage).
"""

import structlog

log = structlog.get_logger("model_registry")

_imported = False


def import_all_models() -> int:
    """Import every module that defines tables, and register projections.

    Returns the number of tables now in the metadata, so a caller can assert
    on it rather than trust that this worked.
    """
    global _imported

    # Business and platform modules. Listed explicitly rather than discovered
    # by walking the package: an explicit list fails loudly when a module is
    # renamed, whereas a silent walk would just find one fewer table.
    import platform_core.core.backup.models
    import platform_core.modules.audit.models
    import platform_core.modules.auth.models
    import platform_core.modules.authz.models
    import platform_core.modules.collection_center.models
    import platform_core.modules.configuration.models
    import platform_core.modules.event_relay.models
    import platform_core.modules.identity.models
    import platform_core.modules.milk_collection.models
    import platform_core.modules.notification.models
    import platform_core.modules.operational_readiness.models
    import platform_core.modules.organization.models
    import platform_core.modules.payment.models
    import platform_core.modules.pricing.models
    import platform_core.modules.receipt.models
    import platform_core.modules.reporting.models
    import platform_core.modules.settlement.models
    import platform_core.modules.supplier.models
    import platform_core.modules.sync.models

    # Projections declare their models at discovery, not at import.
    from platform_core.modules.event_relay.consumers import discover_consumers
    from platform_core.modules.event_relay.projections import discover_projections

    discover_consumers()
    discover_projections()

    from platform_core.core.db import Base

    count = len(Base.metadata.tables)
    if not _imported:
        log.debug("models_registered", tables=count)
        _imported = True
    return count
