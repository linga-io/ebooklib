import logging
import zipfile

from ebooklib import epub

CONTAINER = b"""<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile media-type="application/oebps-package+xml" full-path="OEBPS/content.opf"/>
  </rootfiles>
</container>"""

METADATA = """<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">test-book</dc:identifier>
    <dc:title>Test book</dc:title>
    <dc:language>en</dc:language>
  </metadata>"""

CHAPTER = b"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head><body><p>Text</p></body></html>"""


def make_opf(manifest, spine='<spine><itemref idref="chapter"/></spine>', metadata=METADATA):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  {metadata}
  <manifest>{manifest}</manifest>
  {spine}
</package>""".encode()


def make_epub(path, opf, files):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        for name, content in files.items():
            zf.writestr(name, content)
    return str(path)


def test_missing_manifest_file_is_skipped_with_a_warning(tmp_path, caplog):
    opf = make_opf(
        '<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="gone" href="missing.xhtml" media-type="application/xhtml+xml"/>'
    )
    path = make_epub(tmp_path / "book.epub", opf, {"OEBPS/chapter.xhtml": CHAPTER})

    with caplog.at_level(logging.WARNING, logger="ebooklib.reader"):
        book = epub.read_epub(path)

    assert book.get_item_with_id("chapter") is not None
    assert book.get_item_with_id("gone") is None
    assert "missing.xhtml" in caplog.text


def test_get_raw_content_returns_content_as_read(tmp_path):
    opf = make_opf('<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>')
    path = make_epub(tmp_path / "book.epub", opf, {"OEBPS/chapter.xhtml": CHAPTER})

    item = epub.read_epub(path).get_item_with_id("chapter")

    assert isinstance(item, epub.EpubHtml)
    assert item.get_raw_content() == CHAPTER
