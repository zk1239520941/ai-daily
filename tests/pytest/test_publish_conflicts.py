"""publish 模块：冲突标记防护测试。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.publish import _assert_no_conflict_markers, _has_conflict_markers


def test_has_conflict_markers(tmp_path: Path):
    clean = tmp_path / "ok.json"
    clean.write_text('{"a": 1}\n', encoding="utf-8")
    dirty = tmp_path / "bad.json"
    dirty.write_text("<<<<<<< Updated upstream\nx\n=======\ny\n>>>>>>> Stashed changes\n", encoding="utf-8")
    assert _has_conflict_markers(clean) is False
    assert _has_conflict_markers(dirty) is True


def test_assert_no_conflict_markers_raises(tmp_path: Path):
    root = tmp_path
    dirty = root / "news-data" / "fetch.json"
    dirty.parent.mkdir(parents=True)
    dirty.write_text("<<<<<<< HEAD\na\n=======\nb\n>>>>>>> x\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="冲突标记"):
        _assert_no_conflict_markers(root, [dirty])


def test_assert_no_conflict_markers_ok(tmp_path: Path):
    clean = tmp_path / "ok.json"
    clean.write_text("{}\n", encoding="utf-8")
    _assert_no_conflict_markers(tmp_path, [clean])
