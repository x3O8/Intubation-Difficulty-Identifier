"""Exercise persisted distance review and case switching in an isolated app."""
from streamlit.testing.v1 import AppTest
from airway.db import initialize,transaction
from airway.research import setup,case_report
from airway.ui.components import source_point_from_click


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
