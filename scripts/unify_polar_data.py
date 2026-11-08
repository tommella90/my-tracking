"""Unify the Polar raw data into tables organised by time granularity.

Reads:   data/rawPolarData/*.json  (see docs/polar_data/POLAR_DATA.md)
         data/otherData/energy_tracker.ods  (subjective daily tracking)
Writes:  data/unified/
  daily.csv                     one row per calendar date
                                (energy-tracker entries + activity summary,
                                HR / PPI / skin-temp daily aggregates, plus
                                that date's night sleep+recovery)
  nightly.csv                   one row per night (evening->early-morning sleep session):
                                sleep scores, stages, interruptions, recovery, HRV blob
  continuous/hr.csv             every 24/7 HR sample
  continuous/ppi.csv            every beat-to-beat interval sample (+ validity flag)
  continuous/skin_temperature.csv   5-min skin temperature samples
  continuous/activity_samples.csv   30s MET / 60s step samples (long format)
  continuous/sleep_stages.csv   per-night sleep stage changes (hypnogram timeline)
  README.md                     summary of what was generated

Notes / conventions used:
  * Polar labels a "night" by the date on which the sleep mainly occurs
    (e.g. night 2026-08-22 = sleep from 04:06 to 09:20 on Aug 22).
    Therefore daily date D is joined with night D.
  * Skin temperature sessions start 02:00 local time and cover the whole day.
    Timestamps are computed as UTC + 2h (CEST; the whole 2026 dataset is
    within the DST period, data ends 2026-10-19).
  * Durations in the raw data are ISO 8601 strings (PT5H14M30S) -> seconds.
  * Energy-tracker columns keep their original names (e.g. 'stress_level(1-5)',
    'energy') so app.py can consume them unchanged. Cleaning follows app.py:
    'total activity' strips a trailing 's', 'physical activity' empty -> 0,
    'exertion' coerced to numeric.
"""
from __future__ import annotations

import glob
import json
import os
import re

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "data", "rawPolarData")
OUT = os.path.join(REPO, "data", "unified")
CONT = os.path.join(OUT, "continuous")

DUR_RE = re.compile(r"P(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?")


def iso_dur_s(value):
    """ISO 8601 duration (PT#H#M#S) -> seconds (float, NaN on failure)."""
    if value is None:
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    m = DUR_RE.fullmatch(str(value).strip())
    if not m:
        return np.nan
    h, mi, s = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600.0 + mi * 60.0 + s


def load_json(path):
    with open(path) as f:
        return json.load(f)


def one_file(pattern):
    """Return the single file matching `pattern` (fail loudly if ambiguous)."""
    matches = sorted(glob.glob(os.path.join(RAW, pattern)))
    if not matches:
        raise FileNotFoundError(f"No file matches {pattern} in {RAW}")
    if len(matches) > 1:
        raise ValueError(f"Multiple files match {pattern}: {matches}")
    return matches[0]


def report(title, df):
    print(f"  {title:<28} {len(df):>7} rows  ({df.index.min()} -> {df.index.max()})")


# ---------------------------------------------------------------- activity
def load_activity_daily():
    rows = []
    for f in sorted(glob.glob(os.path.join(RAW, "activity-*.json"))):
        d = load_json(f)
        s = d.get("summary", {})  # some days are samples-only (no summary)
        steps_samples = d["samples"].get("steps", [])
        row = {
            "date": d["date"],
            "step_count": s.get("stepCount",
                                sum(s_.get("value", 0) for s_ in steps_samples)
                                if steps_samples else None),
            "steps_distance_m": s.get("stepsDistance"),
            "calories": s.get("calories"),
            "sleep_quality": s.get("sleepQuality"),
            "sleep_duration_s": iso_dur_s(s.get("sleepDuration")) if s else np.nan,
            "inactivity_alerts": s.get("inactivityAlertCount"),
            "daily_met_minutes": s.get("dailyMetMinutes"),
        }
        for lvl in s.get("activityLevels", []):
            row[f"level_{str(lvl.get('level', 'X')).lower()}_s"] = iso_dur_s(lvl.get("duration"))
        rows.append(row)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def load_activity_samples():
    # Cadence: mets every 30 s, steps every 60 s. A few days have no
    # `localTime` on the samples -> fall back to index * cadence.
    cadence = {"mets": 30, "steps": 60}
    rows = []
    for f in sorted(glob.glob(os.path.join(RAW, "activity-*.json"))):
        d = load_json(f)
        day = pd.Timestamp(d["date"])
        for metric in ("mets", "steps"):
            for i, s in enumerate(d["samples"].get(metric, [])):
                if "localTime" in s:
                    offset = pd.to_timedelta(str(s["localTime"]))
                else:
                    offset = pd.to_timedelta(i * cadence[metric], unit="s")
                rows.append((day + offset, metric, s["value"]))
    return pd.DataFrame(rows, columns=["timestamp", "metric", "value"]).sort_values("timestamp")


# ---------------------------------------------------------------- energy tracker
def load_energy_tracker():
    """Subjective daily tracking (data/otherData/energy_tracker.ods).

    Column names and cleaning follow app.py so the app can consume the
    merged daily.csv unchanged.
    """
    path = os.path.join(REPO, "data", "otherData", "energy_tracker.ods")
    df = pd.read_excel(path, engine="odf", index_col=0)
    df.index.name = "date"
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["total activity"] = pd.to_numeric(
        df["total activity"].astype(str).str.replace("s", "", regex=False),
        errors="coerce")
    df["physical activity"] = pd.to_numeric(
        df["physical activity"].fillna(0), errors="coerce")
    df["exertion"] = pd.to_numeric(df["exertion"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["date"] = df["date"].dt.normalize()
    return df.set_index("date").sort_index()


# ---------------------------------------------------------------- 24/7 HR
def load_hr():
    dates, secs, hrs, srcs = [], [], [], []
    for f in sorted(glob.glob(os.path.join(RAW, "247ohr_*.json"))):
        d = load_json(f)
        for day in d["deviceDays"]:
            base = pd.Timestamp(day["date"])
            for s in day["samples"]:
                dates.append(base)
                secs.append(s["secondsFromDayStart"])
                hrs.append(s["heartRate"])
                srcs.append(s["source"])
    df = pd.DataFrame({"date": dates, "seconds": secs, "heart_rate": hrs, "source": srcs})
    df["timestamp"] = df["date"] + pd.to_timedelta(df["seconds"], unit="s")
    return df.sort_values("timestamp")


def hr_daily(hr, sleep_windows):
    """Daily HR aggregates; sleep-window stats need the night's sleep span."""
    g = hr.groupby(hr["date"])
    daily = pd.DataFrame({
        "hr_mean": g["heart_rate"].mean(),
        "hr_median": g["heart_rate"].median(),
        "hr_min": g["heart_rate"].min(),
        "hr_max": g["heart_rate"].max(),
        "hr_p10": g["heart_rate"].quantile(0.10),   # resting proxy
        "hr_p95": g["heart_rate"].quantile(0.95),
        "hr_samples": g["heart_rate"].size(),
    })
    # HR inside the actual sleep window of that date's night
    win = hr.merge(sleep_windows, left_on="date", right_index=True, how="left")
    asleep = win[win["sleep_start"].notna()
                 & (win["timestamp"] >= win["sleep_start"])
                 & (win["timestamp"] <= win["sleep_end"])]
    if len(asleep):
        ga = asleep.groupby(asleep["date"])["heart_rate"]
        daily["hr_asleep_median"] = ga.median()
        daily["hr_asleep_min"] = ga.min()
    return daily


# ---------------------------------------------------------------- PPI
def load_ppi():
    stamps, rr = [], []
    for f in sorted(glob.glob(os.path.join(RAW, "ppi_samples_*.json"))):
        d = load_json(f)
        for day_rec in d:
            for dev in day_rec["devicePpiSamplesList"]:
                for s in dev["ppiSamples"]:
                    stamps.append(s["sampleDateTime"])
                    rr.append(s["pulseLength"])
    df = pd.DataFrame({"timestamp": pd.to_datetime(stamps, format="ISO8601"),
                       "pulse_length_ms": rr})
    return df.sort_values("timestamp")


def ppi_validity(df):
    """Flag physiologically implausible beats and beat-to-beat artifacts."""
    rr = df["pulse_length_ms"].to_numpy(dtype=float)
    ok_range = (rr >= 300) & (rr <= 2000)
    artifact = np.zeros(len(rr), dtype=bool)
    # artifact: consecutive interval jump > 35% of the mean of the two beats
    for i in range(1, len(rr)):
        if ok_range[i - 1] and ok_range[i]:
            if abs(rr[i] - rr[i - 1]) > 0.35 * (rr[i] + rr[i - 1]) / 2:
                artifact[i] = True
    df["valid"] = ok_range & ~artifact
    return df


def ppi_daily(ppi):
    """Daily HRV aggregates (RMSSD etc.) computed from valid beats."""
    df = ppi[ppi["valid"]].copy()
    df["date"] = df["timestamp"].dt.normalize()
    out = {}
    for day, g in df.groupby("date"):
        rr = g["pulse_length_ms"].to_numpy(dtype=float)
        diffs = np.diff(rr)
        out[day] = {
            "ppi_beats": len(rr),
            "ppi_mean_rr_ms": rr.mean(),
            "ppi_mean_hr_bpm": 60000.0 / rr.mean(),
            "ppi_rmssd_ms": np.sqrt(np.mean(diffs ** 2)) if len(diffs) else np.nan,
            "ppi_sdnn_ms": rr.std(ddof=0),
        }
    return pd.DataFrame.from_dict(out, orient="index").sort_index()


# ---------------------------------------------------------------- skin temperature
def load_skin_temp():
    rows = []
    for f in sorted(glob.glob(os.path.join(RAW, "generic-period-*.json"))):
        d = load_json(f)
        data = d["data"]
        if data.get("measurementType") != "TM_SKIN_TEMPERATURE":
            continue  # skip skin-contact (wear detection) files
        start_utc = int(d["meta"]["id"]["startTimeSeconds"])
        samples = data["temperatureMeasurementSamples"]
        # Sessions start 02:00 local; the whole 2026 dataset is CEST (UTC+2)
        start_local = pd.Timestamp(start_utc, unit="s") + pd.Timedelta(hours=2)
        temps = [s["temperatureCelsius"] for s in samples]
        stamps = start_local + pd.to_timedelta(np.arange(len(temps)) * 5, unit="min")
        for t, v in zip(stamps, temps):
            rows.append((t, v))
    df = pd.DataFrame(rows, columns=["timestamp", "temperature_celsius"])
    return df.sort_values("timestamp")


# ---------------------------------------------------------------- nightly
def load_nightly():
    # ---- sleep_wake (binary state changes, widest night coverage)
    rows = []
    for rec in load_json(one_file("sleep_wake_*.json")):
        night = rec["night"]
        night_date = pd.Timestamp(night)
        changes = (rec["sleepWake"][0]["sleepStateChanges"]
                   .get("sleepWakeStateChangeModels", []))
        sleep_states = [c for c in changes if c.get("state") == "SLEEP"]
        rows.append({
            "night": night,
            "sleep_onset": night_date + pd.to_timedelta(
                min((c["millisInDay"] for c in sleep_states), default=np.nan), unit="ms"),
            "last_state_change": night_date + pd.to_timedelta(
                max((c["millisInDay"] for c in changes), default=np.nan), unit="ms"),
            "wake_changes": sum(c.get("state") == "WAKE" for c in changes),
        })
    nightly = pd.DataFrame(rows).set_index("night") if rows else pd.DataFrame()

    # ---- sleep_score
    rows = []
    for rec in load_json(one_file("sleep_score_*.json")):
        r = {"night": rec["night"]}
        r.update(rec["sleepScoreResult"])
        rows.append(r)
    scores = pd.DataFrame(rows).set_index("night") if rows else pd.DataFrame()

    # ---- sleep_result (evaluation + hypnogram)
    rows, stage_rows = [], []
    for rec in load_json(one_file("sleep_result_*.json")):
        night, ev = rec["night"], rec["evaluation"]
        ana = ev.get("analysis", {})
        itg = ev.get("interruptions", {})
        ph = ev.get("phaseDurations", {})
        hypo = rec.get("sleepResult", {}).get("hypnogram", {})
        sleep_start = pd.to_datetime(hypo.get("sleepStart"))
        sleep_end = pd.to_datetime(hypo.get("sleepEnd"))
        if getattr(sleep_start, "tz", None) is not None:
            sleep_start = sleep_start.tz_localize(None)
        if getattr(sleep_end, "tz", None) is not None:
            sleep_end = sleep_end.tz_localize(None)
        rows.append({
            "night": night,
            "sleep_type": ev.get("sleepType"),
            "sleep_span_s": iso_dur_s(ev.get("sleepSpan")),
            "asleep_s": iso_dur_s(ev.get("asleepDuration")),
            "rem_s": iso_dur_s(ph.get("rem")),
            "light_s": iso_dur_s(ph.get("light")),
            "deep_s": iso_dur_s(ph.get("deep")),
            "wake_in_sleep_s": iso_dur_s(ph.get("wake")),
            "rem_pct": ph.get("remPercentage"),
            "deep_pct": ph.get("deepPercentage"),
            "efficiency_pct": ana.get("efficiencyPercent"),
            "continuity_index": ana.get("continuityIndex"),
            "continuity_class": ana.get("continuityClass"),
            "interruptions_count": itg.get("totalCount"),
            "interruptions_long": itg.get("longCount"),
            "interruptions_total_s": iso_dur_s(itg.get("totalDuration")),
            "sleep_start": sleep_start,
            "sleep_end": sleep_end,
            "sleep_goal_s": iso_dur_s(hypo.get("sleepGoal")),
        })
        for c in hypo.get("sleepStateChanges", []):
            stage_rows.append({
                "night": night,
                "offset_from_start_s": iso_dur_s(c.get("offsetFromStart")),
                "stage": c.get("state"),
            })
    results = pd.DataFrame(rows).set_index("night") if rows else pd.DataFrame()
    stages = pd.DataFrame(stage_rows)

    # ---- nightly_recovery (values are strings -> numeric)
    rows = []
    for rec in load_json(one_file("nightly_recovery_[0-9]*.json")):
        rows.append({
            "night": rec["night"],
            "recovery_rri_ms": pd.to_numeric(rec.get("meanNightlyRecoveryRri"), errors="coerce"),
            "recovery_rmssd_ms": pd.to_numeric(rec.get("meanNightlyRecoveryRmssd"), errors="coerce"),
            "recovery_resp_interval_ms": pd.to_numeric(
                rec.get("meanNightlyRecoveryRespirationInterval"), errors="coerce"),
        })
    recovery = pd.DataFrame(rows).set_index("night") if rows else pd.DataFrame()

    # ---- nightly_recovery_blob (no night key: align by index with sleep_result)
    blob = load_json(one_file("nightly_recovery_blob_*.json"))
    rows = []
    if results.empty:
        print("  WARNING: no sleep_result nights, blob stats cannot be aligned")
    elif len(blob) != len(results):
        print(f"  WARNING: blob nights ({len(blob)}) != sleep_result nights "
              f"({len(results)}); skipping blob stats")
    else:
        for rec, night in zip(blob, results.index):
            hrv = rec.get("hrvData") or [{}]
            br = rec.get("breathingRateData") or [{}]
            hrv_samples = np.asarray(hrv[0].get("samples", []), dtype=float)
            br_samples = np.asarray(br[0].get("samples", []), dtype=float)
            rows.append({
                "night": night,
                "hrv_blob_mean_rmssd_ms": np.nanmean(hrv_samples) if hrv_samples.size else np.nan,
                "hrv_blob_samples": hrv_samples.size,
                "breathing_rate_mean_bpm": np.nanmean(br_samples) if br_samples.size else np.nan,
                "breathing_rate_samples": br_samples.size,
            })
    blob_df = pd.DataFrame(rows).set_index("night") if rows else pd.DataFrame()

    dfs = [df for df in (nightly, scores, results, recovery, blob_df) if not df.empty]
    nightly_all = pd.concat(dfs, axis=1)
    return nightly_all.sort_index(), stages


# ---------------------------------------------------------------- main
def main():
    os.makedirs(CONT, exist_ok=True)
    print("Loading raw Polar data from", RAW)

    print(" activity ...")
    activity = load_activity_daily()
    activity_samples = load_activity_samples()

    print(" 24/7 heart rate ...")
    hr = load_hr()

    print(" PPI samples ...")
    ppi = ppi_validity(load_ppi())

    print(" skin temperature ...")
    skin_temp = load_skin_temp()

    print(" energy tracker ...")
    energy = load_energy_tracker()

    print(" sleep / recovery ...")
    nightly, sleep_stages = load_nightly()
    nightly.index = pd.to_datetime(nightly.index)  # night (str) -> date

    # sleep windows keyed by calendar date (night D == sleep in the early
    # hours of date D, per observed Polar convention)
    windows = pd.DataFrame({
        "sleep_start": nightly["sleep_start"],
        "sleep_end": nightly["sleep_end"],
    })
    windows.index = pd.to_datetime(windows.index)  # night -> date

    print("\nAggregating to daily ...")
    daily = activity.copy()
    daily = daily.join(hr_daily(hr, windows))
    daily = daily.join(ppi_daily(ppi))
    temp_by_day = skin_temp.groupby(skin_temp["timestamp"].dt.normalize())["temperature_celsius"]
    daily = daily.join(pd.DataFrame({
        "skin_temp_mean_c": temp_by_day.mean(),
        "skin_temp_min_c": temp_by_day.min(),
        "skin_temp_max_c": temp_by_day.max(),
        "skin_temp_samples": temp_by_day.size(),
    }))
    # join the night's sleep+recovery onto its calendar date
    daily = daily.join(nightly.drop(columns=["sleep_start", "sleep_end", "sleep_type"]))

    # merge in the subjective energy-tracker entries (outer join: keeps the
    # full tracking history, Polar metrics stay NaN outside device coverage)
    energy = energy[~energy.index.duplicated(keep="first")]
    daily = daily.join(energy, how="outer")

    print("\nWriting outputs to", OUT)
    daily.to_csv(os.path.join(OUT, "daily.csv"))
    nightly.to_csv(os.path.join(OUT, "nightly.csv"))
    hr[["timestamp", "heart_rate", "source"]].to_csv(os.path.join(CONT, "hr.csv"), index=False)
    ppi[["timestamp", "pulse_length_ms", "valid"]].to_csv(
        os.path.join(CONT, "ppi.csv"), index=False)
    skin_temp.to_csv(os.path.join(CONT, "skin_temperature.csv"), index=False)
    activity_samples.to_csv(os.path.join(CONT, "activity_samples.csv"), index=False)
    sleep_stages.to_csv(os.path.join(CONT, "sleep_stages.csv"), index=False)

    print("\nSummary")
    report("daily", daily)
    report("nightly", nightly)
    report("continuous/hr", hr.set_index("timestamp"))
    report("continuous/ppi", ppi.set_index("timestamp"))
    report("continuous/skin_temperature", skin_temp.set_index("timestamp"))
    report("continuous/activity_samples", activity_samples.set_index("timestamp"))
    report("continuous/sleep_stages", sleep_stages.set_index("night"))
    print(f"  valid PPI beats: {int(ppi['valid'].sum())} / {len(ppi)}")

    readme = f"""# Unified Polar Data

Generated by `scripts/unify_polar_data.py` from `data/rawPolarData/`.

| File | Granularity | Rows |
|---|---|---|
| `daily.csv` | calendar date | {len(daily)} |
| `nightly.csv` | night (sleep session) | {len(nightly)} |
| `continuous/hr.csv` | ~5 s | {len(hr)} |
| `continuous/ppi.csv` | beat-to-beat | {len(ppi)} |
| `continuous/skin_temperature.csv` | 5 min | {len(skin_temp)} |
| `continuous/activity_samples.csv` | 30 s (mets) / 60 s (steps) | {len(activity_samples)} |
| `continuous/sleep_stages.csv` | per stage change | {len(sleep_stages)} |

`daily.csv` contains both the Polar device metrics and the subjective
energy-tracker columns (original names, e.g. 'energy', 'fatigue',
'stress_level(1-5)') merged on date. Polar metrics are NaN on dates outside
device coverage (2026-08-20 -> 2026-10-19 plus 2023-01-01); energy-tracker
columns are NaN outside the tracking history.

Conventions:
- A Polar "night" is labelled with the date on which the sleep mainly occurs
  (night 2026-08-22 = sleep 04:06-09:20 on Aug 22). `daily.csv` row for date D
  therefore contains the sleep/recovery of night D (the sleep that ended that
  morning).
- Skin temperature timestamps are UTC + 2 h (CEST; the whole dataset is within
  the DST period).
- `ppi.csv` `valid=False` marks beats outside 300-2000 ms or with a >35 %
  beat-to-beat jump (artifact).
- Durations converted from ISO 8601 to seconds (`*_s` columns).
- Energy-tracker cleaning follows app.py: 'total activity' strips a trailing
  's', 'physical activity' empty -> 0, 'exertion' coerced to numeric.
"""
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(readme)
    print("\nDone.")


if __name__ == "__main__":
    main()
