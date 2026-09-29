from pathlib import Path

import pymupdf
import pytest

from app.services.pdf import UnprocessablePdfError, clean_text, extract_pages


def make_pdf(pages: list[str | None], **save_kwargs) -> bytes:
    """Build a PDF; None creates a page with no text at all."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(72, 72, 540, 770), text, fontsize=11)
    data = doc.tobytes(**save_kwargs)
    doc.close()
    return data


# --- extraction ------------------------------------------------------------

def test_page_numbers_are_preserved_one_based() -> None:
    result = extract_pages(make_pdf(["Alpha content on page one.", "Beta content on page two.", "Gamma on page three."]))
    assert result.page_count == 3
    assert [p.page_number for p in result.pages] == [1, 2, 3]
    assert "Alpha" in result.pages[0].text
    assert "Beta" in result.pages[1].text
    assert "Gamma" in result.pages[2].text


def test_blank_pages_keep_their_slot_so_later_numbers_stay_correct() -> None:
    result = extract_pages(make_pdf(["Intro text on the first page.", None, "Conclusion on the third page."]))
    assert result.page_count == 3
    assert result.pages[1].text == ""
    assert [p.page_number for p in result.text_pages] == [1, 3]
    assert "Conclusion" in result.pages[2].text


def test_to_dicts_matches_documented_shape() -> None:
    result = extract_pages(make_pdf(["Some meaningful text for the page."]))
    assert result.to_dicts() == [{"page_number": 1, "text": "Some meaningful text for the page."}]


def test_accented_text_survives() -> None:
    result = extract_pages(make_pdf(["Café naïve résumé, déjà vu and more text."]))
    assert "Café naïve résumé" in result.pages[0].text


GEORGIAN_FONT = Path("C:/Windows/Fonts/sylfaen.ttf")


@pytest.mark.skipif(not GEORGIAN_FONT.exists(), reason="needs a font with Georgian glyphs")
def test_georgian_text_survives() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="geo", fontfile=str(GEORGIAN_FONT))
    page.insert_text((72, 72), "ხელოვნური ინტელექტი და ცოდნის ბაზა", fontname="geo")
    result = extract_pages(doc.tobytes())
    assert "ხელოვნური ინტელექტი" in result.pages[0].text


def test_owner_password_only_pdf_is_readable() -> None:
    data = make_pdf(["Readable although restricted by an owner password."], encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner")
    assert "Readable" in extract_pages(data).pages[0].text


# --- rejections ------------------------------------------------------------

def test_user_password_pdf_rejected() -> None:
    data = make_pdf(["secret"], encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user", owner_pw="owner")
    with pytest.raises(UnprocessablePdfError, match="password"):
        extract_pages(data)


@pytest.mark.parametrize("data", [b"%PDF-1.7 garbage garbage", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF"])
def test_corrupt_pdf_rejected(data: bytes) -> None:
    with pytest.raises(UnprocessablePdfError):
        extract_pages(data)


def test_pdf_without_text_layer_rejected() -> None:
    with pytest.raises(UnprocessablePdfError, match="OCR"):
        extract_pages(make_pdf([None, None]))


def test_page_limit() -> None:
    data = make_pdf(["Enough text on each page to count."] * 3)
    assert extract_pages(data, max_pages=3).page_count == 3
    with pytest.raises(UnprocessablePdfError, match="maximum is 2"):
        extract_pages(data, max_pages=2)


def test_rejection_status_is_422() -> None:
    assert UnprocessablePdfError().status_code == 422


# --- cleaning --------------------------------------------------------------

def test_clean_removes_nul_and_control_characters() -> None:
    assert clean_text("a\x00b\x07c\td") == "abc d"


def test_clean_rejoins_hyphenated_words_only_before_lowercase() -> None:
    assert clean_text("an exam-\nple here") == "an example here"
    assert clean_text("Covid-\n19 and Anglo-\nSaxon") == "Covid-\n19 and Anglo-\nSaxon"


def test_clean_collapses_whitespace_but_keeps_paragraphs() -> None:
    assert clean_text("  one   two \r\n\r\n\r\n\n three  four  ") == "one two\n\nthree four"


def test_clean_normalizes_unicode() -> None:
    assert clean_text("Café") == "Café"
