import json
from pathlib import Path

import streamlit as st

from airway.protocol import VIDEO_ROLES, create_video_case, thyromental_result, save_thyromental
from airway.research import latest_run, load_frames, query
from airway.ui.components import click_landmark_pair


def intake(db):
    with st.expander('New patient · upload three videos'):
        st.write('Keep the camera fixed, include the head, neck and shoulders, and begin each recording in a neutral position. Move slowly and pause at each comfortable endpoint. Do not force movement.')
        st.caption('For thyromental distance, include a mouth-closed extension hold in the side video. The mentum and thyroid notch must be identifiable, with a known-size reference in the same measurement plane. A reviewer must verify these requirements.')
        with st.form('three_video_intake', clear_on_submit=True):
            label = st.text_input('Patient case label (use a study ID)')
            uploads = [st.file_uploader(role, type=['mp4', 'mov', 'avi', 'mkv', 'webm'], key=f'upload_{index}') for index, role in enumerate(VIDEO_ROLES)]
            reviewer = st.text_input('Uploaded and assigned by')
            confirmed = st.checkbox('I confirm these three recordings belong to the same patient and match the labelled views')
            submitted = st.form_submit_button('Create three-video case')
        if submitted:
            try:
                with st.spinner('Checking all three recordings…'):
                    cid = create_video_case(db, uploads, label, reviewer, confirmed)
                st.session_state['research_case'] = cid
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def assigned_role(db, case_id, video_id):
    rows = query(db, 'SELECT reason FROM segments WHERE case_id=? AND video_id=?', (case_id, video_id))
    for row in rows:
        try:
            role = json.loads(row['reason'])['role']
            if role in VIDEO_ROLES:
                return role
        except (TypeError, ValueError, KeyError):
            pass
    return 'Unassigned'


def thyromental_panel(db, cid, clips):
    st.subheader('Thyromental distance · chin to thyroid notch')
    st.write('The face model does not locate the thyroid notch. Select a side-view frame at full extension with the mouth closed, then mark and verify the endpoints. Without visible anatomy and a suitable scale, this measurement stays unavailable.')
    eligible = []
    for clip in clips:
        run = latest_run(db, cid, clip['id'])
        if run and run['state'] == 'completed':
            eligible.append((clip, run))
    if not eligible:
        st.info('Analyze the side video before recording thyromental evidence.')
        return
    selected = st.selectbox('Video containing the extended side view', range(len(eligible)), format_func=lambda i: eligible[i][0]['relative_path'], key='tmd_video'+cid)
    clip, run = eligible[selected]
    frames = [f for f in load_frames(db, run['id']) if f.get('source_frame_path') and Path(f['source_frame_path']).exists()]
    if not frames:
        st.info('No source frames are available.')
        return
    key = cid + run['id']
    index = st.select_slider('Mouth-closed extension frame', options=list(range(len(frames))), format_func=lambda i: f"{frames[i]['timestamp_ms']/1000:.2f} s", key='tmd_frame'+key)
    frame = frames[index]
    a, b = st.columns(2)
    with a:
        target = click_landmark_pair('tmd_target'+key+str(index), frame['source_frame_path'], frame['source_width'], frame['source_height'], 'A: bony mentum · B: thyroid notch')
    with b:
        reference = click_landmark_pair('tmd_reference'+key+str(index), frame['source_frame_path'], frame['source_width'], frame['source_height'], 'A and B: ends of known-size reference')
    with st.form('tmd_form'+key+str(index)):
        size = st.number_input('Reference length (cm)', min_value=0.0, value=0.0)
        error = st.number_input('Thyromental estimated error ± (cm)', min_value=0.0, value=0.2)
        confirmations = {name: st.checkbox(label) for name, label in (
            ('mentum', 'Bony mentum endpoint verified'),
            ('thyroid_notch', 'Thyroid notch endpoint verified; not an assumed neck contour'),
            ('mouth_closed', 'Mouth is closed'),
            ('full_extension', 'Full comfortable extension is visible'),
            ('true_profile', 'True profile with measurement plane parallel to the image plane'),
            ('same_plane', 'Reference and anatomical endpoints are in the same plane and frame'))}
        reviewer = st.text_input('Thyromental reviewer')
        submit = st.form_submit_button('Save thyromental measurement')
    if submit:
        try:
            result = thyromental_result(frame, target+reference, size, error, reviewer, confirmations)
            save_thyromental(db, cid, clip['id'], run['id'], result)
            st.success(f"Reviewed image estimate: {result['value']:.2f} ± {error:.2f} cm")
        except ValueError as exc:
            st.error(str(exc))
