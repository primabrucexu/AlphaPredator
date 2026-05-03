"""
Tests for initializer snapshot helpers.

The _derive_snapshots_from_bars function was removed as part of the V2 refactor
(the V2 flow writes directly to market_daily_quote without snapshot derivation).
The snapshot rebuild for the daily update is handled by updater._rebuild_snapshot.
This file is kept as a placeholder; substantive V2 tests are in test_v2_initializer.py.
"""
