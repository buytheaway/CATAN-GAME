"""Keep unrelated integration fixtures from exhausting shared admission budgets.

The full suite intentionally creates hundreds of rooms in one disposable DB.
SEC-03 tests override these finite test-only values with strict small budgets;
the defaults test removes overrides and verifies actual production defaults.
"""
import pytest


@pytest.fixture(autouse=True)
def room_fixture_capacity(monkeypatch):
    monkeypatch.setenv("CATAN_ROOM_CREATE_LIMIT", "10000")
    monkeypatch.setenv("CATAN_ROOM_CREATE_LOBBIES_PER_IP", "10000")
    monkeypatch.setenv("CATAN_ROOM_CREATE_LOBBIES_GLOBAL", "100000")
