import sys
from typing import Generator, TypedDict


class HexDumpResult(TypedDict):
    width: int
    addr: list[str]
    hex_part: list[str]
    ascii_part: list[str]


COLOR_RESET = "\033[0m"


def color_for_high_nibble(byte_value: int) -> str:
    high_nibble = (byte_value >> 4) & 0x0F

    if byte_value == 0x00:
        return "\033[90m"
    if byte_value == 0xFF:
        return "\033[97m"

    colors = [
        "\033[91m",
        "\033[38;5;208m",
        "\033[93m",
        "\033[92m",
        "\033[38;5;82m",
        "\033[96m",
        "\033[94m",
        "\033[95m",
        "\033[38;5;205m",
        "\033[38;5;50m",
        "\033[38;5;39m",
        "\033[95m",
        "\033[35m",
        "\033[91m",
        "\033[90m",
        "\033[91m",
    ]

    return colors[high_nibble]


def colorize_hex_digit(byte_value: int, hex_digit: str) -> str:
    color = color_for_high_nibble(byte_value)
    return f"{color}{hex_digit}{COLOR_RESET}"


def colorize_ascii_char(byte_value: int, char: str) -> str:
    if byte_value == 0x20:
        return f"\033[38;5;240m{char}{COLOR_RESET}"

    if 48 <= byte_value <= 57:
        return f"\033[93m{char}{COLOR_RESET}"

    if 65 <= byte_value <= 90:
        return f"\033[38;5;82m{char}{COLOR_RESET}"

    if 97 <= byte_value <= 122:
        return f"\033[92m{char}{COLOR_RESET}"

    if 33 <= byte_value <= 126:
        return f"\033[38;5;228m{char}{COLOR_RESET}"

    if 9 <= byte_value <= 13:
        return f"\033[38;5;245m{char}{COLOR_RESET}"

    return f"\033[90m{char}{COLOR_RESET}"


def format_hex_group(chunk: bytes, start: int, end: int) -> str:
    hex_parts = []
    for i in range(start, end):
        if i < len(chunk):
            b = chunk[i]
            hex_parts.append(colorize_hex_digit(b, f"{b:02x}"))
        else:
            hex_parts.append("  ")
    return " ".join(hex_parts)


def bytes_to_hex_line(chunk: bytes, width: int, offset: int) -> tuple[str, str, str]:
    addr = f"{offset:08x}"

    hex_groups = []
    for i in range(0, width, 4):
        hex_groups.append(format_hex_group(chunk, i, i + 4))

    hex_part = "  ".join(hex_groups)

    ascii_chars = []
    for i, b in enumerate(chunk):
        if i >= width:
            break
        ascii_char = chr(b) if 32 <= b <= 126 else "."
        ascii_chars.append(colorize_ascii_char(b, ascii_char))

    ascii_part = "".join(ascii_chars)

    if len(chunk) < width:
        hex_part = hex_part.ljust(width * 3 + (width // 4 - 1) * 2)
        ascii_part = ascii_part.ljust(width)

    return addr, hex_part, ascii_part


def chunked_file_reader(
    filename: str, chunk_size: int = 4096
) -> Generator[bytes, None, None]:
    with open(filename, "rb") as file:
        while chunk := file.read(chunk_size):
            yield chunk


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
    addr_color = "\033[36m"
    sep_color = "\033[37m"

    for addr, hex_part, ascii_part in zip(
        result["addr"], result["hex_part"], result["ascii_part"]
    ):
        print(
            f"{addr_color}{addr}{COLOR_RESET}{sep_color}  {COLOR_RESET}{hex_part}{sep_color}  {COLOR_RESET}{ascii_part}{COLOR_RESET}"
        )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python script.py <filename>")
        sys.exit(1)

    result = load_hex_file_chunked(sys.argv[1])
    print_hex_result(result)


if __name__ == "__main__":
    main()
