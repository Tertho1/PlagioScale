import psycopg
conn = psycopg.connect('host=postgres dbname=plagioscale user=plagio password=plagio_pass')
cur = conn.cursor()

print("=== Similarity Results ===")
cur.execute("SELECT * FROM similarity_results WHERE batch_id = '154aed35-fd61-448f-a091-57490f5dce1d'")
for r in cur.fetchall():
    print(r)

print("\n=== Jobs status ===")
cur.execute("SELECT job_id, status, error FROM jobs WHERE job_id LIKE '%154aed35%' ORDER BY created_at DESC LIMIT 5")
for r in cur.fetchall():
    print(r)

print("\n=== AI scores ===")
cur.execute("SELECT submission_id, ai_score FROM submissions WHERE batch_id = '154aed35-fd61-448f-a091-57490f5dce1d'")
for r in cur.fetchall():
    print(r)

conn.close()
