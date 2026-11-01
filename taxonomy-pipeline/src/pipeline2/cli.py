"""Pipeline 2 CLI.

  python -m src.pipeline2.cli ingest --pdf-dir data/pilot/pdfs --db data/p2.sqlite [--catalog ../library/catalog.json]
  python -m src.pipeline2.cli enrich --db data/p2.sqlite [--limit 50]       (needs pipeline2.gen in config.yaml)
  python -m src.pipeline2.cli embed  --db data/p2.sqlite                    (needs pipeline2.embed in config.yaml)
  python -m src.pipeline2.cli route  --db data/p2.sqlite "how do I respond to an insult?"
  python -m src.pipeline2.cli eval   --db data/p2.sqlite --gold ../eval/gold_v0.py [-v]
"""
from __future__ import annotations
import json
from pathlib import Path

import click
import yaml

from .models import EmbedConfig, Embedder, GenConfig, Generator
from .store import connect


def _cfg(path: str) -> dict:
    p = Path(path)
    return (yaml.safe_load(p.read_text()) or {}).get("pipeline2", {}) if p.exists() else {}


def _embedder(cfg: dict) -> Embedder:
    return Embedder(EmbedConfig(**cfg.get("embed", {})))


def _generator(cfg: dict) -> Generator:
    return Generator(GenConfig(**cfg.get("gen", {})))


@click.group()
@click.option("--config", "config_path", default="config.yaml")
@click.pass_context
def cli(ctx, config_path):
    ctx.obj = _cfg(config_path)


@cli.command()
@click.option("--pdf-dir", type=click.Path(exists=True), required=True)
@click.option("--db", required=True)
@click.option("--catalog", type=click.Path(), default=None, help="library/catalog.json for identity checks")
@click.option("--only", default=None, help="substring filter on file names")
def ingest(pdf_dir, db, catalog, only):
    from .runner import ingest as run_one
    cat = {}
    if catalog and Path(catalog).exists():
        for b in json.loads(Path(catalog).read_text())["books"]:
            cat[Path(b["asset_key"]).stem] = (b.get("title", ""), b.get("author", ""))
    con = connect(db)
    for pdf in sorted(Path(pdf_dir).glob("*.pdf")):
        if only and only not in pdf.name:
            continue
        title, author = cat.get(pdf.stem, ("", ""))
        r = run_one(con, pdf, pdf.stem, title, author)
        ed, st = r["edition"], r["stats"]
        flag = "" if ed.identity_ok else f"  IDENTITY? {ed.identity_note}"
        click.echo(f"{pdf.stem[:44]:44} units={st['units']:5} divs={st['divisions']:3} zones={st['zones']} "
                   f"comment={st['commentary_units']} med_words={st['median_unit_words']} {st['seconds']}s{flag}")


@cli.command()
@click.option("--db", required=True)
@click.option("--limit", type=int, default=None)
@click.option("--edition", default=None)
@click.pass_obj
def enrich(cfg, db, limit, edition):
    from . import s7_enrich, s8_index
    gen = _generator(cfg)
    if not gen.enabled:
        raise click.UsageError("set pipeline2.gen.provider in config.yaml (ollama or openai)")
    con = connect(db)
    n = s7_enrich.run(con, gen, edition, limit, log=click.echo)
    click.echo(f"enriched {n} units")


@cli.command()
@click.option("--db", required=True)
@click.pass_obj
def embed(cfg, db):
    from . import s8_index
    emb = _embedder(cfg)
    if not emb.enabled:
        raise click.UsageError("set pipeline2.embed.provider in config.yaml (ollama or openai)")
    n = s8_index.build_vectors(connect(db), emb, log=click.echo)
    click.echo(f"embedded {n} units")


@cli.command()
@click.option("--db", required=True)
@click.option("-k", default=5)
@click.argument("question")
@click.pass_obj
def route(cfg, db, k, question):
    from .s9_route import route as do_route
    emb = _embedder(cfg)
    for h in do_route(connect(db), question, k=k, emb=emb if emb.enabled else None):
        who = f" [{h.voice_name or h.voice}]" if h.voice != "author" else ""
        click.echo(f"{h.score:.4f} {h.edition_id[:30]} p{h.page_start}-{h.page_end} {h.zone} {h.ref[:40]}{who}\n    {h.text[:220]}\n")


@cli.command("eval")
@click.option("--db", required=True)
@click.option("--gold", required=True, type=click.Path(exists=True))
@click.option("-k", default=10)
@click.option("-v", "verbose", is_flag=True)
@click.option("--dense/--no-dense", default=True)
@click.pass_obj
def eval_cmd(cfg, db, gold, k, verbose, dense):
    from .evaluate import run
    emb = _embedder(cfg)
    res = run(connect(db), gold, k=k, emb=emb if (dense and emb.enabled) else None, verbose=verbose, log=click.echo)
    for b, (h, n) in res["per_book"].items():
        click.echo(f"  {b[:40]:40} {h}/{n}")
    click.echo(f"recall@{k} {res['recall@k']}/{res['n']}  recall@1 {res['recall@1']}/{res['n']}  MRR {res['mrr']}  "
               f"decoy-first {res['decoy_first']}  anchors-not-in-units {len(res['anchors_not_in_units'])}")
    for m in res["anchors_not_in_units"]:
        click.echo(f"  not in a unit: {m}")


if __name__ == "__main__":
    cli()
