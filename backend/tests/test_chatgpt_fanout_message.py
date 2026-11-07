"""Host fan-out wording for an unreadable provider response."""


def test_unreadable_chatgpt_response_does_not_invent_a_cause():
    from app.services.face_dataset_service import _EMPTY_MSG

    assert 'look identical here' in _EMPTY_MSG
    assert 'retry' not in _EMPTY_MSG.lower()
