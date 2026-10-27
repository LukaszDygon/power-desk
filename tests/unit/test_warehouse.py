import pytest

from power_desk.warehouse import LockRetry, retry_while_locked

NO_WAIT = LockRetry(timeout_seconds=1.0, interval_seconds=0.0)


def test_retry_while_locked_retries_lock_errors_until_the_action_succeeds():
    attempts, retries = [], []

    def flaky() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("IO Error: Could not set lock on file")
        return "done"

    assert retry_while_locked(flaky, NO_WAIT, before_retry=lambda: retries.append(1)) == "done"
    assert (len(attempts), len(retries)) == (3, 2)


def test_retry_while_locked_raises_other_errors_at_once():
    attempts = []

    def broken() -> None:
        attempts.append(1)
        raise ValueError("syntax error")

    with pytest.raises(ValueError, match="syntax error"):
        retry_while_locked(broken, NO_WAIT)
    assert len(attempts) == 1


def test_retry_while_locked_gives_up_after_the_timeout():
    def locked() -> None:
        raise OSError("Conflicting lock is held")

    with pytest.raises(OSError, match="Conflicting lock"):
        retry_while_locked(locked, LockRetry(timeout_seconds=0.0, interval_seconds=0.0))
