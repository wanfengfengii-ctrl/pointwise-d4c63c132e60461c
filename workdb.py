from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3


def _database_uri(path, mode):
    return Path(path).resolve().as_uri() + '?mode=' + mode


@contextmanager
def read_database(path):
    uri = _database_uri(path, 'ro')
    with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as db:
        db.execute('BEGIN')
        yield db


@contextmanager
def write_database(path, *, create=False):
    uri = _database_uri(path, 'rwc' if create else 'rw')
    with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as db:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            yield db
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
