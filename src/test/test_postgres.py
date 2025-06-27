import psycopg2
import time

conn = psycopg2.connect(
    dbname="mmv",
    user="demo",
    password="demo123456",
    host="localhost",
    port="6670"
)
cur = conn.cursor()

st_time = time.time()
# Replace 'your_table' and 'your_column' with actual names
cur.execute("SELECT DISTINCT array_agg(v_id) FROM videos;")

# # Fetch all unique values
# unique_values = [row[0] for row in cur.fetchall()]

print(cur.fetchone()[0])
# print(unique_values)
print(f"----Duration: {time.time()-st_time}")