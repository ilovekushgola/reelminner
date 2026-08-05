from scraper import should_retry


def test_retryable_statuses():
    assert should_retry("timeout") is True
    assert should_retry("error: TimeoutError") is True
    assert should_retry("error: SomeError") is True


def test_non_retryable_statuses():
    assert should_retry("ok") is False
    assert should_retry("session_expired") is False
    assert should_retry("unavailable") is False
    assert should_retry("") is False
