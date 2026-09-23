# Pretrained landmark MVP validation

Validated 20 September 2026 on Windows with Python 3.12, MediaPipe 0.10.20, PyAV 15.1.0, Streamlit 1.49.1, and NumPy 1.26.4.

## Implemented and verified

- Official MediaPipe Face Landmarker float16 task bundle loaded locally in VIDEO mode with two-face detection enabled. SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.
- Per-clip inference uses real PyAV presentation timestamps, a fresh tracker, display-matrix orientation applied once, and explicit duplicate-millisecond dropping.
- Raw 478-point landmarks, transformation matrices, face counts, technical quality, source dimensions, model/source hashes, configuration, and reason codes persist under `data/runs/<run UUID>`.
- Visible lip aperture, mouth width, aperture/mouth-width ratio, aperture/outer-eye-span ratio, and tracking coverage are calculated in orientation-corrected source pixels or dimensionless units.
- Pose rotation is projected to a proper rotation with SVD and determinant correction. Relative rotations are calculated before intrinsic ZYX Euler extraction; reported axes are camera-coordinate yaw, pitch, and roll.
- Reviewer-selected neutral/maneuver intervals, excluded spans, and camera-fixed status produce revision-preserving reviewed summaries. Pose is skipped unless camera fixation is confirmed.
- Unsupported clinical metrics persist as unavailable or not applicable with explicit reasons; Mallampati is deliberately excluded because it is handled by a separate owner-supplied model. No centimetre threshold or overall difficulty prediction is activated.

## Automated checks

`pytest -q`: **26 passed**. Tests include non-square transform round trips, crop/resize round trips, scale-invariant ratios, synthetic rotation recovery, invalid matrices, state rules, safe paths, assignment rules, and fixed scope wording.

## Real-video smoke test

- Obscured lateral clip `39a36d…a475`: 66 frames sampled at 10 Hz, zero usable tracks. This is retained as an honest failure/skip example.
- Usable clip `d0701b…f1fa`: 74 frames sampled at 10 Hz, 57 valid single-face frames, tracking coverage **77.0%**, with gap timestamps stored.
- The usable run created source-pixel overlays with landmark IDs 13, 14, 61, 291, 33, and 263 and persisted raw and robust summaries.
- A neutral interval of 0–500 ms and maneuver interval of 0–7300 ms completed reviewed pose summarization on 57 frames. Example pitch robust excursion (P95–P05) was 6.40 camera-coordinate degrees. This validates software execution only; it is not a clinical movement-accuracy claim.

## Browser check

The live Streamlit application loaded at `127.0.0.1:8501`, showed the 320-clip inventory, the real pretrained-analysis action, the completed validation run, overlay selector, neutral/maneuver sliders, exclusion input, camera-fixed gate, and manual correction controls. No browser console errors or framework error overlay were observed.

## Remaining scientific gates

No manual ground-truth landmark annotations or derived-distance error study has been supplied, so landmark or measurement accuracy is not claimed. The full 320-clip collection run has not been performed. View suitability still requires reviewer judgment, especially for lateral pose, blur, occlusion, and near-frontal ratio eligibility. Camera-relative pose is not isolated neck or atlanto-occipital motion. Physical distances and clinical grades remain out of scope without the required anatomy, protocol, geometry, and calibration.
# Three-video workflow update — 2026-09-23

- Full regression suite: **47 passed**, with two existing protobuf deprecation warnings.
- New checks cover three distinct synthetic video uploads with real decoding, duplicate rejection, explicit patient confirmation, separate frontal mouth/motion review, reviewer-labelled flexion/extension, known-geometry thyromental calculation, missing-prerequisite rejection, persisted exports and stale-analysis invalidation.
- Browser inspection verified the three upload slots, thyromental source-frame controls and final-report unavailable state/download controls. Synthetic upload persistence was tested through the application backend; a complete upload-to-reviewed-patient-result browser run was not performed.
- No new clinical measurement accuracy, automatic thyroid-notch detection, or validated anatomical cervical range-of-motion result is established. No source patient videos were relabelled or accepted during verification.

## Pixel and ratio measurements — 2026-09-23

- Full regression suite: **61 passed**, with two existing protobuf deprecation warnings. Coverage includes all six static distances, scale-invariant ratios, signed two-frame jaw protrusion, reference/error gates, case isolation, persistence, exports and stale-source invalidation.
- Added reviewer-marked anatomical endpoints or explicitly labelled visible surface proxies for thyromental, hyomental, mandible length, bigonial width, thyroid-to-floor-of-mouth, sternomental and jaw protrusion measurements. No new patient measurements were saved during this verification.
- Official MediaPipe Pose Landmarker Heavy loaded and produced valid pose results on all eight sampled frames from the supplied side-view clip. This is an execution check, not an anatomical accuracy benchmark.
- Corrected profile angle geometry to use source-pixel coordinates on non-square frames. Historical affected profile results now require reanalysis/review.
- Browser inspection confirmed the Heavy selector, all seven metric choices, source-frame endpoint/reference controls and reviewer/error fields in the distances-and-ratios tab. Automated Streamlit checks cover saving a synthetic review and the jaw controls.
- The model does not identify the hyoid or internal floor of mouth. Such endpoints require external identification or an explicitly documented surface surrogate; otherwise the result remains unavailable. No SOTA accuracy or clinical neck range-of-motion claim is established.
