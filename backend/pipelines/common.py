import time

from sqlalchemy.dialects.postgresql import insert

SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"]


def with_retries(fn, tries=3, base_delay=2.0):
    for attempt in range(tries):
        try:
            return fn()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(base_delay * (attempt + 1))


def clean(df):
    return df.astype(object).where(df.notna(), None)


def insert_ignore(session, model, rows, chunk=1000):
    for i in range(0, len(rows), chunk):
        part = rows[i: i + chunk]
        if part:
            session.execute(insert(model).values(
                part).on_conflict_do_nothing())
    session.commit()
