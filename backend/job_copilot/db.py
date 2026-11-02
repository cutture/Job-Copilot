import os

import psycopg
from psycopg.rows import DictRow, dict_row


def connect() -> psycopg.Connection[DictRow]:
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
