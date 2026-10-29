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


CHAPTER_ITEM = '<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
NCX_ITEM = '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
NAV_ITEM = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
NCX_SPINE = '<spine toc="ncx"><itemref idref="chapter"/></spine>'


def ncx(body, namespace="http://www.daisy.org/z3986/2005/ncx/"):
    return f'<?xml version="1.0" encoding="utf-8"?><ncx xmlns="{namespace}" version="2005-1">{body}</ncx>'.encode()


def nav(body):
    return (
        '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
        f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Nav</title></head><body>{body}</body></html>'
    ).encode()


NAV_TOC = nav('<nav epub:type="toc"><ol><li><a href="chapter.xhtml">One</a></li></ol></nav>')


def read(tmp_path, manifest, files, spine='<spine><itemref idref="chapter"/></spine>', metadata=METADATA, options=None):
    opf = make_opf(manifest, spine, metadata)
    return epub.read_epub(make_epub(tmp_path / "book.epub", opf, {"OEBPS/chapter.xhtml": CHAPTER, **files}), options)


def links(toc):
    return [(link.href, link.title) for link in toc]


def test_epub_module_still_exports_the_utils_helpers():
    from ebooklib import utils

    for name in ("parse_string", "parse_html_string", "guess_type", "get_pages_for_items"):
        assert getattr(epub, name) is getattr(utils, name)


def test_opf_meta_elements_are_read_under_their_name(tmp_path):
    metadata = METADATA.replace("</metadata>", '<meta name="cover" content="cover-img"/></metadata>')

    book = read(tmp_path, CHAPTER_ITEM, {}, metadata=metadata)

    assert book.get_metadata("OPF", "cover") == [(None, {"name": "cover", "content": "cover-img"})]
