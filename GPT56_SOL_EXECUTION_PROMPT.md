# GPT-5.6 Sol execution prompt

You are implementing a local, offline research prototype for evidence-limited airway-video assessment. Work directly in:

`C:\Users\abhij\Documents\ChatGPT\Mallampati`

Do not stop at a plan. Build, test, and document the application described below. Make ordinary engineering decisions autonomously. Ask the user only when a missing participant mapping or unresolved clinical protocol decision is genuinely required; continue all independent work while it is unavailable.

## Objective

Create a Windows-local Streamlit application using Python 3.12, OpenCV, MediaPipe Tasks Face Landmarker, SQLite, NumPy/pandas, and local media storage. The workflow is:

`inventory -> assign participant/view -> analyze -> review -> report/export -> delete`

The output is limited to observable indicators, measurement completeness, technical quality, and human-reviewed evidence. It must always state:

> Insufficient evidence to estimate overall intubation difficulty.

Do not implement an LLM, cloud processing, biometric identity matching, outcome-model training, probabilities, severity scores, or an overall easy/moderate/difficult classification.

## Inputs and current evidence

Read-only video source:

`C:\Users\abhij\Downloads\Jawline_vids\Jawline_vids`

Clinical sources:

- `C:\Users\abhij\Downloads\lillia joe presentation.pptx`
- `C:\Users\abhij\Downloads\YaynlanmMakale.pdf`

The initial inventory contains 320 MP4 files, 358,512,871 bytes, and no byte-identical duplicates. Filenames are WhatsApp timestamps with numbered suffixes; they are not participant identifiers. Use `planning/video_inventory.csv` as the initial manifest, then revalidate it. Existing planning extracts are evidence aids only, not application inputs or clinical approval.

The expected view slots are:

- `front_flexion_extension`: front view, looking up/down.
- `front_rotation`: front view, looking left/right.
- `lateral_flexion_extension`: side view, looking up/down.

Keep camera view and performed maneuver as separate fields. A front up/down video is not automatically a mouth-opening examination.

## Non-negotiable safeguards

1. Preserve every source file byte-for-byte. Never move, rename, overwrite, or delete anything under Downloads.
2. Do not group clips by filename adjacency, timestamp, suffix, equal groups of three, or face similarity. Do not use face embeddings, clustering, or any biometric identity method.
3. Participant grouping requires an owner-supplied mapping or explicit reviewer confirmation. Use pseudonymous IDs such as `P0001`; retain `unassigned`, `provisional`, `confirmed`, and `disputed` states.
4. Do not infer teeth, hyoid, thyroid notch, manubrium, gonion, mastoid, internal oral anatomy, or hidden neck landmarks from a face mesh.
5. Do not synthesize frontal views or use per-frame facial leveling that erases real head movement.
6. Pixels, ratios, MediaPipe depth, phone model, and assumed face size are not centimetre calibration. Physical units require a known-size reference, suitable geometry, verified endpoints, and a documented protocol.
7. Preserve automated proposals, reviewed corrections, timestamps, coordinate spaces, transforms, calibration, and every report revision separately.
8. External video cannot produce Cormack-Lehane or POGO. Mark both `not_applicable`.
9. Missing, unclear, occluded, unsupported, or uncalibrated evidence must never become a normal finding.
10. Keep difficult laryngoscopy, difficult intubation, and difficult supraglottic-device insertion as separate outcomes. The supplied paper is clinical reference material, not a transferable video model or performance guarantee.

## Phase 1: inventory and grouping

Implement a resumable command such as:

```text
python -m airway.cli inventory --source <path> --output <path>
```

For every video, store a stable UUID, original relative path, SHA-256, bytes, untrusted filename timestamp, codec/container, duration, decoded dimensions, aspect ratio, rotation metadata, frame rates, actual presentation timestamps, frame count, audio presence, and decode status. Decode the full clip sequentially with bounded memory and record first/middle/end access, corrupt sections, and partial failures. Generate a local contact-sheet/gallery with filename, UUID, timestamp, and editable view/maneuver labels.

Implement CSV mapping import and manual assignment. The reviewer must confirm that clips belong to the same participant. Never claim a patient count until mappings are confirmed. Support missing, repeated, mixed, and extra views. Only confirmed mappings may enter a combined participant report.

Copy confirmed files into managed storage without changing originals:

```text
data/airway.sqlite3
data/participants/P0001/originals/<video_uuid>/<original_name>.mp4
data/participants/P0001/participant_manifest.json
data/participants/P0001/cases/<case_uuid>/{frames,analysis,reviews,exports}
```

Verify hashes after copying. Make imports idempotent. Support reviewed reassignment, split, merge, and invalidation of affected reports. Produce inventory CSV/JSON, decode audit, gallery, assignment manifest, confirmed folders, and unresolved-assignment report.

## Phase 2: registry and source reconciliation

Create:

```text
registry/metrics.v1.yaml
registry/protocols.v1.yaml
registry/source_discrepancies.md
```

Every metric/rule must record source hash, slide/page, definition, landmarks, posture, maneuver, view prerequisites, units, formula, comparator, threshold kind, outcome, limitations, and activation status. Use `normal_reference`, `adverse_indicator`, and `descriptive_only`; never invert a normal reference into a diagnostic rule.

Implement these metrics with explicit gates:

- Interincisor opening: reviewer-confirmed upper/lower incisal edges only. Uncalibrated result is pixels. Keep the presentation's `>5 cm` normal reference separate from its `<3 cm` difficult-laryngoscopy reference and the separate `<2 cm` LMA reference. Do not apply centimetre rules without valid calibration.
- Visible lip aperture: exploratory pixels or a documented same-frame dimensionless ratio; never call it interincisor distance.
- Modified Mallampati: human grading only when sitting, eye-level, mouth open, tongue protruded without phonation, and internal oral anatomy is clearly visible. Poor visibility is unavailable, never class IV. Resolve slide 9/10 wording explicitly.
- Upper-lip bite test: human class I/II/III only when the attempted maneuver and incisor/vermilion relationship are visible. Absence of the maneuver is unavailable.
- Jaw protrusion: reviewer records observed incisor relationship or unavailable; no invented continuous score.
- Apparent neck/head motion: descriptive image-plane trajectory and relative pose only. Keep the presentation's AO protocol separate from the paper's supine tragus-to-mouth-corner protocol. Do not apply clinical cutoffs to generic video motion.
- Thyromental, hyomental, sternomental, mandibular, bigonial, neck-length, circumference, thyroid-to-floor-of-mouth, and condylar metrics: unavailable unless the exact endpoints, posture, scale, and examination are supported.
- Cormack-Lehane and POGO: `not_applicable` to external video.

Preserve all source discrepancies instead of silently choosing between conflicting definitions.

## Phase 3: geometry, scale, and analysis

Maintain four coordinate spaces: encoded pixels, orientation-corrected source pixels, detector pixels, and display pixels. Store invertible mappings and coordinate-space IDs. Apply metadata rotation once; preserve actual posture.

Use a 2-D similarity transform `p' = sRp + t` (for example, OpenCV `estimateAffinePartial2D` with RANSAC) only for supported display alignment or camera stabilization. Estimate stabilization from static background features, expose inliers/residuals, disable it when parallax or insufficient evidence makes it unreliable, and never fit away the participant's motion. Do not register asynchronous front/side clips into synthetic 3-D.

Physical calibration is valid only with a known-size reference in suitable geometry and verified endpoints. Reject assumed face dimensions, phone model, cross-plane scale transfer, and MediaPipe depth as centimetres. Optional lip-aperture/outer-canthal ratios are exploratory, view-restricted, and have no clinical cutoff.

Use local MediaPipe Face Landmarker in VIDEO mode with original timestamps. Reset tracking across clips, cuts, multiple faces, and non-monotonic seeks. Analyze a configurable default of 10 Hz, disclose sampling, and allow refinement around reviewer-selected intervals. Preserve raw trajectories and quality flags; do not bridge gaps or report isolated spikes as range of motion.

Require reviewer selection of neutral and maneuver intervals. Store apparent lateral head-line movement separately from torso-relative movement. Store endpoints, sign convention, neutral frame, axis convention, quality limitations, and whether the result is descriptive or protocol-matched. If profile/occlusion makes pose unstable, return missing/descriptive output rather than invented degrees.

For mouth opening, detector proposals may find candidate frames and oral regions. The reviewer must place or accept actual incisor endpoints. Without visible teeth, store only the separate lip-aperture observation.

## Phase 4: application structure and persistence

Implement at least:

```text
app.py
airway/{cli,db,ingest,video,geometry,landmarks,quality,measurements,rules,review,reports}.py
airway/ui/
registry/
models/
tests/
scripts/setup.ps1
start.ps1
start.bat
README.md
VALIDATION_REPORT.md
```

SQLite must enable foreign keys and persist participants, assignment revisions, cases, videos, segments, evidence frames, analysis runs, proposals, review revisions, calibrations, measurements, and report snapshots. Large media/arrays belong in managed storage with hashes and database references.

Each measurement stores IDs/versions, source hash, exact timestamp/interval, neutral/reference frames, value/null, unit, coordinate space, method, endpoints, calibration, quality flags, state, reason codes, proposal/review IDs, reviewer, and revision time. Reject NaN/Infinity in JSON.

States are:

- `available`: accepted under its method, but not necessarily eligible for a clinical rule.
- `needs_review`: proposal or correction awaiting review.
- `unavailable`: missing maneuver, anatomy, calibration, quality, protocol, or readable media.
- `not_applicable`: structurally outside scope, such as Cormack-Lehane/POGO.

Rule evaluation order: accepted review state -> protocol match -> anatomy/quality -> supported units -> calibration/geometry -> active rule/version -> exact comparator. A failed gate emits a specific missing-evidence explanation and never a normal finding.

Build the Streamlit flow for inventory/assignment, case creation, upload/import, analysis progress/cancel/retry, frame/landmark review, neutral/extrema selection, reviewer grading, save/reload, report generation, export, and safe case/participant deletion. Use a maintained point editor or minimal local component plus numeric coordinate fallback.

Generate self-contained printable HTML, JSON, and CSV. Escape user text, embed evidence thumbnails locally, include source UUID/hash/time/method, preserve null/state/reason fields, guard CSV formula injection, and make reports reproducible for a fixed snapshot. Deletion must enforce managed-root containment, preserve Downloads, invalidate caches, cancel jobs, and prevent recreation of deleted artifacts.

## Phase 5: validation and delivery

Use pytest plus real-browser checks. Required tests include:

- all 320 paths accounted for; full decode audit; source hashes unchanged;
- grouping never auto-confirms identity and blocks unassigned/disputed pooled reports;
- coordinate round trips for rotation, crop, letterbox, and resize within 0.5 source pixel;
- uniform resize preserves exploratory ratios within 1%;
- synthetic 0/10/20-degree motion remains within 1 degree after valid fixed orientation correction;
- absent maneuvers, unclear oral anatomy, occlusion, multiple faces, corrupt media, missing calibration, and unsupported views produce explicit states;
- exact boundary tests: 2.99 matches `<3 cm`, 3.00 does not; 5.00 does not meet `>5 cm`, 5.01 does; missing values never match;
- LMA rules cannot emit intubation conclusions; AO protocols remain separate; C–L/POGO remain unavailable/not applicable;
- reviewer edits invalidate dependent measurements and explanations without overwriting prior proposals/reports;
- variable-frame-rate timestamps are retained and tracking state is not reused across clips/cuts;
- offline HTML/JSON/CSV exports are valid and traceable;
- restart restores review state; missing model has a clear recovery path; no media leaves the machine;
- deletion removes only the selected managed case/participant and refuses path escapes.

Run the technical audit across all 320 videos. Run a complete browser flow on at least one owner-confirmed participant with all three views, plus failure examples. If no participant mapping is available, complete all single-clip, synthetic, and technical tests, mark patient-level grouping validation blocked, and say so explicitly.

Browser acceptance flow: start locally; create case; import/upload; assign views; analyze; inspect evidence; edit a landmark and neutral frame; grade or mark a reviewer metric unavailable; save; reload; export/open HTML, JSON, and CSV; delete the test case; verify deletion and source preservation.

`VALIDATION_REPORT.md` must record versions, files, timestamps, tests, browser evidence, pass/fail results, unresolved assignments, inactive rules, and what was not tested. Do not declare completion because Streamlit starts or unit tests pass alone.

## Final response required from you

Report:

1. Exact startup commands and local storage locations.
2. Files and modules created.
3. Tests and browser checks run, with results.
4. Number of videos decoded successfully/partially/failed.
5. Number of confirmed, provisional, disputed, and unassigned participant mappings.
6. Metrics/rules that remain inactive or unavailable and why.
7. Scientific and validation limitations.

Never claim patient grouping, clinical accuracy, or overall intubation prediction unless the required evidence was actually obtained and verified.
