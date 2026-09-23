# Pixel distances and experimental ratios

The research workspace now includes **Distances and ratios**. The existing calibrated thyromental and interincisor workflows remain available below the new review panel.

| Measurement | Required source view and endpoints |
| --- | --- |
| Thyromental | Extended, mouth-closed profile: chin/mentum to superior thyroid notch |
| Hyomental | Profile: chin/mentum to an identified or externally marked hyoid point; record posture |
| Mandible length | Profile: mandibular angle to chin; record side and mouth-closed posture |
| Bigonial width | Neutral frontal view: both mandibular angles |
| Thyroid to floor of mouth | Profile: thyroid notch to a specifically defined floor-of-mouth endpoint or visible external surrogate |
| Sternomental | Extended, mouth-closed profile: upper manubrium to chin |
| Jaw protrusion | Neutral and actively protruded jaw frames from the same profile clip, with matched head pose |

No ruler is needed for a pixel or ratio result. A ruler is still needed for the separate calibrated centimetre workflow. Changing a unit to pixels does not reveal hidden anatomy: identify/mark the anatomical endpoint externally, specify a visible surface proxy, or record an unavailable reason. In particular, hyoid and floor-of-mouth anatomy cannot simply be inferred from a neck contour.

## Reviewing a distance

1. Analyze the source video, choose a measurement and source frame, and confirm the view.
2. Select the endpoint basis: externally identified anatomy or approximate visible surface proxies. Define every surrogate in the notes.
3. Click target endpoints A and B. Mandible length and bigonial width optionally provide **face-contour suggestions** from the existing MediaPipe mesh (IDs 152, 172 and 397). These are editable skin-contour hints, not detected bony gonions.
4. Optionally click a reference pair in the same frame, and name its endpoints. Suggested conventions are outer-eye-corner span for frontal images and tragus-to-lateral-canthus span for profile images. Verify visibility and suitable projection. Use the same definition and posture across cases; do not pool different references or views.
5. Enter the estimated **radial** placement error per endpoint, reviewer name and posture/endpoint notes. Review the annotated source evidence before using the result.

The pixel value is the Euclidean separation in the orientation-corrected source frame. The ratio is `target pixel separation / reference pixel separation`. For example, 100 pixels divided by a 50-pixel reference is 2.0. Uniform resizing preserves the ratio but camera perspective and out-of-plane motion can still change it.

The reported error range is based on reviewer-specified endpoint uncertainty. If each target point is within `e` pixels, distance is bounded by `max(0,d-2e)` and `d+2e`. A ratio range includes both target and reference error. This is not a statistical confidence interval or a measured accuracy claim.

## Jaw protrusion

This requires an actual protrusion maneuver; ordinary head rotation or flexion is insufficient. In both frames, mark upper and lower incisor endpoints for a dental estimate, or explicitly named upper-face/chin points for a surface proxy. Also mark two stable upper-face reference anchors in posterior-to-anterior order (for example, tragus then lateral canthus).

For each frame, project the lower-minus-upper endpoint vector along that frame's upper-face reference axis and divide by reference length. Subtract the neutral normalized offset from the protruded offset. Also report this change multiplied by the neutral reference length, labelled **neutral-frame pixel equivalent**. This compensates for in-plane translation, rotation and uniform scale; matched out-of-plane head pose still requires review. Negative values are retained and mean motion backward along the chosen reference axis. The surface proxy is not an upper-lip bite class or a clinical jaw-protrusion score.

## Models and coordinate correction

The app now offers **MediaPipe Pose Landmarker Heavy** alongside Lite. Heavy is selected first when installed locally. Install the pinned official bundle with:

```powershell
.\.venv\Scripts\python.exe scripts/install_pose_heavy.py
```

The installer checks SHA-256. Model name, hash and coordinate convention persist with each analysis; runtime inference remains offline. The downloaded Heavy bundle is excluded from Git by default.

Heavy is a larger body-pose model, not a new anatomical distance detector. The facial mesh still supplies editable surface-contour suggestions. Alternatives reviewed include [SPIGA](https://github.com/andresprados/SPIGA), [3DDFA-V3](https://github.com/wang-zidu/3DDFA-V3), and Google's [Face Landmarker model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf). Face-alignment benchmarks do not establish hyoid, thyroid-notch, gonion or airway-distance accuracy. No SOTA or superior anatomical accuracy claim is made for this tool. The new pose bundle is documented in Google's [official sample](https://github.com/google-ai-edge/mediapipe-samples-web/blob/main/src/tasks/pose-landmarker.ts).

Profile shoulder-to-nose angles now use **source pixel coordinates**, correcting a previous use of independently normalized x/y coordinates that distorted angles in non-square videos. Historical saved profile results are flagged for reanalysis rather than silently accepted. This correction and a model change may both change reported angles. They remain projected head-motion estimates, not isolated cervical range of motion.

## Traceability and exports

HTML contains annotated evidence frames, values, ranges, reference names, reviewer and limitations. JSON preserves source dimensions, point coordinates, timestamps, source/model hashes, configuration and formulas. CSV includes the coordinates, named reference, ranges and signed numeric values. Values are never averaged across views or pixel scales. Reanalysis, a failed replacement run, or a changed/missing source invalidates saved pixel findings. Missing measurements remain visible as unavailable, and video acceptance is counted separately from completed pixel measurements.
