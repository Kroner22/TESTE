import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), "data", "mvp.db")
if not os.path.exists(db_path):
    print("Database file not found")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print("=== TABLES ===")
for t in tables:
    count = c.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
    print(f"  {t[0]}: {count} rows")

# Show last few events
print("\n=== RECENT EVENTS ===")
try:
    rows = c.execute("SELECT event_id, sport, home_team, away_team, status FROM events ORDER BY id DESC LIMIT 5").fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} {r[2]} vs {r[3]} [{r[4]}]")
except Exception as e:
    print(f"  Error: {e}")

# Show recent odds
print("\n=== RECENT ODDS (last 3) ===")
try:
    rows = c.execute("SELECT event_id, bookmaker, outcome, odd, is_opening FROM odds ORDER BY id DESC LIMIT 3").fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} {r[2]} @ {r[3]} opening={r[4]}")
except Exception as e:
    print(f"  Error: {e}")

# Show paper trades
print("\n=== PAPER TRADES ===")
try:
    rows = c.execute("SELECT position_id, event_id, outcome, entry_odd, stake, is_open FROM paper_trades ORDER BY id DESC LIMIT 5").fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]}: {r[1]} {r[2]} @ {r[3]} stake={r[4]} open={r[5]}")
    else:
        print("  (empty)")
except Exception as e:
    print(f"  Error: {e}")

# Show CLV records
print("\n=== CLV RECORDS ===")
try:
    rows = c.execute("SELECT event_id, clv_pct, clv_grade, simulated_ev FROM clv_records ORDER BY id DESC LIMIT 5").fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]}: CLV={r[1]}% grade={r[2]} EV={r[3]}")
    else:
        print("  (empty)")
except Exception as e:
    print(f"  Error: {e}")

# Show market snapshots
print("\n=== MARKET SNAPSHOTS ===")
try:
    count = c.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0]
    print(f"  Total: {count}")
    if count > 0:
        rows = c.execute("SELECT snapshot_id, provider_count, total_odds_points FROM market_snapshots ORDER BY id DESC LIMIT 3").fetchall()
        for r in rows:
            print(f"  {r[0]}: {r[1]} providers, {r[2]} odds points")
except Exception as e:
    print(f"  Error: {e}")

# Show telemetry
print("\n=== PROVIDER TELEMETRY (last 5) ===")
try:
    rows = c.execute("SELECT provider_name, event, healthy, latency_ms FROM provider_telemetry ORDER BY id DESC LIMIT 5").fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]}: {r[1]} healthy={r[2]} latency={r[3]}ms")
    else:
        print("  (empty)")
except Exception as e:
    print(f"  Error: {e}")

conn.close()
