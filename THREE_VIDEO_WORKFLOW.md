# Three-video measurement workflow

This product assesses what patient-recorded video can measure. It does not predict difficult intubation or assign an airway risk score. Mallampati remains outside this pipeline.

## Recording and intake

In Research workspace, expand **New patient · upload three videos**. Supply a study ID, one recording per slot, and confirmation of patient association. Files are stored locally and checked for complete decoding. Duplicate recordings are rejected. Patient identity is never inferred from faces or filenames.

| Recording | Intended evidence |
| --- | --- |
| Front, mouth open, looking up/down | Sustained visible mouth-opening frame; camera-relative head movement |
| Front, looking left/right | Left/right movement endpoint frames and camera-relative angular excursion |
| Side, looking up/down | Flexion/extension endpoint frames; profile image-plane motion; an eligible extended frame for thyromental review |

Keep the camera fixed and include the head, neck and shoulders. Begin in neutral, move slowly and pause at comfortable endpoints. Do not force movement. The side clip needs an additional mouth-closed extension hold for thyromental measurement. These are research capture instructions that require clinician review before patient deployment.

## Peak movement and mouth opening

Run **Analyze all case videos**, then review each assigned view and neutral/movement interval. The frontal mouth-open clip has separate mouth and motion evidence gates. The profile shoulder-to-nose fallback is disabled for the explicit frontal slots.

Motion endpoints come from a five-sample median-smoothed signal. The report retains endpoint timestamps, signed deviations from neutral, and total excursion. Inspect those frames and verify which sign represents flexion; saving again adds separate observed flexion and extension magnitudes when that direction extends beyond neutral. Sign alone never establishes anatomical direction. A missing direction is not a zero measurement. Mouth opening uses a sustained aperture candidate, with all reported distances from the same frame.

These are camera-relative or profile shoulder-to-nose angles, not validated cervical range of motion. Torso movement, perspective and landmark errors may affect them. A validated head-versus-torso protocol and paired clinician measurements are needed to establish anatomical neck-angle accuracy.

## Thyromental distance

In **Distance references**, select an extended side-view source frame and mark:

1. Bony mentum and thyroid notch.
2. Both endpoints of a reference with a known length.

Verify mouth closure, extension, true profile, endpoint identity and same-plane geometry. Enter the reference length, estimated measurement error and reviewer name. The result is `anatomical pixel separation × reference centimetres / reference pixel separation`. Save as a **reviewed image estimate**, with coordinates, timestamp, frame, run, source hash and stated error bound.

The generic face/pose models do not identify the thyroid notch. If it cannot be identified reliably, or if reference geometry is unsuitable, leave the result unavailable. Assumed face size and model depth cannot substitute for a scale. A scale beside the patient at a different depth does not establish valid calibration. The uncertainty supplied by a reviewer is not an empirically measured confidence interval.

The anatomical measurement protocol is supported by [this prospective study](https://pmc.ncbi.nlm.nih.gov/articles/PMC6748003/), which measures mentum to thyroid notch with full extension and the mouth closed. This does not validate the software's image measurement method.

## Reports and validation

HTML, JSON and CSV include thyromental results or their unavailable reason. Reanalyzing the source video makes old thyromental evidence stale until reviewed against the new run. Existing case files and reviews are preserved.

This is a local research prototype, not a deployed patient submission portal. Existing optional interincisor reference comparison remains separate from the new thyromental measurement; no thyromental threshold or risk score was added.

The next scientific gate is paired same-session video and anaesthetist measurements: quantify endpoint-selection error, distance/angle error, observer agreement and failure rates on independent patients. No clinical accuracy is claimed by software tests.
