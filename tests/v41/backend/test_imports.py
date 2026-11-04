"""Actual in-memory CSV/OOXML bytes, including malicious containers; no spreadsheet mocks."""

import base64
import io
import struct
import time
import zipfile
from xml.sax.saxutils import escape

import pytest
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.imports import (
    FileRejected,
    ParseBudget,
    decode_file,
    parse_file,
    quality_preview,
)

pytestmark = pytest.mark.offline
MAPPING = dto.ColumnMapping(
    sku="sku", title="title", price="price", currency="currency", tags="tags"
)
CSV = b"sku,title,price,currency,tags\nNEW-1,Example,0.10,TWD,a;b\nNEW-2,Other,12.340000,TWD,\n"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def xlsx_parts() -> dict[str, str]:
    return {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": f'<Relationships xmlns="{RELS}"><Relationship Id="root" '
        f'Type="{DOC}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{NS}" xmlns:r="{DOC}"><sheets>'
        '<sheet name="Products" sheetId="1" r:id="sheet"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{RELS}">'
        f'<Relationship Id="sheet" Type="{DOC}/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>",
        "xl/worksheets/sheet1.xml": sheet(
            [
                ["sku", "title", "price", "currency", "tags"],
                ["NEW-1", "Example", "0.10", "TWD", "a;b"],
                ["NEW-2", "Other", "12.340000", "TWD", ""],
            ]
        ),
    }


def sheet(rows: list[list[str]]) -> str:
    content = []
    for number, row in enumerate(rows, start=1):
        cells = "".join(
            f'<c r="{chr(65 + index)}{number}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            for index, value in enumerate(row)
        )
        content.append(f'<row r="{number}">{cells}</row>')
    return f'<worksheet xmlns="{NS}"><sheetData>{"".join(content)}</sheetData></worksheet>'


def archive(parts: dict[str, str], *, compression: int = zipfile.ZIP_STORED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as output:
        for name, value in parts.items():
            output.writestr(name, value.encode())
    return buffer.getvalue()


def test_real_csv_and_xlsx_discovery_mapping_and_exact_normalized_values() -> None:
    outputs = []
    for data, format in ((CSV, "csv"), (archive(xlsx_parts()), "xlsx")):
        table = parse_file(data, format)  # type: ignore[arg-type]
        discovered = quality_preview(table, None, "TWD")
        assert discovered.state == "DISCOVERED" and discovered.products == ()
        assert discovered.table.headers == ("sku", "title", "price", "currency", "tags")
        ready = quality_preview(table, MAPPING, "TWD")
        assert ready.state == "READY" and ready.issue_count == 0
        assert [(row.sku, row.canonical_sku, row.price, row.tags) for row in ready.products] == [
            ("NEW-1", "new-1", "0.1", ("a", "b")),
            ("NEW-2", "new-2", "12.34", ()),
        ]
        outputs.append(ready.products)
    assert outputs[0] == outputs[1]


def test_actual_xlsx_shared_string_and_decimal_cells() -> None:
    parts = xlsx_parts()
    parts["xl/sharedStrings.xml"] = f'<sst xmlns="{NS}"><si><t>NEW-1</t></si></sst>'
    parts["xl/worksheets/sheet1.xml"] = (
        parts["xl/worksheets/sheet1.xml"]
        .replace(
            '<c r="A2" t="inlineStr"><is><t>NEW-1</t></is></c>', '<c r="A2" t="s"><v>0</v></c>'
        )
        .replace('<c r="C2" t="inlineStr"><is><t>0.10</t></is></c>', '<c r="C2"><v>0.10</v></c>')
    )
    assert quality_preview(parse_file(archive(parts), "xlsx"), MAPPING, "TWD").state == "READY"


def add_styles(parts: dict[str, str], formats: tuple[int, ...]) -> None:
    xfs = "".join(f'<xf numFmtId="{number}"/>' for number in formats)
    parts["xl/styles.xml"] = (
        f'<styleSheet xmlns="{NS}"><cellXfs count="{len(formats)}">{xfs}</cellXfs></styleSheet>'
    )
    parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
        "</Relationships>",
        f'<Relationship Id="style" Type="{DOC}/styles" Target="styles.xml"/></Relationships>',
    )


@pytest.mark.parametrize("number", [14, 9, 165])
def test_style_zero_is_not_assumed_general(number: int) -> None:
    parts = xlsx_parts()
    add_styles(parts, (number,))
    parts["xl/worksheets/sheet1.xml"] = parts["xl/worksheets/sheet1.xml"].replace(
        '<c r="C2" t="inlineStr"><is><t>0.10</t></is></c>', '<c r="C2" s="0"><v>45200</v></c>'
    )
    with pytest.raises(FileRejected, match="UNSUPPORTED_CELL_FORMAT"):
        parse_file(archive(parts), "xlsx")


def test_general_style_references_and_numeric_lexical_validation() -> None:
    parts = xlsx_parts()
    add_styles(parts, (0, 0))
    parts["xl/worksheets/sheet1.xml"] = parts["xl/worksheets/sheet1.xml"].replace(
        '<c r="C2" t="inlineStr"><is><t>0.10</t></is></c>', '<c r="C2" s="1"><v>0.10</v></c>'
    )
    data = archive(parts, compression=zipfile.ZIP_DEFLATED)
    assert quality_preview(parse_file(data, "xlsx"), MAPPING, "TWD").products[0].price == "0.1"
    for value in ("NEW-1", "1e2", "NaN", "1.0000001"):
        invalid = dict(parts)
        invalid["xl/worksheets/sheet1.xml"] = invalid["xl/worksheets/sheet1.xml"].replace(
            '<c r="A2" t="inlineStr"><is><t>NEW-1</t></is></c>', f'<c r="A2"><v>{value}</v></c>'
        )
        with pytest.raises(FileRejected, match="INVALID_NUMERIC_CELL"):
            parse_file(archive(invalid), "xlsx")
    invalid = dict(parts)
    invalid["xl/worksheets/sheet1.xml"] = invalid["xl/worksheets/sheet1.xml"].replace(
        'r="C2" s="1"', 'r="C2" s="2"'
    )
    with pytest.raises(FileRejected, match="XLSX_STYLE_REFERENCE"):
        parse_file(archive(invalid), "xlsx")
    invalid = dict(parts)
    invalid["xl/styles.xml"] = invalid["xl/styles.xml"].replace(
        '<xf numFmtId="0"/>', '<xf numFmtId="0" fontId="4"/>', 1
    )
    with pytest.raises(FileRejected, match="XLSX_STYLE_REFERENCE"):
        parse_file(archive(invalid), "xlsx")


@pytest.mark.parametrize("corruption", ["deflate", "crc", "truncated"])
def test_bad_compression_and_crc_are_fixed_file_rejections(corruption: str) -> None:
    data = archive(xlsx_parts(), compression=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(io.BytesIO(data)) as container:
        info = container.getinfo("xl/worksheets/sheet1.xml")
        name_size, extra_size = struct.unpack_from("<HH", data, info.header_offset + 26)
        start = info.header_offset + 30 + name_size + extra_size
    broken = bytearray(data)
    if corruption == "deflate":
        broken[start] = (
            broken[start] & 0xF8
        ) | 7  # Reserved DEFLATE BTYPE, preserving the directory.
    elif corruption == "crc":
        offset = data.find(b"PK\x01\x02")
        broken[offset + 16] ^= 1
    else:
        del broken[-5:]
    with pytest.raises(FileRejected, match="XLSX_ARCHIVE") as caught:
        parse_file(bytes(broken), "xlsx")
    assert caught.value.__suppress_context__ is True or corruption == "truncated"


@pytest.mark.parametrize("cell", ["=1+1", "+1", "-1", "@SUM(A1)", "  =HYPERLINK()"])
def test_csv_formula_rejected_and_never_echoed_in_preview(cell: str) -> None:
    data = f"sku,title,price,currency,tags\nNEW-1,{cell},1,TWD,\n".encode()
    result = quality_preview(parse_file(data, "csv"), MAPPING, "TWD")
    assert result.state == "INVALID" and result.products == ()
    assert result.issues[0].code == "FORMULA_REJECTED"
    assert result.sample[0].cells[1] == "[REJECTED]"


@pytest.mark.parametrize("price", ["1e2", "NaN", "Infinity", "01", "1.0000001", "True"])
def test_price_is_strict_decimal_text(price: str) -> None:
    data = f"sku,title,price,currency,tags\nNEW-1,Name,{price},TWD,\n".encode()
    result = quality_preview(parse_file(data, "csv"), MAPPING, "TWD")
    assert result.state == "INVALID"
    assert any(issue.code == "INVALID_PRICE" for issue in result.issues)


def test_duplicates_currency_wrong_width_and_errors_are_atomic_and_bounded() -> None:
    result = quality_preview(parse_file(CSV, "csv"), MAPPING, "TWD", frozenset({"new-1"}))
    assert result.state == "INVALID" and result.products == ()
    assert result.issues[0].code == "DUPLICATE_SKU"
    wrong_currency = quality_preview(parse_file(CSV, "csv"), MAPPING, "CNY")
    assert wrong_currency.issue_count == 2 and wrong_currency.products == ()
    rows = b"sku,title,price,currency,tags\n" + b"same,Name,1,TWD,\n" * 500
    many = quality_preview(parse_file(rows, "csv"), MAPPING, "TWD")
    assert many.issue_count == 499 and len(many.issues) == 100 and len(many.sample) == 20
    assert many.products == ()
    width = quality_preview(parse_file(b"sku,title\nx\n", "csv"), None, "TWD")
    assert width.issues[0].code == "INVALID_ROW_WIDTH"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"same,same\nx,y\n",
        b",name\nx,y\n",
        b"sku\n\x00\n",
        b"sku\n\xff\n",
        b'sku\n"unclosed',
        b"sku\n" + b"x\n" * 501,
    ],
)
def test_csv_invalid_input_fails_closed(data: bytes) -> None:
    with pytest.raises(FileRejected):
        parse_file(data, "csv")


def test_bom_mapping_missing_and_empty_data_have_clear_states() -> None:
    table = parse_file(b"\xef\xbb\xbfsku,title,price,currency,tags\n", "csv")
    result = quality_preview(table, MAPPING, "TWD")
    assert result.state == "INVALID" and result.issues[0].code == "EMPTY_DATA"
    wrong = dto.ColumnMapping(sku="unknown", title="title", price="price", currency="currency")
    result = quality_preview(parse_file(CSV, "csv"), wrong, "TWD")
    assert result.issues[0].code == "MAPPING_COLUMN_MISSING"


@pytest.mark.parametrize(
    "mutation",
    [
        "formula",
        "dtd",
        "pi",
        "external",
        "macro",
        "path",
        "sparse",
        "date",
        "nested",
        "bad-xml",
        "unknown-node",
    ],
)
def test_actual_malicious_xlsx_bytes_are_rejected(mutation: str) -> None:
    parts = xlsx_parts()
    name = "xl/worksheets/sheet1.xml"
    if mutation == "formula":
        parts[name] = parts[name].replace("<is><t>0.10</t></is>", "<f>SUM(1,2)</f><v>3</v>")
    elif mutation == "dtd":
        parts[name] = '<!DOCTYPE x [<!ENTITY unsafe "text">]>' + parts[name]
    elif mutation == "pi":
        parts[name] = "<?external value?>" + parts[name]
    elif mutation == "external":
        parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
            'Target="worksheets/sheet1.xml"',
            'TargetMode="External" Target="https://invalid.test/x"',
        )
    elif mutation == "macro":
        parts["xl/vbaProject.bin"] = "not executable"
    elif mutation == "path":
        parts["../escape.xml"] = "not a path"
    elif mutation == "sparse":
        parts[name] = parts[name].replace('r="A2"', 'r="X999"')
    elif mutation == "date":
        parts[name] = parts[name].replace('r="C2" t="inlineStr"', 'r="C2" t="d"')
    elif mutation == "nested":
        parts[name] = parts[name].replace("<sheetData>", '<sheetData><row r="1"><row r="1">')
    elif mutation == "bad-xml":
        parts[name] = parts[name][:-1]
    else:
        parts[name] = parts[name].replace("<sheetData>", "<unknown/><sheetData>")
    with pytest.raises(FileRejected):
        parse_file(archive(parts), "xlsx")


def test_zip_bomb_duplicate_entry_and_central_directory_count_are_bounded() -> None:
    parts = xlsx_parts()
    parts["xl/sharedStrings.xml"] = "x" * 1000000
    with pytest.raises(FileRejected, match="EXPANSION_LIMIT"):
        parse_file(archive(parts, compression=zipfile.ZIP_DEFLATED), "xlsx")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        output.writestr("same", "one")
        with pytest.warns(UserWarning):
            output.writestr("same", "two")
    with pytest.raises(FileRejected):
        parse_file(buffer.getvalue(), "xlsx")
    parts.update({f"extra-{number}.xml": "x" for number in range(33)})
    with pytest.raises(FileRejected, match="ARCHIVE_LIMIT"):
        parse_file(archive(parts), "xlsx")


def test_xml_depth_limit_split_dtd_and_budget() -> None:
    parts = xlsx_parts()
    parts["xl/worksheets/sheet1.xml"] = '<worksheet xmlns="' + NS + '">' + "<row>" * 17
    with pytest.raises(FileRejected):
        parse_file(archive(parts), "xlsx")
    parts = xlsx_parts()
    parts["xl/worksheets/sheet1.xml"] = (
        " " * 4093 + "<!DOCTYPE x>" + parts["xl/worksheets/sheet1.xml"]
    )
    with pytest.raises(FileRejected):
        parse_file(archive(parts), "xlsx")
    with pytest.raises(FileRejected, match="PARSE_TIMEOUT"):
        parse_file(CSV, "csv", budget=ParseBudget(deadline=time.monotonic() - 1))


def test_base64_is_canonical_and_has_real_file_limit() -> None:
    assert decode_file(base64.b64encode(CSV).decode()) == CSV
    for value in [
        "!",
        "eA==\n",
        "eB==",
        "",
        base64.b64encode(b"x" * (2 * 1024 * 1024 + 1)).decode(),
    ]:
        with pytest.raises(FileRejected):
            decode_file(value)
