"""
@file ring_buffer_test.py

@brief Standalone functional test for RingBuffer.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )

from ring_buffer import RingBuffer


def expect_equal(
    actual,
    expected,
    description: str
) -> bool:
    """
    @brief Compare actual and expected values.

    @return True on match, otherwise False.
    """

    success = actual == expected

    if success:
        print(
            f"PASS: {description}"
        )
    else:
        print(
            f"FAIL: {description}"
        )

        print(
            f"    actual:   {actual}"
        )

        print(
            f"    expected: {expected}"
        )

    return success


def main() -> int:
    """
    @brief Run RingBuffer functional tests.

    @return 0 on success, non-zero on failure.
    """

    return_code = 0

    buffer = RingBuffer(
        capacity=5
    )

    if not expect_equal(
        buffer.snapshot(),
        [],
        "empty buffer snapshot"
    ):
        return_code = 1

    for iValue in range(
        1,
        6
    ):
        buffer.push(
            iValue
        )

    if not expect_equal(
        buffer.snapshot(),
        [1, 2, 3, 4, 5],
        "filled buffer snapshot"
    ):
        return_code = 1

    status = buffer.get_status()

    if not expect_equal(
        status["count"],
        5,
        "filled buffer count"
    ):
        return_code = 1

    if not expect_equal(
        status["overwrite_count"],
        0,
        "no overwrites before overflow"
    ):
        return_code = 1

    buffer.push(
        6
    )

    buffer.push(
        7
    )

    if not expect_equal(
        buffer.snapshot(),
        [3, 4, 5, 6, 7],
        "overwritten buffer snapshot"
    ):
        return_code = 1

    status = buffer.get_status()

    if not expect_equal(
        status["capacity"],
        5,
        "capacity"
    ):
        return_code = 1

    if not expect_equal(
        status["count"],
        5,
        "count after overwrite"
    ):
        return_code = 1

    if not expect_equal(
        status["total_pushed"],
        7,
        "total pushed after overwrite"
    ):
        return_code = 1

    if not expect_equal(
        status["overwrite_count"],
        2,
        "overwrite count"
    ):
        return_code = 1

    buffer.clear()

    if not expect_equal(
        buffer.snapshot(),
        [],
        "clear snapshot"
    ):
        return_code = 1

    status = buffer.get_status()

    if not expect_equal(
        status["count"],
        0,
        "count after clear"
    ):
        return_code = 1

    if not expect_equal(
        status["total_pushed"],
        0,
        "total pushed after clear"
    ):
        return_code = 1

    print(
        "RingBuffer test complete"
    )

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )