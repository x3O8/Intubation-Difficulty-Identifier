from pathlib import Path

import pandas as pd
import streamlit as st

from airway.analysis import analyze_clip
from airway.landmarks import available_pose_models
from airway.ui.anthropometry_workspace import measurement_panel, findings_panel
from airway.ui.components import click_landmark_pair
from airway.ui.protocol_workspace import intake, assigned_role, thyromental_panel
from airway.research import (ROLES, VERSION, case_clips, case_report, distance_result,
    evaluate_clip, exports, latest_run, load_frames, query, save_distance, save_review, setup, manual_motion, label_flexion_extension)


def findings_dataframe(findings):
    """Render single-frame and endpoint-pair times as one Arrow-safe text column."""
    rows = []
    for finding in findings:
        row = dict(finding)
        timestamp = row.get('timestamp_ms')
        values = timestamp if isinstance(timestamp, (list, tuple)) else [timestamp]
        row['timestamp_ms'] = ', '.join(f'{value:g}' for value in values if value is not None)
        rows.append(row)
    return pd.DataFrame(rows)


def workspace(db):
    setup(db)
    st.header('Research workspace')
    st.caption('Select a case → analyze its videos → review the evidence → export your findings')
    intake(db)
    cases=query(db,'SELECT id,label FROM cases WHERE deleted_at IS NULL ORDER BY created_at DESC')
    if not cases:
        st.info('Upload the three recordings above, or create a case from your inventory.'); return
    cid=st.selectbox('Patient case',[c['id'] for c in cases],format_func=lambda i:next(c['label']+' · '+i[:8] for c in cases if c['id']==i),key='research_case')
    clips=case_clips(db,cid)
    report=case_report(db,cid)
    a,b,c=st.columns(3)
    a.metric('Videos in this case',len(clips));b.metric('Evidence accepted',f"{report['clips_accepted']} / {len(clips)}")
    c.metric('Thyromental distance','Reviewed estimate' if report['thyromental']['state']=='reviewed_estimate' else 'Unavailable')
    analyze,review,distances,final=st.tabs(['1 · Analyze videos','2 · Review evidence','3 · Distances and ratios','4 · Final report'])
    with analyze:
        st.subheader('Process the complete case')
        st.write('All selected videos are processed in one batch. Each keeps its own tracking history, camera view, and findings.')
        frequency=st.select_slider('Samples per second',options=[5,10,15,20],value=10,key=f'hz_{cid}')
        pose_models = available_pose_models()
        pose_choice = st.selectbox('Pose model', list(pose_models), key='pose_model'+cid)
        st.caption('Heavy is the larger pose model and uses more processing time. It tracks body landmarks; thyroid and hyoid endpoints still need review. Accuracy on this dataset has not been benchmarked.')
        if st.button('Analyze all case videos',type='primary',disabled=not clips,key=f'batch_{cid}'):
            progress=st.progress(0.0); failures=[]
            for index,clip in enumerate(clips):
                st.write(f"Analyzing video {index+1} of {len(clips)}")
                try:
                    analyze_clip(cid,clip['id'],sample_hz=frequency,db_path=db,
                                 pose_model_path=pose_models[pose_choice],
                                 progress=lambda p,i=index:progress.progress((i+p)/len(clips)))
                except Exception as exc:
                    failures.append(f"{clip['relative_path']}: {exc}")
                progress.progress((index+1)/len(clips))
            for failure in failures: st.error(failure)
            if not failures: st.success('Analysis complete. Open Review evidence to verify each clip.')
        for clip in clips:
            run=latest_run(db,cid,clip['id'])
            with st.container(border=True):
                st.write(clip['relative_path'])
                st.caption('Analysis: '+(run['state'] if run else 'Not started'))
                if run and run['state']=='completed':
                    frames=load_frames(db,run['id']); n=sum(bool(f.get('valid')) for f in frames); pose_n=sum(bool((f.get('profile_pose') or {}).get('valid')) for f in frames)
                    st.write(f"Face-mesh tracking: {n} / {len(frames)} sampled frames ({n/len(frames):.0%})" if frames else 'No timestamped frames decoded')
                    if frames: st.write(f"Profile-pose fallback: {pose_n} / {len(frames)} sampled frames ({pose_n/len(frames):.0%})")
                    if frames and n/len(frames)<.7: st.warning('Sparse tracking. Check orientation, face visibility, and the selected interval before accepting this video.')
    with review:
        st.subheader('Review each video in its own role')
        st.caption('Quality defaults: at least 10 usable frames, a 1-second interval, and 70% usable coverage. These are engineering settings awaiting measurement validation.')
        for index,clip in enumerate(clips):
            run=latest_run(db,cid,clip['id'])
            with st.expander(f"Video {index+1} · {clip['relative_path']}",expanded=index==0):
                if not run or run['state']!='completed':
                    st.info('Analyze this video first.');continue
                frames=load_frames(db,run['id'])
                if len(frames)<2:
                    st.error('Too few frames to review.');continue
                key=cid+run['id']
                images=[f for f in frames if f.get('overlay_path') and Path(f['overlay_path']).exists()]
                if images:
                    frame=st.select_slider('Inspect tracked frame',options=list(range(len(images))),format_func=lambda i:f"{images[i]['timestamp_ms']/1000:.2f} s",key='frame'+key)
                    st.image(images[frame]['overlay_path'],width=440)
                else: st.warning('No saved overlay is available. Inspect the original clip before confirming landmarks.')
                if st.checkbox('Show original video',key='play'+key): st.video(str(Path(clip['source_path']).resolve()))
                with st.form('review'+key):
                    role=st.selectbox('What does this video show?',ROLES,index=ROLES.index(assigned_role(db,cid,clip['id'])),key='role'+key)
                    lo,hi=float(frames[0]['timestamp_ms']/1000),float(frames[-1]['timestamp_ms']/1000)
                    interval=st.slider('Maneuver interval (seconds)',lo,hi,(lo,hi),key='interval'+key)
                    neutral=st.slider('Neutral interval for motion (seconds)',lo,hi,(lo,min(hi,lo+.5)),key='neutral'+key)
                    fixed=st.checkbox('The camera stays fixed during the motion',key='fixed'+key)
                    visible=st.checkbox('I checked the landmarks and the intended maneuver is visible',key='visible'+key)
                    direction=st.selectbox('Flexion / extension direction after inspecting endpoint frames',
                                           ['Not verified', 'Negative angle is flexion', 'Positive angle is flexion'],key='direction'+key)
                    st.caption('First save to see the proposed endpoints below, then verify direction and save again. These are observed head-motion angles; anatomical neck motion requires a validated head/torso protocol.')
                    reviewer=st.text_input('Reviewer',key='reviewer'+key)
                    submitted=st.form_submit_button('Check quality and save review',type='primary')
                if submitted:
                    try:
                        result=evaluate_clip(frames,role,*[x*1000 for x in interval],*[x*1000 for x in neutral],fixed,visible)
                        label_flexion_extension(result, None if direction=='Not verified' else direction=='Negative angle is flexion')
                        save_review(db,cid,clip['id'],run['id'],reviewer,result)
                        if result['state']=='accepted':st.success('Evidence accepted for this video.')
                        else:st.warning('Evidence needs attention: '+'; '.join(result['reasons']))
                    except Exception as exc: st.error(str(exc))
                saved=next(c for c in case_report(db,cid)['clips'] if c['video_id']==clip['id'])
                st.write('Current review: '+saved['state'])
                if saved.get('coverage') is not None:st.caption(f"Usable interval coverage: {saved['coverage']:.0%} · {saved['usable_frames']} frames")
                if saved.get('endpoint_window_coverage'):
                    st.caption('Peak-frame coverage: ' + ' · '.join(f"{window['coverage']:.0%} at {window['timestamp_ms']/1000:.2f}s" for window in saved['endpoint_window_coverage']['windows']))
                if any('Full-face landmark tracking is unavailable' in reason for reason in saved.get('reasons',[])):
                    st.info('This is a side-profile limitation of the full-face landmark model, not a failed flexion/extension maneuver. Use the reviewer-marked two-frame option below if the same visible head landmarks can be verified.')
                if saved['findings']: st.dataframe(findings_dataframe(saved['findings']),hide_index=True,use_container_width=True)
                if saved.get('peak_evidence'):
                    st.caption('Automatically selected maneuver endpoints — verify these frames before using the measurement.')
                    st.dataframe(pd.DataFrame(saved['peak_evidence']),hide_index=True,use_container_width=True)
                    peak_images = {image['timestamp_ms']: image['data_uri'] for image in saved.get('evidence_images', [])}
                    for point in saved['peak_evidence']:
                        if point['timestamp_ms'] in peak_images:
                            st.image(peak_images[point['timestamp_ms']],caption=f"{point['label']} · {point['timestamp_ms'] / 1000:.2f} s",width=300)
                sources=[f for f in frames if f.get('source_frame_path') and Path(f['source_frame_path']).exists()]
                if sources and st.checkbox('Use manual two-frame movement review',key='manual'+key):
                    st.caption('For lateral views with poor face tracking. Click the same two visible head landmarks in each image, in the same order. This produces an apparent image-plane change only; it is not isolated anatomical neck range of motion.')
                    n=st.selectbox('Neutral source frame',range(len(sources)),format_func=lambda i:f"{sources[i]['timestamp_ms']/1000:.2f} s",key='mn'+key)
                    p=st.selectbox('Movement source frame',range(len(sources)),format_func=lambda i:f"{sources[i]['timestamp_ms']/1000:.2f} s",key='mp'+key)
                    left,right=st.columns(2)
                    with left:
                        neutral_points=click_landmark_pair(f'{key}_neutral_{sources[n]["timestamp_ms"]}',sources[n]['source_frame_path'],sources[n]['source_width'],sources[n]['source_height'],'Neutral frame')
                    with right:
                        movement_points=click_landmark_pair(f'{key}_movement_{sources[p]["timestamp_ms"]}',sources[p]['source_frame_path'],sources[p]['source_width'],sources[p]['source_height'],'Peak-movement frame')
                    with st.form('manualform'+key):
                        verified=st.checkbox('Same visible landmarks, same order, no movement of the endpoints relative to the head')
                        camera_ok=st.checkbox('Fixed camera verified for these two frames')
                        author=st.text_input('Manual reviewer')
                        save=st.form_submit_button('Save manual movement evidence')
                    if save:
                        try:
                            points=neutral_points+movement_points
                            if any(point is None for point in points):
                                raise ValueError('Click Point A and Point B on both the neutral and peak-movement images.')
                            result=manual_motion(sources[n],sources[p],points,camera_ok,verified,role)
                            save_review(db,cid,clip['id'],run['id'],author,result)
                            st.success('Manual image-plane movement saved. See Final report.')
                        except ValueError as exc:st.error(str(exc))
    with distances:
        measurement_panel(db,cid,clips)
        st.divider()
        thyromental_panel(db,cid,clips)
        st.divider()
        st.subheader('Compare an interincisor measurement')
        st.write('Record the gap between upper and lower incisor edges at maximal opening. The reference comparison is below 3 cm. Lip landmarks cannot supply incisor endpoints.')
        st.caption('Use a direct measurement or a same-plane reference with reviewer-identified incisor endpoints. The uncertainty is your stated error bound.')
        method=st.radio('Measurement method',['Manual interincisor measurement','Calibrated incisor endpoints'],key='distance_method'+cid)
        with st.form('distance'+cid):
            if method.startswith('Manual'):
                value=st.number_input('Measured interincisor opening (cm)',min_value=0.0,max_value=20.0,value=0.0,step=.1)
                calibration=None
            else:
                target=st.number_input('Incisor endpoint separation (source pixels)',min_value=0.0,value=0.0)
                reference_px=st.number_input('Reference endpoint separation (same frame pixels)',min_value=0.0,value=0.0)
                reference_cm=st.number_input('Known reference size (cm)',min_value=0.0,value=0.0)
                same_plane=st.checkbox('Incisor and reference endpoints are verified in the same plane and frame')
                value=target*reference_cm/reference_px if reference_px>0 else 0
                calibration={'target_px':target,'reference_px':reference_px,'reference_cm':reference_cm,'same_plane_confirmed':same_plane}
            uncertainty=st.number_input('Estimated measurement error ± (cm)',min_value=0.0,value=.2,step=.05)
            evidence=st.text_input('Evidence / protocol notes (include video and timestamp for image measurements)')
            reviewer=st.text_input('Measured or verified by')
            submitted=st.form_submit_button('Save distance comparison')
        if submitted:
            try:
                if calibration and not calibration['same_plane_confirmed']: raise ValueError('Verify the reference geometry first.')
                result=distance_result(value,uncertainty,method,reviewer,evidence)
                result['calibration']=calibration
                save_distance(db,cid,result);st.success('Distance comparison saved.')
            except ValueError as exc:st.error(str(exc))
    with final:
        current=case_report(db,cid)
        st.subheader(current['status'])
        st.write(current['conclusion'])
        findings_panel(current.get('pixel_measurements', []))
        tmd=current['thyromental']
        if tmd['state']=='reviewed_estimate':
            st.info(f"Thyromental distance: {tmd['value']:.2f} ± {tmd['uncertainty_cm']:.2f} cm · reviewed image estimate")
            st.caption(tmd['limitation'])
        else:
            st.info('Thyromental distance unavailable: '+tmd['reason'])
        for clip in current['clips']:
            with st.container(border=True):
                st.write(('✓ ' if clip['state']=='accepted' else '○ ')+clip['file'])
                st.caption(clip.get('role','Unassigned')+' · '+clip['state'])
                if clip['reasons']:st.write('; '.join(clip['reasons']))
                for f in clip['findings']:st.write(f"{f['label']}: **{f['value']:.3f} {f['unit']}**")
        d=current['distance_assessment']
        if d:
            st.info(f"Interincisor opening: {d['value']:.2f} ± {d['uncertainty_cm']:.2f} cm. {d['status']}.")
            if d['status'] == 'Below reference threshold':
                st.warning(d['factor_assessment'])
            elif d['status'].startswith('Threshold overlap'):
                st.warning(d['factor_assessment'])
            else:
                st.caption(d['factor_assessment'])
            st.caption(d['meaning']);st.link_button('View threshold reference',d['source'])
        else:st.caption('Physical interincisor distance has not been supplied. Visible lip aperture is reported separately.')
        with st.expander('Methods and limitations'):
            for limitation in current['limitations']:st.write('• '+limitation)
            st.caption(VERSION)
        digest,files=exports(current)
        st.caption('These downloads always reflect the current case and latest saved reviews. Snapshot: '+digest)
        columns=st.columns(3)
        for col,(kind,content) in zip(columns,files.items()):
            col.download_button('Download '+('printable report' if kind=='html' else kind.upper()),content,f'research-{cid[:8]}-{digest}.{kind}',mime={'html':'text/html','json':'application/json','csv':'text/csv'}[kind],key=kind+cid+digest)
