import io
import zipfile

import pytest

from ebooklib import epub


def write(options):
    book = epub.EpubBook()
    book.set_identifier("test-writer")
    book.set_title("Test book")
    book.set_language("en")
    chapter = epub.EpubHtml(uid="chapter", file_name="chapter.xhtml")
    chapter.set_content("<body><p>" + "lorem ipsum " * 1000 + "</p></body>")
    book.add_item(chapter)
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = (chapter,)

    f = io.BytesIO()
    epub.write_epub(f, book, options)
    f.seek(0)
    with zipfile.ZipFile(f) as zf:
        return {info.filename: info for info in zf.infolist()}


def test_entries_are_deflated_and_mimetype_is_stored():
    entries = write({})

    assert entries.pop("mimetype").compress_type == zipfile.ZIP_STORED
    assert {name: info.compress_type for name, info in entries.items()} == dict.fromkeys(entries, zipfile.ZIP_DEFLATED)


@pytest.mark.parametrize("level", [0, 9])
def test_compresslevel_option_is_used(level):
    chapter = write({"compresslevel": level})["EPUB/chapter.xhtml"]

    # level 0 deflates into stored blocks, larger than the input; level 9 shrinks the repeated text
    assert (chapter.compress_size > chapter.file_size) == (level == 0)
