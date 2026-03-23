"""Base91 encoding/decoding module.

Implements Base91 encoding for arbitrary bytes into printable ASCII characters.
Base91 is more efficient than Base64: ~23% overhead vs Base64's ~33%.

The alphabet consists of 91 printable ASCII characters
(all printable chars 33..126 except backslash, single quote, and dash).

Reference: http://base91.sourceforge.net/

Example:
    >>> encoded = encode(b"Hello, World!")
    >>> decode(encoded) == b"Hello, World!"
    True
"""

# Base91 alphabet: 91 chars from printable ASCII (33..126), excluding \\ ' -
ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    '!#$%&()*+,./:;<=>?@[]^_`{|}~"'
)
assert len(ALPHABET) == 91, f"Alphabet must be 91 chars, got {len(ALPHABET)}"

# Reverse lookup: char → index
_DECODE_TABLE: dict[str, int] = {c: i for i, c in enumerate(ALPHABET)}


def encode(data: bytes) -> str:
    """Encode bytes to Base91 ASCII string.

    Args:
        data: The byte sequence to encode.

    Returns:
        A Base91 encoded string containing only printable ASCII characters.
    """
    if not data:
        return ""

    result: list[str] = []
    n = 0  # bit accumulator
    nbits = 0  # number of bits in accumulator

    for byte in data:
        n |= byte << nbits
        nbits += 8

        if nbits > 13:
            val = n & 8191  # lower 13 bits
            if val > 88:
                n >>= 13
                nbits -= 13
            else:
                # val <= 88: use 14 bits to avoid ambiguity
                val = n & 16383
                n >>= 14
                nbits -= 14
            result.append(ALPHABET[val % 91])
            result.append(ALPHABET[val // 91])

    # Flush remaining bits
    if nbits:
        result.append(ALPHABET[n % 91])
        if n >= 91 or nbits > 7:
            result.append(ALPHABET[n // 91])

    return "".join(result)


def decode(text: str) -> bytes:
    """Decode Base91 ASCII string back to bytes.

    Args:
        text: The Base91 encoded string.

    Returns:
        The original byte sequence.

    Raises:
        ValueError: If the input contains invalid Base91 characters.
    """
    if not text:
        return b""

    result = bytearray()
    n = 0  # bit accumulator
    nbits = 0  # number of bits in accumulator
    v = -1  # first char of pair (or -1 if waiting)

    for char in text:
        c = _DECODE_TABLE.get(char)
        if c is None:
            raise ValueError(f"Invalid Base91 character: {char!r}")

        if v == -1:
            # First character of pair
            v = c
        else:
            # Second character of pair — reconstruct value
            v += c * 91
            # Determine how many bits this pair encodes
            b = 13 if (v & 8191) > 88 else 14
            n |= v << nbits
            nbits += b
            v = -1

            # Extract complete bytes
            while nbits >= 8:
                result.append(n & 0xFF)
                n >>= 8
                nbits -= 8

    # Handle trailing single character (odd number of chars)
    if v != -1:
        n |= v << nbits
        nbits += 7  # single char = at most 7 bits of data
        while nbits >= 8:
            result.append(n & 0xFF)
            n >>= 8
            nbits -= 8

    return bytes(result)


if __name__ == "__main__":
    import sys

    test_cases = [
        b"",
        b"Hello, World!",
        b"\x00\x01\x02\xff\xfe\xfd",
        b"A" * 100,
        bytes(range(256)),
        b"\x00",
        b"\xff",
        b"\x00\x00\x00",
    ]

    all_passed = True
    for test in test_cases:
        encoded = encode(test)
        decoded = decode(encoded)
        if decoded != test:
            print(f"FAIL: {test!r}")
            print(f"  encoded:  {encoded!r}")
            print(f"  decoded:  {decoded!r}")
            all_passed = False
        else:
            overhead = (len(encoded) / len(test) - 1) * 100 if test else 0
            print(
                f"PASS: {len(test)} bytes -> {len(encoded)} chars ({overhead:+.1f}% overhead)"
            )

    sys.exit(0 if all_passed else 1)
