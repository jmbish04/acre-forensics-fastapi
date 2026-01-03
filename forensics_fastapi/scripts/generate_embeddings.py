import time

import psycopg2
from src.config import DB_CONFIG
from src.core.worker_ai import WorkerAI

BATCH_SIZE = 50


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def process_table(table_name, id_col, text_cols):
    ai = WorkerAI()
    conn = get_conn()
    cur = conn.cursor()

    print(f"Processing table '{table_name}'...")

    cols_sql = " || ' ' || ".join([f"COALESCE({c}, '')" for c in text_cols])

    # Update count query to respect already vectorized rows
    cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE embedding IS NULL")
    total_to_process = cur.fetchone()[0]
    print(f"Found {total_to_process} rows to process in {table_name}.")

    processed = 0

    while True:
        cur.execute(f"""
            SELECT {id_col}, {cols_sql} as text_content
            FROM {table_name}
            WHERE embedding IS NULL
            LIMIT {BATCH_SIZE}
        """)
        rows = cur.fetchall()

        if not rows:
            break

        ids = [r[0] for r in rows]
        texts = [r[1].strip() if r[1] else " " for r in rows]
        # Ensure no empty strings for API stability
        texts = [t if len(t) > 0 else " " for t in texts]

        embeddings = ai.generate_embeddings(texts)

        if embeddings:
            update_data = []
            for i, vector in enumerate(embeddings):
                update_data.append((vector, ids[i]))

            try:
                # Ensure correct vector dimension (768) if not already
                # (Ideally handled in setup, but safety check ok to omit if stable)

                # Check if table has vectorizedAt column to update timestamp
                has_timestamp_col = False
                if table_name == "messages":
                    has_timestamp_col = True

                if has_timestamp_col:
                    cur.executemany(
                        f'UPDATE {table_name} SET embedding = %s, "vectorizedAt" = NOW() WHERE {id_col} = %s',
                        update_data,
                    )
                else:
                    cur.executemany(
                        f"UPDATE {table_name} SET embedding = %s WHERE {id_col} = %s", update_data
                    )

                conn.commit()
                processed += len(rows)
                print(f" - Processed {processed}/{total_to_process}...")
            except Exception as e:
                print(f"DB Update Error: {e}")
                conn.rollback()
                break
        else:
            print("Failed to generate embeddings for batch. Aborting table.")
            break

        time.sleep(0.1)

    cur.close()
    conn.close()
    print(f"Finished {table_name}.")


def main():
    # Process Threads (Subject only)
    process_table("threads", "id", ["subject"])

    # Process Messages (Subject + Body)
    process_table("messages", "id", ["subject", "bodyplain"])


if __name__ == "__main__":
    main()
