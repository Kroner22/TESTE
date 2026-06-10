"""Daily Quant Validation Routine"""
import json, urllib.request, sys, time
from datetime import datetime, timezone
from backend.app.database import SessionLocal, Event, OddsRecord, OpportunityRecord, PaperTradeRecord, AlertRecord, ClvRecordPersistence, MarketSnapshotRecord, ProviderTelemetryRecord

def api(path):
    try:
        r = urllib.request.urlopen(f"http://localhost:8000{path}", timeout=5)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

print("=" * 60)
print("  DAILY QUANT VALIDATION — SPORTS QUANT SYSTEM")
print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("=" * 60)

db = SessionLocal()

# === 1. PROVIDER STATUS ===
print("\n## 1. PROVIDER STATUS")
live = api("/health/live")
if "error" in live:
    print(f"  API ERROR: {live['error']}")
else:
    print(f"  Uptime: {live.get('uptime_seconds', 0):.0f}s")
    print(f"  Data mode: {live.get('mode', '?')}")
    providers = live.get("providers", {})
    print(f"  Active providers: {sum(1 for p in providers.values() if p.get('healthy'))}/{len(providers)}")
    for name, p in sorted(providers.items()):
        h = "HEALTHY" if p.get("healthy") else "UNHEALTHY"
        f = p.get("consecutive_failures", 0)
        ls = f"last={p.get('last_success','?')}" if p.get("last_success") else ""
        print(f"    {name:20s} {h:10s} failures={f} {ls}")

# === 2. DATA VOLUME ===
print("\n## 2. DATA VOLUME")
event_count = db.query(Event).count()
odds_count = db.query(OddsRecord).count()
snap_count = db.query(MarketSnapshotRecord).count()
opp_count = db.query(OpportunityRecord).count()
trade_count = db.query(PaperTradeRecord).count()
alert_count = db.query(AlertRecord).count()
clv_count = db.query(ClvRecordPersistence).count()
tel_count = db.query(ProviderTelemetryRecord).count()

print(f"  Events:          {event_count:>5}")
print(f"  Odds records:    {odds_count:>5}")
print(f"  Snapshots:       {snap_count:>5}")
print(f"  Opportunities:   {opp_count:>5}")
print(f"  Paper trades:    {trade_count:>5}")
print(f"  Alerts:          {alert_count:>5}")
print(f"  CLV records:     {clv_count:>5}")
print(f"  Telemetry:       {tel_count:>5}")

evals = api("/reports/efficiency") if not "error" in live else {}
if "error" not in evals:
    print(f"\n  Validation reports: {len(evals) if isinstance(evals, list) else '?'}")

# === 3. KEY METRICS ===
print("\n## 3. KEY METRICS")

# Paper trade stats
trades = db.query(PaperTradeRecord).all()
open_trades = [t for t in trades if t.is_open]
closed_trades = [t for t in trades if not t.is_open]
print(f"  Open positions:   {len(open_trades)}")
print(f"  Closed positions: {len(closed_trades)}")

if closed_trades:
    total_pnl = sum(float(t.pnl or 0) for t in closed_trades)
    total_stake = sum(float(t.stake or 0) for t in closed_trades)
    win_rate = sum(1 for t in closed_trades if float(t.pnl or 0) > 0) / len(closed_trades) * 100
    roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0
    print(f"  Total PnL:        ${total_pnl:.2f}")
    print(f"  Total staked:     ${total_stake:.2f}")
    print(f"  Win rate:         {win_rate:.1f}%")
    print(f"  ROI:              {roi:.2f}%")
else:
    print(f"  Total staked:     ${sum(float(t.stake or 0) for t in trades):.2f}")
    print(f"  (No closed trades yet)")

# Opportunity stats
opps = db.query(OpportunityRecord).all()
if opps:
    evs = [float(o.ev) for o in opps]
    grades = [o.value_grade for o in opps]
    print(f"  Opportunities:    {len(opps)}")
    print(f"  EV range:         {min(evs)*100:.2f}% to {max(evs)*100:.2f}%")
    print(f"  EV avg:           {sum(evs)/len(evs)*100:.2f}%")
    print(f"  Grades:           {', '.join(f'{g}={grades.count(g)}' for g in sorted(set(grades)))}")

# Alert stats
alerts = db.query(AlertRecord).all()
if alerts:
    types = [a.alert_type for a in alerts]
    severities = [a.severity for a in alerts]
    print(f"  Alerts:           {len(alerts)}")
    print(f"  Types:            {', '.join(f'{t}={types.count(t)}' for t in sorted(set(types)))}")
    print(f"  Severities:       {', '.join(f'{s}={severities.count(s)}' for s in sorted(set(severities)))}")

# Sports distribution
sports = db.query(Event.sport).distinct().all()
sport_events = {}
for (s,) in sports:
    cnt = db.query(Event).filter(Event.sport == s).count()
    sport_events[s] = cnt
print(f"  Sports:           {', '.join(f'{k}={v}' for k,v in sorted(sport_events.items()))}")

# Odds by provider
providers_telemetry = db.query(ProviderTelemetryRecord).order_by(ProviderTelemetryRecord.id.desc()).limit(20).all()
if providers_telemetry:
    provider_names = set(t.provider_name for t in providers_telemetry)
    print(f"  Providers seen:   {', '.join(sorted(provider_names))}")

# === 4. CLV ANALYSIS ===
print("\n## 4. CLV ANALYSIS")
clv_records = db.query(ClvRecordPersistence).all()
if clv_records:
    clvs = [float(r.clv_pct) for r in clv_records]
    evs_clv = [float(r.simulated_ev or 0) for r in clv_records]
    avg_clv = sum(clvs) / len(clvs)
    avg_ev_clv = sum(evs_clv) / len(evs_clv) if evs_clv else 0
    positive = sum(1 for c in clvs if c > 0)
    negative = sum(1 for c in clvs if c < 0)
    
    print(f"  CLV records:      {len(clv_records)}")
    print(f"  Avg CLV:          {avg_clv:.2f}%")
    print(f"  Avg simulated EV: {avg_ev_clv:.2f}%")
    print(f"  Positive/Negative:{positive}/{negative}")
    print(f"  Hit rate:         {positive/len(clv_records)*100:.1f}%")
else:
    print("  No CLV data yet — need closed events")

# === 5. PATTERN DETECTION ===
print("\n## 5. PATTERN DETECTION")
if opps:
    high_ev = [o for o in opps if float(o.ev) > 0.05]
    low_conf = [o for o in opps if float(o.confidence_score) < 0.5]
    print(f"  High EV opps (>5%): {len(high_ev)}")
    print(f"  Low conf opps (<50%): {len(low_conf)}")
    
    # Multi-outcome same event
    opp_events = {}
    for o in opps:
        opp_events.setdefault(o.event_id, []).append(o.outcome)
    multi_outcome = {k: v for k, v in opp_events.items() if len(set(v)) >= 2}
    print(f"  Events w/ multiple outcomes: {len(multi_outcome)}")

# Timing check
if trades:
    earliest = min(t.entry_timestamp for t in trades) if trades else 0
    latest = max(t.entry_timestamp for t in trades) if trades else 0
    trade_span = latest - earliest
    trades_per_min = len(trades) / (trade_span / 60) if trade_span > 0 else 0
    print(f"  Trade span:       {trade_span:.0f}s")
    print(f"  Trade rate:       {trades_per_min:.2f}/min")

db.close()

# === 6. FINAL VERDICT ===
print("\n" + "=" * 60)
print("  FINAL VERDICT")
print("=" * 60)

issues = []
positives = []

# Provider health
if "error" not in live:
    providers = live.get("providers", {})
    all_healthy = all(p.get("healthy") for p in providers.values())
    positives.append(f"Providers: {sum(1 for p in providers.values() if p.get('healthy'))}/{len(providers)} healthy") if all_healthy else issues.append(f"Unhealthy providers detected")

# Data flow
if event_count > 0: positives.append(f"Events flowing: {event_count}")
else: issues.append("No events in DB")

if odds_count > 100: positives.append(f"Odds volume adequate: {odds_count}")
elif odds_count > 0: issues.append(f"Low odds volume: {odds_count}")

if trade_count > 0: positives.append(f"Paper trading active: {trade_count} positions")
else: issues.append("No paper trades")

# CLV
if clv_records:
    if avg_clv > 0: positives.append(f"CLV positive: {avg_clv:.2f}%")
    else: issues.append(f"CLV negative: {avg_clv:.2f}%")

print()
for p in positives:
    print(f"  [OK] {p}")
for i in issues:
    print(f"  [WARN] {i}")

if not issues:
    print("\n  >>> SISTEMA OPERACIONAL — Aguardando CLV para validacao estatistica <<<")
elif len(issues) <= 2:
    print("\n  >>> SISTEMA FUNCIONAL — Pequenos ajustes necessarios <<<")
else:
    print("\n  >>> REVISAO NECESSARIA — Multiplos problemas detectados <<<")

print()
