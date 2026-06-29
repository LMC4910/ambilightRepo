"""Tests for the served GitHub rule taxonomy (event types + actions per event)."""

from ambilight.integrations.github import taxonomy


def test_event_actions_keys_are_known_event_types():
    event_values = {v for v, _ in taxonomy.EVENT_TYPES}
    for key in taxonomy.EVENT_ACTIONS:
        assert key in event_values, f"actions for unknown event type {key!r}"


def test_every_event_type_has_a_nonempty_action_list():
    for value, _label in taxonomy.EVENT_TYPES:
        assert value in taxonomy.EVENT_ACTIONS, f"missing actions for {value!r}"
        assert taxonomy.EVENT_ACTIONS[value], f"empty action list for {value!r}"


def test_key_actions_present():
    assert "merged" in taxonomy.EVENT_ACTIONS["pull_request"]
    assert "failure" in taxonomy.EVENT_ACTIONS["workflow_run"]
    # ci_activity is what the notifications path emits for CI runs.
    assert "ci_activity" in taxonomy.EVENT_ACTIONS["workflow_run"]


def test_meta_shape_is_json_ready():
    m = taxonomy.meta()
    assert {"event_types", "actions_by_event"} <= set(m)
    assert all(set(e) == {"value", "label"} for e in m["event_types"])
    assert isinstance(m["actions_by_event"], dict)
    assert m["actions_by_event"]["workflow_run"]
