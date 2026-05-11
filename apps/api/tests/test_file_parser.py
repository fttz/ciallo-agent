import asyncio
import json
from io import BytesIO

from fastapi import UploadFile
from openpyxl import Workbook

from app.file_parser import parse_uploaded_file


def _upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def test_parse_csv_as_markdown_table(tmp_path):
    file = _upload("scores.csv", "name,score\n小明,98\nAlice,87\n".encode("utf-8"))

    result = asyncio.run(parse_uploaded_file(str(tmp_path), file, max_chars=4000, web_fetch_timeout_sec=1))

    assert result["kind"] == "sheet"
    assert "| name | score |" in result["content"]
    assert "| 小明 | 98 |" in result["content"]


def test_parse_json_as_pretty_text(tmp_path):
    file = _upload("config.json", json.dumps({"enabled": True, "items": ["a", "b"]}).encode("utf-8"))

    result = asyncio.run(parse_uploaded_file(str(tmp_path), file, max_chars=4000, web_fetch_timeout_sec=1))

    assert result["kind"] == "json"
    assert '"enabled": true' in result["content"]
    assert '"items": [' in result["content"]


def test_parse_xlsx_as_sheet_sections(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "预算"
    sheet.append(["项目", "金额"])
    sheet.append(["服务器", 120])
    xlsx_path = tmp_path / "budget.xlsx"
    workbook.save(xlsx_path)

    file = _upload("budget.xlsx", xlsx_path.read_bytes())

    result = asyncio.run(parse_uploaded_file(str(tmp_path), file, max_chars=4000, web_fetch_timeout_sec=1))

    assert result["kind"] == "sheet"
    assert "## Sheet: 预算" in result["content"]
    assert "| 项目 | 金额 |" in result["content"]
    assert "| 服务器 | 120 |" in result["content"]
