import struct
from typing import Optional

from .hexfile import HexFile

_STRUCT_FORMATS: list[tuple[str, str, str, int]] = [
    ("i8", "int8", ">b", 1),
    ("u8", "uint8", ">B", 1),
    ("i16le", "int16le", "<h", 2),
    ("i16be", "int16be", ">h", 2),
    ("u16le", "uint16le", "<H", 2),
    ("u16be", "uint16be", ">H", 2),
    ("i32le", "int32le", "<i", 4),
    ("i32be", "int32be", ">i", 4),
    ("u32le", "uint32le", "<I", 4),
    ("u32be", "uint32be", ">I", 4),
    ("i64le", "int64le", "<q", 8),
    ("i64be", "int64be", ">q", 8),
    ("u64le", "uint64le", "<Q", 8),
    ("u64be", "uint64be", ">Q", 8),
    ("f32le", "float32le", "<f", 4),
    ("f32be", "float32be", ">f", 4),
    ("f64le", "float64le", "<d", 8),
    ("f64be", "float64be", ">d", 8),
]


def _read_raw(hf: HexFile, offset: int, length: int) -> Optional[bytes]:
    if offset + length > hf.size:
        return None
    chunks: list[int] = []
    for i in range(length):
        chunks.append(hf.read_byte(offset + i))
    return bytes(chunks)


def _fmt_float(v: float) -> str:
    if v != v:
        return "NaN"
    if v == float("inf"):
        return "+Inf"
    if v == float("-inf"):
        return "-Inf"
    return f"{v:.6g}"


def _interpret_struct(raw: bytes, fmt: str, is_float: bool) -> str:
    try:
        (v,) = struct.unpack(fmt, raw)
        return _fmt_float(v) if is_float else str(v)
    except struct.error:
        return "—"


def _interpret_utf8(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8")
        printable = "".join(c if c.isprintable() else "·" for c in text)
        return repr(printable)
    except UnicodeDecodeError:
        return "—"


def _interpret_bits(raw: bytes) -> str:
    return " ".join(f"{b:08b}" for b in raw[:2])


InterpretRow = tuple[str, str]


def interpret_at(hf: HexFile, offset: int) -> list[InterpretRow]:
    rows: list[InterpretRow] = []

    for _key, label, fmt, size in _STRUCT_FORMATS:
        is_float = fmt[-1] in ("f", "d")
        raw = _read_raw(hf, offset, size)
        value = _interpret_struct(raw, fmt, is_float) if raw is not None else "—"
        rows.append((label, value))

    raw1 = _read_raw(hf, offset, 1)
    if raw1 is not None:
        rows.append(("bits(1B)", _interpret_bits(raw1)))

    raw4 = _read_raw(hf, offset, 4)
    if raw4 is not None:
        rows.append(("utf8(4B)", _interpret_utf8(raw4)))

    raw8 = _read_raw(hf, offset, 8)
    if raw8 is not None:
        rows.append(("utf8(8B)", _interpret_utf8(raw8)))

    return rows
