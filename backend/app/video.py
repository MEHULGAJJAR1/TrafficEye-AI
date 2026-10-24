from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2


class VideoInvalid(ValueError):
    pass


def inspect_video(path: Path, max_seconds: int):
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise VideoInvalid("OpenCV could not open this file. Use an MP4, AVI or MOV with a supported video codec.")
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps, frames = float(cap.get(cv2.CAP_PROP_FPS)), float(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not all(math.isfinite(v) for v in (fps, frames)) or fps <= 0 or frames < 1 or fps > 240:
            raise VideoInvalid("The video has invalid FPS/frame metadata. Re-encode it to a constant-frame-rate MP4.")
        if width < 16 or height < 16 or width * height > 16_777_216:
            raise VideoInvalid("Unsupported frame dimensions (maximum 16 megapixels).")
        if frames / fps > max_seconds:
            raise VideoInvalid(f"Video exceeds the {max_seconds}-second duration limit. Trim it before uploading.")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise VideoInvalid("No video frames could be decoded; the file may be corrupt.")
        codec_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((codec_int >> 8 * i) & 255) for i in range(4)).strip("\x00")
        return {"width": width, "height": height, "fps": fps, "total_frames": int(frames), "duration": frames / fps, "codec": codec}
    finally:
        cap.release()


def transcode_preview(source: Path, output: Path, max_seconds: int):
    import imageio_ffmpeg
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-loglevel", "error", "-i", str(source), "-map", "0:v:0", "-an", "-t", str(max_seconds), "-vf", "scale=w='min(1280,iw)':h=-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    # No shell invocation; uploaded filenames never become command fragments.
    result = subprocess.run(command, capture_output=True, timeout=1800, check=False)
    if result.returncode or not output.exists() or output.stat().st_size < 100:
        output.unlink(missing_ok=True)
        raise VideoInvalid("Could not create an H.264 browser preview. The original remains available for backend processing.")
