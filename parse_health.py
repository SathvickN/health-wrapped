"""Parse Apple Health export.xml -> clean DataFrame of running workouts.

Handles two Apple export layouts:
  1. Older: distance/calories live on <Workout> attributes
     (totalDistance / totalEnergyBurned).
  2. Newer: <Workout> has no distance/energy attrs; the numbers live in
     child <WorkoutStatistics> elements (DistanceWalkingRunning sum,
     ActiveEnergyBurned sum).
Both are supported transparently.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
from tqdm import tqdm

RUNNING_TYPES = {
    "HKWorkoutActivityTypeRunning",
    "HKWorkoutActivityTypeTrailRunning",
}

# Candidate names for the export xml inside the zip.
_XML_CANDIDATES = (
    "apple_health_export/export.xml",
    "apple_health_export/Export.xml",
)

KM_TO_MI = 0.621371
M_TO_FT = 3.28084

# Same physical workout is often logged by several apps/devices with
# near-identical start times. Cluster starts within this many minutes and
# collapse to one. The representative is the most complete record; source name
# is only a tiebreak — so any device (Garmin, Whoop, ...) works, not a fixed list.
DEDUP_WINDOW_MIN = 15


# Wearables (wrist GPS + HR) generally hold the most complete record, so they
# win ties. This is only a *tiebreak* — the representative is chosen by data
# completeness first (see _dedup_*), so unknown sources still work fine.
# Add your device's name here if you want it to win close calls.
_WEARABLE_HINTS = ("watch", "garmin", "whoop", "fitbit", "coros", "polar",
                   "oura", "suunto", "wahoo", "amazfit", "pixel watch")
_APP_HINTS = ("strava", "runna", "nike", "adidas", "mapmyrun", "runkeeper",
              "komoot")


def _source_rank(name: str) -> int:
    """Tiebreak priority: wearable (0) > known app (1) > unknown (2)."""
    n = (name or "").lower()
    if any(h in n for h in _WEARABLE_HINTS):
        return 0
    if any(h in n for h in _APP_HINTS):
        return 1
    return 2


def _find_xml_name(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    for cand in _XML_CANDIDATES:
        if cand in names:
            return cand
    # Fallback: first export*.xml that is not the CDA file.
    for n in names:
        low = n.lower()
        if low.endswith(".xml") and "export" in low and "cda" not in low:
            return n
    raise KeyError(
        "Could not find export.xml in zip. Contents: "
        + ", ".join(names[:10])
    )


def _parse_date(date_str: str):
    """Apple dates look like '2026-05-30 07:14:22 -0700'. TZ suffix varies."""
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _to_miles(value: float, unit: str) -> float:
    if value is None:
        return None
    if unit and unit.lower() == "km":
        return value * KM_TO_MI
    return value  # assume miles


def _stat_float(attrib: dict, *keys):
    """Return first parseable float among given attribute keys."""
    for k in keys:
        v = attrib.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def _process_workout(w: dict):
    """Turn raw workout dict into a clean row dict, or None if unusable."""
    date = _parse_date(w.get("startDate", ""))
    if date is None:
        return None

    # --- Distance ---
    distance = _stat_float(w, "totalDistance")
    dist_unit = w.get("totalDistanceUnit", "mi")
    # --- Calories ---
    calories = _stat_float(w, "totalEnergyBurned")
    # --- HR / elevation from child statistics ---
    avg_hr = max_hr = elevation = None

    for s in w["_stats"]:
        stype = s.get("type", "")
        unit = s.get("unit", "")
        if "DistanceWalkingRunning" in stype and distance is None:
            distance = _to_miles(_stat_float(s, "sum"), unit)
            dist_unit = "mi"
        elif "ActiveEnergyBurned" in stype and calories is None:
            calories = _stat_float(s, "sum")
        elif "HeartRate" in stype:
            avg_hr = _stat_float(s, "average")
            max_hr = _stat_float(s, "maximum")
        elif "FlightsClimbed" in stype or "ElevationAscended" in stype:
            ev = _stat_float(s, "sum", "average")
            if ev is not None:
                # ElevationAscended is usually meters; flights -> ~10ft each.
                if "Elevation" in stype and unit in ("m", "meter", "meters"):
                    elevation = ev * M_TO_FT
                elif "Flights" in stype:
                    elevation = ev * 10.0
                else:
                    elevation = ev

    distance = _to_miles(distance, dist_unit)
    duration = _stat_float(w, "duration")

    # Drop corrupted / zero records.
    if not distance or distance < 0.1:
        return None
    if not duration or duration <= 0:
        return None

    pace = duration / distance
    # Drop GPS-error outliers.
    if pace < 4.0 or pace > 20.0:
        return None

    return {
        "date": date,
        "distance_mi": distance,
        "duration_min": duration,
        "pace_min_per_mi": pace,
        "calories": calories,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "elevation_ft": elevation,
        "source": w.get("sourceName", ""),
    }


def _dedup_workouts(df: pd.DataFrame,
                    window_min: int = DEDUP_WINDOW_MIN) -> pd.DataFrame:
    """Collapse multi-app duplicates of the same run into one row.

    Runs whose start times fall within `window_min` of the cluster's first
    start are treated as the same physical run. Representative distance,
    duration and pace come from the highest-priority source present; HR,
    calories and elevation are taken from the representative when available,
    else from the first source in the cluster that has them.
    """
    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)

    # Assign cluster ids by start-time gap.
    cluster_ids = []
    cid = -1
    anchor = None
    for d in df["date"]:
        if anchor is None or (d - anchor).total_seconds() / 60.0 > window_min:
            cid += 1
            anchor = d
        cluster_ids.append(cid)
    df = df.assign(_cluster=cluster_ids)
    df["_rank"] = df["source"].map(_source_rank)
    # Prefer the most complete record (most of distance/HR/calories present);
    # source name only breaks ties. Works for any device, not a fixed list.
    df["_complete"] = df[["distance_mi", "avg_hr", "calories"]].notna().sum(axis=1)

    merged = []
    for _, g in df.groupby("_cluster"):
        g = g.sort_values(["_complete", "_rank", "duration_min"],
                          ascending=[False, True, False])
        rep = g.iloc[0]  # most complete record (source name breaks ties)

        def pick(col):
            """Representative value, else first non-null in the cluster."""
            if pd.notna(rep[col]):
                return rep[col]
            vals = g[col].dropna()
            return vals.iloc[0] if len(vals) else None

        distance = float(rep["distance_mi"])
        duration = float(rep["duration_min"])
        merged.append({
            "date": rep["date"],
            "distance_mi": distance,
            "duration_min": duration,
            "pace_min_per_mi": duration / distance if distance else None,
            "calories": pick("calories"),
            "avg_hr": pick("avg_hr"),
            "max_hr": pick("max_hr"),
            "elevation_ft": pick("elevation_ft"),
            "source": rep["source"],
            "n_sources": int(g["source"].nunique()),
        })

    return pd.DataFrame(merged).sort_values("date").reset_index(drop=True)


def _clean_activity_name(raw: str) -> str:
    """'HKWorkoutActivityTypeTraditionalStrengthTraining' -> 'Strength Training'."""
    t = (raw or "").replace("HKWorkoutActivityType", "")
    t = re.sub(r"(?<!^)(?=[A-Z])", " ", t).strip()
    # A few friendlier names.
    t = t.replace("Traditional Strength Training", "Strength")
    t = t.replace("Functional Strength Training", "Functional Strength")
    t = t.replace("High Intensity Interval Training", "HIIT")
    t = t.replace("Distance Walking Running", "Walk/Run")
    return t or "Other"


def _process_activity(w: dict):
    """Generic processor for ANY workout type (not just running)."""
    date = _parse_date(w.get("startDate", ""))
    if date is None:
        return None
    duration = _stat_float(w, "duration")
    if not duration or duration <= 0:
        return None

    distance = _stat_float(w, "totalDistance")
    dist_unit = w.get("totalDistanceUnit", "mi")
    calories = _stat_float(w, "totalEnergyBurned")
    avg_hr = max_hr = None
    for s in w["_stats"]:
        stype = s.get("type", "")
        unit = s.get("unit", "")
        if "Distance" in stype and distance is None:
            distance = _stat_float(s, "sum")
            dist_unit = unit or "mi"
        elif "ActiveEnergyBurned" in stype and calories is None:
            calories = _stat_float(s, "sum")
        elif "HeartRate" in stype:
            avg_hr = _stat_float(s, "average")
            max_hr = _stat_float(s, "maximum")

    if distance is not None:
        distance = _to_miles(distance, dist_unit)

    return {
        "date": date,
        "activity": _clean_activity_name(w.get("workoutActivityType", "")),
        "duration_min": duration,
        "distance_mi": distance,
        "calories": calories,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "source": w.get("sourceName", ""),
    }


def _dedup_activities(df: pd.DataFrame,
                      window_min: int = DEDUP_WINDOW_MIN) -> pd.DataFrame:
    """Like _dedup_workouts but clusters within the SAME activity type."""
    if df.empty:
        return df
    df = df.sort_values(["activity", "date"]).reset_index(drop=True)
    df["_rank"] = df["source"].map(_source_rank)
    df["_complete"] = df[["distance_mi", "avg_hr", "calories"]].notna().sum(axis=1)

    cluster_ids = []
    cid = -1
    anchor = None
    prev_act = None
    for act, d in zip(df["activity"], df["date"]):
        if (act != prev_act or anchor is None
                or (d - anchor).total_seconds() / 60.0 > window_min):
            cid += 1
            anchor = d
            prev_act = act
        cluster_ids.append(cid)
    df = df.assign(_cluster=cluster_ids)

    merged = []
    for _, g in df.groupby("_cluster"):
        g = g.sort_values(["_complete", "_rank", "duration_min"],
                          ascending=[False, True, False])
        rep = g.iloc[0]  # most complete record (source name breaks ties)

        def pick(col):
            if pd.notna(rep[col]):
                return rep[col]
            vals = g[col].dropna()
            return vals.iloc[0] if len(vals) else None

        merged.append({
            "date": rep["date"],
            "activity": rep["activity"],
            "duration_min": float(rep["duration_min"]),
            "distance_mi": pick("distance_mi"),
            "calories": pick("calories"),
            "avg_hr": pick("avg_hr"),
            "max_hr": pick("max_hr"),
            "source": rep["source"],
        })
    return pd.DataFrame(merged).sort_values("date").reset_index(drop=True)


def parse_activities(zip_path: str, year: int = None) -> pd.DataFrame:
    """Parse ALL workout types (runs, walks, cycling, strength, ...).

    Columns: date, activity, duration_min, distance_mi, calories, avg_hr,
    max_hr, source.
    """
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        xml_name = _find_xml_name(zf)
        with zf.open(xml_name) as f:
            current = None
            pbar = tqdm(desc="Scanning activities", unit=" elem", unit_scale=True)
            for event, elem in ET.iterparse(f, events=("start", "end")):
                tag = elem.tag
                if event == "start":
                    if tag == "Workout":
                        current = dict(elem.attrib)
                        current["_stats"] = []
                    elif tag == "WorkoutStatistics" and current is not None:
                        current["_stats"].append(dict(elem.attrib))
                else:
                    if tag == "Workout":
                        if current is not None:
                            row = _process_activity(current)
                            if row is not None:
                                rows.append(row)
                            current = None
                        pbar.update(1)
                        elem.clear()
                    elif tag == "Record":
                        elem.clear()
            pbar.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    df = _dedup_activities(df)
    if year is not None:
        df = df[df["date"].dt.year == year].reset_index(drop=True)
    return df


def parse_workouts(zip_path: str, year: int = None) -> pd.DataFrame:
    """Open zip, iteratively parse export.xml, return running-workout DataFrame.

    Columns: date, distance_mi, duration_min, pace_min_per_mi, calories,
    avg_hr, max_hr, elevation_ft, source.
    """
    workouts = []

    with zipfile.ZipFile(zip_path) as zf:
        xml_name = _find_xml_name(zf)
        with zf.open(xml_name) as f:
            current = None
            pbar = tqdm(desc="Scanning workouts", unit=" elem", unit_scale=True)
            for event, elem in ET.iterparse(f, events=("start", "end")):
                tag = elem.tag
                if event == "start":
                    if tag == "Workout":
                        if elem.attrib.get("workoutActivityType") in RUNNING_TYPES:
                            current = dict(elem.attrib)
                            current["_stats"] = []
                        else:
                            current = None
                    elif tag == "WorkoutStatistics" and current is not None:
                        current["_stats"].append(dict(elem.attrib))
                else:  # end
                    if tag == "Workout":
                        if current is not None:
                            row = _process_workout(current)
                            if row is not None:
                                workouts.append(row)
                            current = None
                        pbar.update(1)
                        elem.clear()  # CRITICAL: free memory
                    elif tag == "Record":
                        elem.clear()  # millions of these; never retained
            pbar.close()

    df = pd.DataFrame(workouts)
    if df.empty:
        return df

    df = df.sort_values("date").reset_index(drop=True)
    df = _dedup_workouts(df)
    if year is not None:
        df = df[df["date"].dt.year == year].reset_index(drop=True)
    return df
