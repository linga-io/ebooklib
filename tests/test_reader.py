import logging
import zipfile

import pytest

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


def test_metadata_without_dublin_core_reads_as_empty(tmp_path):
    book = read(tmp_path, CHAPTER_ITEM, {}, metadata="<metadata/>")

    assert book.title == ""
    assert book.get_metadata("DC", "creator") == []


def test_comments_and_processing_instructions_are_not_read_as_entries(tmp_path):
    metadata = METADATA.replace("</metadata>", "<!-- note --><?generator x?></metadata>")
    spine = (
        '<spine><!-- body --><itemref idref="chapter"/></spine>'
        '<guide><!-- landmarks --><reference type="text" title="Text" href="chapter.xhtml"/></guide>'
    )

    book = read(tmp_path, CHAPTER_ITEM, {}, spine=spine, metadata=metadata)

    assert book.title == "Test book"
    assert book.spine == [("chapter", "yes")]
    assert book.guide == [{"href": "chapter.xhtml", "title": "Text", "type": "text"}]


def test_missing_container_raises_epub_exception(tmp_path):
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")

    with pytest.raises(epub.EpubException):
        epub.read_epub(str(path))


def test_archive_is_closed_when_loading_fails(tmp_path):
    reader = epub.EpubReader(make_epub(tmp_path / "book.epub", b"<package/>", {}))

    with pytest.raises(epub.EpubException):
        reader.load()

    assert isinstance(reader.zf, zipfile.ZipFile)
    assert reader.zf.fp is None


@pytest.mark.parametrize(
    "toc_ncx",
    [
        ncx("<docTitle><text>Book</text></docTitle>"),
        ncx('<navMap><navPoint id="p1"><content src="chapter.xhtml"/></navPoint></navMap>', namespace="urn:x-other"),
    ],
    ids=["no-nav-map", "other-namespace"],
)
def test_ncx_without_a_nav_map_reads_as_an_empty_toc(tmp_path, toc_ncx):
    book = read(tmp_path, CHAPTER_ITEM + NCX_ITEM, {"OEBPS/toc.ncx": toc_ncx}, spine=NCX_SPINE)

    assert book.toc == []


def test_ncx_nav_point_without_a_label_reads_with_an_empty_title(tmp_path):
    toc_ncx = ncx('<navMap><navPoint id="p1"><navLabel/><content src="chapter.xhtml"/></navPoint></navMap>')

    book = read(tmp_path, CHAPTER_ITEM + NCX_ITEM, {"OEBPS/toc.ncx": toc_ncx}, spine=NCX_SPINE)

    assert links(book.toc) == [("chapter.xhtml", "")]


def test_empty_ncx_nav_map_leaves_the_toc_to_the_nav_document(tmp_path):
    files = {"OEBPS/toc.ncx": ncx("<navMap/>"), "OEBPS/nav.xhtml": NAV_TOC}

    book = read(tmp_path, CHAPTER_ITEM + NCX_ITEM + NAV_ITEM, files, spine=NCX_SPINE, options={"ignore_ncx": False})

    assert links(book.toc) == [("chapter.xhtml", "One")]


@pytest.mark.parametrize("manifest", [CHAPTER_ITEM, CHAPTER_ITEM + NCX_ITEM], ids=["unknown-id", "missing-file"])
def test_missing_ncx_leaves_the_toc_to_the_nav_document(tmp_path, caplog, manifest):
    files = {"OEBPS/nav.xhtml": NAV_TOC}

    with caplog.at_level(logging.WARNING, logger="ebooklib.reader"):
        book = read(tmp_path, manifest + NAV_ITEM, files, spine=NCX_SPINE, options={"ignore_ncx": False})

    assert links(book.toc) == [("chapter.xhtml", "One")]
    assert "ncx" in caplog.text


@pytest.mark.parametrize(
    "nav_body",
    [
        '<nav epub:type="landmarks"><ol><li><a href="chapter.xhtml">One</a></li></ol></nav>',
        '<nav epub:type="toc"><h1>Contents</h1></nav>',
        '<nav epub:type="toc"><h1>Contents</h1></nav><nav epub:type="page-list"><h1>Pages</h1></nav>',
    ],
    ids=["no-toc-nav", "toc-without-list", "page-list-without-list"],
)
def test_nav_document_without_a_list_reads_as_an_empty_toc(tmp_path, nav_body):
    book = read(tmp_path, CHAPTER_ITEM + NAV_ITEM, {"OEBPS/nav.xhtml": nav(nav_body)})

    assert book.toc == []
    assert book.pages == []


@pytest.mark.parametrize("codec", ["utf-16-le", "utf-16-be"])
def test_utf16_document_keeps_its_text(tmp_path, codec):
    chapter = "\ufeff" + CHAPTER.decode().replace('encoding="utf-8"', 'encoding="utf-16"')

    book = read(tmp_path, CHAPTER_ITEM, {"OEBPS/chapter.xhtml": chapter.encode(codec)})

    item = book.get_item_with_id("chapter")
    assert isinstance(item, epub.EpubHtml)
    assert b"<p>Text</p>" in item.get_content()
    assert b"<p>Text</p>" in item.get_body_content()


def make_directory(path, opf, files):
    for name, content in {"META-INF/container.xml": CONTAINER, "OEBPS/content.opf": opf, **files}.items():
        if content is not None:
            (path / name).parent.mkdir(parents=True, exist_ok=True)
            (path / name).write_bytes(content)
    return str(path)


@pytest.mark.parametrize("href", ["missing.xhtml", "../../outside.xhtml"], ids=["missing-file", "outside-directory"])
def test_unreadable_file_in_a_directory_source_is_skipped_with_a_warning(tmp_path, caplog, href):
    (tmp_path / "outside.xhtml").write_bytes(CHAPTER)
    opf = make_opf(CHAPTER_ITEM + f'<item id="gone" href="{href}" media-type="application/xhtml+xml"/>')
    path = make_directory(tmp_path / "book", opf, {"OEBPS/chapter.xhtml": CHAPTER})

    with caplog.at_level(logging.WARNING, logger="ebooklib.reader"):
        book = epub.read_epub(path)

    assert book.get_item_with_id("chapter") is not None
    assert book.get_item_with_id("gone") is None
    assert href in caplog.text


@pytest.mark.parametrize("missing", ["META-INF/container.xml", "OEBPS/content.opf"])
def test_directory_source_without_its_package_files_raises_epub_exception(tmp_path, missing):
    path = make_directory(tmp_path / "book", make_opf(CHAPTER_ITEM), {"OEBPS/chapter.xhtml": CHAPTER, missing: None})

    with pytest.raises(epub.EpubException):
        epub.read_epub(path)


def test_nav_section_title_skips_a_leading_comment(tmp_path):
    nav_body = (
        '<nav epub:type="toc"><ol><li><!-- part --><span>Part</span>'
        '<ol><li><a href="chapter.xhtml">One</a></li></ol></li></ol></nav>'
    )

    book = read(tmp_path, CHAPTER_ITEM + NAV_ITEM, {"OEBPS/nav.xhtml": nav(nav_body)})

    [(section, children)] = book.toc
    assert section.title == "Part"
    assert links(children) == [("chapter.xhtml", "One")]


@pytest.mark.parametrize(
    ("nav_label", "title"),
    [("<navLabel><!-- c --><text>A</text></navLabel>", "A"), ("<navLabel><text/></navLabel>", "")],
    ids=["leading-comment", "empty-text"],
)
def test_ncx_nav_point_title_is_the_text_of_its_label(tmp_path, nav_label, title):
    toc_ncx = ncx(f'<navMap><navPoint id="p1">{nav_label}<content src="chapter.xhtml"/></navPoint></navMap>')

    book = read(tmp_path, CHAPTER_ITEM + NCX_ITEM, {"OEBPS/toc.ncx": toc_ncx}, spine=NCX_SPINE)

    assert links(book.toc) == [("chapter.xhtml", title)]


def test_ncx_is_read_from_the_archive_once(tmp_path):
    reads = []

    class RecordingReader(epub.EpubReader):
        def read_file(self, name):
            reads.append(name)
            return super().read_file(name)

    toc_ncx = ncx(
        '<navMap><navPoint id="p1"><navLabel><text>One</text></navLabel><content src="chapter.xhtml"/>'
        "</navPoint></navMap>"
    )
    opf = make_opf(CHAPTER_ITEM + NCX_ITEM, spine=NCX_SPINE)
    reader = RecordingReader(
        make_epub(tmp_path / "book.epub", opf, {"OEBPS/chapter.xhtml": CHAPTER, "OEBPS/toc.ncx": toc_ncx})
    )

    book = reader.load()

    assert links(book.toc) == [("chapter.xhtml", "One")]
    assert reads.count("OEBPS/toc.ncx") == 1
