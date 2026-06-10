import sqlite3

c = sqlite3.connect("data/mvp.db").cursor()

# Check what odds are being generated
print("=== FALLBACK ODDS (sample) ===")
rows = c.execute("""
    SELECT odd, event_id, bookmaker, outcome 
    FROM odds WHERE event_id LIKE 'fallback%' 
    ORDER BY id DESC LIMIT 15
""").fetchall()
for r in rows:
    print(f"  {r[1][:25]}: {r[2]} {r[3]} @ {r[0]}")

# Check opportunities detail
print("\n=== TOP OPPORTUNITIES DETAIL ===")
rows = c.execute("""
    SELECT event_id, outcome, odd, ev, edge_score, confidence_score, value_grade
    FROM opportunities ORDER BY ev DESC LIMIT 5
""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} odd={r[2]} ev={r[3]} edge={r[4]} conf={r[5]} grade={r[6]}")

# Check alerts
print(f"\n=== ALERTS: {c.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]} ===")
print(f"=== PAPER TRADES: {c.execute('SELECT COUNT(*) FROM paper_trades').fetchone()[0]} ===")
print(f"=== CLV RECORDS: {c.execute('SELECT COUNT(*) FROM clv_records').fetchone()[0]} ===")

# Check fallback template odds vs what's in DB
print("\n=== RAW ODDS DISTRIBUTION ===")
rows = c.execute("SELECT odd, COUNT(*) as cnt FROM odds WHERE event_id LIKE 'fallback%' GROUP BY odd HAVING cnt > 2 ORDER BY odd LIMIT 20").fetchall()
print(f"  {len(rows)} distinct odds values")
for r in rows:
    print(f"  {r[0]}: {r[1]}x")

# Check the provider_telemetry
print(f"\n=== TELEMETRY: {c.execute('SELECT COUNT(*) FROM provider_telemetry').fetchone()[0]} ===")
