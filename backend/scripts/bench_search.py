"""
Search speed on a synthetic corpus (BUG-027), on a throwaway local PostgreSQL.

    uv run scripts/bench_search.py [--files 100000] [--words 400]

Builds shares/folders/files/documents of the requested size (text drawn from a
skewed vocabulary, so some words are in most documents and others in few), then
times the real search code: the home page, rare and common words, filters and
deep pages. Half the folders are readable by the benchmark user, as with real
permissions. Nothing touches the dev database.
"""

import argparse
import contextlib
import statistics
import sys
import tempfile
import time
from pathlib import Path

import pgserver

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import make_engine
from app.services import access
from app.services.indexer import PG_TITLE_VECTOR, PG_VECTOR
from app.services.search import SearchParams, search

EVERYONE = "S-1-1-0"
STAFF = "S-1-5-21-1-2-3-5000"
# Ordered from most to least frequent (log-uniform draws: word k has probability ~1/k).
VOCABULARY = (
    "informe contrato proyecto cliente factura presupuesto reunion acta plan anual "
    "report contract project client invoice budget meeting minutes annual review "
    "obra licencia proveedor pedido oferta calidad seguridad riesgo auditoria norma "
    "estructura hormigon cimentacion fachada instalacion electrica climatizacion "
    "fontaneria saneamiento urbanizacion topografia geotecnia memoria pliego medicion "
    "certificacion replanteo planificacion cronograma subcontrata garantia penalizacion "
    "arbitraje mediacion recurso alegacion subvencion convenio patente marca dominio "
    "kanban retrospectiva hito entregable stakeholder onboarding offboarding ergonomia"
).split()
RARE = ["xilografia", "wolframio", "quimera"]  # each in about 1 document in 1,000


def _sql(vector: str) -> str:
    """The indexer's vector expression, fed from the tables instead of parameters."""
    return (vector.replace(":name", "f.name").replace(":path", "'proyectos carpeta ' || f.folder_id")
            .replace(":content", "d.content"))


def build(engine, files: int, words: int) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    vocab = "ARRAY[" + ",".join(f"'{w}'" for w in VOCABULARY) + "]"
    rare = "ARRAY[" + ",".join(f"'{w}'" for w in RARE) + "]"
    n = len(VOCABULARY)
    with engine.begin() as c:
        c.execute(text("INSERT INTO acls (id, hash, is_protected, is_null_dacl, has_explicit) VALUES "
                       "(1, 'everyone', true, false, true), (2, 'staff-only', true, false, true)"))
        c.execute(text("INSERT INTO acl_entries (acl_id, position, sid, ace_type, mask, flags) VALUES "
                       f"(1, 0, '{EVERYONE}', 'allow', 1179785, 3), (2, 0, '{STAFF}', 'allow', 1179785, 3)"))
        c.execute(text("INSERT INTO shares (id, name, path, enabled, created_at) VALUES "
                       "(1, 'Proyectos', '\\\\fs01\\proyectos', true, now())"))
        c.execute(text("INSERT INTO folders (id, share_id, parent_id, name, path, depth, acl_id) "
                       "VALUES (1, 1, NULL, '', '', 0, 1)"))
        c.execute(text("""
            INSERT INTO folders (id, share_id, parent_id, name, path, depth, acl_id)
            SELECT i, 1, 1, 'Carpeta ' || i, 'Carpeta ' || i, 1, CASE WHEN i % 2 = 0 THEN 1 ELSE 2 END
            FROM generate_series(2, 2001) AS i
        """))
    print(f"Creating {files:,} files with ~{words} words each ...", flush=True)
    started = time.perf_counter()
    batch = 20_000
    for start in range(0, files, batch):
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO files (id, share_id, folder_id, name, extension, size, mtime, indexed_at)
                SELECT i, 1, 2 + i % 2000, 'documento ' || i || ' ' || (ARRAY['pdf','docx','xlsx','txt'])[1 + i % 4],
                       (ARRAY['pdf','docx','xlsx','txt'])[1 + i % 4], 1000 + i,
                       now() - (i % 3650) * interval '1 day', now()
                FROM generate_series(CAST(:a AS integer), CAST(:b AS integer)) AS i
            """), {"a": start + 1, "b": min(start + batch, files)})
            c.execute(text(f"""
                INSERT INTO documents (file_id, status, content)
                SELECT i, 'text', (
                    SELECT string_agg(({vocab})[least({n}, floor(exp(random() * ln({n} + 1)))::int)], ' ')
                    FROM generate_series(1, CAST(:words AS integer)) WHERE i > 0
                ) || CASE WHEN i % 997 = 0 THEN ' ' || ({rare})[1 + i % 3] ELSE '' END
                FROM generate_series(CAST(:a AS integer), CAST(:b AS integer)) AS i
            """), {"a": start + 1, "b": min(start + batch, files), "words": words})
            c.execute(text(f"""
                UPDATE documents d SET search_vector = {_sql(PG_VECTOR)}, title_vector = {_sql(PG_TITLE_VECTOR)}
                FROM files f WHERE f.id = d.file_id AND d.file_id BETWEEN :a AND :b
            """), {"a": start + 1, "b": min(start + batch, files)})
        print(f"  {min(start + batch, files):,} files ({time.perf_counter() - started:.0f} s)", flush=True)
    with engine.begin() as c:
        c.execute(text("ANALYZE"))
        size = c.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
    print(f"Done in {time.perf_counter() - started:.0f} s; database size {size}.\n")


ONLY = None


def timed(engine, label: str, params: SearchParams, runs: int = 5) -> None:
    if ONLY and ONLY not in label:
        return
    token = frozenset({EVERYONE})
    times = []
    for _ in range(runs):
        with Session(engine) as db:
            access.acl_cache = access.AclCache()  # cold permission cache, as after a restart
            t = time.perf_counter()
            r = search(db, token, params)
            times.append((time.perf_counter() - t) * 1000)
    total = "-" if r["total"] is None else f"{r['total']:,}{'+' if r['total_capped'] else ''}"
    print(f"{label:<48} median {statistics.median(times):7.0f} ms   max {max(times):7.0f} ms   total {total}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=100_000)
    ap.add_argument("--words", type=int, default=400)
    ap.add_argument("--keep", metavar="DIR",
                    help="keep the database in DIR and reuse it on the next run (same --files)")
    ap.add_argument("--only", help="run only the measurements whose label contains this text")
    args = ap.parse_args()
    global ONLY
    ONLY = args.only
    with (contextlib.nullcontext(args.keep) if args.keep else tempfile.TemporaryDirectory(prefix="corplib-bench-")) as data_dir:
        reuse = args.keep and (Path(data_dir) / "PG_VERSION").exists()
        server = pgserver.get_server(data_dir, cleanup_mode="stop")
        engine = make_engine(server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1))
        try:
            if reuse:
                print(f"Reusing the database in {data_dir}.\n")
            else:
                build(engine, args.files, args.words)
            common, rare = VOCABULARY[0], RARE[0]
            timed(engine, "home page (newest 10, no count)", SearchParams(sort="newest", limit=10, count=False))
            timed(engine, "home page (newest 10, with count)", SearchParams(sort="newest", limit=10))
            timed(engine, f"common word '{common}' (relevance)", SearchParams(q=common))
            timed(engine, f"common word '{common}' (relevance, no count)", SearchParams(q=common, count=False))
            timed(engine, f"common word '{common}', type pdf", SearchParams(q=common, type="pdf"))
            timed(engine, f"common word '{common}', page 50", SearchParams(q=common, offset=980))
            timed(engine, f"common word '{common}' (newest)", SearchParams(q=common, sort="newest"))
            timed(engine, f"two common words '{common} {VOCABULARY[1]}'", SearchParams(q=f"{common} {VOCABULARY[1]}"))
            timed(engine, f"rare word '{rare}'", SearchParams(q=rare))
            timed(engine, f"mid word '{VOCABULARY[40]}'", SearchParams(q=VOCABULARY[40]))
            timed(engine, f"common word minus a mid one", SearchParams(q=f"{common} -{VOCABULARY[40]}"))
            timed(engine, "file name 'documento 4242'", SearchParams(q="documento 4242"))
        finally:
            engine.dispose()
            server.cleanup()


if __name__ == "__main__":
    main()
