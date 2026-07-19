"""The dev seed must cover every tenant-scoped model.

``scripts/seed_dev.py`` is the fixture set the /ui-validation browser loop and
every dev environment run against — a model the seed never creates is a feature
no one can see in the running app (CLAUDE.md, "Adding a new feature" step 6).
This runs the real seed against the test harness's in-memory DB and asserts a
row per tenant-FK model, turning that doc claim into an enforced invariant.
"""

from tests.conftest import DEFAULT_TEST_TENANT_ID, _scoped_models

# Model name -> one-line reason a runtime-artifact model is excused from the
# seed. Keep empty unless a model genuinely cannot be seeded.
EXEMPT: dict[str, str] = {}


async def test_seed_covers_every_tenant_scoped_model(db):
    from scripts.seed_dev import seed_all

    await seed_all()

    missing = [
        m.__name__
        for m in _scoped_models()
        if m.__name__ not in EXEMPT
        and not await m.filter(tenant_id=DEFAULT_TEST_TENANT_ID).exists()
    ]
    assert not missing, (
        f"scripts/seed_dev.py leaves these tenant-FK models empty for the "
        f"default tenant: {missing}. Add at least one representative row per "
        f"meaningful state (add-feature skill, step 6), or record a reason in "
        f"EXEMPT above."
    )


async def test_seed_is_idempotent_for_scoped_models(db):
    from scripts.seed_dev import seed_all

    await seed_all()
    counts = {
        m.__name__: await m.filter(tenant_id=DEFAULT_TEST_TENANT_ID).count()
        for m in _scoped_models()
    }
    await seed_all()
    recounts = {
        m.__name__: await m.filter(tenant_id=DEFAULT_TEST_TENANT_ID).count()
        for m in _scoped_models()
    }
    grew = {n: (counts[n], recounts[n]) for n in counts if recounts[n] != counts[n]}
    assert not grew, f"re-running seed_all() duplicated rows: {grew}"
