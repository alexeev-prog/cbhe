import sys
from typing import Generator, TypedDict


class HexDumpResult(TypedDict):
    width: int
    addr: list[str]
    hex_part: list[str]
    ascii_part: list[str]


def chunked_file_reader(
    filename: str, chunk_size: int = 4096
) -> Generator[bytes, None, None]:
    with open(filename, "rb") as file:
        while chunk := file.read(chunk_size):
            yield chunk


def bytes_to_hex_line(chunk: bytes, width: int, offset: int) -> tuple[str, str, str]:
    addr = f"{offset:08x}"

    hex_parts = []
    ascii_parts = []

    for i, b in enumerate(chunk):
        hex_parts.append(f"{b:02x}")
        ascii_parts.append(chr(b) if 32 <= b <= 126 else ".")

    expected_hex_width = width * 3 - 1
    hex_part = " ".join(hex_parts)

    if len(hex_part) < expected_hex_width:
        hex_part = hex_part.ljust(expected_hex_width)

    ascii_part = "".join(ascii_parts)

    return addr, hex_part, ascii_part


def load_hex_file_chunked(filename: str, width: int = 16) -> HexDumpResult:
    result: HexDumpResult = {
        "width": width,
        "addr": [],
        "hex_part": [],
        "ascii_part": [],
    }

    global_offset = 0

    for raw_chunk in chunked_file_reader(filename):
        for i in range(0, len(raw_chunk), width):
            chunk = raw_chunk[i : i + width]
            addr, hex_part, ascii_part = bytes_to_hex_line(
                chunk, width, global_offset + i
            )
            result["addr"].append(addr)
            result["hex_part"].append(hex_part)
            result["ascii_part"].append(ascii_part)

        global_offset += len(raw_chunk)

    return result


def print_hex_result(result: HexDumpResult) -> None:
    for addr, hex_part, ascii_part in zip(
        result["addr"], result["hex_part"], result["ascii_part"]
    ):
        print(f"{addr}  {hex_part}  {ascii_part}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: cbhe <filename>")
        sys.exit(1)

    print("CBHE - Colored Bytes Hex Editor (C) alexeev-prog")
    result = load_hex_file_chunked(sys.argv[1])
    print_hex_result(result)


if __name__ == "__main__":
    main()
