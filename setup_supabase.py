#!/usr/bin/env python3
"""
Check that the Supabase `ideas` table exists and is reachable.

The PostgREST API cannot create tables, so if the table is missing this prints
the SQL to paste into the Supabase SQL editor (also stored in
supabase/schema.sql).

Usage:
    python setup_supabase.py
"""

import importlib

import config

SupabaseIdeaStore = importlib.import_module("01_ideas.supabase_store").SupabaseIdeaStore

SCHEMA_PATH = config.PROJECT_ROOT / "supabase" / "schema.sql"


def main() -> int:
    store = SupabaseIdeaStore()

    if not store.is_configured:
        print("❌ SUPABASE_URL / SUPABASE_SERVICE_KEY are not set in .env.")
        return 1

    print(f"🔎 Checking Supabase table '{store.table}' at {store.url} ...")
    if store.table_exists():
        try:
            rows = store.list_ideas(limit=1)
            print(f"✅ Table '{store.table}' exists ({len(rows)} row(s) visible).")
        except Exception:
            print(f"✅ Table '{store.table}' exists.")
        return 0

    print(f"\n❌ Table '{store.table}' was not found.\n")
    print("Run this SQL once in the Supabase SQL editor:")
    print("  https://supabase.com/dashboard/project/"
          f"{config.SUPABASE_URL.replace('https://', '').split('.')[0]}/sql/new\n")
    if SCHEMA_PATH.exists():
        print("-" * 60)
        print(SCHEMA_PATH.read_text(encoding="utf-8"))
        print("-" * 60)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())