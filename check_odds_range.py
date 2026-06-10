import sqlite3

c = sqlite3.connect("data/mvp.db").cursor()

# Check all odds > 2.5 (to detect slips)
print("=== ODDS > 2.5 (potential slips) ===")
rows = c.execute(
    "SELECT odd, event_id, bookmaker, outcome "
    "FROM odds WHERE odd > 2.5 AND event_id LIKE 'fallback%' "
    "ORDER BY odd DESC LIMIT 20"
).fetchall()
for r in rows:
    print(f"  {r[1][:25]}: {r[2]} {r[3]} @ {r[0]}")

# Check odds that are significantly different within the same event
print("\n=== FALLBACK_SOCCER_3 ODDS (one with highest EV) ===")
rows = c.execute(
    "SELECT odd, bookmaker, outcome FROM odds "
    "WHERE event_id = 'fallback_soccer_3' "
    "ORDER BY odd DESC LIMIT 15"
).fetchall()
for r in rows:
    print(f"  {r[1]}: {r[2]} @ {r[0]}")

# Check the odds for the event with highest EV 
print("\n=== FALLBACK_AMERICAN_FOOTBALL_19 ODDS (max EV) ===")
rows = c.execute(
    "SELECT odd, bookmaker, outcome FROM odds "
    "WHERE event_id = 'fallback_american_football_19' "
    "ORDER BY odd DESC LIMIT 10"
).fetchall()
for r in rows:
    print(f"  {r[1]}: {r[2]} @ {r[0]}")

# Check unique odds values to see distribution
print("\n=== UNIQUE ODD VALUES (fallback) ===")
rows = c.execute(
    "SELECT odd, COUNT(*) as cnt FROM odds "
    "WHERE event_id LIKE 'fallback%' "
    "GROUP BY odd HAVING cnt > 5 "
    "ORDER BY odd LIMIT 30"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}x")
