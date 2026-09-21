# Airway Evidence Review

**Current interface: Research workspace v2.** See [RESEARCH_MVP_V2.md](RESEARCH_MVP_V2.md) for the current four-step workflow, quality checks, distance comparisons, and validation boundaries. The old median/band workflow described below is superseded in the application UI.

A Windows-local, offline-first Streamlit research prototype for inventorying, assigning, reviewing, and exporting observable airway-video evidence. It does **not** identify people, infer hidden anatomy, predict clinical outcomes, assign an overall difficulty class, or send media off the machine.

> **Insufficient evidence to estimate overall intubation difficulty.**

## Setup and startup

From PowerShell in `C:\Users\abhij\Documents\ChatGPT\Mallampati`:

```powershell
.\scripts\setup.ps1
.\start.ps1
```

Or run `start.bat`. The local app opens at `http://127.0.0.1:8501`.

The official MediaPipe Face Landmarker bundle is installed at `models\face_landmarker.task`. A local MediaPipe Pose Landmarker fallback supports side-profile flexion/extension endpoint selection from visible shoulder/nose landmarks. Their origins, license notes, byte sizes, and SHA-256 values are recorded in `models\manifest.json`. Runtime analysis is offline and never downloads a model.

## Full inventory audit

```powershell
.\.venv\Scripts\python.exe -m airway.cli inventory `
  --source "C:\Users\abhij\Downloads\Jawline_vids\Jawline_vids" `
  --output "data\inventory"
```

This command is resumable and reads each clip sequentially with bounded memory. It hashes but never moves, renames, overwrites, or deletes source files. Outputs include `inventory.csv`, `inventory.json`, per-clip presentation timestamps, `decode_audit.jsonl`, local contact frames, `gallery.html`, `unresolved_assignments.csv`, and `summary.json`.

## Storage

- SQLite: `data\airway.sqlite3`
- Technical inventory: `data\inventory\`
- Confirmed copied originals: `data\participants\P0001\originals\<video_uuid>\`
- Cases and exports: `data\participants\P0001\cases\<case_uuid>\`
- Source videos remain read-only in Downloads.

Only owner/reviewer-confirmed assignments can be materialized or used for combined participant cases. Filename order, timestamp proximity, numbered suffixes, groups of three, and facial similarity are never identity evidence.

## Workflow

1. Inventory all source clips and review the local gallery.
2. Import an owner/reviewer CSV mapping or enter reviewed assignments. Keep unresolved files `unassigned`, `provisional`, or `disputed`.
3. Copy confirmed originals into managed storage with post-copy hash verification.
4. Create a case, run local pretrained inference, inspect overlays, and review neutral/maneuver intervals, exclusions, camera stability, and supported measurements.
5. Export fixed-snapshot HTML, JSON, and CSV reports.

The application also shows a low/mid/high **relative visible mouth-opening** band after interval review. This is a display-only proof-of-concept heuristic derived from a dimensionless lip-aperture/mouth-width ratio. It is not a centimetre estimate, physical measurement, or clinical threshold.

The Analysis screen presents each available technical measure as a read-only evidence checklist. A checked entry means that measurement's calculation and review prerequisites were met; it is not evidence that intubation will be easy or difficult. The application does not provide a difficult-intubation verdict.

For three-video cases, the application also derives a cross-video evidence summary after each clip is reviewed independently. It reports the number of reviewed clips plus median and range for each measurement. This is descriptive aggregation, not a diagnostic model.
6. Delete selected managed cases through containment-checked deletion. Downloads are never deletion targets.

## Evidence limits

- Pixels, ratios, MediaPipe depth, phone model, or assumed face size are not centimetre calibration.
- Interincisor distance requires reviewer-confirmed incisal edges; otherwise only visible lip aperture may be recorded.
- Mallampati assessment is deliberately outside this face-landmark test pipeline and is handled separately by the owner's dedicated model.
- Generic video head motion is descriptive and is not silently equated with either source AO protocol.
- Thyromental, hyomental, sternomental, mandibular, bigonial, circumference, hidden landmark, and related physical metrics remain unavailable without exact endpoints, posture, geometry, and scale.
- Cormack–Lehane and POGO are `not_applicable` to external video.
- Difficult laryngoscopy, difficult intubation, and difficult supraglottic-device insertion remain separate outcomes.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

See `VALIDATION_REPORT.md` for the exact validation performed and unresolved gates.
