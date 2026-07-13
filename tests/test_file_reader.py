from pathlib import Path

import pandas as pd
import benchcore.file_reader as file_reader

from benchcore.file_reader import read_file, search_file


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


def test_xlsx_reader_and_search_cover_rows_beyond_preview_head(tmp_path: Path):
    path = tmp_path / "annual.xlsx"
    df = pd.DataFrame(
        {
            "company": [f"company-{i}" for i in range(200)] + ["山东凯马汽车"],
            "net_profit": [i for i in range(200)] + [-8343],
        }
    )
    df.to_excel(path, index=False)

    preview = read_file(path, 600)
    hits = search_file(path, ["山东凯马汽车", "-8343"])

    assert "middle truncated" in preview
    assert "山东凯马汽车" in preview
    assert hits["山东凯马汽车"] is not None
    assert hits["-8343"] is not None


def test_legacy_doc_reader_does_not_route_binary_doc_to_python_docx(tmp_path: Path, monkeypatch):
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"legacy")
    monkeypatch.setattr(file_reader.shutil, "which", lambda name: None)

    text = read_file(path)

    assert "legacy .doc parsing unavailable" in text
