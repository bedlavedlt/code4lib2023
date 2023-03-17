import sqlite3
import logging
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)


class NewColumn(NamedTuple):
    name: str
    type: str
    options: Optional[str] = None


class Table:
    """object for inserting, updating, deleting from a table"""

    def __init__(self, database_connection: sqlite3.Connection,
                 table_name: str,
                 columns: list[NewColumn],
                 primary_key: Optional[tuple[str, ...]] = None):

        logger.debug(f"Initializing table: {table_name}")
        self.name = table_name
        self.database_connection = database_connection
        self.create_table(columns, primary_key)

    def insert(self, items_to_insert: dict[str, str | int | None]):
        """insert items into table"""

        keys = ", ".join(f"{key}" for key in items_to_insert.keys())
        values = ", ".join("?" for _ in range(len(items_to_insert)))
        statement = (f"INSERT INTO {self.name} "
                     f"({keys}) VALUES ({values});")
        params = tuple(items_to_insert.values())
        logger.debug(f"Database insert. {locals()}")
        self.execute_statement(statement, params)

    def update(self, key: dict[str, str | int],
               items_to_update: dict[str, str | int]):

        keys = " AND ".join(f"{key}=?" for key in key.keys())
        sets = ", ".join(f"{key}=?" for key in items_to_update.keys())
        statement = f"UPDATE {self.name} SET {sets} WHERE {keys};"
        params = tuple(items_to_update.values()) + tuple(key.values())
        logger.debug(f"Database update. {locals()}")
        self.execute_statement(statement, params)

    def delete(self, key: dict[str, str]):

        keys = " AND ".join(f"{key}=?" for key in key.keys())
        params = tuple(key.values())
        statement = f"DELETE FROM {self.name} WHERE {keys};"
        logger.debug(f"Database delete. {locals()}")
        self.execute_statement(statement, params)

    def execute_statement(self, statement: str,
                          params: tuple[str | int | None, ...]):
        """Handle cursor and commit changes"""

        logger.debug("Executing statement. "
                     f"Statement: {statement} "
                     f"Params: {params}")
        with self.database_connection as connection:
            connection.execute(statement, params)

    def create_table(self, columns: list[NewColumn],
                     primary_key: Optional[tuple[str, ...]] = None):

        columns_text = ', '.join(
            f"{column.name} {column.type} {column.options or ''}"
            for column in columns
        )
        primary_key_text = f", PRIMARY KEY {primary_key}"
        create_table_statement = (
            "CREATE TABLE IF NOT EXISTS "
            f"{self.name} ({columns_text}"
            f"{primary_key_text if primary_key else ''});"
        )

        self.execute_statement(
            create_table_statement, tuple()
        )

    def list_columns(self):

        select_columns_statement = f"select * from {self.name}"
        logger.debug("Executing statement. "
                     f"Statement: {select_columns_statement}")

        with self.database_connection as connection:
            cursor = connection.execute(select_columns_statement)
            existing_columns = list(map(lambda x: x[0], cursor.description))

        logger.debug(f"Existing columns: {existing_columns}")

        return existing_columns

    def add_columns(self, columns: list[NewColumn]):

        select_columns_statement = f"select * from {self.name};"
        logger.debug("Executing statement. "
                     f"Statement: {select_columns_statement}")

        with self.database_connection as connection:
            cursor = connection.execute(select_columns_statement)
            existing_columns = list(map(lambda x: x[0], cursor.description))

        logger.debug(f"Existing columns: {existing_columns}")

        for column in columns:
            if column.name not in existing_columns:

                add_column_statement = (f"ALTER TABLE {self.name} ADD COLUMN "
                                        f"{column.name} {column.type} "
                                        f"{column.options};")
                logger.debug(f"Adding column to table: "
                             f"{add_column_statement}")

                self.execute_statement(add_column_statement, tuple())


class Database:

    def __init__(self, database_path: str):
        logger.debug(f"Initializing database: {database_path}")
        self.connection = sqlite3.connect(f"{database_path}")
        self.database_path = database_path
        self.tables: dict[str, Table] = {}

    def add_table(self, table_name: str, columns: list[NewColumn],
                  primary_key: Optional[tuple[str, ...]] = None):

        list_tables_query = ("SELECT name FROM sqlite_master "
                             "WHERE type='table';")
        with self.connection as connection:
            cursor = connection.execute(list_tables_query)
            tables = [table[0] for table in cursor.fetchall()]

        if table_name in tables:
            logger.debug("Table already exists in "
                         f"{self.database_path}: {tables}")
        else:
            logger.debug(f"Adding table '{table_name}' to database "
                         f"'{self.database_path}'.")
        self.tables[table_name] = Table(self.connection,
                                        table_name,
                                        columns,
                                        primary_key)

    def close(self):

        self.connection.close()

    def add_columns(self, table_name: str, new_columns: list[NewColumn]):
        self.tables[table_name].add_columns(new_columns)

    def insert(self, table_name: str,
               items_to_insert: dict[str, str | int | None]):
        # self._verify_table(table_name)
        self.tables[table_name].insert(items_to_insert)

    def update(self, table_name: str,
               key: dict[str, str | int],
               items_to_update: dict[str, str | int]):

        # self._verify_table(table_name)
        self.tables[table_name].update(key, items_to_update)

    def delete(self, table_name: str, key: dict[str, str]):

        # self._verify_table(table_name)
        self.tables[table_name].delete(key)

    # # def _verify_table(self, table_name: str):

    #     if table_name not in self.tables:
    #         self.add_table(table_name)
