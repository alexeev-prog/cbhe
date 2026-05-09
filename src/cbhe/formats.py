import json
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class FieldType(Enum):
    MAGIC = auto()
    SIZE = auto()
    OFFSET = auto()
    FLAGS = auto()
    CHECKSUM = auto()
    VERSION = auto()
    DATA = auto()
    RESERVED = auto()
    HEADER = auto()
    UNKNOWN = auto()


_FIELD_TYPE_MAP: dict[str, FieldType] = {ft.name: ft for ft in FieldType}


@dataclass
class FieldDef:
    offset: int
    length: int
    name: str
    ftype: FieldType


@dataclass
class FormatDef:
    name: str
    mime: str
    signatures: list[tuple[int, bytes]]
    fields: list[FieldDef]
    _index: dict[int, FieldDef] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._build_index()

    def _build_index(self) -> None:
        self._index = {}
        for fdef in self.fields:
            for off in range(fdef.offset, fdef.offset + fdef.length):
                self._index[off] = fdef

    def match(self, data: bytes) -> bool:
        for offset, sig in self.signatures:
            if offset + len(sig) > len(data):
                return False
            if data[offset : offset + len(sig)] != sig:
                return False
        return True

    def get_field_at(self, offset: int) -> Optional[FieldDef]:
        return self._index.get(offset)


FORMATS: list[FormatDef] = []

BUILTIN_FORMATS: list[FormatDef] = [
    FormatDef(
        name="PNG",
        mime="image/png",
        signatures=[(0, b"\x89PNG\r\n\x1a\n")],
        fields=[
            FieldDef(0, 8, "Signature", FieldType.MAGIC),
            FieldDef(8, 4, "IHDR Length", FieldType.SIZE),
            FieldDef(12, 4, "IHDR Chunk Type", FieldType.HEADER),
            FieldDef(16, 4, "Width", FieldType.SIZE),
            FieldDef(20, 4, "Height", FieldType.SIZE),
            FieldDef(24, 1, "Bit Depth", FieldType.FLAGS),
            FieldDef(25, 1, "Color Type", FieldType.FLAGS),
            FieldDef(26, 1, "Compression", FieldType.FLAGS),
            FieldDef(27, 1, "Filter", FieldType.FLAGS),
            FieldDef(28, 1, "Interlace", FieldType.FLAGS),
            FieldDef(29, 4, "CRC", FieldType.CHECKSUM),
        ],
    ),
    FormatDef(
        name="ELF",
        mime="application/x-elf",
        signatures=[(0, b"\x7fELF")],
        fields=[
            FieldDef(0, 4, "Magic", FieldType.MAGIC),
            FieldDef(4, 1, "Class", FieldType.VERSION),
            FieldDef(5, 1, "Endianness", FieldType.FLAGS),
            FieldDef(6, 1, "Version", FieldType.VERSION),
            FieldDef(7, 1, "OS/ABI", FieldType.FLAGS),
            FieldDef(8, 1, "ABI Version", FieldType.VERSION),
            FieldDef(9, 7, "Padding", FieldType.RESERVED),
            FieldDef(16, 2, "Type", FieldType.FLAGS),
            FieldDef(18, 2, "Machine", FieldType.FLAGS),
            FieldDef(20, 4, "ELF Version", FieldType.VERSION),
            FieldDef(24, 4, "Entry Point (32-bit)", FieldType.OFFSET),
            FieldDef(28, 4, "PH Offset (32-bit)", FieldType.OFFSET),
            FieldDef(32, 4, "SH Offset (32-bit)", FieldType.OFFSET),
            FieldDef(36, 4, "Flags", FieldType.FLAGS),
            FieldDef(40, 2, "Header Size", FieldType.SIZE),
            FieldDef(42, 2, "PH Entry Size", FieldType.SIZE),
            FieldDef(44, 2, "PH Count", FieldType.SIZE),
            FieldDef(46, 2, "SH Entry Size", FieldType.SIZE),
            FieldDef(48, 2, "SH Count", FieldType.SIZE),
            FieldDef(50, 2, "SH String Index", FieldType.OFFSET),
        ],
    ),
    FormatDef(
        name="JPEG",
        mime="image/jpeg",
        signatures=[(0, b"\xff\xd8\xff")],
        fields=[
            FieldDef(0, 2, "SOI Marker", FieldType.MAGIC),
            FieldDef(2, 1, "APP0 Marker", FieldType.MAGIC),
            FieldDef(3, 1, "APP0 Marker", FieldType.MAGIC),
            FieldDef(4, 2, "APP0 Length", FieldType.SIZE),
            FieldDef(6, 5, "JFIF Identifier", FieldType.HEADER),
            FieldDef(11, 2, "JFIF Version", FieldType.VERSION),
            FieldDef(13, 1, "Density Units", FieldType.FLAGS),
            FieldDef(14, 2, "X Density", FieldType.SIZE),
            FieldDef(16, 2, "Y Density", FieldType.SIZE),
            FieldDef(18, 1, "Thumbnail Width", FieldType.SIZE),
            FieldDef(19, 1, "Thumbnail Height", FieldType.SIZE),
        ],
    ),
    FormatDef(
        name="ZIP",
        mime="application/zip",
        signatures=[(0, b"PK\x03\x04")],
        fields=[
            FieldDef(0, 4, "Local File Signature", FieldType.MAGIC),
            FieldDef(4, 2, "Version Needed", FieldType.VERSION),
            FieldDef(6, 2, "Flags", FieldType.FLAGS),
            FieldDef(8, 2, "Compression Method", FieldType.FLAGS),
            FieldDef(10, 2, "Last Mod Time", FieldType.DATA),
            FieldDef(12, 2, "Last Mod Date", FieldType.DATA),
            FieldDef(14, 4, "CRC-32", FieldType.CHECKSUM),
            FieldDef(18, 4, "Compressed Size", FieldType.SIZE),
            FieldDef(22, 4, "Uncompressed Size", FieldType.SIZE),
            FieldDef(26, 2, "Filename Length", FieldType.SIZE),
            FieldDef(28, 2, "Extra Field Length", FieldType.SIZE),
        ],
    ),
]


def _parse_json_format(raw: dict) -> FormatDef:
    signatures = [
        (sig["offset"], bytes.fromhex(sig["hex"])) for sig in raw.get("signatures", [])
    ]
    fields = [
        FieldDef(
            offset=f["offset"],
            length=f["length"],
            name=f["name"],
            ftype=_FIELD_TYPE_MAP.get(f.get("type", "UNKNOWN"), FieldType.UNKNOWN),
        )
        for f in raw.get("fields", [])
    ]
    return FormatDef(
        name=raw["name"],
        mime=raw.get("mime", "application/octet-stream"),
        signatures=signatures,
        fields=fields,
    )


def load_formats_from_json(path: str) -> list[FormatDef]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [_parse_json_format(entry) for entry in data]


def register_format(fmt: FormatDef) -> None:
    FORMATS.append(fmt)


def detect_format(data: bytes) -> Optional[FormatDef]:
    for fmt in FORMATS:
        if fmt.match(data):
            return fmt
    return None


def get_field_at(offset: int, fmt: FormatDef) -> Optional[FieldDef]:
    return fmt.get_field_at(offset)


def _register_builtins() -> None:
    for builtin in BUILTIN_FORMATS:
        register_format(builtin)


_register_builtins()
