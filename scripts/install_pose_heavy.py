"""Explicit local model installation; analysis itself never downloads weights."""
import hashlib
import urllib.request
from pathlib import Path

URL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task'
SHA256 = '64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b'


def main():
    target = Path(__file__).resolve().parents[1] / 'models' / 'pose_landmarker_heavy.task'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.download')
    urllib.request.urlretrieve(URL, temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
        temporary.unlink()
        raise ValueError('Downloaded model checksum does not match the pinned bundle.')
    temporary.replace(target)
    print('Installed verified MediaPipe Pose Landmarker Heavy:', target)


if __name__ == '__main__':
    main()
