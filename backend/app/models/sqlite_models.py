from sqlmodel import Field, SQLModel



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


