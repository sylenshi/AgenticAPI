"""分页参数归一化（/monitor、/redeem、/admin 各分页接口共用，保证口径一致）"""

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 10


def normalize_page(page: int, page_size: int) -> tuple[int, int]:
    """归一化分页参数：page 从 1 起；pageSize 越界（<1 或 >100）回落默认 10"""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        page_size = DEFAULT_PAGE_SIZE
    return page, page_size
