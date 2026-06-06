from datetime import datetime
from datetime import timezone


def utc_now() -> str:
    """
    Return current UTC timestamp string.
    """

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )

    return timestamp