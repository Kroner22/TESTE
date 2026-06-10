import sqlite3

c = sqlite3.connect("data/mvp.db").cursor()

# Check fallback_soccer_5 specifically
print("=== fallback_soccer_5 ===")
rows = c.execute(
    "SELECT event_id, outcome, odd, ev FROM opportunities WHERE event_id = 'fallback_soccer_5'"
).fetchall()
if rows:
    for r in rows:
        print(f"  {r[1]}: odd={r[2]} ev={r[3]}")
else:
    print("  (no opportunities)")

# All fallback_soccer events
print("\n=== ALL FALLBACK SOCCER ===")
rows = c.execute(
    "SELECT event_id, COUNT(*) as cnt, MAX(ev) as maxev "
    "FROM opportunities WHERE event_id LIKE 'fallback_soccer_%' "
    "GROUP BY event_id ORDER BY maxev DESC"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} opps, max EV={r[2]}")

# Check the highest EV opportunities by event
print("\n=== ALL OPPORTUNITIES WITH EV > 0.02 ===")
rows = c.execute(
    "SELECT event_id, outcome, odd, ev FROM opportunities WHERE ev > 0.02 ORDER BY ev DESC"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} odd={r[2]} ev={r[3]}")

# Check how many odds updates we're getting (is data flowing properly?)
print("\n=== ODDS PER EVENT (top 5) ===")
rows = c.execute(
    "SELECT event_id, COUNT(*) FROM odds GROUP BY event_id ORDER BY COUNT(*) DESC LIMIT 5"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} odds records")
