from pathlib import Path

import psycopg

from app.core.config import get_settings

MIGRATIONS_PATH = Path(__file__).resolve().parents[2] / "migrations"


def run_migrations() -> None:
    settings = get_settings()
    migration_files = sorted(MIGRATIONS_PATH.glob("*.sql"))

    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            for migration_file in migration_files:
                version = migration_file.stem
                cursor.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                )
                if cursor.fetchone():
                    continue

                cursor.execute(migration_file.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )

        connection.commit()


if __name__ == "__main__":
    run_migrations()
