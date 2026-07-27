import psycopg
conn = psycopg.connect('host=postgres dbname=plagioscale user=plagio password=plagio_pass')
cur = conn.cursor()
# Clean up old batch compute jobs for this batch so user can start fresh
cur.execute("DELETE FROM jobs WHERE job_id LIKE '%154aed35%' AND status != 'COMPLETED'")
print(f"Deleted {cur.rowcount} stale job records")
# But keep the COMPLETED ones so the matrix remains available
conn.commit()
conn.close()
