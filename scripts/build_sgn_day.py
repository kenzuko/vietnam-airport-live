from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "sgn.json"
DAY = ROOT / "data" / "sgn-day.json"
HISTORY_DIR = ROOT / "data" / "history"
HISTORY_INDEX = ROOT / "data" / "history-index.json"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize(value):
    return " ".join(str(value or "").lower().split())


def flight_key(f):
    return "|".join([
        str(f.get("direction") or ""),
        str(f.get("terminal") or ""),
        str(f.get("scheduled") or ""),
        normalize(f.get("route_airport")),
    ])


def merge_flight(store, flight):
    key = flight_key(flight)
    if not key.strip("|"):
        return
    if key not in store:
        store[key] = dict(flight)
        return
    old = store[key]
    nums = list(old.get("flight_numbers") or [])
    for n in flight.get("flight_numbers") or []:
        if n and n not in nums:
            nums.append(n)
    old["flight_numbers"] = nums
    if nums:
        old["flight_number"] = old.get("flight_number") or nums[0]
    for field in ("estimated", "actual", "status", "gate", "counter", "belt", "delay_minutes", "airline"):
        value = flight.get(field)
        if value not in (None, ""):
            old[field] = value


def git_versions_for_date(date_str):
    out = []
    try:
        commits = subprocess.check_output(
            ["git", "log", "--format=%H", "--", "data/sgn.json"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()[:120]
    except Exception:
        return out

    for sha in commits:
        try:
            raw = subprocess.check_output(
                ["git", "show", f"{sha}:data/sgn.json"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("date") == date_str and isinstance(data.get("flights"), list):
            out.append(data)
    return out


def baseline_day(date_str):
    path = os.environ.get("SGN_BASELINE_DAY")
    if not path:
        return None
    data = read_json(Path(path))
    if not data or data.get("date") != date_str or not isinstance(data.get("flights"), list):
        return None
    return data


def earliest_iso(*values):
    valid = []
    for value in values:
        if not value:
            continue
        try:
            valid.append((datetime.fromisoformat(value), value))
        except Exception:
            pass
    return min(valid, key=lambda x: x[0])[1] if valid else next((v for v in values if v), None)


def delayed(f):
    value = f.get("delay_minutes")
    try:
        if value is not None and float(value) >= 15:
            return True
    except Exception:
        pass
    status = normalize(f.get("status"))
    return "trễ" in status or "delay" in status or "late" in status


def build_summary(flights):
    return {
        "total": len(flights),
        "arrivals": sum(1 for f in flights if f.get("direction") == "arrival"),
        "departures": sum(1 for f in flights if f.get("direction") == "departure"),
        "international": sum(1 for f in flights if f.get("is_international")),
        "delayed": sum(1 for f in flights if delayed(f)),
        "terminals": sorted({f.get("terminal") for f in flights if f.get("terminal")}),
    }


def archive_old_day(day):
    if not day or not day.get("date"):
        return
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{day['date']}.json"
    path.write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def rebuild_history_index():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for p in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        data = read_json(p) or {}
        entries.append({
            "date": data.get("date") or p.stem,
            "file": f"./history/{p.name}",
            "summary": data.get("summary") or {},
        })
    HISTORY_INDEX.write_text(json.dumps({"days": entries}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    current = read_json(CURRENT)
    if not current or not isinstance(current.get("flights"), list):
        raise SystemExit("Current SGN dataset missing or invalid")

    date_str = current.get("date")
    generated_at = current.get("generated_at")
    existing = read_json(DAY)
    if existing and existing.get("date") != date_str:
        archive_old_day(existing)
        existing = None

    baseline = baseline_day(date_str)
    store = {}
    first_seen = earliest_iso(
        baseline.get("first_seen_at") if baseline else None,
        existing.get("first_seen_at") if existing else None,
        generated_at,
    )

    for dataset in (baseline, existing):
        if dataset and isinstance(dataset.get("flights"), list):
            for f in dataset["flights"]:
                merge_flight(store, f)

    for version in git_versions_for_date(date_str):
        for f in version.get("flights") or []:
            merge_flight(store, f)

    for f in current.get("flights") or []:
        merge_flight(store, f)

    flights = sorted(store.values(), key=lambda f: (
        f.get("scheduled_date") or date_str or "",
        f.get("scheduled") or "99:99",
        f.get("direction") or "",
        f.get("terminal") or "",
    ))
    summary = build_summary(flights)

    complete_day = False
    try:
        dt = datetime.fromisoformat(first_seen)
        complete_day = dt.hour == 0 and dt.minute <= 30
    except Exception:
        pass

    day = {
        "airport": current.get("airport"),
        "date": date_str,
        "first_seen_at": first_seen,
        "last_seen_at": generated_at,
        "complete_day": complete_day,
        "coverage_note": "Observed flights accumulated from live airport data. A day is marked complete only when collection started near midnight.",
        "summary": summary,
        "flights": flights,
    }
    DAY.write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    current["day_summary"] = {
        **summary,
        "complete_day": complete_day,
        "first_seen_at": first_seen,
        "last_seen_at": generated_at,
    }
    current.setdefault("summary", {})["feed_total"] = len(current.get("flights") or [])
    CURRENT.write_text(json.dumps(current, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    rebuild_history_index()
    seed_note = " + baseline" if baseline else ""
    print(f"SGN day archive {date_str}: {summary['total']} observed flights; live window {len(current.get('flights') or [])}{seed_note}")


if __name__ == "__main__":
    main()
