# Research MVP v2

Open the **Research workspace**. Existing cases and original files remain available.

1. Select a case and analyze all its videos in one batch.
2. Assign each video's role, inspect landmarks, choose a relevant interval, and save review.
3. For lateral footage with unreliable face tracking, use manual two-frame movement review. Enter the same visible head-line endpoints in source pixels. This measures apparent image-plane change only.
4. Optionally record interincisor opening measured directly or from verified incisor endpoints and a same-plane known-size reference. Record measurement evidence, reviewer, and error bound.
5. Open Final report and download HTML, JSON, or CSV. Downloads are rebuilt from the selected case and latest saved reviews on every rerun; filenames identify the snapshot.

## What changed

- Source frames are retained even when face detection fails, enabling manual review.
- Each completed rerun retires older active measurements for that clip. The new report only accepts reviews associated with the latest run, including when a later run fails.
- Full-case reporting includes missing and unprocessed videos. Tracking coverage alone no longer counts as reviewed evidence.
- Automatic review requires at least 10 usable frames, one second, and 70% usable coverage in the chosen interval. Mouth review checks frontal pose, endpoint scale, finite measurements, and extreme image quality. These are engineering defaults, not validated clinical limits.
- Mouth findings use a single representative frame nearest the 90th percentile aperture/mouth-width ratio; its distances and ratios retain the same timestamp. Isolated maxima are not used as the final finding.
- Different views, maneuvers, and pixel scales are no longer averaged into an artificial patient measurement. Each contributes appropriate evidence to one report.
- The arbitrary low/mid/high opening bands are absent from the new workspace. There is no learned relationship between those old bins and intubation outcomes.
- Saved reviews preserve reviewer, run, interval, quality policy, source hash, and selected source-frame images. Printable reports embed available evidence images.
- Distance comparison uses the historical ASA interincisor reference of <3 cm, attributed in each result. A reviewer-specified error range crossing the threshold yields indeterminate. A negative comparison does not imply easy intubation.

## Validation and remaining work

The three source videos from report-5ecfaf8de1d2.csv were rerun in an isolated database. Tracking reproduced 10.5%, 82.0%, and 9.3%; filtering found 2, 26, and 0 mouth-eligible frames respectively. Inspection showed a lateral movement view with unreliable facial landmark placement. This establishes a view/model mismatch and motivates manual lateral review; it does not establish improved automatic tracking accuracy.

Regression tests exercise sparse tracking, profile rejection, spike resistance, shared frame timestamps, threshold uncertainty, manual geometry, missing clips, stale runs, exports, and escaping. Streamlit application loading and browser navigation to the final report were checked.

This release improves evidence handling and reporting reliability. It has no independently measured landmark accuracy, distance error, or difficult-intubation predictive performance. Validate against reviewer-annotated landmarks, physical measurements, and patient-level outcome labels before claiming those capabilities. Separate patients across train/validation/test sets.

Threshold source: https://www.asahq.org/~/media/sites/asahq/files/public/resources/standards-guidelines/practice-guidelines-for-management-of-the-difficult-airway.pdf
