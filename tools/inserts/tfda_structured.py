"""Download and normalize TFDA structured electronic inserts.

The API returns official XML. This module keeps the official section title and
content so a later search layer can show evidence instead of making a clinical
inference.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET


ENDPOINT = "https://mcp.fda.gov.tw/Serv/Query.asmx/GetDrugDoc"
OFFICIAL_HOST = "mcp.fda.gov.tw"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}


class QueryError(ValueError):
    """The requested official API query is invalid."""


class APIResponseError(RuntimeError):
    """TFDA returned an error or an unexpected response."""


class NoDocumentError(APIResponseError):
    """A targeted license or NHI-code lookup returned no document."""


def _parse_date(value: str) -> date:
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise QueryError("日期格式必須是 YYYY/MM/DD 或 YYYY-MM-DD")


@dataclass(frozen=True)
class Query:
    license_code: str = ""
    nhi_code: str = ""
    start_date: str = ""
    end_date: str = ""

    def normalized(self) -> "Query":
        license_code = self.license_code.strip().upper()
        nhi_code = self.nhi_code.strip().upper()
        start_date = self.start_date.strip()
        end_date = self.end_date.strip()

        if license_code and not re.fullmatch(r"[0-9]{2}[A-Z0-9]{6}", license_code):
            raise QueryError("藥證代碼必須是 2 碼證別加 6 碼證號")
        if nhi_code and not re.fullmatch(r"[A-Z0-9]{6,20}", nhi_code):
            raise QueryError("健保碼格式不正確")
        if bool(start_date) != bool(end_date):
            raise QueryError("開始日期與結束日期必須同時提供")

        if start_date:
            start = _parse_date(start_date)
            end = _parse_date(end_date)
            if end < start:
                raise QueryError("結束日期不能早於開始日期")
            # TFDA examples define an inclusive window of at most 10 dates.
            if (end - start).days > 9:
                raise QueryError("官方 API 每次最多查詢 10 天")
            start_date = start.strftime("%Y/%m/%d")
            end_date = end.strftime("%Y/%m/%d")

        if not any((license_code, nhi_code, start_date)):
            raise QueryError("藥證代碼、健保碼或日期區間至少要提供一種")

        return Query(license_code, nhi_code, start_date, end_date)

    @property
    def targeted(self) -> bool:
        return bool(self.license_code or self.nhi_code)

    def api_parameters(self) -> dict[str, str]:
        query = self.normalized()
        return {
            "license": query.license_code,
            "s_code": query.nhi_code,
            "startdate": query.start_date,
            "enddate": query.end_date,
        }


def build_url(query: Query) -> str:
    return f"{ENDPOINT}?{urlencode(query.api_parameters())}"


def _validate_official_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != OFFICIAL_HOST
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise APIResponseError("TFDA API 重新導向到非官方網址")
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_xml(query: Query, attempts: int = 3) -> bytes:
    """Fetch one bounded response, retrying only temporary failures."""
    url = _validate_official_url(build_url(query))
    opener = build_opener(OfficialRedirect())
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "TFDA-label-search/0.1"})
            with opener.open(request, timeout=45) as response:
                _validate_official_url(response.geturl())
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_RESPONSE_BYTES:
                    raise APIResponseError("TFDA API 回應超過 64 MiB 上限")
                payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise APIResponseError("TFDA API 回應超過 64 MiB 上限")
            return payload
        except HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP_CODES or attempt + 1 == attempts:
                raise
        except (TimeoutError, ConnectionError, URLError):
            if attempt + 1 == attempts:
                raise
        time.sleep(2**attempt)
    raise APIResponseError("TFDA API 下載失敗")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    return next((child for child in list(element) if _local_name(child.tag) == name), None)


def _text(element: ET.Element | None) -> str:
    return "" if element is None else "".join(element.itertext()).strip()


def _attr(element: ET.Element, name: str, default: str = "") -> str:
    wanted = name.casefold()
    return next((value for key, value in element.attrib.items() if key.casefold() == wanted), default)


class _HTMLText(HTMLParser):
    BREAKS = {"br", "div", "p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.casefold() in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(source: str) -> str:
    parser = _HTMLText()
    parser.feed(source)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _decode_element(element: ET.Element) -> str:
    raw = _text(element)
    if _attr(element, "encode") != "1" or not raw:
        return raw
    try:
        binary = base64.b64decode("".join(raw.split()), validate=True)
        return binary.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise APIResponseError("TFDA XML 含有無法解碼的文字") from exc


def _parse_rich_text(parent: ET.Element, name: str) -> dict[str, str]:
    element = _first(parent, name)
    if element is None:
        return {"html": "", "text": ""}
    source = _decode_element(element)
    return {"html": source, "text": html_to_text(source)}


def _parse_sections(content: ET.Element | None) -> list[dict]:
    records: list[dict] = []
    counter = 0

    def visit(element: ET.Element, parent_id: str | None, ancestors: list[str]) -> None:
        nonlocal counter
        counter += 1
        number = _text(_first(element, "NO"))
        title_html = _text(_first(element, "TITLE"))
        title = html_to_text(title_html)
        section_id = _attr(element, "ID") or number or f"section-{counter}"
        level_text = _attr(element, "LEVEL", "1")
        try:
            level = int(level_text)
        except ValueError:
            level = 1

        html_fragments: list[str] = []
        text_fragments: list[str] = []
        images: list[dict[str, object]] = []
        for value in _children(element, "VALUE"):
            value_type = _attr(value, "type", "text").casefold()
            if value_type == "image":
                raw = _text(value)
                images.append({
                    "filename": _attr(value, "filename") or _attr(value, "filenme"),
                    "encoding": "base64" if _attr(value, "encode") == "1" else "unknown",
                    "encoded_characters": len("".join(raw.split())),
                })
                continue
            source = _decode_element(value)
            html_fragments.append(source)
            plain = html_to_text(source)
            if plain:
                text_fragments.append(plain)

        content_html = "\n".join(html_fragments)
        content_text = "\n".join(text_fragments)
        path = [*ancestors, title] if title else list(ancestors)
        search_text = "\n".join(part for part in (number, title, content_text) if part)
        records.append({
            "id": section_id,
            "parent_id": parent_id,
            "level": level,
            "number": number,
            "title": title,
            "title_html": title_html,
            "path": path,
            "content_text": content_text,
            "content_html": content_html,
            "search_text": search_text,
            "images": images,
            "style": {
                "border": _attr(element, "border") == "1",
                "redfont": _attr(element, "redfont") == "1",
                "strong": _attr(element, "strong") == "1",
            },
        })
        for child in _children(element, "SECTION"):
            visit(child, section_id, path)

    if content is not None:
        for section in _children(content, "SECTION"):
            visit(section, None, [])
    return records


def _parse_parties(document: ET.Element, tag: str, prefix: str) -> list[dict[str, str]]:
    result = []
    for group in _children(document, tag):
        item = {
            "number": _text(_first(group, f"{prefix}NO")),
            "name": _text(_first(group, f"{prefix}NAME")),
            "address": _text(_first(group, f"{prefix}ADD")),
        }
        if any(item.values()):
            result.append(item)
    return result


def _parse_document(document: ET.Element, query: Query) -> dict:
    info = _first(document, "INFO")
    if info is None:
        raise APIResponseError("TFDA 文件缺少 INFO 基本資料")
    get = lambda name: _text(_first(info, name))
    license_no = get("SNO")
    version = get("VERSION")
    sections = _parse_sections(_first(document, "CONTENT"))
    characteristics = _parse_rich_text(document, "CHARACT")
    warning = _parse_rich_text(document, "WARNING")
    full_text = "\n".join(
        part
        for part in (
            characteristics["text"],
            warning["text"],
            *(section["search_text"] for section in sections),
        )
        if part
    )
    return {
        "id": f"{license_no}:{version}" if version else license_no,
        "source_kind": "tfda_structured_insert",
        "license_no": license_no,
        "matched_license_code": query.license_code,
        "matched_nhi_code": query.nhi_code,
        "drug_name_zh": get("CNAME"),
        "drug_name_en": get("ENAME"),
        "drug_category": get("DTYPE"),
        "display_category": get("SNAME"),
        "version": version,
        "approved_at": get("VDATE"),
        "characteristics": characteristics,
        "warning": warning,
        "sections": sections,
        "full_text": full_text,
        "main_factories": _parse_parties(document, "MAINFACTORY", "FAC"),
        "sub_factories": _parse_parties(document, "SUBFACTORY", "FAC"),
        "companies": _parse_parties(document, "COMPANY", "COM"),
    }


def parse_xml(payload: bytes, query: Query, retrieved_at: str | None = None) -> dict:
    if len(payload) > MAX_RESPONSE_BYTES:
        raise APIResponseError("TFDA XML 超過 64 MiB 上限")
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise APIResponseError("TFDA XML 含有不允許的實體宣告")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise APIResponseError("TFDA 回應不是有效 XML") from exc

    root_name = _local_name(root.tag)
    if root_name.casefold() == "error":
        message = _text(_first(root, "Message")) or "TFDA API 回傳錯誤"
        raise APIResponseError(message)
    if root_name != "ROOTDOCUMENT":
        raise APIResponseError(f"TFDA XML 根節點不正確：{root_name}")

    normalized = query.normalized()
    document_elements = [element for element in root.iter() if _local_name(element.tag) == "DOCUMENT"]
    documents = [_parse_document(element, normalized) for element in document_elements]
    if normalized.targeted and not documents:
        raise NoDocumentError("指定的藥證或健保碼沒有已發布的結構化電子仿單")

    return {
        "schema_version": 1,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        "source": {
            "provider": "衛生福利部食品藥物管理署",
            "endpoint": ENDPOINT,
            "query": normalized.api_parameters(),
        },
        "document_count": len(documents),
        "documents": documents,
    }


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def refresh(
    query: Query,
    output: Path,
    fetch: Callable[[Query], bytes] = fetch_xml,
    retrieved_at: str | None = None,
) -> dict:
    """Fetch, validate, and atomically replace output only after success."""
    normalized = query.normalized()
    payload = fetch(normalized)
    result = parse_xml(payload, normalized, retrieved_at=retrieved_at)
    write_json_atomic(output, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下載 TFDA 結構化電子仿單")
    parser.add_argument("--license-code", default="", help="2 碼證別加 6 碼證號，例如 01016162")
    parser.add_argument("--nhi-code", default="", help="健保藥品代碼")
    parser.add_argument("--start-date", default="", help="YYYY/MM/DD 或 YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="YYYY/MM/DD 或 YYYY-MM-DD")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/inserts/structured-sample.json"),
        help="驗證成功後才會取代的 JSON 檔案",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    query = Query(args.license_code, args.nhi_code, args.start_date, args.end_date)
    result = refresh(query, args.output)
    print(json.dumps({
        "output": str(args.output),
        "document_count": result["document_count"],
        "licenses": [doc["license_no"] for doc in result["documents"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

