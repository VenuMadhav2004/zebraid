"""Frame-order-preserving OpenCV video adapter; frames at the API are RGB."""
from pathlib import Path
import cv2
import numpy as np
from .simulator import simulate_vision

def process_video(input_path: str, output_path: str, config: dict) -> dict:
    options = dict(config); max_frames = options.pop('max_frames', None); max_width = options.pop('max_width', None)
    frames_dir = options.pop('frames_dir', None)
    if frames_dir is not None: Path(frames_dir).mkdir(parents=True, exist_ok=True)
    if max_frames is not None and (not isinstance(max_frames, int) or max_frames < 1): raise ValueError('max_frames must be positive')
    if max_width is not None and (not isinstance(max_width, int) or max_width < 2): raise ValueError('max_width must be at least 2')
    if Path(input_path).resolve() == Path(output_path).resolve(): raise ValueError('input and output paths must differ')
    cap = cv2.VideoCapture(str(input_path)); writer = None; count = 0
    if not cap.isOpened(): raise OSError(f'Cannot open video: {input_path}')
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not np.isfinite(fps) or fps <= 0: raise ValueError('Input FPS unavailable')
        while max_frames is None or count < max_frames:
            ok, bgr = cap.read()
            if not ok: break
            if max_width and bgr.shape[1] > max_width:
                bgr = cv2.resize(bgr, (max_width, max(2, round(bgr.shape[0]*max_width/bgr.shape[1]))))
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            processed = simulate_vision(rgb, **options)['image']
            combined = np.concatenate((rgb, np.round(processed*255).astype(np.uint8)), axis=1)
            if writer is None:
                writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (combined.shape[1], combined.shape[0]))
                if not writer.isOpened(): raise OSError('Cannot open output video codec')
            frame_bgr = cv2.cvtColor(combined, cv2.COLOR_RGB2BGR)
            writer.write(frame_bgr)
            if frames_dir is not None and not cv2.imwrite(str(Path(frames_dir) / f'frame_{count:06d}.png'), frame_bgr):
                raise OSError('Cannot write exported frame')
            count += 1
        if count == 0: raise ValueError('Input video contains no readable frames')
        return {'frames': count, 'fps': fps, 'output_path': str(output_path), 'audio_preserved': False}
    finally:
        cap.release()
        if writer is not None: writer.release()
