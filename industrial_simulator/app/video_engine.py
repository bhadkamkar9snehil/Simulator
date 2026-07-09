from __future__ import annotations

import json
import math
import struct
import uuid
from pathlib import Path

from app import csv_manager, job_manager
from app.models import VideoJobRequest, utc_now_iso

VIDEO_ROOT = csv_manager.ROOT / "generated_data" / "video"


def _ppm_frame(path: Path, width: int, height: int, frame_index: int, camera_index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    data = bytearray()
    for y in range(height):
        for x in range(width):
            r = (x + frame_index * 3 + camera_index * 31) % 256
            g = (y + frame_index * 5) % 256
            b = ((x + y) // 2 + frame_index * 7) % 256
            data.extend((r, g, b))
    path.write_bytes(header + bytes(data))


def start_video_job(request: VideoJobRequest) -> str:
    job = job_manager.create_job(request.name, "video_generation")
    job_manager.run_background(job.job_id, run_video_job, request)
    return job.job_id


def run_video_job(job_id: str, request: VideoJobRequest) -> None:
    run_id = request.run_id or f"video_run_{uuid.uuid4().hex[:10]}"
    total_frames = request.duration_seconds * request.fps * request.camera_count
    frames_done = 0
    segments: list[dict] = []
    for camera in range(request.camera_count):
        camera_id = f"{request.camera_id_prefix}-{camera + 1:03d}"
        camera_dir = VIDEO_ROOT / run_id / camera_id
        frames_per_segment = request.segment_seconds * request.fps
        frame_count = request.duration_seconds * request.fps
        for frame in range(frame_count):
            segment_index = frame // frames_per_segment + 1
            frame_path = camera_dir / f"segment-{segment_index:06d}" / f"frame-{frame:08d}.ppm"
            _ppm_frame(frame_path, request.width, request.height, frame, camera)
            frames_done += 1
            if frame % max(request.fps, 1) == 0:
                job_manager.update_job(
                    job_id,
                    progress_percent=min(99.0, frames_done / max(total_frames, 1) * 100),
                    current_step=f"camera {camera_id} frame {frame}",
                    rows_done=frames_done,
                    message="Generating synthetic video frames.",
                )
        segment_count = math.ceil(frame_count / max(frames_per_segment, 1))
        for segment in range(1, segment_count + 1):
            segment_dir = camera_dir / f"segment-{segment:06d}"
            size = sum(p.stat().st_size for p in segment_dir.glob("*.ppm"))
            segments.append(
                {
                    "run_id": run_id,
                    "camera_id": camera_id,
                    "segment_id": f"segment-{segment:06d}",
                    "fps": request.fps,
                    "width": request.width,
                    "height": request.height,
                    "path": str(segment_dir),
                    "size_bytes": size,
                    "linked_dataset_id": request.linked_dataset_id,
                    "created_at": utc_now_iso(),
                }
            )
    manifest = VIDEO_ROOT / run_id / "video_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"run_id": run_id, "segments": segments, "updated_at": utc_now_iso()}, indent=2), encoding="utf-8")
    job_manager.mark_completed(job_id, "Synthetic video frames generated.", rows_done=frames_done, output_paths=[str(manifest)], bytes_done=sum(s["size_bytes"] for s in segments))
