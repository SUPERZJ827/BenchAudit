from pathlib import Path

from benchcore.file_reader import read_file


def test_plain_reader_keeps_head_and_tail_for_long_files(tmp_path: Path):
    path = tmp_path / "manual.txt"
    path.write_text(
        "important opening\n" + ("middle filler\n" * 300) + "emergency mutual aid agreement\n",
        encoding="utf-8",
    )

    text = read_file(path, 500)

    assert "important opening" in text
    assert "middle truncated" in text
    assert "emergency mutual aid agreement" in text
