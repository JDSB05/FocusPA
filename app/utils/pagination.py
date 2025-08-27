from math import ceil
from types import SimpleNamespace
from flask import request


def paginate(data_source, page=None, per_page=None, total=None):
    """Universal pagination helper.

    Accepts either a SQLAlchemy query (with ``paginate`` method) or an iterable of
    pre-fetched items. Optionally ``total`` can be provided for the second case.
    ``page`` and ``per_page`` default to values from ``request.args`` when not
    explicitly supplied.

    Returns a tuple of ``items``, ``pagination`` object and the calculated
    ``start_page`` and ``end_page`` for navigation widgets.
    """
    if page is None:
        page = request.args.get('page', 1, type=int)
    if per_page is None:
        per_page = request.args.get('per_page', 20, type=int)

    if hasattr(data_source, 'paginate'):
        pagination = data_source.paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items
    else:
        items = data_source
        if total is None:
            total = len(items)
        pages = ceil(total / per_page) if per_page else 0
        pagination = SimpleNamespace(
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
            has_prev=page > 1,
            has_next=page < pages,
            prev_num=page - 1 if page > 1 else None,
            next_num=page + 1 if page < pages else None,
        )

    start_page = max(1, pagination.page - 2)
    end_page = min(pagination.pages, pagination.page + 2)

    return items, pagination, start_page, end_page
