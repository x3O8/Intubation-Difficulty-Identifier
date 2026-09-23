"""Pixel and ratio review using full-resolution source-frame coordinates."""
from pathlib import Path

import streamlit as st

from airway.anthropometry import METRICS, BASES, save_review, surface_suggestion
from airway.research import latest_run, load_frames
from airway.ui.components import click_landmark_pair
from airway.ui.protocol_workspace import assigned_role
from airway.protocol import VIDEO_ROLES


def findings_panel(reviews):
    st.subheader('Pixel distances and experimental ratios')
    for result in reviews:
        with st.expander(result['label'] + ' · ' + result['state'].replace('_', ' ')):
            if result.get('reason'):
                st.caption(result['reason'])
            if result.get('file'):
                st.caption(result['file'] + ' · reviewer: ' + result.get('reviewer', ''))
            for finding in result.get('findings', []):
                st.write(f"**{finding['value']:.3f} {finding['unit']}** · {finding['label']}")
                if finding.get('range'):
                    st.caption(f"Placement-error range: {finding['range'][0]:.3f} to {finding['range'][1]:.3f} {finding['unit']}")
            if result.get('notes'):
                st.write(result['notes'])
            if result.get('formula'):
                st.caption(result['formula'])
            if result.get('limitation'):
                st.caption(result['limitation'])
            for evidence in result.get('evidence_images', []):
                st.image(evidence['data_uri'], caption=f"Reviewed points at {evidence['timestamp_ms']/1000:.3f} s", width=360)


def measurement_panel(db, cid, clips):
    st.subheader('Measure distances in pixels or as ratios')
    st.write('Choose source frames and mark the endpoints. A ratio divides the distance by a named reference in the same frame. No ruler is required for pixels or ratios.')
    metric = st.selectbox('Research measurement', list(METRICS), format_func=lambda k: METRICS[k][0], key='anthro_metric'+cid)
    name, point_a, point_b, required_view, posture = METRICS[metric]
    st.caption(f'{required_view} view · {posture}. A: {point_a}; B: {point_b}.')
    if metric in ('hyomental_pixels', 'thyroid_floor_pixels', 'thyromental_pixels'):
        st.info('An internal landmark cannot be recovered from a skin outline. Use an externally identified/marked point, or explicitly describe a visible surface surrogate. If neither can be identified, record unavailable.')
    eligible = [(c, latest_run(db, cid, c['id'])) for c in clips]
    eligible = [(c, r) for c, r in eligible if r and r['state'] == 'completed']
    if not eligible:
        st.info('Analyze a video to obtain source frames.'); return
    default_video = 0
    if metric == 'jaw_protrusion':
        side_indices = [i for i, (c, _) in enumerate(eligible) if assigned_role(db, cid, c['id']) == VIDEO_ROLES[2]]
        if side_indices:
            default_video = side_indices[0]
        st.info('Use the side-view video for jaw protrusion. Compare a neutral jaw with an actively forward-protruded jaw while the head stays in the same posture. Looking up and down alone does not demonstrate jaw protrusion.')
        if not side_indices:
            st.caption('No analyzed clip is assigned to the side-view slot. Select and verify a suitable profile clip below.')
    index = st.selectbox('Source video', range(len(eligible)), index=default_video, format_func=lambda i: eligible[i][0]['relative_path'], key='anthro_video_side_default'+cid+metric)
    clip, run = eligible[index]
    frames = [f for f in load_frames(db, run['id']) if f.get('source_frame_path') and Path(f['source_frame_path']).exists()]
    if not frames:
        st.info('No source frames found.'); return
    key = cid + run['id'] + metric
    unavailable = st.checkbox('Record this measurement as unavailable', key='anthro_skip'+key)
    timestamps, targets, references = [], [], []
    basis = st.selectbox('Endpoint basis', BASES, index=1, key='anthro_basis'+key)
    view = st.selectbox('Observed view', ['Unconfirmed', 'Frontal', 'Profile'], key='anthro_view'+key)
    reference_label = ''
    paired = metric == 'jaw_protrusion'
    ratio = paired or st.checkbox('Also calculate a ratio', value=True, key='anthro_ratio'+key)
    if ratio:
        default = 'Tragus to lateral canthus' if required_view == 'Profile' else 'Outer-eye-corner span'
        reference_label = st.text_input('Reference endpoints (use the same definition in every case)', value=default, key='anthro_reference_name'+key)
        st.caption('Reference points must be visible in the same plane; a short or foreshortened reference makes the ratio unstable.')
    if paired:
        st.write('Select neutral and actively protruded jaw frames. In both frames, target A is the upper incisor/fixed upper-face point and B is the lower incisor/chin point. Reference A → B runs from a stable posterior upper-face anchor toward an anterior upper-face anchor. Keep head pose and view matched.')
    if not unavailable:
        for n in range(2 if paired else 1):
            caption = ('Neutral jaw frame' if n == 0 else 'Protruded jaw frame') if paired else 'Measurement frame'
            selected = st.select_slider(caption, options=list(range(len(frames))), format_func=lambda i: f"{frames[i]['timestamp_ms']/1000:.3f} s", key='anthro_frame'+key+str(n))
            frame = frames[selected]; timestamps.append(frame['timestamp_ms'])
            prefix = 'anthro_target'+key+str(n)+str(selected)
            side = st.selectbox('Jaw side for contour suggestion', ['Left', 'Right'], key='anthro_side'+prefix) if metric == 'mandible_length_pixels' else 'Left'
            suggestion = surface_suggestion(metric, frame, side)
            if suggestion and basis == BASES[1]:
                st.caption('The existing face mesh can suggest jaw-contour points. They are surface proxies, not detected bony gonions. Inspect and move each point before accepting.')
                if st.button('Start from face-contour suggestion', key='anthro_suggest'+prefix):
                    st.session_state[prefix+'_points'] = dict(zip(('Point A', 'Point B'), suggestion))
                    st.rerun()
            targets.append(click_landmark_pair(prefix, frame['source_frame_path'], frame['source_width'], frame['source_height'], f'{caption} · A: {point_a} · B: {point_b}'))
            if ratio:
                references.append(click_landmark_pair('anthro_ref'+key+str(n)+str(selected), frame['source_frame_path'], frame['source_width'], frame['source_height'], 'Reference: '+reference_label+(' · A posterior, B anterior' if paired else '')))
    with st.form('anthro_save'+key):
        error = st.number_input('Estimated radial error per clicked endpoint (source pixels)', min_value=0.1, value=3.0, step=0.5)
        notes = st.text_area('Endpoint identity, side, posture and approximation notes', help='Name any visible surrogate used for hyoid, floor of mouth or bony landmarks. Record posture and why the estimate is usable.')
        reason = st.text_input('Reason unavailable') if unavailable else ''
        verified = st.checkbox('I checked the points, reference, required view and posture on these source frames') if not unavailable else False
        maneuver = st.checkbox('I observed jaw protrusion between these frames; head pose and the upper-face reference are matched') if paired and not unavailable else False
        reviewer = st.text_input('Measurement reviewer')
        submitted = st.form_submit_button('Save pixel / ratio review')
    if submitted:
        try:
            if unavailable and not reason.strip():
                raise ValueError('Provide an unavailable reason.')
            result = save_review(db, cid, clip['id'], run['id'], dict(metric=metric, basis=basis, view=view,
                timestamps=timestamps, targets=targets, references=references, reference_label=reference_label,
                placement_error_px=error, reviewer=reviewer, notes=notes, verified=verified,
                maneuver_verified=maneuver, unavailable_reason=reason))
            st.success('Review saved with source points and evidence. See Final report.')
            for finding in result['findings']:
                st.write(f"{finding['label']}: {finding['value']:.3f} {finding['unit']}")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
