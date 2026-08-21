from __future__ import annotations

from sqlalchemy import Engine, inspect

from .models import StockTag, Tag, WatchlistItem


def migrate_legacy_watchlists(engine: Engine) -> bool:
    """Convert group-based watchlists once while retaining the legacy tables."""
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "watchlist_items" not in tables:
            return False
        columns = {column["name"] for column in inspect(connection).get_columns("watchlist_items")}
        if "group_id" not in columns:
            return False
        if {"legacy_watchlist_items", "legacy_watchlist_groups"} & tables:
            raise RuntimeError("检测到未完成的旧自选迁移，请先恢复 legacy_* 表")

        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS stock_tags (
                id INTEGER PRIMARY KEY,
                symbol VARCHAR(16) NOT NULL,
                name VARCHAR(64) NOT NULL,
                UNIQUE(symbol, name)
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT OR IGNORE INTO stock_tags (symbol, name)
            SELECT wi.symbol, wg.name
            FROM watchlist_items wi
            JOIN watchlist_groups wg ON wg.id = wi.group_id
            WHERE wg.is_default = 0 AND trim(wg.name) <> ''
            """
        )
        connection.exec_driver_sql("ALTER TABLE watchlist_items RENAME TO legacy_watchlist_items")
        connection.exec_driver_sql("ALTER TABLE watchlist_groups RENAME TO legacy_watchlist_groups")
        connection.exec_driver_sql("DROP INDEX IF EXISTS ix_watchlist_items_symbol")
        connection.exec_driver_sql("DROP INDEX IF EXISTS ix_watchlist_items_group_id")
        WatchlistItem.__table__.create(connection)
        connection.exec_driver_sql(
            """
            INSERT INTO watchlist_items (symbol, created_at)
            SELECT symbol, MIN(created_at)
            FROM legacy_watchlist_items
            GROUP BY symbol
            """
        )
        return True


def migrate_legacy_tags(engine: Engine) -> bool:
    """Promote name-based stock tags to ordered global tag entities."""
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "stock_tags" not in tables:
            return False
        columns = {column["name"] for column in inspect(connection).get_columns("stock_tags")}
        if "name" not in columns:
            return False
        if "legacy_stock_tags" in tables:
            raise RuntimeError("检测到未完成的旧标签迁移，请先恢复 legacy_stock_tags 表")

        connection.exec_driver_sql("ALTER TABLE stock_tags RENAME TO legacy_stock_tags")
        connection.exec_driver_sql("DROP INDEX IF EXISTS ix_stock_tags_symbol")
        Tag.__table__.create(connection, checkfirst=True)
        StockTag.__table__.create(connection)
        connection.exec_driver_sql(
            """
            INSERT INTO tags (name, sort_order)
            SELECT name, ROW_NUMBER() OVER (ORDER BY name) - 1
            FROM (
                SELECT DISTINCT trim(name) AS name
                FROM legacy_stock_tags
                WHERE trim(name) <> ''
            ) names
            """
        )
        connection.exec_driver_sql(
            """
            INSERT OR IGNORE INTO stock_tags (symbol, tag_id, sort_order)
            SELECT legacy.symbol, tags.id,
                   ROW_NUMBER() OVER (PARTITION BY tags.id ORDER BY legacy.id) - 1
            FROM legacy_stock_tags legacy
            JOIN tags ON tags.name = trim(legacy.name)
            """
        )
        return True


def migrate_stock_tag_order(engine: Engine) -> bool:
    """Add per-tag stock ordering while preserving association ID order."""
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "stock_tags" not in tables:
            return False
        columns = {column["name"] for column in inspect(connection).get_columns("stock_tags")}
        if "sort_order" in columns:
            return False
        connection.exec_driver_sql("ALTER TABLE stock_tags ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        connection.exec_driver_sql(
            """
            UPDATE stock_tags
            SET sort_order = (
                SELECT COUNT(*)
                FROM stock_tags previous
                WHERE previous.tag_id = stock_tags.tag_id
                  AND previous.id < stock_tags.id
            )
            """
        )
        return True


def sync_tagged_stocks_to_watchlist(engine: Engine) -> int:
    """Ensure every manually tagged stock is also present in the watchlist."""
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if not {"stock_tags", "watchlist_items"} <= tables:
            return 0
        result = connection.exec_driver_sql(
            """
            INSERT OR IGNORE INTO watchlist_items (symbol, created_at)
            SELECT DISTINCT stock_tags.symbol, CURRENT_TIMESTAMP
            FROM stock_tags
            """
        )
        return result.rowcount
