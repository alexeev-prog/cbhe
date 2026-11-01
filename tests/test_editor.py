import tempfile
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from cbhe.constants import EditorMode
from cbhe.formats import FieldType, _parse_json_format
from cbhe.handlers import dispatch_key
from cbhe.hexfile import HexFile
from cbhe.search import SearchPattern
from cbhe.state import EditorState


class EditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sample.bin"

    def open_file(self, data: bytes, **kwargs: object) -> HexFile:
        self.path.write_bytes(data)
        hf = HexFile(str(self.path), **kwargs)
        self.addCleanup(hf.close)
        return hf

    def test_search_sees_edits_and_undo_clears_dirty(self) -> None:
        hf = self.open_file(b"abcdef")
        hf.write_byte(0, 1, ord("Z"))
        self.assertEqual(hf.find_bytes(b"aZc"), 0)
        self.assertIsNone(hf.find_bytes(b"abc"))
        hf.write_byte(0, 1, ord("b"))
        self.assertFalse(hf.is_dirty)

    def test_chunk_boundaries_and_overlapping_matches(self) -> None:
        hf = self.open_file(b"xabababaxababa")
        with patch("cbhe.hexfile._SEARCH_CHUNK", 3):
            self.assertEqual(hf.find_bytes(b"ababa", 2), 3)
            self.assertEqual(hf.find_bytes_backward(b"ababa", 4), 3)
            self.assertEqual(hf.find_bytes_backward(b"ababa", 3), 1)
            self.assertEqual(hf.find_bytes_backward(b"ababa", hf.size), 9)
            self.assertIsNone(hf.find_bytes_backward(b"ababa", 0))

    def test_masks_forward_backward_and_binary(self) -> None:
        hf = self.open_file(bytes.fromhex("48 8b 0a af 48 8b ff a1"))
        pattern = SearchPattern.from_hex("48 8b ?? a?")
        with patch("cbhe.hexfile._SEARCH_CHUNK", 2):
            self.assertEqual(hf.find_pattern(pattern), 0)
            self.assertEqual(hf.find_pattern(pattern, 1), 4)
            self.assertEqual(hf.find_pattern(pattern, hf.size, True), 4)
            self.assertEqual(hf.find_pattern(pattern, 4, True), 0)
        self.assertEqual(hf.find_pattern(SearchPattern.from_hex("?a")), 2)
        for text in ("", "gg", "0xzz"):
            with self.assertRaises(ValueError):
                SearchPattern.from_hex(text)

    def test_atomic_save_and_backup(self) -> None:
        hf = self.open_file(b"abc")
        hf.write_byte(0, 1, ord("Z"))
        hf.save()
        self.assertEqual(self.path.read_bytes(), b"aZc")
        self.assertEqual(Path(str(self.path) + ".bak").read_bytes(), b"abc")
        self.assertFalse(hf.is_dirty)
        hf.write_byte(0, 0, ord("X"))
        with self.assertRaises(FileExistsError):
            hf.save()
        self.assertTrue(hf.is_dirty)
        self.assertEqual(self.path.read_bytes(), b"aZc")
        hf.save(backup=False)
        self.assertEqual(self.path.read_bytes(), b"XZc")

    def test_external_change_refuses_save(self) -> None:
        hf = self.open_file(b"abc")
        hf.write_byte(0, 0, 0)
        self.path.write_bytes(b"external")
        with self.assertRaises(OSError):
            hf.save()
        self.assertEqual(self.path.read_bytes(), b"external")
        self.assertTrue(hf.is_dirty)

    def test_save_as_and_read_only(self) -> None:
        hf = self.open_file(b"abc", read_only=True)
        with self.assertRaises(PermissionError):
            hf.write_byte(0, 0, 0)
        with self.assertRaises(PermissionError):
            hf.save_as(str(self.path), overwrite=True)
        target = Path(self.temp.name) / "copy.bin"
        hf.save_as(str(target))
        self.assertEqual(target.read_bytes(), b"abc")
        with self.assertRaises(FileExistsError):
            hf.save_as(str(target))

    def test_mmap_search_and_save(self) -> None:
        with patch("cbhe.hexfile._LARGE_FILE_THRESHOLD", 1):
            hf = self.open_file(b"abcabc")
            hf.write_byte(0, 0, ord("X"))
            self.assertEqual(hf.find_bytes(b"Xbc"), 0)
            self.assertEqual(hf.find_bytes_backward(b"abc", 6), 3)
            hf.save()
            self.assertEqual(hf.read_range(0, 6), b"Xbcabc")

    def test_undo_after_width_change_and_save(self) -> None:
        hf = self.open_file(bytes(range(64)))
        state = EditorState(hf)
        state.set_mode(EditorMode.HEX)
        state.jump_to_offset(20, 10)
        state.write_ascii("Z")
        state.cycle_width()
        self.assertEqual(state.cursor_offset, 21)
        state.undo()
        self.assertEqual(hf.read_byte(20), 20)
        self.assertFalse(hf.is_dirty)
        state.redo()
        hf.save()
        state.undo()
        self.assertEqual(hf.read_byte(20), 20)
        self.assertTrue(hf.is_dirty)

    def test_selection_copy_fill_paste_export(self) -> None:
        hf = self.open_file(b"abcdefgh")
        state = EditorState(hf)
        state.toggle_selection()
        state.move_cursor(0, 2)
        self.assertEqual(state.selection, (0, 3))
        state.copy_selection()
        state.replace_range(b"Z", fill=True)
        self.assertEqual(hf.read_range(0, 8), b"ZZZdefgh")
        state.undo()
        self.assertEqual(hf.read_range(0, 8), b"abcdefgh")
        state.redo()
        self.assertEqual(hf.read_range(0, 8), b"ZZZdefgh")
        state.toggle_selection()
        state.jump_to_offset(4, 10)
        state.replace_range(state.clipboard)
        self.assertEqual(hf.read_range(0, 8), b"ZZZd abch".replace(b" ", b""))
        state.toggle_selection()
        state.move_cursor(0, 2)
        target = Path(self.temp.name) / "range.bin"
        state.export_selection(str(target))
        self.assertEqual(target.read_bytes(), b"abc")
        with self.assertRaises(FileExistsError):
            state.export_selection(str(target))

    def test_comparison_lengths_and_dirty_bytes(self) -> None:
        hf = self.open_file(b"abc")
        target = Path(self.temp.name) / "other.bin"
        target.write_bytes(b"abXd")
        other = HexFile(str(target))
        self.addCleanup(other.close)
        with patch("cbhe.hexfile._SEARCH_CHUNK", 2):
            self.assertEqual(hf.find_difference(other), 2)
            self.assertEqual(hf.find_difference(other, 3), 3)
            self.assertEqual(hf.find_difference(other, 4, True), 3)
        hf.write_byte(0, 2, ord("X"))
        self.assertEqual(hf.find_difference(other), 3)

    def test_nested_structure_validation_and_lookup(self) -> None:
        fmt = _parse_json_format(
            {
                "name": "Test",
                "signatures": [{"offset": 0, "hex": "4142"}],
                "fields": [
                    {
                        "offset": 2,
                        "length": 10,
                        "name": "Header",
                        "type": "HEADER",
                        "fields": [
                            {
                                "offset": 1,
                                "length": 2,
                                "name": "Size",
                                "type": "SIZE",
                                "endian": "big",
                            }
                        ],
                    }
                ],
            }
        )
        self.assertEqual(fmt.get_field_at(3).name, "Size")
        self.assertEqual(fmt.get_field_at(2).ftype, FieldType.HEADER)
        self.assertEqual(fmt.walk_fields()[1][0], 1)
        with self.assertRaises(ValueError):
            _parse_json_format(
                {"name": "Bad", "fields": [{"offset": -1, "length": 1, "name": "Bad"}]}
            )

    def test_quit_confirmation_and_ascii_u(self) -> None:
        hf = self.open_file(b"abc")
        state = EditorState(hf)
        state.set_mode(EditorMode.ASCII)
        state.enter_edit()
        dispatch_key(state, None, ord("u"), 10)
        self.assertEqual(hf.read_byte(0), ord("u"))
        state.exit_edit()
        with patch("cbhe.handlers.draw_input_prompt", return_value=""):
            self.assertTrue(dispatch_key(state, None, ord("q"), 10))
        with patch("cbhe.handlers.draw_input_prompt", return_value="d"):
            self.assertFalse(dispatch_key(state, None, ord("q"), 10))

    def test_empty_file_and_clamped_offset(self) -> None:
        hf = self.open_file(b"")
        state = EditorState(hf)
        state.jump_to_offset(100, 10)
        self.assertEqual(state.cursor_offset, 0)
        state.write_ascii("a")
        self.assertFalse(hf.is_dirty)
        self.assertIsNone(hf.find_bytes(b"a"))

    def test_failed_replace_preserves_source_and_dirty_state(self) -> None:
        hf = self.open_file(b"abc")
        hf.write_byte(0, 0, ord("X"))
        with patch("cbhe.hexfile.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                hf.save(backup=False)
        self.assertEqual(self.path.read_bytes(), b"abc")
        self.assertTrue(hf.is_dirty)
        self.assertEqual(list(Path(self.temp.name).glob(".cbhe-*")), [])

    def test_random_mask_search_against_reference(self) -> None:
        rng = random.Random(42)
        data = bytes(rng.randrange(16) for _ in range(100))
        hf = self.open_file(data)
        hf.write_byte(0, 5, 255)
        data = data[:5] + b"\xff" + data[6:]
        with patch("cbhe.hexfile._SEARCH_CHUNK", 7):
            for _ in range(50):
                length = rng.randrange(1, 12)
                masks = bytes(rng.choice((0, 15, 240, 255)) for _ in range(length))
                values = bytes(rng.randrange(256) & mask for mask in masks)
                pattern = SearchPattern(values, masks)
                matches = [
                    pos
                    for pos in range(len(data) - length + 1)
                    if all(data[pos + i] & masks[i] == values[i] for i in range(length))
                ]
                start = rng.randrange(len(data) + 1)
                forward = next((pos for pos in matches if pos >= start), None)
                backward = next((pos for pos in reversed(matches) if pos < start), None)
                self.assertEqual(hf.find_pattern(pattern, start), forward)
                self.assertEqual(hf.find_pattern(pattern, start, True), backward)


if __name__ == "__main__":
    unittest.main()
