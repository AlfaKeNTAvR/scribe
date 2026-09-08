import os
import time


ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {char: value for value, char in enumerate(ALPHABET)}


def generate(timestamp: int | None = None) -> str:
    """Generate a ULID using a millisecond timestamp and OS randomness."""
    timestamp = int(time.time() * 1000) if timestamp is None else timestamp
    if not 0 <= timestamp < 2**48:
        raise ValueError("timestamp must fit in 48 bits")
    value = (timestamp << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        chars.append(ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def is_valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 26
        and value[0] in "01234567"
        and all(char in _DECODE for char in value)
    )


def timestamp_ms(value: str) -> int:
    if not is_valid(value):
        raise ValueError("invalid ULID")
    result = 0
    for char in value[:10]:
        result = (result << 5) | _DECODE[char]
    return result
