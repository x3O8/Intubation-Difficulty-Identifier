# Local video-based airway assessment: execution plan for GPT-5.6 Sol

Prepared 20 September 2026. Deliverable: a local research application with traceable observations, human review, deterministic explanations, and reproducible exports. No LLM, identity-recognition model, outcome-model training, or unsupported overall difficulty score.

## 1. Starting point and verified evidence

Workspace: `C:\Users\abhij\Documents\ChatGPT\Mallampati`.

Read-only input collection: `C:\Users\abhij\Downloads\Jawline_vids\Jawline_vids`.

Clinical sources:

- `C:\Users\abhij\Downloads\lillia joe presentation.pptx`: 17 slides; inspect embedded images as well as editable text.
- `C:\Users\abhij\Downloads\YaynlanmMakale.pdf`: Çelik and Aydemir, *Prediction of Difficult Tracheal Intubation by Artificial Intelligence: A Prospective Observational Study*, 2021, DOI `10.18678/dtfd.862467`.

This planning pass inventoried and SHA-256 hashed all **320 MP4 files**, totaling **358,512,871 bytes (341.90 MiB)**. No byte-identical duplicate files were found. The filenames are WhatsApp timestamps, some with numbered suffixes. These are not verified participant identifiers or acquisition timestamps. There are no participant subfolders in this input collection.

Filename-date counts: 2026-08-27: 56; 2026-09-05: 24; 2026-09-06: 20; 2026-09-07: 95; 2026-09-08: 75; 2026-09-09: 41; 2026-09-10: 9. These counts describe filenames only.

Artifacts already present:

- `planning/video_inventory.csv`: all original relative paths, sizes, hashes, and blank participant assignments.
- `planning/inventory.json` and `planning/inventory_summary.json`: machine-readable inventory.
- `planning/presentation_text.txt`, `planning/paper_text.txt`, and source-image previews: planning evidence, not application inputs or clinical rule approvals.

Verification boundary: the current pass did not decode the 320 videos, establish identities, assign patients, verify maneuvers, or build/test the application. Do not claim those steps have happened. Only a `.venv` existed before this planning work; its Python is 3.12, but OpenCV and MediaPipe were not installed when checked. Recheck the environment before reuse.

The latest user description supersedes the earlier three-clip example. Expected view slots are:

1. `front_flexion_extension`: front camera, participant looking up/down.
2. `front_rotation`: front camera, participant looking left/right.
3. `lateral_flexion_extension`: side camera, participant looking up/down.

Keep camera view and performed maneuver as separate fields. A front up/down clip is not automatically a mouth-opening examination. Accept `unknown`, `mixed`, `unsupported`, and additional maneuvers without forcing a label.

## 2. Product contract and non-negotiable limits

Build with Python 3.12, Streamlit, OpenCV, MediaPipe Tasks Face Landmarker, SQLite, NumPy, pandas, and local media storage. Use PyAV or a bundled, documented FFmpeg/ffprobe installation for reliable decoding and presentation timestamps. Use Jinja2 with HTML escaping for reports. Add a torso detector only if needed for a clearly labelled apparent-motion mode; manual torso reference correction must remain possible.

The product must:

- Preserve downloaded source files exactly; organize verified copies inside the workspace, never move or rename the source collection.
- Measure visible evidence only. Never infer hidden anatomical endpoints, perform generative frontalization, or substitute face mesh points for teeth, hyoid, thyroid notch, or internal oral anatomy.
- Preserve automated proposals and every reviewer revision separately.
- Distinguish research motion/geometry from protocol-matched clinical measurements.
- Report observable indicators and measurement completeness, never fabricated probabilities, easy/moderate/difficult categories, or an aggregate severity score.
- Always display the v1 conclusion: **“Insufficient evidence to estimate overall intubation difficulty.”** Reviewed measurements do not remove the absence of outcome validation.
- Work offline after explicit dependency/model setup. No uploads, cloud processing, analytics, or runtime model downloads.

The supplied paper used directly acquired clinical measurements and linked procedural outcomes; it is not a pretrained video model. Its flow diagram shows 1,486 procedure participants but 341 selected records for AI analysis (121 + 108 + 110 + 2), with 10-fold cross-validation described on PDF page 4. Do not transfer its performance, sampling prevalence, or model claims to this collection. Keep difficult laryngoscopy, difficult intubation, and difficult supraglottic-device insertion as different outcomes.

## 3. Stage A — inventory, grouping, and patient folders FIRST

### A1. Complete the technical audit

Implement a resumable `python -m airway.cli inventory --source <path> --output <path>` command. Reuse existing hashes only after verifying file size/modification metadata; calculate new hashes when uncertain. Never treat a hash as a patient identifier.

For each input, record a stable video UUID, original relative path, SHA-256, bytes, filename timestamp as untrusted metadata, container/codec, duration, decoded dimensions, sample aspect ratio, rotation metadata, nominal/average frame rate, actual presentation timestamps, frame count, audio presence, and decode result. Unknown metadata stays null.

Decode each full clip sequentially, logging first/middle/end frame access and corrupt/truncated sections. A readable header is not a successful decode. Preserve partial success, offending timestamps, and errors without stopping the batch. Work with bounded memory and per-file status/progress. Do not put identifiable images into logs or version control.

Generate contact sheets and a local review gallery with original filename, video UUID, time, and view/maneuver labels. Start with frames around 10%, 50%, and 90% of duration, but support playback and additional frames. These sheets support human review; they do not establish identity.

### A2. Establish participant assignments from trusted records or the dataset owner

Provide CSV import and manual assignment using the owner's acquisition log or confirmed participant-to-file mapping. **Do not implement face embeddings, face clustering, biometric similarity matching, or an automated same-person determination.** Facial landmarks in the measurement pipeline are for visible geometry, not identity linkage.

The dataset owner/reviewer confirms that assigned clips belong to the same participant. Record assignment source, reviewer, time, and status: `unassigned`, `provisional`, `confirmed`, or `disputed`. Metadata/time proximity may sort the review queue but must never confirm identity. If trusted mapping is unavailable, keep clips unassigned; the application may still support single-clip technical analysis without a pooled patient report.

Use pseudonymous IDs such as `P0001`, assigned only through this workflow. Never deduce patient count by dividing 320 by three. Do not impose `k = 3`, and do not treat filename suffixes as patient labels. One participant can have incomplete views, repeats, mixed clips, or more than three files.

### A3. Materialize confirmed groups safely

Copy only confirmed assignments into the workspace, preserving original basenames and hashes:

```text
data/
  airway.sqlite3
  participants/
    P0001/
      originals/<video_uuid>/<original_filename>.mp4
      participant_manifest.json
      cases/<case_uuid>/
        frames/
        analysis/<run_uuid>/
        reviews/
        exports/
```

Store the three expected view slots in the manifest, each referencing zero or more video UUIDs and a selected primary clip. Do not overwrite a clip when the same view appears twice. Verify copied SHA-256 values before completing assignment. Use normal copies rather than writable hard links to protect the source bytes.

Support manifest preview, reassignment, split, and merge through reviewed mapping changes. Any reassignment invalidates affected case aggregation and reports. Use temporary copy paths, checked destination containment, and atomic finalization. Repeated imports of the same source must be idempotent without conflating different participants.

Stage A deliverables: inventory CSV/JSON, decode audit, local review gallery, owner-confirmed assignment manifest, confirmed participant folders, and unresolved-assignment report. An honest unresolved list is an acceptable boundary; fabricated grouping is not.

## 4. Stage B — versioned metric registry and source reconciliation

Create `registry/metrics.v1.yaml`, `registry/protocols.v1.yaml`, and `registry/source_discrepancies.md`. Store source-file hashes, slide/PDF page, definition, landmarks, posture, maneuver, camera prerequisites, units, formula, comparator, threshold kind, target outcome, limitations, and activation status for every metric/rule.

Distinguish `normal_reference`, `adverse_indicator`, and `descriptive_only`. A normal reference is never inverted into a diagnostic rule. Unknown or conflicting clinical definitions remain inactive until a qualified reviewer resolves the exact protocol. Software tests use isolated test rules and must not silently activate disputed clinical rules.

Initial registry content:

| Metric | Exact requirements and source | Implementation and rule handling |
|---|---|---|
| Interincisor opening | Upper/lower incisal edges; maximum opening, sitting with neutral head in paper PDF p.3; PPT slides 3–4 | Reviewer identifies actual teeth. Mesh lip points can propose an oral region, not incisors. Uncalibrated value is pixels. Slide 4: `>5 cm` normal reference; `<3 cm` adverse reference specifically for difficult laryngoscopy. Keep them separate; only evaluate the latter for reviewed, eligible, calibrated measurements under the approved protocol. |
| LMA insertion opening reference | Slide 4: `<2 cm` | Retain as a separate source reference, inactive in the intubation-indicator panel. Do not relabel as an intubation threshold. |
| Visible lip aperture | Inner upper/lower lip points; sufficiently frontal, visible mouth | Separate exploratory metric in pixels and, optionally, a defined dimensionless ratio. Not an interincisor measurement; no clinical cutoff. |
| Modified Mallampati | Sitting, eye-level inspection, maximum mouth opening and tongue protrusion without phonation; visible oral anatomy; slides 9–10, PDF p.3 | Human grading only. Adopt a named rubric after resolving wording differences. I–IV are categorical; slide 9's class 0 is a separately documented observation, not automatically part of the I–IV ordering. Poor visibility is unavailable, never class IV. If phonation/posture cannot be established, record protocol uncertainty. |
| Upper-lip bite test | Lower incisors actually bite upper lip; relationship to vermilion border visible; slides 3/5, PDF p.3 | Reviewer assigns I, II, or III using a selected source rubric. Class III requires an observed attempted maneuver, not absence of a clip. Reviewed class III can be a source-supported indicator; I/II do not establish easy intubation. |
| Jaw protrusion | Visible upper/lower incisor relationship during deliberate protrusion; slide 3 | Reviewer records lower incisors beyond, edge-to-edge, or behind upper incisors, or unavailable. No invented continuous score or threshold. |
| Apparent flexion/extension | Neutral frame, valid lateral view and visible head reference; torso reference if available; motion illustrated on slide 12 | Reviewable image-plane trajectory and angle change. Separate front-camera pitch estimate, lateral image-plane measurement, and torso-relative estimate. No clinical cutoff. |
| Apparent left/right rotation | Front view, neutral baseline, stable camera and usable tracked face | Exploratory relative yaw only while a documented pose method is valid. No clinical cutoff; do not call raw 2-D displacement an angle. |
| Presentation AO protocol | Slide 11: incisor occlusal-plane movement; text includes at least 80–85 degrees and chin-to-sternum description of 25–30 degrees | Separate inactive clinical protocol. Cannot be equated to ordinary nose/face pitch. Range wording and exact endpoints require reviewer clarification before comparisons. |
| Paper AO protocol | PDF p.3: supine, full extension, tragus-to-mouth-corner line versus horizontal | Separate measurement definition. Do not merge with slide 11, or apply it to seated front up/down clips. |
| Thyromental distance | Superior thyroid notch to mental protuberance, mouth closed/full extension; paper additionally specifies supine; slide 7, PDF p.3 | Need genuine endpoints, matching posture, valid scale/geometry. Otherwise unavailable. PPT `>6.5 cm` is a normal reference, not an automatic adverse cutoff. |
| Hyomental distance | Hyoid-to-mentum; slide 7 and diagram on slide 13 | Hyoid cannot be assumed from face shape. Required posture must be resolved in protocol. PPT `>6 cm` normal reference; unavailable without supported endpoints and scale. |
| Sternomental distance | Upper manubrium to mentum, closed mouth/full extension; supine in paper; slide 14, PDF p.3 | Same evidence/calibration gates. PPT `>12.5 cm` normal reference, not an inverted adverse rule. |
| Horizontal mandibular length | Gonion/mandibular angle to mental protuberance; slides 7–8, PDF p.3 | Reviewer-visible endpoints and suitable scale/view required. PPT `>=9 cm` reference; jaw-outline mesh is not verified bony gonion. |
| Bigonial width | Two gonions; PDF p.3 | Calibrated and verified endpoints only; no threshold imported from study averages. |
| Neck length | Mastoid process to upper medial manubrium, supine/full extension/closed mouth; PDF p.3 | Unavailable unless actual endpoints, posture, and scale are supported. |
| Neck/head circumference | Tape-based perimeter at defined anatomical levels; PDF p.3 | Unavailable from these ordinary views. Never estimate circumference from front width or an assumed circular neck. |
| Thyroid-to-floor-of-mouth | Specified examination, slide 13; two-finger reference | Not inferable from face landmarks. Record unavailable unless the examination itself is adequately evidenced. Fingers are not a centimetre calibration. |
| Condylar movement | Condyle movement anterior to tragus during mouth opening; slides 3/6 | Generic jaw motion is insufficient. Require identifiable examination/endpoints; otherwise unavailable. |
| Cormack–Lehane and POGO | Laryngeal visualization, slides 15–16 | `not_applicable` to external-video inference, explicitly excluded. No predictor or proxy grade. |

Reconcile at least these source issues: slide 9 versus slide 10 Mallampati wording; slide 11 versus paper AO definitions; normal versus adverse opening references; different endpoint/posture descriptions; slide 16's illustrated grading labels versus slide 15. Preserve discrepancies; do not silently copy a conflicting illustration into active logic.

These metrics describe relevant airway observations, not a sufficient set for successfully predicting an individual's intubation outcome. Broader clinical assessment includes history and procedural context not available here. Keep demographic/history fields outside inferred video output; never infer age, sex, BMI, disease, or prior airway history from appearance.

## 5. Stage C — geometry, scale, and lighting

### C1. Coordinate systems

Define and test four spaces: encoded pixels, orientation-corrected source pixels, detector input pixels, and display pixels. Keep invertible mappings for rotations, letterboxing, resize, and crops. Record any lens-distortion remapping separately; it is not a single affine matrix. Store every landmark's coordinate-space ID.

Apply metadata rotation exactly once; distinguish that from the person's posture. Display overlays and click corrections must map back into source coordinates. Disable automatic per-frame eye-line leveling in measurement space. Preserve raw frames, automated points, reviewed points, transforms, and timestamps.

### C2. What to use instead of an undefined “k similarity” method

Use a **2-D similarity transform**, `p' = s R p + t`, for supported translation, uniform scale, and in-plane rotation. OpenCV `estimateAffinePartial2D` with RANSAC is one implementation. It is an image-alignment tool, not a clinical model or a physical-scale estimator.

- For consistent display crops, a face-based transform is acceptable if every correction maps back to source coordinates.
- For camera stabilization, estimate from static background features outside the moving participant; expose inlier count and residual. Disable when parallax, camera movement, changing viewpoint, or inadequate static evidence makes the estimate unreliable. Do not fit the face itself to remove head movement.
- Use a fixed reviewer-supported camera-roll correction per stable clip segment where justified. If no external reference exists, record unknown camera roll; do not equate head tilt with camera tilt.
- Compute head motion in source or justified camera-corrected coordinates, with torso-relative motion only where a torso reference is observed and validated for that view.
- Do not register asynchronous front and side clips into a synthetic 3-D person. Do not treat per-clip scaling as cross-phone calibration.

Optional exploratory mouth ratio: visible inner-lip aperture divided by a specified visible outer-canthal span in the same frame, only within a reviewed near-frontal segment. Give the ratio its own ID, endpoints, pose restrictions, and failure reasons. This can reduce uniform resize sensitivity but changes with pose/perspective; never use it on profile frames or compare it to centimetre thresholds.

Camera intrinsics correct aspects of projection/distortion; they do not establish the participant's physical size. Physical distance conversion requires a known-size reference with suitable geometry, verified endpoints, and a documented protocol. For a valid coplanar configuration, record `distance_cm = target_px * reference_cm / reference_px`, along with calibration evidence and applicable frame interval. Reject cross-plane scale transfer, assumed face dimensions, phone model alone, or inferred MediaPipe depth as centimetre calibration. Do not assume a marker remains valid through rotation or depth changes.

### C3. Lighting and quality

Compute blur/sharpness, clipping/darkness fractions, visible oral-region size, tracking availability, occlusion flags, and view suitability. Calibrate configurable technical screening defaults on reviewed examples across the collection; do not present them as validated clinical thresholds.

Optional contrast enhancement may assist detection/display. Retain original pixels, map proposals back, and require original-frame review for oral grading. Do not use enhancement or super-resolution to manufacture anatomical detail. Flag clipped highlights, darkness, motion blur, and obstruction independently. Detector success is not proof of visibility or measurement validity; predicted hidden points are not observations.

## 6. Stage D — analysis implementation

1. Create an explicit local setup command; pin tested dependency versions after an import/decoding/model smoke test. Fetch the official MediaPipe model once, store its source URL, license, SHA-256, and version in a model manifest. Startup must explain a missing model and preserve review-only mode.
2. Analyze independently per clip and stable segment. Use original presentation timestamps for variable-frame-rate recordings; never infer all timestamps as `index/fps`.
3. Start with a configurable 10 Hz analysis sample; retain native-resolution candidate evidence and allow full-rate refinement around extrema or reviewer-selected intervals. Store sampling settings. Never claim unsampled frames were analyzed.
4. Produce face landmark proposals with MediaPipe Tasks VIDEO mode. Reset state across clips/cuts/non-monotonic seeks. Preserve model output but expose validity masks. MediaPipe has no general per-landmark clinical confidence score; do not invent one from detection/tracking settings.
5. Segment on scene cuts, multiple faces, tracking loss, and unsupported views. Exclude multi-person frames from measurement. Do not track identity across clips. Offer manual frame/landmark review when profile detection fails rather than substituting hidden points.
6. Ask the reviewer to accept a neutral frame/interval and maximal visible maneuver intervals. Keep raw trajectories and a documented, configurable smoothed series; do not bridge long tracking gaps or report spike extrema as range of motion.
7. Lateral 2-D motion: use two reviewer-confirmed visible head reference points (e.g. visible tragus and mouth corner where usable) to define a line angle `theta(t)`. Record `unwrap(theta(t)) - theta(neutral)`. Label this image-plane head-line movement, not isolated AO motion. Mouth movement can alter the line and must be flagged/excluded. With a suitable torso reference `phi(t)`, also calculate change in `theta(t) - phi(t)`; otherwise torso compensation is unknown. Store the actual endpoints and signs, not only the result.
8. Front-view rotation/pitch: use a documented relative-pose method based on model transformation matrices, with rotation orthogonalization and a fixed axis convention verified on synthetic examples. Calculate relative rotation against neutral before extracting yaw/pitch. Label generic-model/intrinsics assumptions. If the method is unstable at profile/occlusion, return missing intervals or descriptive movement instead of degrees. Do not claim canonical face geometry is measured anatomy.
9. Mouth measurements: use the detector to find candidate opening frames and oral regions. Reviewer places/accepts upper and lower incisor endpoints when visible. Without teeth, store only the separate lip-aperture metric. Record the largest observed usable opening as such; do not assume it is the person's physiological maximum.
10. Persist analysis atomically, including errors and no-evidence outputs. Cache by source hash, model hash, analysis config, transform version, and algorithm version. Reviewer changes create revisions and recompute dependencies; they must not overwrite the original run.

## 7. Stage E — storage, review, rules, and exports

Use a small modular application:

```text
app.py
airway/
  cli.py               # inventory, batch analysis, audit
  db.py                # SQLite schema and migrations
  ingest.py            # originals, hashes, assignments
  video.py             # decode, PTS, orientation, frames
  geometry.py          # coordinate transforms and calibration
  landmarks.py         # local detector adapter
  quality.py           # technical quality flags
  measurements.py      # pure, unit-aware calculations
  rules.py             # eligibility gates and deterministic templates
  review.py            # revisions and invalidation
  reports.py           # HTML/JSON/CSV
  ui/                  # Streamlit workflow and landmark editor
registry/
models/                # local assets, excluded from Git as appropriate
tests/
scripts/setup.ps1
start.ps1
start.bat
README.md
VALIDATION_REPORT.md
```

SQLite entities: participants, assignment revisions, cases, videos, segments, evidence frames, analysis runs, landmark proposals, review revisions, calibrations, measurements, and report snapshots. Enable foreign keys. Keep large arrays/frames in case storage with DB references and hashes. Persistent state belongs in SQLite/files, not only Streamlit session state.

Each measurement must include: metric/protocol/rule IDs and versions; participant/case/video/run IDs; source hash; frame ID and exact timestamp or interval; neutral/reference frame IDs; value or null; unit; coordinate space; method; endpoint evidence; calibration ID or null; quality flags; state; reason codes; proposal ID; review revision; reviewer and time. Angles additionally record axis convention and view assumptions. Prohibit NaN/Infinity in JSON.

The four states are:

- `available`: supported and accepted under its stated method; an available exploratory pixel/angle metric still may not be eligible for any clinical rule.
- `needs_review`: a usable proposal or disputed correction awaiting review; no accepted clinical indicator.
- `unavailable`: absent maneuver, missing calibration/endpoints, unsuitable view, unreadable video, unknown protocol, or inadequate detail.
- `not_applicable`: structurally outside the intended assessment, such as external-video C–L/POGO. Do not use this to hide missing evidence.

Implement the rule gate in this order: metric state and review acceptance; protocol match; required anatomy/quality; supported units; calibration/geometry if physical units; rule activation/version; exact comparison. Evaluate using full stored precision, then round for display. A failed gate emits its missing-evidence explanation, never a normal finding.

Deterministic example templates:

- “Interincisor separation: {value} pixels at {time}. No valid physical reference is available, so centimetre thresholds were not evaluated.”
- “Mallampati classification unavailable: {specific_missing_evidence}.”
- “Apparent lateral head-line excursion: {value} degrees relative to {neutral_time}; {torso_status}. This measurement does not implement the presentation's AO protocol.”
- “Reviewed interincisor opening is below the source's difficult-laryngoscopy reference under protocol {id}. This is an observed indicator, not an overall intubation prediction.”

Reports show observed accepted indicators, exploratory observations, pending review, unavailable evidence with reasons, and the fixed overall limitation. Show completeness as named counts over a displayed registry-defined applicable set, not a risk score. Always list missing clinically relevant metrics. Do not let a narrower denominator imply a clinically complete assessment.

UI workflow:

1. Dataset inventory and assignment queue, with unresolved items visible.
2. Create/open participant case; upload or import local videos and label view/maneuver/side.
3. Analyze with per-clip progress, cancellation, retry, and persistent results.
4. Review original frames beside overlays; scrub/select time; choose neutral/extrema; edit points; accept/reject proposals; mark anatomy invisible; grade only evidenced maneuvers.
5. Generate report from a committed review revision; download printable self-contained HTML, structured JSON, and flat CSV.
6. Delete a chosen case's managed files and records after an explicit in-app confirmation. Preserve source Downloads files and participant originals referenced by other cases. Offer participant deletion separately and remove all managed media/derivatives/DB rows for that participant only after clear confirmation.

Use a maintained Streamlit-compatible point editor or a minimal local Streamlit component. Include numeric coordinate entry as a reliable fallback; do not make the core review workflow depend on an abandoned canvas package. Every click must be tested through crop/resize/rotation mappings.

Reports must embed evidence thumbnails locally, label source UUID/hash/time and method, escape user text, and contain no external resources or absolute original file paths by default. CSV should include null values/states/reasons rather than dropping unavailable metrics; guard spreadsheet formula injection in user-entered cells. Report generation should be idempotent for a fixed analysis/review/rule snapshot, apart from separately recorded export time.

The deletion service must resolve and check every target under managed storage, refuse source directories and path escapes, cancel work on deleted cases, invalidate caches, and prevent jobs from recreating deleted files. Explain that browser-downloaded/exported copies outside managed storage are not automatically removed.

## 8. Acceptance tests and evidence required

Use pytest for geometry, state transitions, rules, and integration. Use synthetic geometry and non-identifying fixtures for most tests. Keep original participant media and screenshots out of Git. Browser checks must interact with the real app, not just import its modules.

| Test | Required result |
|---|---|
| Inventory accounting | All 320 original paths accounted for once; successes, partial decodes, and failures sum to the total. Original bytes/hashes unchanged. Confirmed participant count comes from reviewed mapping. |
| Grouping | No automatic confirmation from adjacency or equal group size. Missing/repeated views supported. Unassigned/disputed clips cannot enter a combined participant report. Conflicting imported mappings are surfaced. |
| Source preservation | Managed copy hashes equal source hashes; analysis, review, export, and deletion do not modify any source hash. |
| Coordinates | Synthetic rotations 0/90/180/270, crop, letterbox, and resize round-trip selected points within 0.5 source pixel. Display resizing does not alter measurements. |
| Scale | Uniform synthetic resize preserves dimensionless ratios within 1%; source pixel distances behave according to the documented space. A pixel or dimensionless value cannot enter a centimetre comparator. |
| Motion preservation | Synthetic 0/10/20-degree head rotation remains 0/10/20 within 1 degree after fixed orientation correction; independently introduced camera roll is removed only using its reference. Background stabilization preserves independently moving head points. |
| Torso/camera ambiguity | Shared head/torso motion differs from head-relative-to-torso motion. Without suitable torso/camera references, output carries the corresponding limitation. |
| Missing evidence | Missing maneuver, obscured teeth, unclear uvula, no neutral frame, absent calibration, missing hyoid/thyroid endpoints, profile detector failure, multiple faces, and corrupt files produce explicit missing/needs-review states. |
| Boundary logic | For the approved `<3 cm` test rule: 2.99 matches, 3.00 and 3.01 do not. For `>5 cm` normal reference: 5.00 does not meet it, 5.01 does. Neither 3–5 cm nor any missing value becomes a blanket easy/difficult finding. |
| Distinct outcomes | LMA `<2 cm` rule never emits an intubation conclusion. C–L/POGO cannot be generated from external clips. AO protocols stay separate. |
| Review reproducibility | Point/frame/neutral/calibration/protocol changes invalidate dependent measurements and explanations. Prior automated proposals and prior reports remain attributable to their original revisions. Same snapshot reproduces the same values/reasons. |
| Temporal processing | Variable-frame-rate PTS retained; no tracking state reused across clips/cuts; missing intervals stay missing. Sample rate and extrema selection are disclosed. |
| Export | HTML prints legibly offline; JSON parses with explicit nulls; CSV preserves all metric states; all referenced frames and timestamps exist and match case identity. |
| Persistence/local mode | App restart restores accepted review; analysis works with network disabled after setup; missing model offers clear recovery; no media is sent externally. |
| Deletion | Test case and managed artifacts disappear, other cases remain, outside-root deletion is refused, and originals remain unchanged. Cancellation does not recreate deleted records. |

Test tolerances above are software-test tolerances on synthetic fixtures, not evidence of clinical measurement accuracy.

Run the technical decode/analysis audit on all 320 videos. Run full measurement/review/export flow on at least one owner-confirmed participant with all three view types, plus supported failure examples from the inventory. If no mapping is available, complete single-clip and synthetic tests, identify the grouping acceptance test as blocked, and do not claim patient-level validation.

Browser acceptance sequence: start locally; create case; upload actual approved clips through the upload control; assign views; analyze; inspect traceable frames; change a landmark and neutral frame; assign or explicitly mark unavailable a reviewer-only metric; save; reload; generate and open HTML/JSON/CSV; delete the test case; verify disappearance and source preservation. Also exercise import from the managed dataset and cancel deletion once. Record versions, files used, timestamps, screenshots kept locally, pass/fail results, and unresolved issues in `VALIDATION_REPORT.md`.

## 9. Delivery order and completion gates

1. **Environment and dataset audit:** dependency/model manifest, full decode audit, originals preserved.
2. **Grouping workflow:** owner-mapping import and review UI; verified folders; unresolved list. Continue independent implementation while awaiting mapping.
3. **Registry:** all named metrics represented; source differences documented; inactive rules explicit; boundary/unit tests passing.
4. **Single-clip pipeline:** orientation, quality, proposals, source-frame traceability, motion estimates, safe missingness.
5. **Review and persistence:** point editor, maneuver grading, revisions, deterministic recomputation.
6. **Case report/export/deletion:** complete workflow and local launch scripts.
7. **Batch and browser verification:** 320-file audit, all three views, failure cases, true browser acceptance, final validation report.

Do not let one unsupported metric block the application; implement its explicit unavailable state and evidence requirement. Do not declare completion solely because Streamlit starts or unit tests pass. Report software completion separately from unresolved participant assignments and scientific validation.

Windows delivery: `scripts/setup.ps1` creates/validates the environment and downloads pinned assets explicitly; `start.ps1` and `start.bat` start Streamlit bound to `127.0.0.1`, disable usage telemetry, use paths relative to the project, and provide actionable missing-dependency messages. No recurring network setup on launch. Document storage location, backup/export, local deletion behavior, and recovery from interrupted analysis. Add `.gitignore` rules for data, originals, models, source extracts, reports, and identifying QA artifacts as appropriate.

## 10. Later research gate, outside this build

To study overall intubation difficulty later, first define the endpoint and obtain linked clinician measurements and procedural outcomes, including device/technique, operator, attempts, aids, and laryngeal view as an outcome rather than an externally inferred predictor. Separate difficult visualization from tube placement and other airway outcomes. Establish reference-measurement agreement and inter-reviewer reliability before training.

Use participant-independent splits/resampling, with every clip/frame/visit and derivative from a participant kept in one partition. Evaluate phone/site/lighting shifts, missingness, outcome imbalance, calibration, and uncertainty. Select sample size and model complexity from the intended study and event counts, not the number of frames. Do not import the supplied paper's reported accuracy as a target achieved by this software.

## 11. Sources for implementation decisions

- Supplied presentation, especially slides 3–5, 7–11, and 13–16. Embedded-image inspection is necessary: the opening adverse thresholds are in slide 4's image.
- Supplied paper: PDF pp.2–3 for cohort/definitions and p.4 for evaluation method; DOI [10.18678/dtfd.862467](https://doi.org/10.18678/dtfd.862467).
- [OpenCV camera calibration](https://docs.opencv.org/4.13.0/d4/d94/tutorial_camera_calibration.html): intrinsics/distortion and calibration prerequisites.
- [OpenCV estimateAffinePartial2D](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html): restricted affine transformation with translation, rotation, uniform scale. The separation between display alignment and measurement is a design requirement of this plan.
- [MediaPipe Face Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python): local model, video timestamps, optional facial transformation matrices. It does not establish clinical landmark validity or physical scale.
- [Cochrane diagnostic-test review](https://doi.org/10.1002/14651858.CD008874.pub2): bedside tests have variable, limited screening sensitivity; supports avoiding a guaranteed overall prediction from a small set of video observations.

## 12. Handoff instruction

Implement this plan in the current workspace, starting with the technical inventory and owner-confirmed patient-assignment workflow. Use `planning/video_inventory.csv` as the initial source manifest and revalidate it. Preserve all original files. Build the complete local app, tests, reports, deletion flow, and Windows startup scripts. Make routine engineering choices without repeatedly requesting approval. Request only genuinely missing participant mappings or clinical rubric decisions; keep independent implementation moving. Never substitute facial identity matching, guessed scale, hidden landmarks, or invented outcomes for missing evidence. Finish with exact startup instructions, validation evidence, unresolved assignments, inactive rules, and a candid statement of what was and was not tested.
