"""Apply the idempotent RFP schema migrations to DATABASE_URL in order."""
from pathlib import Path

from database import get_engine


MIGRATION_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATIONS = (
    "20261024_rfp_intake.sql",
    "20261110_rfp_response_generation.sql",
    "20261112_rfp_sse_acceptance.sql",
    "20261201_rfp_approval.sql",
)


def main() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        for name in MIGRATIONS:
            migration = MIGRATION_DIR / name
            sql = migration.read_text(encoding="utf-8")
            statements = [
                statement.strip()
                for statement in sql.split(";")
                if statement.strip()
            ]
            for statement in statements:
                connection.exec_driver_sql(statement)
            print(f"Applied {migration.name}")


if __name__ == "__main__":
    main()
