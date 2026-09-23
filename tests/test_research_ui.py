"""Exercise persisted distance review and case switching in an isolated app."""
from streamlit.testing.v1 import AppTest
from airway.db import initialize,transaction
from airway.research import setup,case_report
from airway.ui.components import source_point_from_click
from airway.ui.research_workspace import findings_dataframe


def test_mixed_timestamp_findings_render_without_changing_saved_evidence(tmp_path):
    import copy
    import json
    import pyarrow as pa
    from airway.research import save_review

    findings = [
        {'metric':'pitch', 'label':'Excursion', 'value':45., 'unit':'degree', 'timestamp_ms':[100., 1200.]},
        {'metric':'pitch_negative_endpoint', 'label':'Endpoint', 'value':-20., 'unit':'degree', 'timestamp_ms':100.},
        {'metric':'missing_time', 'label':'No timestamp', 'value':1., 'unit':'ratio', 'timestamp_ms':None},
        {'metric':'legacy', 'label':'Legacy finding', 'value':2., 'unit':'ratio'},
    ]
    original = copy.deepcopy(findings)
    table = pa.Table.from_pandas(findings_dataframe(findings))
    assert table['timestamp_ms'].to_pylist() == ['100, 1200', '100', '', '']
    assert table['value'].to_pylist() == [45., -20., 1., 2.]
    assert findings == original

    db=tmp_path/'mixed.db'; initialize(db); setup(db)
    artifact=tmp_path/'frames.json'
    artifact.write_text(json.dumps({'frames':[{'timestamp_ms':0}, {'timestamp_ms':1500}]}))
    with transaction(db) as c:
        c.execute("INSERT INTO cases(id,label,created_at) VALUES('case','Mixed timestamps','1')")
        c.execute("INSERT INTO videos(id,source_path,relative_path,sha256,bytes,created_at) VALUES('video','synthetic.mp4','synthetic.mp4','hash',1,'1')")
        c.execute("INSERT INTO segments(id,case_id,video_id) VALUES('segment','case','video')")
        c.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,state,started_at) VALUES('run','case','video','{}','completed','1')")
        c.execute("INSERT INTO analysis_artifacts(id,run_id,kind,path,sha256,created_at) VALUES('artifact','run','per_frame_json',?,'hash','1')", (str(artifact),))
    save_review(db,'case','video','run','Test reviewer',
                {'role':'Head flexion / extension','state':'accepted','reasons':[],'findings':findings})
    app=AppTest.from_string(f'from airway.ui.research_workspace import workspace\nworkspace({str(db)!r})',default_timeout=30).run()
    assert not app.exception
    assert app.dataframe[0].value['timestamp_ms'].tolist() == ['100, 1200', '100', '', '']
    assert case_report(db,'case')['clips'][0]['findings'] == original


def test_image_click_maps_rendered_pixels_to_source_pixels():
    assert source_point_from_click({'x': 50, 'y': 25, 'width': 100, 'height': 50}, 480, 848) == [240.0, 424.0]
    assert source_point_from_click(None, 480, 848) is None


def test_distance_form_persists_and_does_not_leak_to_other_case(tmp_path):
    db=tmp_path/'ui.sqlite3';initialize(db);setup(db)
    with transaction(db) as c:
        for case in ('A','B'):
            c.execute('INSERT INTO cases(id,label,created_at) VALUES(?,?,?)',(case,case,case))
    app=AppTest.from_string(f'from airway.ui.research_workspace import workspace\nworkspace({str(db)!r})',default_timeout=30).run()
    assert not app.exception
    app.selectbox(key='research_case').set_value('A').run()
    next(x for x in app.number_input if x.label=='Measured interincisor opening (cm)').set_value(2.5)
    next(x for x in app.text_input if x.label.startswith('Evidence /')).set_value('Synthetic test measurement')
    next(x for x in app.text_input if x.label=='Measured or verified by').set_value('Test reviewer')
    next(b for b in app.button if b.label=='Save distance comparison').click().run()
    assert not app.exception
    assert case_report(db,'A')['distance_assessment']['status']=='Below reference threshold'
    app.selectbox(key='research_case').set_value('B').run()
    assert not app.exception
    assert case_report(db,'B')['distance_assessment'] is None
    next(r for r in app.radio if r.label=='Measurement method').set_value('Calibrated incisor endpoints').run()
    assert not app.exception
    assert any(n.label=='Known reference size (cm)' for n in app.number_input)
