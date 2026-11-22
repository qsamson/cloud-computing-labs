"""Polls an HTTP endpoint and reports up/down transitions."""

import time
import requests


def probe_once(url: str, timeout: float = 3.0) -> bool:
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def wait_for_state(url: str, want_up: bool, poll_interval: float, max_wait: float, log_rows: list):
    """Poll `url` until it reaches the wanted state (up or down).

    Appends (elapsed_seconds, is_up) to log_rows on every poll.
    Returns the elapsed time in seconds when the target state was reached,
    or None if max_wait was exceeded.
    """

    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start

        if elapsed > max_wait:
            return None

        is_up = probe_once(url)
        log_rows.append((round(elapsed, 2), is_up))

        if is_up == want_up:
            return elapsed

        time.sleep(poll_interval)
