import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchPattern:
    values: bytes
    masks: bytes

    def __post_init__(self) -> None:
        if not self.values or len(self.values) != len(self.masks):
            raise ValueError("empty or inconsistent search pattern")

    @classmethod
    def exact(cls, query: bytes) -> "SearchPattern":
        return cls(query, b"\xff" * len(query))

    @classmethod
    def from_hex(cls, text: str) -> "SearchPattern":
        values = bytearray()
        masks = bytearray()
        for token in text.split():
            token = token.removeprefix("0x").removeprefix("0X")
            if len(token) % 2:
                token = "0" + token
            for i in range(0, len(token), 2):
                value = mask = 0
                for char in token[i : i + 2]:
                    value <<= 4
                    mask <<= 4
                    if char != "?":
                        try:
                            value |= int(char, 16)
                        except ValueError:
                            raise ValueError(f"invalid hex token: {token!r}") from None
                        mask |= 15
                values.append(value)
                masks.append(mask)
        return cls(bytes(values), bytes(masks))

    def compile(self) -> re.Pattern[bytes]:
        parts = []
        for value, mask in zip(self.values, self.masks):
            if mask == 255:
                parts.append(re.escape(bytes([value])))
            elif mask == 0:
                parts.append(b".")
            else:
                choices = bytes(b for b in range(256) if b & mask == value)
                parts.append(b"[" + re.escape(choices) + b"]")
        # Lookahead retains overlapping matches when searching backwards.
        return re.compile(b"(?=" + b"".join(parts) + b")", re.DOTALL)
