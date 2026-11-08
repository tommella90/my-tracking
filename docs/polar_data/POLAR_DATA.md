# Polar Raw Data — Unified File Type Reference

Folder: `data/rawPolarData/` — 191 JSON files exported from Polar (device: Polar Street X, user ID `64764843`).

**Naming convention:** `<type>_<period-or-id>-<uuid>.json`, e.g. `activity-2026-10-01-47f26c2e-....json`

**Coverage:** most continuous data runs 2026-08-20 → 2026-10-19, plus an isolated month in 2023-01.

## Overview

| Type | Count | Content | Coverage |
|---|---|---|---|
| `activity` | 62 | Daily activity (steps, calories, METs) | 2023-01-01, 2026-08-20 → 2026-10-19 |
| `247ohr` | 4 | Continuous 24/7 heart rate (monthly) | 2023-01, 2026-08 → 2026-10 |
| `ppi_samples` | 10 | Pulse-to-pulse interval / HRV samples (month parts) | 2023-01, 2026-08 → 2026-10 |
| `generic-period` | 104 | Skin temperature + skin contact changes | nightly sessions, 2026-08 → 2026-10 |
| `sleep_wake` | 1 | Sleep/wake state changes per night | 2026-08-20 → 2026-10-19 (61 nights) |
| `sleep_score` | 1 | Nightly sleep scores | 2026-08-22 → 2026-10-19 (54 nights) |
| `sleep_result` | 1 | Nightly sleep evaluation + hypnogram | 2026-08-22 → 2026-10-19 (54 nights) |
| `nightly_recovery` | 1 | Nightly recovery summary | 2026-08-22 → 2026-10-19 (54 nights) |
| `nightly_recovery_blob` | 1 | Nightly HRV + breathing rate raw samples | 2026-08-22 → 2026-10-19 |
| Account & reference | 6 | Account, profile, device, sport profiles, calendar | one-off |

---

## 1. `activity-YYYY-MM-DD-<uuid>.json`

Daily activity data. One file per calendar day.

- **Coverage:** 2023-01-01 and 2026-08-20 → 2026-10-19

### Top-level structure

```json
{
  "exportVersion": "2.7",
  "date": "2026-10-01",
  "summary": { ... },
  "samples": { "mets": [...], "steps": [...], "metSources": [...] },
  "physicalInformation": { ... }
}
```

### `summary` fields

| Field | Type | Description |
|---|---|---|
| `startTime` / `endTime` | string | Day bounds (`00:00:00.000` → `23:59:59.000`) |
| `stepCount` | int | Total steps for the day |
| `stepsDistance` | float | Distance in meters |
| `calories` | int | Active + basal calories for the day |
| `sleepQuality` | float | 0–1 |
| `sleepDuration` | ISO 8601 duration | e.g. `PT21540S` (~6h) |
| `inactivityAlertCount` | int | Number of inactivity alerts |
| `dailyMetMinutes` | float | Total MET minutes |
| `activityLevels` | list | Duration per level: `NO_DATA`, `SLEEP`, `SEDENTARY`, `LIGHT`, `MODERATE`, `VIGOROUS`, ... each `{ "level": ..., "duration": "PT28680S" }` |

### `samples`

- `mets`: ~2880 entries (one per 30 s) — `{ "localTime": "00:00:00.000", "value": 1.375 }` (MET value; 1.0 = resting)
- `steps`: ~1441 entries (one per 60 s) — same shape as `mets`
- `metSources`: device IDs that produced MET data

### `physicalInformation`

User snapshot for that day: `sex`, `birthday`, `height, cm`, `weight, kg`, `sleepGoal`.

---

## 2. `247ohr_YYYY_MM-<uuid>.json`

Continuous 24/7 heart rate. One file per month.

- **Coverage:** 2023-01, 2026-08, 2026-09, 2026-10
- **Cadence:** roughly one sample every ~5 s per day (~3600 samples/day); gaps where the device was not worn

### Structure

```json
{
  "deviceDays": [
    {
      "userId": 64764843,
      "deviceId": "1A581F3F",
      "date": "2026-10-01",
      "samples": [
        { "heartRate": 70, "secondsFromDayStart": 145, "source": "TIMED_24_7" }
      ]
    }
  ]
}
```

### Sample fields

| Field | Type | Description |
|---|---|---|
| `heartRate` | int | Beats per minute |
| `secondsFromDayStart` | int | Seconds since local midnight |
| `source` | string | `TIMED_24_7` (periodic) or `HIGH_24_7` (high-resolution, e.g. during activity) |

**Notes:** timestamp = `date` + `secondsFromDayStart`. `HIGH_24_7` samples are denser, usually during workouts. Useful for daily aggregates: resting HR (e.g. median of nighttime samples), min/max HR, time in HR zones.

---

## 3. `ppi_samples_YYYY_M_N-<uuid>.json`

Pulse-to-pulse interval (PPI) samples — the raw beat-to-beat data behind HRV. One file per month-part (each month split into up to 4 parts). Largest files in the export (up to ~24 MB).

- **Coverage:** 2023-01 (part 1), 2026-08 (parts 3–4), 2026-09 (parts 1–4), 2026-10 (parts 1–3)

### Structure

Top level: list of days.

```json
[
  {
    "date": "2026-10-17",
    "devicePpiSamplesList": [
      {
        "deviceId": "1A581F3F",
        "ppiSamples": [
          { "sampleDateTime": "2026-10-17T00:00:04.165", "pulseLength": 738 }
        ]
      }
    ]
  }
]
```

### Sample fields

| Field | Type | Description |
|---|---|---|
| `sampleDateTime` | ISO datetime | Timestamp of the beat |
| `pulseLength` | int | Interval between successive beats, in milliseconds |

**Notes:** `pulseLength` ≈ R-R interval (60 000 / pulseLength = instantaneous BPM). PPI is only recorded when the device detects skin contact, so coverage is intermittent (nights + wear time). Basis for Polar's HRV / stress features; RMSSD, SDNN, etc. can be computed from windows of consecutive samples. Filter out physiologically impossible intervals (e.g. < 300 ms or > 2000 ms) before computing HRV metrics.

---

## 4. `generic-period-<hex-id>-<uuid>.json`

Generic periodic measurement container holding two sub-types (104 files):

1. **Skin temperature** (`TM_SKIN_TEMPERATURE`) — nightly measurement sessions
2. **Skin contact changes** — wear detection events

### Common structure

```json
{
  "meta": {
    "id": { ... },
    "type": 7,
    "version": 5,
    "ownerId": 64764843,
    "created": "2026-10-19T00:00:00Z",
    "modified": "2026-10-19T11:25:00.461Z",
    "endTime": "2026-10-19T13:25:00Z"
  },
  "data": { ... }
}
```

`meta.endTime` is the session end; the hex id in the filename is the device's internal period UUID — it does not encode dates, use the `meta` timestamps.

### Sub-type 1: skin temperature

`data.measurementType == "TM_SKIN_TEMPERATURE"` (about half the files).

```json
{
  "measurementType": "TM_SKIN_TEMPERATURE",
  "sourceDeviceId": "1A581F3F",
  "sensorLocation": "SL_DISTAL",
  "temperatureMeasurementSamples": [
    { "temperatureCelsius": 32.523438 }
  ]
}
```

~162 samples per session (one per ~5 min over the night). `sensorLocation`: `SL_DISTAL` (wrist).

### Sub-type 2: skin contact changes

`data` has `skinContactChanges` and no `measurementType`.

```json
{
  "sourceDeviceId": "1A581F3F",
  "skinContactChanges": [
    { "recordingTimeDeltaMilliseconds": "29538578" },
    { "recordingTimeDeltaMilliseconds": "29602578", "skinContact": true }
  ]
}
```

`recordingTimeDeltaMilliseconds` is milliseconds from day start; presence of `skinContact: true` marks when contact was regained, absence marks contact lost. Files appear in pairs (temperature session + contact changes for the same night).

---

## 5. `sleep_wake_<userId>-<uuid>.json`

Sleep/wake state changes for each night. Single file containing all nights.

- **Coverage:** 2026-08-20 → 2026-10-19 (61 nights)

### Structure

Top level: list of nights.

```json
[
  {
    "night": "2026-08-20",
    "sleepWake": [
      {
        "deviceId": "1A581F3F",
        "sleepStateChanges": {
          "sleepWakeStateChangeModels": [
            { "millisInDay": 39435001, "state": "WAKE" }
          ]
        }
      }
    ]
  }
]
```

### Sample fields

| Field | Type | Description |
|---|---|---|
| `millisInDay` | int | Milliseconds from midnight (local) when the state change occurred |
| `state` | string | `WAKE` or `SLEEP` |

**Notes:** `night` is the evening date; the sleep itself may extend into the next calendar day. This is the coarsest sleep data (binary sleep/wake); `sleep_result` provides full stages. Useful for: sleep onset time, wake time, number and duration of night awakenings.

---

## 6. `sleep_score_<userId>-<uuid>.json`

Nightly sleep quality scores. Single file containing all nights.

- **Coverage:** 2026-08-22 → 2026-10-19 (54 nights)

### Structure

```json
[
  {
    "night": "2026-08-22",
    "sleepScoreResult": { ... }
  }
]
```

### `sleepScoreResult` fields

| Field | Description |
|---|---|
| `sleepScore` | Overall sleep score (e.g. 51.07) |
| `sleepTimeOwnTargetScore` | Score for sleep duration vs. your own target |
| `sleepTimeRecommendationScore` | Score for duration vs. recommended amount |
| `continuityScore` | How uninterrupted the sleep was |
| `efficiencyScore` | Time asleep vs. time in bed |
| `remScore` | REM sleep amount vs. optimal |
| `n3Score` | Deep (N3) sleep amount vs. optimal |
| `longInterruptionsScore` | Penalty for long awakenings |
| `groupDurationScore` / `groupSolidityScore` / `groupRefreshScore` | Grouped sub-scores (duration, solidity, refreshment) |

**Notes:** all sub-scores appear to be on a 0–100-ish scale; `sleepScore` is the composite. Easiest sleep dataset to join with your energy tracker on date.

---

## 7. `sleep_result_<userId>-<uuid>.json`

Detailed nightly sleep evaluation: durations, stage analysis, interruptions, hypnogram and sleep cycles. Single file containing all nights.

- **Coverage:** 2026-08-22 → 2026-10-19 (54 nights)

### Structure

```json
[
  {
    "night": "2026-08-22",
    "evaluation": { ... },
    "sleepResult": { "hypnogram": { ... }, "sleepCycles": { ... } }
  }
]
```

### `evaluation` fields

| Field | Description |
|---|---|
| `sleepType` | e.g. `SLEEP_PLUS_STAGES` (sleep with stages tracking) |
| `sleepSpan` | ISO 8601 — time from lying down to getting up (e.g. `PT5H14M30S`) |
| `asleepDuration` | ISO 8601 — actual time asleep (e.g. `PT4H46M30S`) |
| `age` | Age used for reference values |
| `analysis` | `efficiencyPercent`, `continuityIndex`, `continuityClass`, `feedback`, ... |
| `interruptions` | `totalDuration`, `totalCount`, `shortDuration`, `shortCount`, `longDuration`, `longCount` |
| `phaseDurations` | `wake`, `rem`, `light`, `deep`, `unknown`, ... — all ISO 8601 durations |

### `sleepResult.hypnogram`

- `sleepStart` / `sleepEnd`: ISO datetimes with timezone (e.g. `2026-08-22T04:06:15.504+02:00`)
- `alarmSnoozeTimes`: list
- sleep state changes: timeline of sleep stages through the night

### `sleepResult.sleepCycles`

- `cycles.sleepCycleModels`: list of `{ "secondsFromSleepStart": ..., "sleepDepthStart": ... }` — sleep cycle boundaries.

**Notes:** richest sleep dataset; combine `phaseDurations` (per-night stage totals) with `sleep_score` for a compact daily sleep table.

---

## 8. `nightly_recovery_<userId>-<uuid>.json`

Nightly recovery summary derived from overnight HRV. Single file containing all nights.

- **Coverage:** 2026-08-22 → 2026-10-19 (54 nights)

### Structure

```json
[
  {
    "night": "2026-08-22",
    "sleepTip": "-1",
    "vitalityTip": "-1",
    "exerciseTip": "-1",
    "meanNightlyRecoveryRri": "994",
    "meanNightlyRecoveryRmssd": "38",
    "meanNightlyRecoveryRespirationInterval": "4019"
  }
]
```

### Fields

| Field | Type | Description |
|---|---|---|
| `night` | date | Evening date |
| `meanNightlyRecoveryRri` | string (int) | Mean R-R interval during the night, in ms (994 ms ≈ 60 BPM) |
| `meanNightlyRecoveryRmssd` | string (int) | Mean nightly RMSSD (HRV), in ms — higher = better recovery |
| `meanNightlyRecoveryRespirationInterval` | string (int) | Mean respiration interval, in ms (4019 ms ≈ 15 breaths/min) |
| `sleepTip` / `vitalityTip` / `exerciseTip` | string (int) | Polar tips; `-1` = none available |

**Notes:** values are stored as **strings**, not numbers — convert before use. `meanNightlyRecoveryRmssd` is the single best overnight recovery indicator here; pair with `nightly_recovery_blob` for the full time series.

---

## 9. `nightly_recovery_blob_<userId>-<uuid>.json`

Raw nightly HRV and breathing-rate sample series behind the nightly recovery scores. Single file containing all nights.

- **Coverage:** 2026-08-22 → 2026-10-19

### Structure

Top level: list of night records (**no `night` field** — the first entry corresponds to the first sleep result night, 2026-08-22; align by index or use `startTime`).

```json
[
  {
    "hrvData": [
      {
        "startTime": "2026-08-22T04:08:45",
        "samplingIntervalInMillis": 301000,
        "samples": [17.20, 24.11, ...]
      }
    ],
    "breathingRateData": [
      {
        "startTime": "2026-08-22T04:06:15",
        "samplingIntervalInMillis": 300000,
        "samples": [14.26, 13.98, ...]
      }
    ]
  }
]
```

### Fields

| Section | Field | Description |
|---|---|---|
| `hrvData` | `startTime` | Start of the night's HRV recording (ISO datetime) |
| `hrvData` | `samplingIntervalInMillis` | ~301 000 ms ≈ 5 min between samples |
| `hrvData` | `samples` | RMSSD values (ms), one per interval (~60 per night) |
| `breathingRateData` | `startTime` | Start of breathing recording |
| `breathingRateData` | `samplingIntervalInMillis` | 300 000 ms = 5 min |
| `breathingRateData` | `samples` | Breathing rate in breaths per minute |

Timestamp of sample *i* = `startTime + i * samplingIntervalInMillis`. Higher RMSSD during the night generally = better recovery; falling RMSSD toward morning can indicate stress.

---

## 10. Account & Reference Files

One-off JSON files with account, device, and settings data. No time series — reference only.

| File | Content |
|---|---|
| `account-data-<userId>-<uuid>.json` | Account info (`username`, `firstName`, `lastName`) + `physicalInformation` (sex, birthday, height, weight, `trainingBackground`, `sleepGoal`, resting HR, max HR, VO2max, etc.) |
| `account-profile-<userId>-<uuid>.json` | `favouriteSports`, `countryCode` (DE), `city` |
| `products-devices-<userId>-<uuid>.json` | Registered devices (Polar Street X, `deviceId: 1A581F3F`), registration date, device settings (e.g. handedness) |
| `calendar-items-<userId>-<uuid>.json` | `perceivedRecovery` (currently empty), `physicalInformations` (dated history: height, weight, VO2max, max HR, resting HR), training calendar items |
| `sport_profiles-<userId>-<uuid>.json` | Per-sport settings profiles (HR zones, speed zones, sensor broadcasting, etc.) |
| `favourite-targets-<userId>-<uuid>.json` | Currently an empty list |

---

## General Notes

- Durations use ISO 8601 format (`PT5H14M30S`).
- Sleep files key records by `night` (the evening date), while activity files key by calendar `date`.
- Most analysis value: `activity`, `247ohr`, `sleep_score`, `sleep_result`, `nightly_recovery`, `ppi_samples`.
