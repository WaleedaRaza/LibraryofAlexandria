import json

from app.config import settings
from app.services.reading_desk import _initial_candidate, assess_edition, parse_books


def test_parse_books_handles_batch_formats_and_deduplicates():
    books = parse_books(
        """
        1. The Analects — Confucius
        The Republic by Plato
        Frankenstein\tMary Shelley
        The Analects — Confucius
        """
    )
    assert books == [
        {"title": "The Analects", "author": "Confucius"},
        {"title": "The Republic", "author": "Plato"},
        {"title": "Frankenstein", "author": "Mary Shelley"},
    ]


def test_candidate_scoring_prefers_open_pdf_and_penalizes_slop():
    book = {"title": "The Analects", "author": "Confucius"}
    open_pdf = _initial_candidate(
        {
            "title": "The Analects of Confucius — PDF",
            "href": "https://archive.org/download/analects/analects.pdf",
            "body": "Full text of the Analects by Confucius",
        },
        book,
        '"The Analects" filetype:pdf',
        1,
    )
    slop = _initial_candidate(
        {
            "title": "The Analects summary and study guide",
            "href": "https://www.scribd.com/preview/analects-summary",
            "body": "Sign in to read this sample",
        },
        book,
        '"The Analects" filetype:pdf',
        1,
    )
    assert open_pdf is not None and slop is not None
    assert open_pdf["score"] > slop["score"] + 80
    assert "archive host" in open_pdf["reasons"]
    assert "known gated host" in slop["reasons"]


def test_wrong_volume_is_not_a_first_pick():
    book = {"title": "The Hunger Games", "author": "Suzanne Collins"}
    first_book = _initial_candidate(
        {"title": "The Hunger Games — PDF", "href": "https://example.edu/books/the-hunger-games.pdf", "body": "Full novel"},
        book,
        "The Hunger Games PDF",
        1,
    )
    other_volume = _initial_candidate(
        {"title": "Mockingjay", "href": "https://archive.org/download/mockingjay/mockingjay.pdf", "body": "Part of The Hunger Games series"},
        book,
        "The Hunger Games PDF",
        1,
    )
    assert first_book and other_volume
    assert first_book["score"] > other_volume["score"]


def test_book_named_folder_does_not_hide_wrong_pdf_filename():
    book = {"title": "Thinking, Fast and Slow", "author": "Daniel Kahneman"}
    wrong = _initial_candidate(
        {"title": "How To Win Friends & Influence People", "href": "https://archive.org/download/thinking-fast-and-slow/how-to-win-friends.pdf", "body": "Books in this collection"},
        book,
        "Thinking Fast and Slow PDF",
        1,
    )
    right = _initial_candidate(
        {"title": "Thinking, Fast and Slow", "href": "https://example.edu/books/thinking-fast-and-slow.pdf", "body": "Daniel Kahneman"},
        book,
        "Thinking Fast and Slow PDF",
        1,
    )
    assert wrong and right
    assert right["score"] > wrong["score"]


def test_collection_length_is_penalized():
    book = {"title": "Percy Jackson and the Lightning Thief", "author": "Rick Riordan"}
    item = {"url": "https://archive.org/percy-jackson-complete-series.pdf", "title": "The Lightning Thief", "viewable": True, "page_count": 1189, "score": 82, "reasons": []}
    assess_edition(book, item, 384)
    assert item["edition_fit"] == "possible collection"
    assert item["score"] <= 50


def test_essential_list_is_exactly_fifty_unique_books():
    path = settings.BASE_DIR / "library" / "reading_lists" / "essential_50.json"
    books = json.loads(path.read_text(encoding="utf-8"))["books"]
    identities = {(book["title"].casefold(), book["author"].casefold()) for book in books}
    assert len(books) == 50
    assert len(identities) == 50
    assert len({book["category"] for book in books}) >= 8


def test_launch_list_is_exactly_seventy_two_unique_books():
    path = settings.BASE_DIR / "library" / "reading_lists" / "launch_72.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    books = data["books"]
    identities = {(book["title"].casefold(), book["author"].casefold()) for book in books}
    assert data["batch_size"] == 12
    assert len(books) == len(identities) == 72
