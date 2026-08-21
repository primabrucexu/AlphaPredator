from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.database.migrations import migrate_legacy_tags, migrate_legacy_watchlists, migrate_stock_tag_order, sync_tagged_stocks_to_watchlist


def test_group_watchlists_migrate_to_tags_and_distinct_items():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE watchlist_groups (id INTEGER PRIMARY KEY, name VARCHAR(64), is_default BOOLEAN, created_at DATETIME)")
        connection.exec_driver_sql("CREATE TABLE watchlist_items (id INTEGER PRIMARY KEY, group_id INTEGER, symbol VARCHAR(16), created_at DATETIME)")
        connection.exec_driver_sql("CREATE INDEX ix_watchlist_items_symbol ON watchlist_items (symbol)")
        connection.exec_driver_sql("CREATE INDEX ix_watchlist_items_group_id ON watchlist_items (group_id)")
        connection.exec_driver_sql("CREATE TABLE stock_tags (id INTEGER PRIMARY KEY, symbol VARCHAR(16), name VARCHAR(64), UNIQUE(symbol, name))")
        connection.exec_driver_sql("INSERT INTO watchlist_groups VALUES (1, '默认分组', 1, '2026-01-01'), (2, '高股息', 0, '2026-01-01')")
        connection.exec_driver_sql("INSERT INTO watchlist_items VALUES (1, 1, '600519.SH', '2026-01-01'), (2, 2, '600519.SH', '2026-01-02'), (3, 2, '000001.SZ', '2026-01-03')")
        connection.exec_driver_sql("INSERT INTO stock_tags (symbol, name) VALUES ('600519.SH', '白酒'), ('300394.SZ', '光通信')")

    assert migrate_legacy_watchlists(engine) is True
    assert migrate_legacy_watchlists(engine) is False
    assert migrate_legacy_tags(engine) is True
    assert migrate_legacy_tags(engine) is False
    assert migrate_stock_tag_order(engine) is False
    assert sync_tagged_stocks_to_watchlist(engine) == 1
    assert sync_tagged_stocks_to_watchlist(engine) == 0

    assert {"watchlist_items", "legacy_watchlist_items", "legacy_watchlist_groups", "legacy_stock_tags", "tags"} <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        items = connection.execute(text("SELECT symbol FROM watchlist_items ORDER BY symbol")).scalars().all()
        tags = connection.execute(text(
            "SELECT stock_tags.symbol, tags.name FROM stock_tags JOIN tags ON tags.id = stock_tags.tag_id ORDER BY stock_tags.symbol, tags.name"
        )).all()
    assert items == ["000001.SZ", "300394.SZ", "600519.SH"]
    assert tags == [("000001.SZ", "高股息"), ("300394.SZ", "光通信"), ("600519.SH", "白酒"), ("600519.SH", "高股息")]


def test_existing_stock_tags_gain_independent_order():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE stock_tags (id INTEGER PRIMARY KEY, symbol VARCHAR(16), tag_id INTEGER)")
        connection.exec_driver_sql("INSERT INTO stock_tags VALUES (4, '600519.SH', 1), (7, '000001.SZ', 2), (9, '300394.SZ', 1)")

    assert migrate_stock_tag_order(engine) is True
    assert migrate_stock_tag_order(engine) is False

    with engine.connect() as connection:
        rows = connection.execute(text("SELECT symbol, tag_id, sort_order FROM stock_tags ORDER BY id")).all()
    assert rows == [("600519.SH", 1, 0), ("000001.SZ", 2, 0), ("300394.SZ", 1, 1)]
