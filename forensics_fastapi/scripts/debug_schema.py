from sqlalchemy import text
from src.config import DB_CONFIG
from src.core.database import get_engine


def inspect_tables():
    engine = get_engine(DB_CONFIG)
    tables = ["attachments", "email_tags", "rolodex", "threads", "messages"]

    with engine.connect() as conn:
        for t in tables:
            print(f"\n--- TABLE: {t} ---")
            try:
                # Get columns
                result = conn.execute(
                    text(
                        f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{t}'"
                    )
                )
                for row in result:
                    print(f"  {row[0]} ({row[1]})")

                # Get row count
                count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"  Row Count: {count}")

                # Sample data
                if count > 0:
                    print("  Sample Row:")
                    sample = conn.execute(text(f"SELECT * FROM {t} LIMIT 1")).mappings().fetchone()
                    print(f"    {dict(sample)}")
            except Exception as e:
                print(f"  Error: {e}")


if __name__ == "__main__":
    inspect_tables()
