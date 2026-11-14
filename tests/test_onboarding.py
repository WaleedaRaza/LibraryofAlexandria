"""First run (/welcome), first steps, and asking a book for a passage."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.services import book_search, onboarding
from app.services.catalog_service import CatalogService
from test_library_app import _register, client  # noqa: F401  (pytest fixture)

PAGES = [
    "THE PRINCE\n\nTranslated by N. H. Thomson\n\nCONTENTS ........ 1",
    ("Here comes in the question whether it is better to be loved rather than feared, or feared rather than "
     "loved. It might perhaps be answered that we should wish to be both; but since love and fear can hardly "
     "exist together, if we must choose between them, it is far safer to be feared than loved. For of men it "
     "may generally be affirmed that they are thankless, fickle, false, studious to avoid danger, greedy of gain."),
    ("Every one understands how praiseworthy it is in a Prince to keep faith, and to live uprightly and not "
     "craftily. Nevertheless we see from what has taken place in our own days that Princes who have set little "
     "store by their word, but have known how to overreach men by their cunning, have accomplished great things."),
    ("I think it may be the case that Fortune is the mistress of one half our actions, and yet leaves the control "
     "of the other half, or a little less, to ourselves. And I would liken her to one of those wild torrents which, "
     "when angry, overflow the plains, sweep away trees and buildings, and carry off soil from one place to another."),
]
PASSAGES = book_search.passages_from_pages(PAGES)


def _top(question):
    queries = book_search.expand_question(None, {}, question)
    ranked = book_search.bm25(PASSAGES, queries)
    return PASSAGES[ranked[0][1]], queries


@pytest.mark.parametrize("question,page", [
    ("Is it better to be feared or loved?", 2),
    ("Should a ruler keep his promises?", 3),  # promise → faith, ruler → prince
    ("How much does luck matter?", 4),  # luck → fortune
])
def test_search_finds_the_passage_and_its_page(question, page):
    passage, queries = _top(question)
    assert passage.page == page
    quote = book_search.best_quote(passage.text, queries)
    assert book_search.quote_in(quote, passage.text)


def test_contents_pages_are_not_passages():
    assert all(p.page != 1 for p in PASSAGES)


def test_a_model_quote_that_is_not_in_the_book_is_replaced(monkeypatch):
    class FakeLLM:
        def call(self, system, user, **kwargs):
            if "search phrasings" in system:
                return {"queries": ["fortune mistress of our actions"]}
            return {"passage": 1, "quote": "Luck is everything, said Machiavelli.", "answer": "He gives fortune half."}

    async def fake_passages(book):
        return PASSAGES

    monkeypatch.setattr(book_search, "_llm", lambda: FakeLLM())
    monkeypatch.setattr(book_search, "book_passages", fake_passages)
    result = asyncio.run(book_search.ask_book({"id": "x", "title": "The Prince"}, "How much does luck matter?"))
    assert result.page == 4
    assert result.answer == "He gives fortune half."
    assert "Luck is everything" not in result.quote
    assert book_search.quote_in(result.quote, PAGES[3])


def test_open_url_points_at_the_page_and_the_words():
    url = book_search.open_url("the-prince", 32, "And here comes in the question whether it is better to be loved")
    assert url.startswith("/read/the-prince?page=32&find=")
    assert "question%20whether" in url


@pytest.fixture()
def searchable(monkeypatch):
    async def fake_passages(book):
        return PASSAGES

    monkeypatch.setattr(book_search, "book_passages", fake_passages)
    from app.routes import onboarding as route

    route._ask_times.clear()
    return CatalogService().get_book("the-prince-machiavelli-v-2-6c31ddd3")


def test_visitors_can_ask_but_sign_up_to_open_the_page(client: TestClient, searchable):
    response = client.post(f"/library/book/{searchable['id']}/ask", json={"question": "Is it better to be feared or loved?"})
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2 and "feared" in data["quote"]
    assert data["open_url"].startswith("/auth/register?next=/read/")
    assert data["alternates"] == []


def test_readers_get_the_reader_link_and_the_step_is_marked(client: TestClient, searchable):
    _register(client)
    response = client.post(f"/library/book/{searchable['id']}/ask", json={"question": "How much does luck matter?"})
    data = response.json()
    assert data["open_url"].startswith(f"/read/{searchable['id']}?page=4&find=")
    assert "asked" in response.cookies.get(onboarding.STEPS_COOKIE, "")
    client.cookies.set(onboarding.STEPS_COOKIE, response.cookies.get(onboarding.STEPS_COOKIE))
    client.cookies.set(onboarding.WELCOMED_COOKIE, "1")
    board = client.get("/library/my")
    assert "Ask a book a question" in board.text
    assert "1 of 6 done" in board.text


def test_ask_rejects_short_questions_and_link_books(client: TestClient, searchable):
    assert client.post(f"/library/book/{searchable['id']}/ask", json={"question": "hi"}).status_code == 400
    assert client.post("/library/book/not-a-book/ask", json={"question": "What is justice?"}).status_code == 404


def test_new_readers_land_on_welcome_once(client: TestClient):
    _register(client)
    first = client.get("/library/my", follow_redirects=False)
    assert first.status_code == 303 and first.headers["location"] == "/welcome"
    welcome = client.get("/welcome")
    assert welcome.status_code == 200
    assert "Pick a door" in welcome.text and "Ask a book something" in welcome.text and "Send the eye" in welcome.text
    assert "The Prince" in welcome.text
    again = client.get("/library/my", follow_redirects=False)
    assert again.status_code == 200


def test_welcome_asks_visitors_to_join(client: TestClient):
    response = client.get("/welcome", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/auth/register?next=/welcome"


def test_starter_shelf_saves_only_starter_books(client: TestClient):
    _register(client)
    starter = sorted(onboarding.starter_ids())[:3]
    response = client.post("/welcome/shelf", json={"book_ids": [*starter, "1984-george-orwell-v-1-b8d4aaee"]})
    assert response.status_code == 200
    assert response.json()["saved"] == starter
    client.cookies.set(onboarding.WELCOMED_COOKIE, "1")
    board = client.get("/library/my")
    assert "Build a starter shelf" in board.text and "1 of 6 done" in board.text
    assert client.post("/welcome/shelf", json={"book_ids": ["nope"]}).status_code == 400


def test_every_door_book_is_in_the_catalog_with_questions(client: TestClient):
    configured = [b for door in onboarding._doors_file() for b in door["books"]]
    resolved = onboarding.starter_ids()
    assert {b["id"] for b in configured} == resolved
    assert all(b["questions"] for b in configured)


def test_reader_opens_at_a_linked_page_and_carries_the_words(client: TestClient):
    _register(client)
    book = CatalogService().get_book("the-prince-machiavelli-v-2-6c31ddd3")
    page = client.get(f"/read/{book['id']}?page=32&find=whether+it+is+better")
    assert 'data-start-page="32"' in page.text
    assert 'data-find="whether it is better"' in page.text


def test_book_preview_offers_its_questions(client: TestClient):
    page = client.get("/library/book/the-prince-machiavelli-v-2-6c31ddd3")
    assert "Ask this book" in page.text
    assert "Is it better to be feared or loved?" in page.text
