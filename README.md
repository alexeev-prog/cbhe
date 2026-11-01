# cbhe

Colored Bytes Hex Editor: a terminal hex editor in Python, with no third-party
runtime dependencies. Uses the standard-library `curses` module (Linux/macOS;
Windows is not supported out of the box). Requires Python 3.13+.

## Install and run

```sh
uv sync
uv run cbhe file.bin
uv run cbhe --read-only file.bin
uv run cbhe --compare original.bin modified.bin
uv run cbhe --formats user_formats.json -w 16 -m hex file.bin
```

Alternatively, install with `pip install .`, then run `cbhe file.bin`.
Use `cbhe --help` for CLI options and **F1** inside the editor for help.

## Features

- HEX and ASCII overwrite editing, byte interpretation, format-aware colors.
- Inclusive range selection, internal copy/paste, fill and binary export.
- Byte-by-byte comparison, difference highlighting and navigation.
- Structure navigator for built-in and custom JSON formats, including nesting.
- UTF-8 text search and HEX search with byte/nibble wildcards.
- Forward/backward search includes unsaved changes and overlapping matches;
  both directions read bounded blocks rather than loading the whole file.
- Undo/redo survives changes in row width; fill/paste is one undo operation.
- Atomic save, backup, external-change detection, read-only mode and exit guard.

## Keys

| Key | Action |
| --- | --- |
| F1 | Help (any key closes it) |
| h / a / r | HEX / ASCII / read mode |
| Arrows, PgUp/PgDn, Home/End | Navigate |
| g | Go to hexadecimal offset |
| w | Cycle 8 / 16 / 32 bytes per row |
| e / Esc | Start / stop editing |
| Ctrl+Z / Ctrl+R | Undo / redo; `u` also undoes outside edit mode |
| Del / Backspace | Overwrite byte with zero (does not resize file) |
| Ctrl+S | Save source, with backup |
| S | Save a copy to a **new** file; original remains open and dirty |
| / | Text search (UTF-8 encoded) |
| ? | HEX search, e.g. `48 8b ?? a? ?f` |
| n / N | Next / previous match, wrapping around |
| v | Start / clear selection; move cursor to extend it |
| y / p | Copy selected bytes / overwrite from internal buffer |
| f | Fill selection with one hexadecimal byte |
| x | Export selection to a new binary file |
| c | Open comparison file; empty input closes comparison |
| ] / [ | Next / previous differing byte, wrapping around |
| t | Structure navigator; arrows/Home/End select, Enter jumps, Esc closes |
| i | Toggle numeric interpretation panel |
| q | Quit; asks save/discard/cancel when dirty |

Commands operate outside edit mode unless noted. While editing, printable ASCII
is data (including `u`); use Ctrl+Z for undo. Escape cancels input prompts.
Selections include both endpoints. Copy is internal, not the system clipboard;
it is limited to 16 MiB, and fill/paste to 1 MiB per operation. Export streams
larger ranges. Pasting never inserts bytes or changes file size.

## Comparison and structure

Comparison is by absolute byte offset, not sequence alignment. Differing bytes
are bold/underlined; the status bar shows the comparison byte and file size.
The header marks active comparison with `[DIFF]`. A longer comparison-only tail
is reported by offset in the status bar; the source cursor stays at its EOF.
The second file is never edited. Close and reopen it to refresh external changes.

The structure overlay lists offsets, lengths, types and live values, including
unsaved edits. Small fields display an unsigned integer in their declared
endianness; larger fields display a HEX preview. Truncated fields are marked.
Built-ins are lightweight fixed-header descriptions, not full validating parsers
(the ELF built-in currently describes ELF32).

Custom definitions are a JSON array, loaded with `-f/--formats` (repeatable) or
`--format-dir`. Nested `fields` have offsets **relative to their parent**;
top-level offsets are absolute. Children must fit within their parent.

```json
[
  {
    "name": "Demo",
    "signatures": [{"offset": 0, "hex": "44454d4f"}],
    "fields": [
      {"offset": 0, "length": 4, "name": "Magic", "type": "MAGIC"},
      {
        "offset": 4, "length": 8, "name": "Header", "type": "HEADER",
        "fields": [
          {"offset": 0, "length": 4, "name": "Size", "type": "SIZE", "endian": "big"},
          {"offset": 4, "length": 4, "name": "Flags", "type": "FLAGS"}
        ]
      }
    ]
  }
]
```

Lengths and offsets are non-negative integers. Endianness defaults to `little`.
Dynamic lengths, pointer following and automatic checksum repair are not supported.
Signatures are detected from the first 1024 bytes. `--no-auto-detect` disables
initial detection.

## Save safety

Ctrl+S streams the edited content into a temporary file in the source directory,
flushes it and atomically replaces the source. It preserves permission bits and
creates `file.bin.bak` without overwriting existing backups. If a backup already
exists, saving requires explicit `yes` to proceed without a new backup.
Save requires directory write access and enough disk space for a full copy.

Changes to source identity, size or timestamps cause saving to fail; no dirty
changes are cleared on failure. Save As/export never overwrite existing paths.
Read-only mode blocks source edits/saves but permits saving a copy. Atomic replace
does not preserve hard-link relationships, ACLs or extended attributes. Concurrent
writers are not locked; avoid editing files modified by another process,
especially memory-mapped files that could be truncated externally.

## Development

```sh
uv run python -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
```

Tests use only the standard library. See [CHANGELOG.md](CHANGELOG.md) for changes
and [docs/article.md](docs/article.md) for the original project article (historical).
