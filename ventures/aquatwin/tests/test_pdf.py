import pathlib

import pytest

from aquatwin import cli, pdf


def test_pdf_engine_failure_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf, "engines", lambda: [])
    src = tmp_path / "x.html"
    src.write_text("<html><body>x</body></html>", encoding="utf-8")
    with pytest.raises(pdf.PdfError):
        pdf.html_to_pdf(src, tmp_path / "x.pdf")


@pytest.mark.skipif(not pdf.engines(), reason="本机没有 PDF 引擎")
def test_html_to_pdf(tmp_path):
    src = tmp_path / "x.html"
    src.write_text("<html><body><h1>AquaTwin</h1></body></html>", encoding="utf-8")
    dst = pdf.html_to_pdf(src, tmp_path / "x.pdf",
                          engine=pdf.engines()[0], title="t")
    assert dst.is_file() and dst.stat().st_size > 1000


@pytest.mark.skipif(not pdf.engines(), reason="本机没有 PDF 引擎")
def test_pdf_cli(tmp_path):
    root = pathlib.Path(__file__).resolve().parents[1]
    rc = cli.main(["pdf", "--scenario", str(root / "scenarios" / "small_6x3.json"),
                   "--out", str(tmp_path / "pdf"), "--engine", pdf.engines()[0]])
    assert rc == 0
    assert (tmp_path / "pdf" / "quote.pdf").stat().st_size > 1000


def test_measurement_schema_cli(capsys):
    rc = cli.main(["schema", "--what", "measurements"])
    assert rc == 0
    import json
    d = json.loads(capsys.readouterr().out)
    assert d["properties"]["schema"]["const"] == "aquatwin.measurements/1"
    assert "time_min" in d["properties"]["runs"]["items"]["required"]
