import psycopg

with psycopg.connect(DATABASE_URL) as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS audit (id serial primary key, payload jsonb)")
