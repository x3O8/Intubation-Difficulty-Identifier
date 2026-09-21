# Pretrained face-landmark research MVP

Prepared: 20 September 2026. This is a new implementation plan, not a claim that the planned analysis is already running.

## 1. Deliverable

Build a small Windows-local Streamlit application that accepts a video, runs an existing face-landmark model, displays an overlay, calculates supported geometric observations, and exports results. No training, fine-tuning, outcome prediction, or participant identity inference is required.

The main workflow is **select clip → select view/maneuver → analyze → inspect overlay and select neutral interval → export**. Individual clips can be processed without participant grouping. Optional participant labels must come from the owner; no automated matching.

Retain the existing source files and inventory. Keep new work separate from the original implementation plan. Unsupported metrics are omitted from the main results and listed under a collapsed “Skipped metrics” section with a short reason. The report retains: “Insufficient evidence to estimate overall intubation difficulty.” This is a scope statement, not an analysis error. Keep it as a compact research-scope notice rather than a dominant red error panel.

## 2. Existing model

Use **Google MediaPipe Tasks Face Landmarker**, running locally in VIDEO mode. It provides a dense face mesh and optional facial transformation matrices. Download its official pretrained task bundle once during setup, record its origin and SHA-256, and use the local file thereafter. No additional model-approval step is needed for this implementation plan; respect the model's published license and document it.

Start with the installed Python 3.12 / MediaPipe 0.10.20 stack if the model smoke test succeeds. Pin the combination actually tested. The existing model manifest currently has no model asset or hash; installing the Python package alone is insufficient.

Use `num_faces=2` to identify detected multi-face frames and skip them. Do not assume this setting supplies built-in smoothing or proves only one person exists. Store raw output and implement any temporal smoothing explicitly.

Official references:

- [Face Landmarker overview and pretrained models](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
- [Python VIDEO-mode setup and output API](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python)

## 3. Metrics included

These are exploratory video measurements. Availability is decided per frame/interval; a successful model detection alone does not establish anatomical visibility.

| Metric | Calculation | Conditions and output |
|---|---|---|
| Visible inner-lip aperture | Euclidean distance between upper and lower inner-lip midpoint landmarks | Source pixels; only use frames where both edges are visibly plausible. Describe the largest supported observed opening, not physiological maximum mouth opening. |
| Mouth width | Euclidean distance between left and right mouth-corner landmarks | Source pixels; a supporting geometric measurement. |
| Lip-aperture / mouth-width ratio | Aperture divided by mouth width in the same frame | Dimensionless; reviewed near-frontal frames only. Mouth width itself changes with expression, so this is an opening-shape descriptor. |
| Lip-aperture / outer-eye-corner span | Aperture divided by visible outer-canthal span in the same frame | Dimensionless; reviewed near-frontal frames with both eye corners usable. Skip profile, substantial yaw, and occlusion. |
| Relative head yaw, pitch, roll | Relative rotation from the model's facial transformation matrices against a selected neutral interval | Exploratory degrees in the camera coordinate system, conditional on stable valid pose. Report camera/torso ambiguity. Do not label as isolated neck or atlanto-occipital range of motion. |
| Tracking coverage | Valid analyzed frames divided by sampled frames, with counts and gap locations | Technical quality, not clinical risk or landmark accuracy. |

Verify landmark IDs against the installed model topology and overlays before use; keep a small versioned semantic mapping file. Normalize x/y back to orientation-corrected source pixels before calculating distances. Do not calculate distances directly between normalized x/y coordinates when image width and height differ.

For head pose, extract the rotation block, remove scale/shear using SVD with determinant correction, and document matrix direction, axes, handedness, and Euler order. Calculate relative rotations before extracting angles. A neutral frame selection must lie inside a valid continuous interval. Reject unstable matrices and implausible discontinuities. Lateral clips may fail pose tracking; if they do, skip the angle output for that interval. Do not infer hidden points to rescue a metric.

Summaries include neutral-relative extrema and a robust excursion (for example the 95th minus 5th percentile) within a reviewer-selected maneuver interval. Label the chosen summary and sampled frequency explicitly. Preserve raw series and raw extrema separately; do not bridge tracking gaps or present a lone spike as movement range.

## 4. Metrics skipped in this MVP

| Requested clinical metric | Reason to skip |
|---|---|
| Interincisor distance | The face model does not identify actual incisal edges. Lip distance is a different measurement. |
| Modified Mallampati | Requires internal oral structures and the examination protocol; ordinary external face landmarks cannot provide the grade. |
| Upper-lip bite class / incisor-based jaw protrusion | Requires actual visible tooth-to-lip or tooth-to-tooth relationships. Face mesh output does not provide these endpoints. |
| Thyromental, hyomental, sternomental distances | Required neck landmarks are outside the supported face mesh and physical scale is absent. |
| Bony mandibular length, bigonial width, neck length | Surface face landmarks do not establish the exact bony/neck endpoints. |
| Neck/head circumference, thyroid-to-floor-of-mouth distance, condylar movement | The required examination or geometry is not supplied by this model. |
| Clinical AO measurements and cutoffs | Their source protocols differ from camera-relative model pose. |
| Cormack–Lehane and POGO | External video does not show the required laryngeal view. |
| All centimetre thresholds | The supplied videos have no established valid physical calibration. No assumed face-size or model-depth conversion. |

Do not add manual clinical grading, tooth detection, calibration UI, another model, or custom training to the first release. Those are separate potential extensions if appropriate new evidence becomes available.

## 5. Processing pipeline

1. Read one selected source clip, preserve its hash, and decode using PyAV. Retain actual frame PTS/time base, dimensions, and orientation metadata, including display-matrix rotation where present.
2. Apply metadata orientation exactly once. Maintain explicit encoded-to-source and source-to-detector/display transforms. No per-frame face leveling in measurement space.
3. Sample at a default 10 Hz using real timestamps; disclose analyzed frame count. Offer a higher sample-rate rerun of a selected interval. Do not claim unsampled frames were assessed.
4. Run the local pretrained detector on RGB frames. Start a new VIDEO instance for each clip and after cuts, tracking interruptions, or non-monotonic timestamp/seek events. Record dropped duplicate millisecond timestamps rather than inventing timing.
5. Save landmark coordinates, transformation matrices, face count, frame time, model hash, configuration, and algorithm version. Model-inferred z is retained only as model output and is never a physical distance.
6. Mark suspect intervals using missing detection, multiple faces, out-of-frame endpoints, poor image quality, jumps, and unsuitable view. A reviewer can exclude intervals when an overlay fails. Detection thresholds are technical settings and do not become per-landmark confidence or clinical accuracy.
7. Compute lip geometry on eligible frames. Compute pose only on stable intervals with a selected neutral baseline. Missing outputs remain null with reason codes.
8. Display overlays, trajectory charts, peak candidate frames, and technical coverage. The reviewer selects/adjusts neutral and maneuver intervals and accepts or rejects outputs.
9. Export per-frame CSV, summary JSON, and a compact self-contained HTML report with selected local thumbnails and source UUID/hash/timestamps. Escape text and guard spreadsheet formula injection.

For reliable comparisons, the MVP asks the reviewer whether the camera remained fixed. If camera motion is evident or uncertain, skip quantitative pose excursion or mark it for review. Background stabilization and torso tracking are deferred.

## 6. Minimal application changes

Reuse the existing Python environment, inventory, source-hash functions, SQLite storage, and Streamlit shell. Add actual model execution before describing results as automated analysis: the current “Create evidence proposals” action inserts predefined evidence states and does not invoke the detector.

- `airway/landmarks.py`: local asset loading, timestamps, resets, and serializable raw results.
- `airway/video.py` and `geometry.py`: PTS-preserving sampling and verified orientation/resize mappings.
- New `airway/analysis.py`: real per-clip inference, progress, cancellation between frames, cache key, and derived trajectories.
- `airway/measurements.py`: lip distances, ratios, and neutral-relative pose summaries.
- `airway/quality.py`: conservative technical masks and skip reasons.
- `app.py` / `airway/ui/`: video playback, landmark overlays, timeline, view/maneuver selector, neutral/interval selection, and results/export.
- `airway/review.py` / `reports.py`: preserve raw runs and reviewed selection revisions; invalidate dependent summaries on edits; trace every result to its clip and interval.
- `models/manifest.json`: official asset URL/version/license/hash and verified load status.
- `registry/metrics.v1.yaml`: active exploratory metrics and explicit skipped clinical metrics; no active clinical threshold rules.

Keep large per-frame arrays in managed case storage with hashes and database references. A cache key includes source hash, model hash, sampling, transforms, and algorithm version. Recompute reviewed summaries separately so changing neutral time does not overwrite model proposals.

Use one clip per analysis job; a simple progress display, cancel flag, and retry are sufficient. Local file selection from the existing inventory is the primary input. Optional uploads copy into managed storage. Downloading the model is setup-only; analysis has no external requests. Delete only contained managed artifacts and prevent cancelled/deleted jobs from writing further output.

## 7. Work sequence and acceptance

1. **Model smoke test:** download/document the asset, load it locally, run one clip, and visually verify selected lip/eye landmark labels and mesh alignment. If tracking is unusable, document the failure before expanding the scope.
2. **Geometry and metrics:** implement pixel/ratio calculations and relative pose; test non-square image scaling, rotation/crop round trips, synthetic rotations, invalid matrices, missing frames, and duplicate timestamps. Synthetic tests validate code geometry, not human measurement accuracy.
3. **Usable review flow:** select a clip, label its view/maneuver, run inference, inspect overlays, select neutral/maneuver intervals, exclude a bad interval, export, reload, and verify results persist.
4. **Representative video checks:** inspect frontal and lateral examples, closed/open-mouth examples if actually present, and clips with blur/occlusion. Never fabricate a maneuver to satisfy a test. Use synthetic corrupt/multiple-face/timestamp fixtures where appropriate.
5. **Collection run:** batch all 320 clips independently, saving success/partial/failure, tracking coverage, and per-metric availability. Unknown views produce proposals pending review; no automated participant grouping. Recheck source hashes.
6. **Delivery:** create `VALIDATION_REPORT.md` with actual environment/model hashes, tests, browser evidence, inference counts, skipped metrics, and known failure modes. Include several manually annotated frames to quantify landmark/derived-distance error in source pixels or dimensionless units, with sample size and limitations; no fabricated accuracy target.

The MVP is complete when real model inference produces reviewable overlays and supported measurements for at least one usable clip, correctly skips unsupported evidence, and the local review/export/reload/delete flow is verified. Completion is not contingent on calculating every original clinical metric or obtaining participant mappings. Claims about performance across the collection must be backed by the collection run.

## 8. Deliberately outside this release

Custom model training; intubation risk classification; combined severity scores; biometric matching; synthetic 3-D reconstruction across asynchronous clips; teeth/oral grading models; physical calibration workflows; neck/torso models; background stabilization; elaborate participant merge/split administration; cloud deployment.

The result is a practical pretrained-model research tool for facial geometry and apparent head movement, with a small and explicit set of measurements that can actually be inspected in the source video.
