from __future__ import annotations
import streamlit as st
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

def state_badge(state):
    colors={"available":"#1f7a5a","needs_review":"#a15c00","unavailable":"#9b2c2c","not_applicable":"#53657a"}
    st.markdown(f"<span style='padding:.2rem .55rem;border-radius:99px;background:{colors.get(state,'#555')}22;color:{colors.get(state,'#555')};font-weight:650'>{state.replace('_',' ')}</span>",unsafe_allow_html=True)

def point_editor(prefix, defaults=((0.0,0.0),(0.0,0.0))):
    st.caption("Numeric coordinate fallback (orientation-corrected source pixels)")
    c1,c2=st.columns(2); points=[]
    for i,(x,y) in enumerate(defaults):
        with (c1 if i==0 else c2):
            st.markdown(f"**Endpoint {i+1}**")
            px=st.number_input("x",min_value=0.0,value=float(x),key=f"{prefix}_x{i}")
            py=st.number_input("y",min_value=0.0,value=float(y),key=f"{prefix}_y{i}")
            points.append((px,py))
    return points


def source_point_from_click(click, source_width, source_height):
    """Map a component click from rendered pixels back to the source frame."""
    if not click or not click.get('width') or not click.get('height'):
        return None
    x = float(click['x']) * float(source_width) / float(click['width'])
    y = float(click['y']) * float(source_height) / float(click['height'])
    return [min(max(x, 0.0), float(source_width) - 1.0), min(max(y, 0.0), float(source_height) - 1.0)]


def click_landmark_pair(prefix, image_path, source_width, source_height, heading):
    """Let a reviewer place two ordered landmarks directly on a source frame."""
    state_key = f'{prefix}_points'
    if state_key not in st.session_state:
        st.session_state[state_key] = {}
    points = st.session_state[state_key]
    target = st.radio('Place landmark', ['Point A', 'Point B'], horizontal=True, key=f'{prefix}_target')
    image = Image.open(image_path).convert('RGB')
    draw = ImageDraw.Draw(image)
    colors = {'Point A': '#ff9f1c', 'Point B': '#00c2a8'}
    for label, point in points.items():
        x, y = point
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=colors[label], outline='white', width=2)
        draw.text((x + 10, y - 10), label, fill='white', stroke_width=2, stroke_fill='black')
    st.caption(f'{heading}: choose Point A or Point B, then click the matching visible landmark on the image.')
    click = streamlit_image_coordinates(image, width='stretch', key=f'{prefix}_image', cursor='crosshair')
    event_key = f'{prefix}_event'
    if click and click.get('unix_time') != st.session_state.get(event_key):
        point = source_point_from_click(click, source_width, source_height)
        if point:
            points[target] = point
            st.session_state[event_key] = click.get('unix_time')
            st.rerun()
    left, right = st.columns(2)
    left.caption('Point A: ' + ('{:.1f}, {:.1f}'.format(*points['Point A']) if 'Point A' in points else 'click image'))
    right.caption('Point B: ' + ('{:.1f}, {:.1f}'.format(*points['Point B']) if 'Point B' in points else 'click image'))
    if st.button('Clear points', key=f'{prefix}_clear'):
        st.session_state[state_key] = {}
        st.session_state.pop(event_key, None)
        st.rerun()
    return [points.get('Point A'), points.get('Point B')]
