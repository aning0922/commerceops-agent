"""Bounded CSV/OOXML subset and quality preview. No files, database, network or execution."""

import base64
import binascii
import codecs
import csv
import hashlib
import io
import re
import stat
import struct
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import ValidationError

from commerceops.application.v4_demo.contracts import Currency
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.analytics import amount_text
from commerceops.domain.commerce_values import facts_hash

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500
MAX_COLUMNS = 24
MAX_UNPACKED_BYTES = 8 * 1024 * 1024
MAX_PART_BYTES = 2 * 1024 * 1024
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
PARTS = frozenset(
    {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        "xl/worksheets/sheet1.xml",
        "xl/sharedStrings.xml",
        "xl/styles.xml",
        "xl/theme/theme1.xml",
        "docProps/core.xml",
        "docProps/app.xml",
    }
)
REQUIRED_PARTS = frozenset(
    {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        "xl/worksheets/sheet1.xml",
    }
)
FORBIDDEN_NODES = frozenset(
    {
        "f",
        "formula",
        "formula1",
        "formula2",
        "definedName",
        "externalReference",
        "externalLink",
        "ddeLink",
        "oleObject",
        "connection",
        "queryTable",
    }
)
ALLOWED_NODES: dict[str, frozenset[str]] = {
    "[Content_Types].xml": frozenset({"Types", "Default", "Override"}),
    "_rels/.rels": frozenset({"Relationships", "Relationship"}),
    "xl/_rels/workbook.xml.rels": frozenset({"Relationships", "Relationship"}),
    "xl/workbook.xml": frozenset(
        {
            "workbook",
            "fileVersion",
            "workbookPr",
            "bookViews",
            "workbookView",
            "sheets",
            "sheet",
            "calcPr",
            "definedNames",
        }
    ),
    "xl/worksheets/sheet1.xml": frozenset(
        {
            "worksheet",
            "dimension",
            "sheetViews",
            "sheetView",
            "selection",
            "sheetFormatPr",
            "cols",
            "col",
            "sheetData",
            "row",
            "c",
            "v",
            "is",
            "t",
            "pageMargins",
        }
    ),
    "xl/sharedStrings.xml": frozenset({"sst", "si", "t"}),
    "xl/styles.xml": frozenset(
        {
            "styleSheet",
            "numFmts",
            "numFmt",
            "fonts",
            "font",
            "name",
            "family",
            "charset",
            "sz",
            "color",
            "b",
            "i",
            "u",
            "scheme",
            "fills",
            "fill",
            "patternFill",
            "fgColor",
            "bgColor",
            "borders",
            "border",
            "left",
            "right",
            "top",
            "bottom",
            "diagonal",
            "cellStyleXfs",
            "xf",
            "alignment",
            "protection",
            "cellXfs",
            "cellStyles",
            "cellStyle",
            "dxfs",
            "dxf",
            "tableStyles",
            "colors",
            "indexedColors",
            "rgbColor",
        }
    ),
    "xl/theme/theme1.xml": frozenset(
        {
            "theme",
            "themeElements",
            "clrScheme",
            "dk1",
            "lt1",
            "dk2",
            "lt2",
            "accent1",
            "accent2",
            "accent3",
            "accent4",
            "accent5",
            "accent6",
            "hlink",
            "folHlink",
            "sysClr",
            "srgbClr",
            "fontScheme",
            "majorFont",
            "minorFont",
            "latin",
            "ea",
            "cs",
            "font",
            "fmtScheme",
            "fillStyleLst",
            "solidFill",
            "schemeClr",
            "gradFill",
            "gsLst",
            "gs",
            "tint",
            "satMod",
            "shade",
            "lumMod",
            "lumOff",
            "lin",
            "path",
            "fillToRect",
            "lnStyleLst",
            "ln",
            "prstDash",
            "miter",
            "headEnd",
            "tailEnd",
            "effectStyleLst",
            "effectStyle",
            "effectLst",
            "outerShdw",
            "bgFillStyleLst",
            "objectDefaults",
            "extraClrSchemeLst",
        }
    ),
    "docProps/core.xml": frozenset(
        {
            "coreProperties",
            "title",
            "subject",
            "creator",
            "keywords",
            "description",
            "lastModifiedBy",
            "revision",
            "created",
            "modified",
            "category",
            "contentStatus",
        }
    ),
    "docProps/app.xml": frozenset(
        {
            "Properties",
            "Application",
            "AppVersion",
            "DocSecurity",
            "ScaleCrop",
            "HeadingPairs",
            "TitlesOfParts",
            "vector",
            "variant",
            "lpstr",
            "i4",
            "Company",
            "LinksUpToDate",
            "SharedDoc",
            "HyperlinksChanged",
        }
    ),
}


class FileRejected(ValueError):
    """Only a fixed safe reason is returned; exception chains/input text are never public."""


@dataclass
class ParseBudget:
    deadline: float = field(default_factory=lambda: time.monotonic() + 2)
    nodes: int = 0

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            raise FileRejected("PARSE_TIMEOUT")


@dataclass(frozen=True)
class ParsedTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    file_digest: str


@dataclass(frozen=True)
class QualityPreview:
    table: ParsedTable
    state: Literal["DISCOVERED", "READY", "INVALID"]
    products: tuple[dto.NormalizedProduct, ...]
    sample: tuple[dto.ImportSample, ...]
    issues: tuple[dto.ImportIssue, ...]
    issue_count: int


def _formula(value: str) -> bool:
    return value.lstrip().startswith(("=", "+", "-", "@"))


def _cell(value: str) -> str:
    if len(value) > 512 or any(not character.isprintable() for character in value):
        raise FileRejected("INVALID_CELL")
    return value


def _table(rows: list[tuple[str, ...]], data: bytes) -> ParsedTable:
    if not rows or not 1 <= len(rows[0]) <= MAX_COLUMNS:
        raise FileRejected("INVALID_HEADER")
    headers = tuple(unicodedata.normalize("NFC", cell.strip()) for cell in rows[0])
    if any(not cell or len(cell) > 80 or _formula(cell) for cell in headers):
        raise FileRejected("INVALID_HEADER")
    if len(set(headers)) != len(headers):
        raise FileRejected("INVALID_HEADER")
    return ParsedTable(headers, tuple(rows[1:]), hashlib.sha256(data).hexdigest())


def decode_file(value: str) -> bytes:
    if len(value) > 2796204:
        raise FileRejected("FILE_LIMIT")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise FileRejected("INVALID_BASE64") from None
    if not data or len(data) > MAX_FILE_BYTES:
        raise FileRejected("FILE_LIMIT")
    if base64.b64encode(data).decode("ascii") != value:
        raise FileRejected("INVALID_BASE64")
    return data


def _csv(data: bytes, budget: ParseBudget) -> ParsedTable:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise FileRejected("CSV_ENCODING") from None
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",", strict=True)
    rows: list[tuple[str, ...]] = []
    try:
        for row in reader:
            budget.check()
            if len(rows) >= MAX_ROWS + 1 or len(row) > MAX_COLUMNS:
                raise FileRejected("TABLE_LIMIT")
            rows.append(tuple(_cell(cell) for cell in row))
    except csv.Error:
        raise FileRejected("CSV_INVALID") from None
    return _table(rows, data)


def _archive(data: bytes, budget: ParseBudget) -> dict[str, bytes]:
    # Check directory count/size before ZipFile allocates central-directory objects.
    offset = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if offset < 0 or offset + 22 > len(data) or not data.startswith(b"PK\x03\x04"):
        raise FileRejected("XLSX_ARCHIVE")
    _, disk, first_disk, local_count, count, size, start, comment = struct.unpack_from(
        "<4s4H2IH", data, offset
    )
    if (
        disk
        or first_disk
        or not 1 <= count <= 32
        or local_count != count
        or size > 32768
        or start + size != offset
        or offset + 22 + comment != len(data)
    ):
        raise FileRejected("XLSX_ARCHIVE_LIMIT")
    parts: dict[str, bytes] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) != count:
                raise FileRejected("XLSX_ARCHIVE_LIMIT")
            for info in infos:
                budget.check()
                if (
                    info.filename not in PARTS
                    or info.filename in parts
                    or info.orig_filename != info.filename
                    or info.flag_bits & 1
                    or stat.S_ISLNK(info.external_attr >> 16)
                    or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                ):
                    raise FileRejected("XLSX_PART_REJECTED")
                if info.file_size > MAX_PART_BYTES or info.file_size > 100 * max(
                    1, info.compress_size
                ):
                    raise FileRejected("XLSX_EXPANSION_LIMIT")
                chunks = bytearray()
                with archive.open(info) as stream:
                    while block := stream.read(16384):
                        budget.check()
                        total += len(block)
                        if total > MAX_UNPACKED_BYTES or len(chunks) + len(block) > MAX_PART_BYTES:
                            raise FileRejected("XLSX_EXPANSION_LIMIT")
                        chunks.extend(block)
                parts[info.filename] = bytes(chunks)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError):
        raise FileRejected("XLSX_ARCHIVE") from None
    if not REQUIRED_PARTS.issubset(parts):
        raise FileRejected("XLSX_REQUIRED_PART")
    return parts


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_events(data: bytes, name: str, budget: ParseBudget) -> Iterator[tuple[str, ET.Element]]:
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    parser: ET.XMLPullParser[ET.Element[str]] = ET.XMLPullParser(events=("start", "end", "pi"))
    tail = ""
    depth = 0
    try:
        for index in range(0, len(data), 4096):
            budget.check()
            text = decoder.decode(data[index : index + 4096], final=index + 4096 >= len(data))
            scan = tail + text
            if "<!" in scan or "\x00" in scan:
                raise FileRejected("UNSAFE_XML")
            if index == 0:
                declaration = re.match(r"\ufeff?<\?xml\s+([^?]*)\?>", text)
                if declaration:
                    encoding = re.search(r"encoding\s*=\s*['\"]([^'\"]+)['\"]", declaration[1])
                    if encoding and encoding[1].lower() not in ("utf-8", "utf8"):
                        raise FileRejected("XML_ENCODING")
            tail = scan[-16:]
            parser.feed(text)
            for parsed_event in parser.read_events():
                budget.check()
                if len(parsed_event) != 2:
                    raise FileRejected("UNSAFE_XML")
                event, element = parsed_event
                if event == "pi":
                    raise FileRejected("UNSAFE_XML")
                if not isinstance(element, ET.Element) or not isinstance(element.tag, str):
                    raise FileRejected("UNSAFE_XML")
                tag = _local(element.tag)
                if event == "start":
                    budget.nodes += 1
                    depth += 1
                    if depth > 16 or budget.nodes > 60000 or len(element.attrib) > 16:
                        raise FileRejected("XML_LIMIT")
                    if any(len(value) > 1024 for value in element.attrib.values()):
                        raise FileRejected("XML_LIMIT")
                    if tag in FORBIDDEN_NODES:
                        raise FileRejected("FORMULA_OR_EXTERNAL_XML")
                    if tag not in ALLOWED_NODES[name]:
                        raise FileRejected("XLSX_NODE_REJECTED")
                else:
                    depth -= 1
                    if element.text is not None and len(element.text) > 8192:
                        raise FileRejected("XML_TEXT_LIMIT")
                yield event, element
        parser.close()
    except (UnicodeError, ET.ParseError):
        raise FileRejected("INVALID_XML") from None
    if depth != 0:
        raise FileRejected("INVALID_XML")


def _metadata(parts: dict[str, bytes], budget: ParseBudget) -> None:
    sheets = []
    root_targets = []
    sheet_targets: dict[str, str] = {}
    main_type = False
    for name, data in parts.items():
        if name in ("xl/worksheets/sheet1.xml", "xl/sharedStrings.xml"):
            continue
        for event, element in _xml_events(data, name, budget):
            if event != "start":
                continue
            tag = _local(element.tag)
            attrs = element.attrib
            if tag == "Relationship":
                kind, target = attrs.get("Type", ""), attrs.get("Target", "")
                allowed = {
                    DOC_REL + suffix
                    for suffix in (
                        "officeDocument",
                        "worksheet",
                        "styles",
                        "sharedStrings",
                        "theme",
                        "extended-properties",
                    )
                } | {
                    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
                }
                if (
                    element.tag != "{" + REL_NS + "}Relationship"
                    or kind not in allowed
                    or attrs.get("TargetMode", "Internal") != "Internal"
                    or not target
                    or ":" in target
                    or "\\" in target
                    or ".." in target.split("/")
                ):
                    raise FileRejected("XLSX_RELATIONSHIP")
                resolved = "xl/" if name.startswith("xl/") and not target.startswith("/") else ""
                resolved += target.lstrip("/")
                if resolved not in parts:
                    raise FileRejected("XLSX_RELATIONSHIP")
                if kind == DOC_REL + "officeDocument":
                    root_targets.append(resolved)
                if kind == DOC_REL + "worksheet":
                    identity = attrs.get("Id", "")
                    if not identity or identity in sheet_targets:
                        raise FileRejected("XLSX_RELATIONSHIP")
                    sheet_targets[identity] = resolved
            elif name == "xl/workbook.xml" and tag == "sheet":
                sheets.append(attrs.get("{" + DOC_REL.rstrip("/") + "}id", ""))
            elif name == "[Content_Types].xml" and tag in ("Default", "Override"):
                content_type = attrs.get("ContentType", "")
                if any(
                    word in content_type.lower() for word in ("macro", "vba", "external", "ole")
                ):
                    raise FileRejected("XLSX_CONTENT_TYPE")
                if attrs.get("PartName") == "/xl/workbook.xml":
                    main_type = content_type == (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
                    )
    if (
        root_targets != ["xl/workbook.xml"]
        or len(sheets) != 1
        or len(sheet_targets) != 1
        or sheet_targets.get(sheets[0]) != "xl/worksheets/sheet1.xml"
        or not main_type
    ):
        raise FileRejected("XLSX_SINGLE_SHEET_REQUIRED")


def _shared_strings(parts: dict[str, bytes], budget: ParseBudget) -> list[str]:
    result: list[str] = []
    if "xl/sharedStrings.xml" not in parts:
        return result
    for event, element in _xml_events(
        parts["xl/sharedStrings.xml"], "xl/sharedStrings.xml", budget
    ):
        if event == "end" and _local(element.tag) == "si":
            if len(result) >= (MAX_ROWS + 1) * MAX_COLUMNS:
                raise FileRejected("SHARED_STRING_LIMIT")
            result.append(
                _cell(
                    "".join(
                        child.text or "" for child in element if child.tag == "{" + SHEET_NS + "}t"
                    )
                )
            )
            element.clear()
    return result


def _sheet(data: bytes, strings: list[str], budget: ParseBudget) -> list[tuple[str, ...]]:
    result: list[tuple[str, ...]] = []
    cells: dict[int, str] = {}
    row_number = 0
    parents: list[str] = []
    children: dict[str, set[str]] = {
        "worksheet": {
            "dimension",
            "sheetViews",
            "sheetFormatPr",
            "cols",
            "sheetData",
            "pageMargins",
        },
        "sheetViews": {"sheetView"},
        "sheetView": {"selection"},
        "cols": {"col"},
        "sheetData": {"row"},
        "row": {"c"},
        "c": {"v", "is"},
        "is": {"t"},
    }
    data_sections = 0
    for event, element in _xml_events(data, "xl/worksheets/sheet1.xml", budget):
        if not element.tag.startswith("{" + SHEET_NS + "}"):
            raise FileRejected("XLSX_NAMESPACE")
        tag = _local(element.tag)
        if event == "start":
            if not parents:
                if tag != "worksheet":
                    raise FileRejected("XLSX_STRUCTURE")
            elif tag not in children.get(parents[-1], set()):
                raise FileRejected("XLSX_STRUCTURE")
            parents.append(tag)
            if tag == "sheetData":
                data_sections += 1
                if data_sections != 1:
                    raise FileRejected("XLSX_STRUCTURE")
        else:
            if not parents or parents.pop() != tag:
                raise FileRejected("XLSX_STRUCTURE")
        if event == "start" and tag == "row":
            row_number = len(result) + 1
            if element.get("r") != str(row_number) or row_number > MAX_ROWS + 1:
                raise FileRejected("TABLE_LIMIT")
            cells = {}
        elif event == "end" and tag == "c":
            reference = re.fullmatch(r"([A-X])([1-9][0-9]{0,2})", element.get("r", ""))
            if reference is None or int(reference[2]) != row_number:
                raise FileRejected("CELL_REFERENCE")
            column = ord(reference[1]) - ord("A")
            if column in cells:
                raise FileRejected("CELL_REFERENCE")
            kind = element.get("t", "n")
            values = [child.text or "" for child in element if _local(child.tag) == "v"]
            if len(values) > 1:
                raise FileRejected("CELL_VALUE")
            value = values[0] if values else ""
            if kind == "inlineStr":
                if values or sum(_local(child.tag) == "is" for child in element) != 1:
                    raise FileRejected("CELL_VALUE")
                value = "".join(
                    node.text or "" for node in element.iter() if node.tag == "{" + SHEET_NS + "}t"
                )
            elif kind == "s":
                if any(_local(child.tag) == "is" for child in element):
                    raise FileRejected("CELL_VALUE")
                if not value.isascii() or not value.isdecimal() or len(value) > 6:
                    raise FileRejected("SHARED_STRING_INDEX")
                index = int(value)
                if not 0 <= index < len(strings):
                    raise FileRejected("SHARED_STRING_INDEX")
                value = strings[index]
            elif kind not in ("n", "str") or element.get("s", "0") != "0":
                raise FileRejected("UNSUPPORTED_CELL_FORMAT")
            elif any(_local(child.tag) == "is" for child in element):
                raise FileRejected("CELL_VALUE")
            cells[column] = _cell(value)
            element.clear()
        elif event == "end" and tag == "row":
            width = max(cells, default=-1) + 1
            result.append(tuple(cells.get(index, "") for index in range(width)))
            element.clear()
    return result


def parse_file(
    data: bytes, format: Literal["csv", "xlsx"], *, budget: ParseBudget | None = None
) -> ParsedTable:
    budget = budget or ParseBudget()
    budget.check()
    if not data or len(data) > MAX_FILE_BYTES:
        raise FileRejected("FILE_LIMIT")
    if format == "csv":
        return _csv(data, budget)
    if format != "xlsx":
        raise FileRejected("FILE_FORMAT")
    parts = _archive(data, budget)
    _metadata(parts, budget)
    strings = _shared_strings(parts, budget)
    return _table(_sheet(parts["xl/worksheets/sheet1.xml"], strings, budget), data)


def quality_preview(
    table: ParsedTable,
    mapping: dto.ColumnMapping | None,
    currency: Currency,
    existing_skus: frozenset[str] = frozenset(),
) -> QualityPreview:
    issues: list[dto.ImportIssue] = []
    issue_count = 0
    products: list[dto.NormalizedProduct] = []
    seen = {value.casefold() for value in existing_skus}

    def issue(row: int, column: str | None, code: dto.ImportIssueCode) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < 100:
            issues.append(dto.ImportIssue(row=row, column=column, code=code))

    positions = {header: index for index, header in enumerate(table.headers)}
    columns = mapping.model_dump() if mapping else {}
    missing = any(name is not None and name not in positions for name in columns.values())
    if missing:
        issue(0, None, "MAPPING_COLUMN_MISSING")
    if not table.rows:
        issue(0, None, "EMPTY_DATA")
    for number, row in enumerate(table.rows, start=2):
        before = issue_count
        if len(row) != len(table.headers):
            issue(number, None, "INVALID_ROW_WIDTH")
            continue
        for column, value in zip(table.headers, row, strict=True):
            if _formula(value):
                issue(number, column, "FORMULA_REJECTED")
        if mapping is None or missing or issue_count != before:
            continue
        sku = row[positions[mapping.sku]].strip()
        title = unicodedata.normalize("NFC", row[positions[mapping.title]].strip())
        price = row[positions[mapping.price]].strip()
        code = row[positions[mapping.currency]].strip()
        tags = (
            tuple(
                unicodedata.normalize("NFC", part.strip())
                for part in row[positions[mapping.tags]].split(";")
            )
            if mapping.tags
            else ()
        )
        if tags == ("",):
            tags = ()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", sku) is None:
            issue(number, mapping.sku, "INVALID_SKU")
        elif sku.casefold() in seen:
            issue(number, mapping.sku, "DUPLICATE_SKU")
        seen.add(sku.casefold())
        if not 1 <= len(title) <= 120:
            issue(number, mapping.title, "INVALID_TITLE")
        if re.fullmatch(r"(0|[1-9][0-9]{0,13})(\.[0-9]{1,6})?", price) is None:
            issue(number, mapping.price, "INVALID_PRICE")
        if code != currency:
            issue(number, mapping.currency, "CURRENCY_MISMATCH")
        if (
            len(tags) > 8
            or len(set(tags)) != len(tags)
            or any(not 1 <= len(tag) <= 24 for tag in tags)
        ):
            issue(number, mapping.tags, "INVALID_TAGS")
        if before == issue_count:
            with localcontext() as context:
                context.prec = 50
                canonical_price = amount_text(Decimal(price))
            try:
                products.append(
                    dto.NormalizedProduct(
                        sku=sku,
                        canonical_sku=sku.casefold(),
                        title=title,
                        price=canonical_price,
                        currency=currency,
                        tags=tags,
                    )
                )
            except ValidationError:
                raise FileRejected("NORMALIZED_PRODUCT_INVALID") from None
    samples = tuple(
        dto.ImportSample(
            row=number, cells=tuple("[REJECTED]" if _formula(cell) else cell for cell in row)
        )
        for number, row in enumerate(table.rows[:20], start=2)
    )
    state: Literal["DISCOVERED", "READY", "INVALID"] = (
        "INVALID" if issue_count else "DISCOVERED" if mapping is None else "READY"
    )
    return QualityPreview(
        table,
        state,
        tuple(products) if not issue_count else (),
        samples,
        tuple(issues),
        issue_count,
    )


def preview_request_digest(command: dto.ImportPreviewInput, file_digest: str) -> str:
    material = command.model_dump(mode="json", exclude={"file_base64"})
    return facts_hash(dict(command=material, file_digest=file_digest))
