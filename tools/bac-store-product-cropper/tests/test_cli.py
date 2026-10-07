# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_store_product_cropper import __version__, gui
from bac_store_product_cropper.cli import TOOL, _main, plan_jobs
from bac_store_product_cropper.export import ExportOptions
from cropper_testkit import make_image

from bac_common.errors import ExternalToolError
from bac_common.testing import assert_standard_flags, invoke


def test_standard_flags():
    assert_standard_flags(_main, TOOL, __version__)


def test_plan_jobs_default_folder_and_dedup(photos: Path):
    jobs = plan_jobs([photos], None, force=False)
    names = [job.source.name for job in jobs]
    assert names == ["square.tif", "tall.png", "UPPER.JPG", "wide.jpg"]  # case-insensitive order
    assert all(job.target.parent == photos / "out_webp" for job in jobs)
    assert jobs[-1].target.name == "wide.webp"
    # The same folder twice, and a file given explicitly as well, is still one job each.
    again = plan_jobs([photos, photos, photos / "wide.jpg"], None, force=False)
    assert len(again) == 4


def test_plan_jobs_out_dir_and_existing(photos: Path, tmp_path: Path):
    out = tmp_path / "web"
    make_image(out / "wide.webp", (10, 10))
    jobs = plan_jobs([photos], out, force=False)
    by_name = {job.source.name: job for job in jobs}
    assert by_name["wide.jpg"].status == "skipped"
    assert by_name["wide.jpg"].note == "exists"
    assert by_name["tall.png"].status == "pending"
    forced = plan_jobs([photos], out, force=True)
    assert all(job.status == "pending" for job in forced)


def test_collision_is_refused_before_any_work(tmp_path: Path):
    make_image(tmp_path / "a" / "p.jpg", (20, 20))
    make_image(tmp_path / "b" / "p.png", (20, 20))
    result = invoke(_main, [str(tmp_path / "a"), str(tmp_path / "b"), "--out-dir", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "same output file" in result.stderr
    assert not (tmp_path / "out").exists()


def test_dry_run_lists_the_plan(photos: Path, monkeypatch):
    monkeypatch.setattr(gui, "run", lambda *a, **k: pytest.fail("the GUI must not open in a dry run"))
    result = invoke(_main, [str(photos), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "wide.jpg" in result.stdout and "out_webp/wide.webp" in result.stdout
    assert "dry run" in result.stdout
    assert "To crop" in result.stdout
    assert not (photos / "out_webp").exists()


def test_existing_outputs_are_reported(photos: Path, monkeypatch):
    make_image(photos / "out_webp" / "tall.webp", (10, 10))
    monkeypatch.setattr(gui, "run", lambda *a, **k: pytest.fail("not reached"))
    result = invoke(_main, [str(photos), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "tall.webp exists" in result.stdout and "--force" in result.stdout


@pytest.mark.parametrize(
    ("argv", "text"),
    [
        (["--start-q", "5", "--min-q", "10"], "start quality must not be below"),
        (["--aspect", "0"], "aspect must be positive"),
        (["--target-kb", "-3"], "negative"),
        (["--max-width", "0"], "max width"),
        (["--min-q", "0"], "between 1 and 100"),
    ],
)
def test_bad_options_exit_2(photos: Path, argv, text):
    result = invoke(_main, [str(photos), *argv])
    assert result.exit_code == 2
    assert text in result.stderr


def test_aspect_accepts_fractions(photos: Path, monkeypatch):
    seen = {}

    def fake_run(jobs, options, *, report):
        seen["aspect"] = options.aspect
        return gui.Counts()

    monkeypatch.setattr(gui, "run", fake_run)
    assert invoke(_main, [str(photos), "--aspect", "4/3"]).exit_code == 0
    assert seen["aspect"] == pytest.approx(4 / 3)
    result = invoke(_main, [str(photos), "--aspect", "4:3"])
    assert result.exit_code == 2 and "not a ratio" in result.stderr
    assert invoke(_main, [str(photos), "--aspect", "1/0"]).exit_code == 2


def test_no_images_and_missing_path(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = invoke(_main, [str(empty)])
    assert result.exit_code == 2 and "No images found" in result.stderr
    result = invoke(_main, [str(tmp_path / "nope")])
    assert result.exit_code == 2 and "No such file" in result.stderr


def test_out_dir_that_is_a_file(photos: Path, tmp_path: Path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    result = invoke(_main, [str(photos), "--out-dir", str(target)])
    assert result.exit_code == 2
    assert "not a directory" in result.stderr


def test_run_reports_and_summarises(photos: Path, monkeypatch):
    """The GUI is replaced by a stand-in that saves the first image, skips one, fails one and quits."""

    def fake_run(jobs, options: ExportOptions, *, report):
        assert isinstance(options, ExportOptions) and options.aspect == 2.0
        counts = gui.Counts(remaining=len(jobs))
        kinds = iter(["done", "skipped", "failed"])
        for job in jobs[:3]:
            kind = next(kinds)
            job.status = kind
            counts.remaining -= 1
            setattr(
                counts,
                {"done": "saved", "skipped": "skipped", "failed": "failed"}[kind],
                getattr(counts, {"done": "saved", "skipped": "skipped", "failed": "failed"}[kind]) + 1,
            )
            report(kind, job, "1000×500 px, 120 kB at q25" if kind == "done" else "broken")
        return counts

    monkeypatch.setattr(gui, "run", fake_run)
    result = invoke(_main, [str(photos), "--aspect", "2"])
    assert result.exit_code == 1, result.output
    assert "✓" in result.stdout and "120 kB at q25" in result.stdout
    assert "✗" in result.stdout and "broken" in result.stdout
    assert "Remaining" in result.stdout


def test_missing_tk_is_an_error(photos: Path, monkeypatch):
    def fake_run(jobs, options, *, report):
        raise ExternalToolError("Tk is not available in this Python.", "Install python3-tk.")

    monkeypatch.setattr(gui, "run", fake_run)
    result = invoke(_main, [str(photos)])
    assert result.exit_code == 1
    assert "Tk is not available" in result.stderr


def test_gui_without_pending_jobs_returns_at_once(photos: Path):
    jobs = plan_jobs([photos], None, force=False)
    for job in jobs:
        job.status = "skipped"
    counts = gui.run(jobs, ExportOptions())
    assert counts.remaining == 0 and counts.saved == 0


def test_gui_import_error_is_reported(photos: Path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tkinter":
            raise ImportError("No module named tkinter")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    jobs = plan_jobs([photos], None, force=False)
    with pytest.raises(ExternalToolError, match="Tk is not available"):
        gui.run(jobs, ExportOptions())
