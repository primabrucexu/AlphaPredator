from sqlmodel import Field, SQLModel


class StockProfile(SQLModel, table=True):
    __tablename__ = 'stock_profiles'

    stock_code: str = Field(primary_key=True)
    stock_name: str
    sectors_json: str
    ai_quick_summary: str


class StockList(SQLModel, table=True):
    __tablename__ = 'stock_list'

    full_code: str = Field(primary_key=True)
    code: str
    name: str
    is_st: bool = False
    cnspell: str = ''
    market: str = ''


class TaskInfo(SQLModel, table=True):
    __tablename__ = 'task_info'

    task_id: str = Field(primary_key=True)
    task_type: str = 'MARKET_DATA'
    start_date: str
    end_date: str
    status: str = 'PENDING'
    total_items: int = 0
    processed_items: int = 0
    current_label: str = ''
    error_message: str = ''
    task_start_date: str = ''
    task_end_date: str = ''


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
