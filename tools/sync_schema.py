from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine

# Ensure project root is importable when running via absolute path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse app config and engine builder
from app.infra.config import load_app_config
from app.dal.db import make_engine


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _dump_tables_sql(engine: Engine) -> str:
    lines: list[str] = []
    insp = inspect(engine)
    tables = sorted(insp.get_table_names())

    with engine.connect() as conn:
        # Make sure we are in the correct schema
        current_db = conn.execute(text("SELECT DATABASE()")).scalar() or ""
        lines.append(f"-- Database: `{current_db}`")
        lines.append("SET FOREIGN_KEY_CHECKS=0;\n")

        for t in tables:
            # Use MySQL-native DDL for fidelity
            ddl_row = conn.execute(text(f"SHOW CREATE TABLE `{t}`")).mappings().first()
            if not ddl_row:
                continue
            # MySQL returns columns: Table, Create Table
            ddl = ddl_row.get("Create Table") or ddl_row.get("Create Table") or ""
            lines.append(f"-- ----------------------------\n-- Table structure for `{t}`\n-- ----------------------------")
            lines.append(f"DROP TABLE IF EXISTS `{t}`;")
            lines.append(f"{ddl};\n")

        lines.append("SET FOREIGN_KEY_CHECKS=1;\n")
    return "\n".join(lines)


def _dump_views_sql(engine: Engine) -> str:
    lines: list[str] = []
    with engine.connect() as conn:
        # Identify views
        rows = conn.execute(text("SHOW FULL TABLES WHERE Table_type = 'VIEW'"))
        views: list[str] = []
        for r in rows:
            # Result columns are (Table, Table_type); table name is first
            views.append(str(list(r)[0]))
        views.sort()

        for v in views:
            ddl_row = conn.execute(text(f"SHOW CREATE VIEW `{v}`")).mappings().first()
            if not ddl_row:
                continue
            ddl = ddl_row.get("Create View") or ""
            lines.append(f"-- ----------------------------\n-- View structure for `{v}`\n-- ----------------------------")
            lines.append(f"DROP VIEW IF EXISTS `{v}`;")
            lines.append(f"{ddl};\n")
    return "\n".join(lines)


def _dump_triggers_sql(engine: Engine) -> str:
    lines: list[str] = []
    with engine.connect() as conn:
        rows = conn.execute(text("SHOW TRIGGERS"))
        triggers = [dict(r._mapping) for r in rows]
        for trg in triggers:
            name = trg.get("Trigger") or trg.get("Trigger_name") or ""
            timing = trg.get("Timing")  # BEFORE/AFTER
            event = trg.get("Event")  # INSERT/UPDATE/DELETE
            tbl = trg.get("Table")
            stmt = trg.get("Statement")
            definer = trg.get("Definer")
            sql_mode = trg.get("sql_mode") or ""  # depends on MySQL version
            if not name or not tbl or not stmt:
                continue
            lines.append(f"-- ----------------------------\n-- Trigger structure for `{name}`\n-- ----------------------------")
            lines.append(f"DROP TRIGGER IF EXISTS `{name}`;")
            # Keep it simple; definer and sql_mode often optional to recreate elsewhere
            lines.append(
                f"CREATE TRIGGER `{name}` {timing} {event} ON `{tbl}` FOR EACH ROW {stmt};\n"
            )
    return "\n".join(lines)


def _dump_schema_json(engine: Engine) -> dict:
    insp = inspect(engine)
    data: dict = {"tables": {}, "views": []}

    # Tables and columns
    for t in sorted(insp.get_table_names()):
        cols = insp.get_columns(t)
        pks = insp.get_pk_constraint(t) or {}
        fks = insp.get_foreign_keys(t) or []
        idxs = insp.get_indexes(t) or []
        data["tables"][t] = {
            "columns": [
                {
                    "name": c.get("name"),
                    "type": str(c.get("type")),
                    "nullable": bool(c.get("nullable")),
                    "default": c.get("default"),
                    "autoincrement": c.get("autoincrement"),
                    "comment": c.get("comment"),
                }
                for c in cols
            ],
            "primary_key": pks.get("constrained_columns", []) or [],
            "foreign_keys": [
                {
                    "name": fk.get("name"),
                    "constrained_columns": fk.get("constrained_columns", []),
                    "referred_table": fk.get("referred_table"),
                    "referred_columns": fk.get("referred_columns", []),
                    "referred_schema": fk.get("referred_schema"),
                    "options": fk.get("options"),
                }
                for fk in fks
            ],
            "indexes": idxs,
        }

    # Views
    with engine.connect() as conn:
        rows = conn.execute(text("SHOW FULL TABLES WHERE Table_type = 'VIEW'"))
        for r in rows:
            view_name = str(list(r)[0])
            data["views"].append(view_name)

    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump MySQL schema (tables/views) to files.")
    parser.add_argument(
        "--output-sql",
        default=str(Path("schema.sql").resolve()),
        help="Path to write DDL dump (default: schema.sql)",
    )
    parser.add_argument(
        "--output-json",
        default=str(Path("schema.json").resolve()),
        help="Path to write JSON schema (default: schema.json)",
    )
    args = parser.parse_args(argv)

    base_dir = Path(__file__).resolve().parents[1]
    settings = load_app_config(base_dir)
    engine = make_engine(settings.model_dump())

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        "/*\n"
        f" Auto-generated schema snapshot by tools/sync_schema.py\n"
        f" Generated: {now}\n"
        "*/\n\n"
    )

    # SQL DDL dump
    ddl_sections = [
        header,
        _dump_tables_sql(engine),
        _dump_views_sql(engine),
        _dump_triggers_sql(engine),
    ]
    _write(Path(args.output_sql), "\n".join(s for s in ddl_sections if s))

    # JSON schema dump
    schema_json = _dump_schema_json(engine)
    Path(args.output_json).write_text(json.dumps(schema_json, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote: {args.output_sql}")
    print(f"Wrote: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
