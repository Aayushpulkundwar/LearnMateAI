from unittest.mock import Mock

import pytest
from celery.exceptions import TimeoutError

from scripts.retry_failed_documents import retry_sequential


def test_next_retry_is_dispatched_only_after_previous_terminal_result():
    events = []

    def dispatch(document_id):
        events.append(("dispatch", document_id))
        result = Mock(id="task")
        def wait(**kwargs):
            events.append(("finished", document_id))
            return {"status": "completed"}
        result.get.side_effect = wait
        return result

    assert retry_sequential(["a", "b"], dispatch=dispatch) == []
    assert events == [("dispatch", "a"), ("finished", "a"), ("dispatch", "b"), ("finished", "b")]


def test_wait_timeout_stops_dispatching_more_documents():
    dispatch = Mock()
    dispatch.return_value.get.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        retry_sequential(["a", "b"], dispatch=dispatch)
    dispatch.assert_called_once_with("a")


def test_terminal_failure_is_reported_and_next_document_can_run():
    dispatch = Mock()
    outcomes = iter([ValueError("extraction failed"), {"status": "completed"}])
    dispatch.return_value.get.side_effect = lambda **kwargs: next(outcomes)
    assert retry_sequential(["a", "b"], dispatch=dispatch) == ["a"]
