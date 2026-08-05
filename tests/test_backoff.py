from scraper import backoff_delay


def test_zero_failures_no_delay():
    assert backoff_delay(0) == 0.0
    assert backoff_delay(-1) == 0.0


def test_exponential_growth():
    assert backoff_delay(1) == 2.0
    assert backoff_delay(2) == 4.0
    assert backoff_delay(3) == 8.0


def test_capped():
    assert backoff_delay(10) == 30.0
    assert backoff_delay(50) == 30.0


def test_custom_base_and_cap():
    assert backoff_delay(2, base=1.0, cap=5.0) == 2.0
    assert backoff_delay(10, base=1.0, cap=5.0) == 5.0
