from sqlmodel import Field, SQLModel


class StockProfile(SQLModel, table=True):
    __tablename__ = 'stock_profiles'

    stock_code: str = Field(primary_key=True)
    stock_name: str
    sectors_json: str
    ai_quick_summary: str


class StockList(SQLModel, table=True):
    __tablename__ = 'stock_list'

    ts_code: str = Field(primary_key=True)
    symbol: str
    name: str
    cnspell: str = ''
    market: str = ''
    list_status: str = ''
    list_date: str = ''
    delist_date: str = ''
    uploaded_at: str


class InitTask(SQLModel, table=True):
    __tablename__ = 'init_task'

    task_id: str = Field(primary_key=True)
    task_type: str = 'MARKET_DATA'
    mode: str = 'RANGE'
    start_date: str
    end_date: str
    status: str = 'PENDING'
    total_days: int = 0
    processed_days: int = 0
    trading_days: int = 0
    done_trading_days: int = 0
    current_date: str = ''
    error_message: str = ''
    created_at: str = ''
    started_at: str = ''
    finished_at: str = ''


class InitTaskDay(SQLModel, table=True):
    __tablename__ = 'init_task_day'

    task_id: str = Field(primary_key=True)
    trade_date: str = Field(primary_key=True)
    is_trading_day: int = 0
    status: str = 'PENDING'
    row_count: int = 0
    started_at: str = ''
    finished_at: str = ''
    error_message: str = ''


class DataRangeMeta(SQLModel, table=True):
    __tablename__ = 'data_range_meta'

    dataset: str = Field(primary_key=True)
    min_trade_date: str = ''
    max_trade_date: str = ''
    trading_day_count: int = 0
    updated_at: str = ''


class JygsAuth(SQLModel, table=True):
    __tablename__ = 'jygs_auth'

    id: int | None = Field(default=None, primary_key=True)
    auth_cookie: str = ''
    updated_at: str = ''
    last_checked_at: str = ''
    is_valid: int = 0
    last_error: str = ''


class JygsSyncLog(SQLModel, table=True):
    __tablename__ = 'jygs_sync_log'

    slot_key: str = Field(primary_key=True)
    trade_date: str
    mode: str
    status: str
    message: str = ''
    triggered_at: str
