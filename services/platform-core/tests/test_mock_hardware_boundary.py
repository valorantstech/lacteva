"""SEC-003 / F-01 — a fabricated measurement must never reach production.

FINAL-001: `MockScaleAdapter` derives a weight from `sha256(container_id)` and
`MockAnalyzerAdapter` derives fat/SNF/CLR the same way. Those values are
stored as the transaction's real net weight and quality, and from there they
are priced, settled, paid and receipted. No downstream check can distinguish
an invented reading from a weighed one, because by then it is just a number.

The source was accepted in every environment, including `prod`, and the mobile
app shipped two buttons that used it.

The boundary is enforced in three places on purpose:

  1. `Settings` refuses to start in prod with `allow_mock_hardware=true`, so
     the accident cannot be configured.
  2. `MilkCollectionService` refuses the source, covering both callers — the
     HTTP route and the offline sync replay — before any state is touched.
  3. The adapters themselves refuse to produce a number, so a caller that has
     not been written yet cannot reach around either of the above.

Each of the three is tested here in its own right, because a defence in depth
that has only been tested at the outermost layer is one layer deep.
"""

import pytest

from platform_core.core.config import get_settings
from platform_core.core.errors import ForbiddenError
from tests.test_milk_collection import _engine_fixture
from tests.test_milk_collection_validation import _fresh_tx, _identify


async def _transaction_awaiting_weight(client):
    """A real transaction, driven the ordinary way, parked at the step where
    a weight is next."""
    headers, _, session, supplier = await _engine_fixture(client)
    tid = await _fresh_tx(client, headers, session["id"])
    await _identify(client, headers, tid, "code", value=supplier["code"])
    await client.post(
        f"/v1/milk-transactions/{tid}/milk",
        json={"milk_type": "cow", "container_type": "can", "container_identifier": "SEC-1"},
        headers=headers,
    )
    return headers, tid


@pytest.fixture
def prod_env(monkeypatch):
    """The production POSTURE, without the production environment.

    Flipping `settings.env` to `prod` wholesale would also switch the JWT key
    registry to production mode, which refuses the suite's ephemeral keys —
    the test could then no longer log in to reach the endpoint it is trying to
    test. So this sets the resolved posture directly, and
    `test_mock_hardware_is_off_in_prod_without_anyone_configuring_it` carries
    the other half: that `env=prod` is what produces this posture.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "allow_mock_hardware", False)
    return settings


# --- 1. the resolved predicate ----------------------------------------------


def test_mock_hardware_is_off_in_prod_without_anyone_configuring_it(monkeypatch):
    """The default must be safe. An operator who has never heard of this
    setting still cannot invent milk."""
    settings = get_settings()
    monkeypatch.setattr(settings, "allow_mock_hardware", None)
    for env, expected in (("dev", True), ("test", True), ("staging", True), ("prod", False)):
        monkeypatch.setattr(settings, "env", env)
        assert settings.mock_hardware_enabled is expected, env


def test_an_explicit_setting_wins_outside_prod(monkeypatch):
    """A developer who wants the mocks off in dev can have them off — the
    derivation is a default, not a lock."""
    settings = get_settings()
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "allow_mock_hardware", False)
    assert settings.mock_hardware_enabled is False


def test_production_refuses_to_start_with_mock_hardware_enabled():
    """Requirement 5: the accident is not merely ignored, it is rejected."""
    from platform_core.core.config import Settings

    with pytest.raises(ValueError) as excinfo:
        Settings(
            env="prod",
            allow_mock_hardware=True,
            jwt_algorithm="RS256",
            jwt_keys='[{"kid":"k1","private_pem":"x","public_pem":"y","not_before":"2020-01-01"}]',
            rls_enabled=True,
            debug=False,
            cors_origins=("https://admin.example",),
            database_url="postgresql+asyncpg://someone:s3cret@db/lacteva",
            event_bus="rabbitmq",
            outbox_mode="background",
            rate_limit_backend="redis",
            minio_secret_key="a-real-secret",
            notification_sms_provider="disabled",
            notification_email_provider="disabled",
            backup_offsite_endpoint="s3.example.com",
            backup_offsite_access_key="k",
            backup_offsite_secret_key="s",
        )
    assert "LACTEVA_ALLOW_MOCK_HARDWARE" in str(excinfo.value)


# --- 2. the service, which covers HTTP and offline sync alike ---------------


async def test_production_refuses_a_mock_weight_over_the_api(client, prod_env):
    """The end-to-end statement of F-01, over real HTTP."""
    headers, tx_id = await _transaction_awaiting_weight(client)
    r = await client.post(
        f"/v1/milk-transactions/{tx_id}/weight",
        json={"source": "mock_scale"},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    assert r.json()["title"] == "mock_hardware_refused"


async def test_production_refuses_a_mock_quality_reading_over_the_api(client, prod_env):
    headers, tx_id = await _transaction_awaiting_weight(client)
    await client.post(
        f"/v1/milk-transactions/{tx_id}/weight",
        json={"source": "manual", "gross": 20.0, "tare": 2.0},
        headers=headers,
    )
    r = await client.post(
        f"/v1/milk-transactions/{tx_id}/quality",
        json={"source": "mock_analyzer"},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    assert r.json()["title"] == "mock_hardware_refused"


async def test_a_refused_mock_capture_leaves_the_transaction_untouched(client, prod_env):
    """A refusal must not be a partial write. The transaction is still waiting
    for a weight, so a real one can still be captured."""
    headers, tx_id = await _transaction_awaiting_weight(client)
    await client.post(
        f"/v1/milk-transactions/{tx_id}/weight",
        json={"source": "mock_scale"},
        headers=headers,
    )
    after = await client.get(f"/v1/milk-transactions/{tx_id}", headers=headers)
    assert after.json()["state"] == "MILK_RECEIVED"
    assert after.json()["net_weight"] is None

    real = await client.post(
        f"/v1/milk-transactions/{tx_id}/weight",
        json={"source": "manual", "gross": 20.0, "tare": 2.0},
        headers=headers,
    )
    assert real.status_code == 200
    assert real.json()["net_weight"] == 18.0


async def test_setting_the_environment_to_prod_is_what_closes_the_door(client, monkeypatch):
    """Joins the two halves: nothing but `env=prod` is configured, and the
    capture is refused. The login happens first, because production settings
    also change how JWT keys are resolved."""
    headers, tx_id = await _transaction_awaiting_weight(client)

    settings = get_settings()
    monkeypatch.setattr(settings, "allow_mock_hardware", None)
    monkeypatch.setattr(settings, "env", "prod")

    r = await client.post(
        f"/v1/milk-transactions/{tx_id}/weight",
        json={"source": "mock_scale"},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    assert r.json()["title"] == "mock_hardware_refused"


async def test_development_still_gets_its_mocks(client):
    """Requirement 3. The point is to stop production inventing milk, not to
    take the tooling away from the people who need it."""
    headers, tx_id = await _transaction_awaiting_weight(client)
    r = await client.post(
        f"/v1/milk-transactions/{tx_id}/weight",
        json={"source": "mock_scale"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["net_weight"] > 0


async def test_the_offline_sync_replay_cannot_smuggle_a_mock_reading_in(prod_env):
    """The second caller, and the one a client controls most directly.

    The mobile app queues operations offline and replays them on sync. If the
    boundary lived only in the HTTP route, a queued `capture_weight` with
    `source=mock_scale` would walk straight past it — the replay calls the
    service directly. Both callers reach `capture_weight`, which is why the
    refusal lives there.
    """
    from platform_core.modules.sync.service import OPERATION_KINDS

    assert "capture_weight" in OPERATION_KINDS
    assert "capture_quality" in OPERATION_KINDS

    from platform_core.modules.milk_collection.service import _refuse_mock_source

    for source in ("mock_scale", "mock_analyzer"):
        with pytest.raises(ForbiddenError):
            _refuse_mock_source(source)


# --- 3. the adapters, the last line ----------------------------------------


def test_the_adapters_refuse_to_fabricate_a_reading_in_prod(prod_env):
    """A caller that does not exist yet must not be able to reach around the
    service check. This is the assertion that keeps the guarantee true for
    code nobody has written."""
    from platform_core.infrastructure.hardware import (
        MockHardwareRefused,
        mock_analyzer,
        mock_scale,
    )

    with pytest.raises(MockHardwareRefused):
        mock_scale.read("CAN-1")
    with pytest.raises(MockHardwareRefused):
        mock_analyzer.read("CAN-1")


def test_the_adapters_still_work_where_they_are_meant_to(monkeypatch):
    from platform_core.infrastructure.hardware import mock_analyzer, mock_scale

    settings = get_settings()
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "allow_mock_hardware", None)
    assert mock_scale.read("CAN-1").gross_kg > 0
    assert mock_analyzer.read("CAN-1").fat > 0


def test_the_refusal_is_a_403_with_a_translatable_message(prod_env):
    """The operator-facing half. A field worker who taps a stale button needs
    to be told to weigh the milk, not shown a stack trace."""
    from platform_core.core.i18n import translate
    from platform_core.infrastructure.hardware import MockHardwareRefused, mock_scale

    with pytest.raises(MockHardwareRefused) as excinfo:
        mock_scale.read("CAN-1")
    assert excinfo.value.status_code == 403
    for locale in ("en", "sw", "hi"):
        assert translate(excinfo.value.message_key, locale) != excinfo.value.message_key
