import logging
import time

import requests
from django.core.cache import cache

from .adapters.base import CourierAuthError, CourierError, CourierUnavailable

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 1.5)
RETRY_STATUS = {408, 429, 500, 502, 503, 504}

BREAKER_THRESHOLD = 5
BREAKER_COOLDOWN = 120


def _breaker_key(courier_code):
    return f"courier:breaker:{courier_code}"


def circuit_is_open(courier_code):
    state = cache.get(_breaker_key(courier_code))
    return bool(state and state.get("failures", 0) >= BREAKER_THRESHOLD)


def record_failure(courier_code):
    key = _breaker_key(courier_code)
    state = cache.get(key) or {"failures": 0}
    state["failures"] = state.get("failures", 0) + 1
    cache.set(key, state, BREAKER_COOLDOWN)
    return state["failures"]


def record_success(courier_code):
    cache.delete(_breaker_key(courier_code))


def request(
    courier_code,
    method,
    url,
    *,
    headers=None,
    json_body=None,
    params=None,
    timeout=DEFAULT_TIMEOUT,
    retry=True,
):
    if circuit_is_open(courier_code):
        raise CourierUnavailable(
            "This courier is temporarily unreachable. Book manually or try "
            "again shortly.",
            details={"courier": courier_code},
        )

    attempts = MAX_ATTEMPTS if retry else 1
    last_error = None

    for attempt in range(attempts):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            last_error = exc
            logger.warning(
                "Courier %s timed out on attempt %s: %s",
                courier_code, attempt + 1, url,
            )
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "Courier %s request failed on attempt %s: %s",
                courier_code, attempt + 1, exc,
            )
        else:
            if response.status_code in (401, 403):
                record_failure(courier_code)
                raise CourierAuthError(
                    "The courier rejected the stored credentials.",
                    details={"courier": courier_code,
                             "status": response.status_code},
                )
            if response.status_code in RETRY_STATUS and attempt < attempts - 1:
                last_error = CourierError(
                    f"Courier returned {response.status_code}."
                )
                time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                continue
            if response.status_code >= 500:
                record_failure(courier_code)
                raise CourierUnavailable(
                    "The courier service is not responding.",
                    details={"courier": courier_code,
                             "status": response.status_code},
                )

            record_success(courier_code)
            return response

        if attempt < attempts - 1:
            time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])

    failures = record_failure(courier_code)
    logger.error(
        "Courier %s unreachable after %s attempts (%s consecutive failures)",
        courier_code, attempts, failures,
    )
    raise CourierUnavailable(
        "The courier service is not responding. The parcel was not booked.",
        details={"courier": courier_code, "attempts": attempts},
    ) from last_error


def safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {"raw_text": response.text[:2000]}
