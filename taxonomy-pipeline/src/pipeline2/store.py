"""SQLite store for the pilot. One file holds every edition, unit and index."""
from __future__ import annotations
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS edition(id TEXT PRIMARY KEY, data TEXT, text TEXT, offset_map TEXT, stats TEXT);
CREATE TABLE IF NOT EXISTS division(edition_id TEXT, id TEXT, level INT, label TEXT, start INT, end INT, zone TEXT,
    ordinal INT, page INT, PRIMARY KEY(edition_id, id));
CREATE TABLE IF NOT EXISTS unit(id TEXT PRIMARY KEY, edition_id TEXT, division_id TEXT, zone TEXT, voice TEXT,
    voice_name TEXT, ref TEXT, start INT, end INT, page_start INT, page_end INT, text TEXT, words INT);
CREATE TABLE IF NOT EXISTS unit_question(unit_id TEXT, question TEXT, model TEXT);
CREATE TABLE IF NOT EXISTS unit_vec(unit_id TEXT, kind TEXT, model TEXT, dim INT, vec BLOB, PRIMARY KEY(unit_id, kind, model));
CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5(unit_id UNINDEXED, body, search, questions, tokenize='porter unicode61');
"""


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA)
    return con


def save_edition(con, ed, text, omap, stats, divs, units):
    con.execute("DELETE FROM division WHERE edition_id=?", (ed.id,))
    con.execute("DELETE FROM unit_fts WHERE unit_id IN (SELECT id FROM unit WHERE edition_id=?)", (ed.id,))
    con.execute("DELETE FROM unit_question WHERE unit_id IN (SELECT id FROM unit WHERE edition_id=?)", (ed.id,))
    con.execute("DELETE FROM unit_vec WHERE unit_id IN (SELECT id FROM unit WHERE edition_id=?)", (ed.id,))
    con.execute("DELETE FROM unit WHERE edition_id=?", (ed.id,))
    con.execute("INSERT OR REPLACE INTO edition VALUES(?,?,?,?,?)",
                (ed.id, json.dumps(asdict(ed)), text, json.dumps(omap), json.dumps(stats)))
    con.executemany("INSERT INTO division VALUES(?,?,?,?,?,?,?,?,?)",
                    [(ed.id, d.id, d.level, d.label, d.start, d.end, d.zone, d.ordinal, d.page) for d in divs])
    con.executemany("INSERT INTO unit VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(u.id, u.edition_id, u.division_id, u.zone, u.voice, u.voice_name, u.ref, u.start, u.end,
                      u.page_start, u.page_end, u.text, u.words) for u in units])
    con.commit()
