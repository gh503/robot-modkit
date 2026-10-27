"""HTML → PDF：优先 WeasyPrint，其次 wkhtmltopdf。

PDF 只是把已经生成的 quote.html/dashboard.html 打印出来，不引入新的计算。
没有渲染引擎时明确报错，不返回空 PDF。
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess


class PdfError(RuntimeError):
    pass


def engines() -> list[str]:
    out = []
    try:
        import weasyprint  # noqa: F401
        out.append("weasyprint")
    except Exception:
        pass
    if shutil.which("wkhtmltopdf"):
        out.append("wkhtmltopdf")
    return out


def html_to_pdf(html_path: str | pathlib.Path, pdf_path: str | pathlib.Path,
                *, engine: str = "auto", title: str = "") -> pathlib.Path:
    src, dst = pathlib.Path(html_path), pathlib.Path(pdf_path)
    if not src.is_file():
        raise PdfError(f"HTML 不存在：{src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    chosen = engine
    if engine == "auto":
        es = engines()
        if not es:
            raise PdfError("没有 PDF 引擎：pip install 'aquatwin[pdf]' 或 apt install wkhtmltopdf")
        chosen = es[0]
    if chosen == "weasyprint":
        try:
            from weasyprint import HTML
        except Exception as e:
            raise PdfError(f"WeasyPrint 不可用：{e}") from e
        HTML(filename=str(src)).write_pdf(str(dst))
    elif chosen == "wkhtmltopdf":
        exe = shutil.which("wkhtmltopdf")
        if not exe:
            raise PdfError("找不到 wkhtmltopdf")
        cmd = [exe, "--quiet", "--enable-local-file-access",
               "--page-size", "A4", "--margin-top", "12mm", "--margin-bottom", "12mm",
               "--margin-left", "12mm", "--margin-right", "12mm"]
        if title:
            cmd += ["--title", title]
        cmd += [str(src), str(dst)]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=90, check=False)
        if r.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
            raise PdfError(f"wkhtmltopdf 失败（{r.returncode}）：{(r.stderr or r.stdout)[-400:]}")
    else:
        raise PdfError(f"未知 PDF 引擎：{engine}")
    if not dst.is_file() or dst.stat().st_size == 0:
        raise PdfError("PDF 输出为空")
    return dst


__all__ = ["PdfError", "engines", "html_to_pdf"]
