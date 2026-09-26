"""Known tier-2 limitations must match narrowly.

These are pure policy tests: no SITL or Gazebo is needed.
"""
import pytest

from argazui import knownfailures

pytestmark = pytest.mark.tier1


MODEL = {
    "id": "example",
    "expected_failure": {
        "category": "procedure",
        "code": "step-timeout",
        "procedure": "plane_takeoff",
        "detail_contains": "takeoff roll",
    },
}


def test_exact_known_failure_matches():
    assert knownfailures.matches(MODEL, {
        "category": "procedure",
        "code": "step-timeout",
        "procedure": "plane_takeoff",
        "detail": "Confirm the takeoff roll started: takeoff roll never began",
    })


@pytest.mark.parametrize("change", [
    {"category": "environment"},
    {"code": "step-failed"},
    {"procedure": "plane_land"},
    {"detail": "a different timeout"},
])
def test_failure_contract_drift_is_not_hidden(change):
    failure = {
        "category": "procedure",
        "code": "step-timeout",
        "procedure": "plane_takeoff",
        "detail": "Confirm the takeoff roll started: takeoff roll never began",
    }
    failure.update(change)
    assert not knownfailures.matches(MODEL, failure)


def test_models_without_a_declared_failure_never_match():
    assert not knownfailures.matches({"id": "healthy"}, {
        "category": "procedure",
        "code": "step-timeout",
        "procedure": "plane_takeoff",
        "detail": "takeoff roll",
    })
