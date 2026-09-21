# Local model assets

The application never downloads models at runtime. Place an owner-approved official MediaPipe Face Landmarker task bundle at `models/face_landmarker.task`, then record its source URL, version, license, and SHA-256 in `models/manifest.json`. If absent, the app remains usable in review-only mode and reports the missing-model recovery path.

`pose_landmarker_lite.task` is the local fallback for profile flexion/extension endpoint selection. It uses the visible shoulder-to-nose image-plane line only; it does not estimate physical neck range of motion.
