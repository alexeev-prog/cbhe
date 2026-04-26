import sys
from typing import Generator, TypedDict


class HexDumpResult(TypedDict):
    width: int
    addr: list[str]
    hex_part: list[str]
    ascii_part: list[str]


COLOR_RESET = "\033[0m"


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h % 360.0
    c = v * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = v - c

    if 0 <= h < 60:
        r, g, b = c, x, 0.0
    elif 60 <= h < 120:
        r, g, b = x, c, 0.0
    elif 120 <= h < 180:
        r, g, b = 0.0, c, x
    elif 180 <= h < 240:
        r, g, b = 0.0, x, c
    elif 240 <= h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x

    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


def gradient_color(byte_value: int) -> str:
    if byte_value == 0x00:
        return "\033[38;2;64;64;64m"

    if byte_value == 0xFF:
        return "\033[38;2;255;255;255m"

    hue = (byte_value / 255.0) * 360.0

    r, g, b = hsv_to_rgb(hue, 0.8, 0.9)

    return f"\033[38;2;{r};{g};{b}m"


def ascii_color(byte_value: int) -> str:
    if 32 <= byte_value <= 126:
        gray = 150 + int((byte_value - 32) / 94 * 105)
        return f"\033[38;2;{gray};{gray};{gray}m"

    dark_gray = 40 + int(byte_value % 64)
    return f"\033[38;2;{dark_gray};{dark_gray};{dark_gray}m"


def colorize_hex_digit(byte_value: int, hex_digit: str) -> str:
    return f"{gradient_color(byte_value)}{hex_digit}{COLOR_RESET}"


def colorize_ascii_char(byte_value: int, char: str) -> str:
    return f"{ascii_color(byte_value)}{char}{COLOR_RESET}"


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
