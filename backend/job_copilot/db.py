import os
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends
from psycopg.rows import DictRow, dict_row

SEEDED_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
# The invented person Eval Cases run as. Their spending counts towards the owner's cap.
EVAL_USER_ID = UUID("00000000-0000-0000-0000-00000000e7a1")


def connect() -> psycopg.Connection[DictRow]:
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def current_user_id() -> UUID:
    # The app runs on one computer for one person, so there is no login.
    return SEEDED_USER_ID


UserId = Annotated[UUID, Depends(current_user_id)]
