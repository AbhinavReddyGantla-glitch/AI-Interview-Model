"""Audio preprocessing and caching module for the STT pipeline.

Layer 2:
- Converts input audio to 16 kHz mono WAV via ffmpeg.
- Applies high-pass filter (~80 Hz) and loudness normalization (loudnorm).
- Computes SHA-256 audio hash for result caching.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger("app.services.speech_audio")

_ffmpeg_bin_cache: Optional[str] = None


def get_ffmpeg_binary() -> Optional[str]:
    """Locate the ffmpeg binary from PATH or imageio-ffmpeg bundled binary."""
    global _ffmpeg_bin_cache
    if _ffmpeg_bin_cache and os.path.exists(_ffmpeg_bin_cache):
        return _ffmpeg_bin_cache

    # 1. Check system PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        _ffmpeg_bin_cache = system_ffmpeg
        return _ffmpeg_bin_cache

    # 2. Check imageio-ffmpeg package
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.exists(bundled):
            _ffmpeg_bin_cache = bundled
            logger.info("Using imageio-ffmpeg bundled binary: %s", bundled)
            return _ffmpeg_bin_cache
    except Exception as exc:
        logger.debug("imageio-ffmpeg lookup failed: %s", exc)

    return None


def compute_audio_hash(audio_bytes: bytes) -> str:
    """Compute SHA-256 hex digest of audio bytes for caching."""
    return hashlib.sha256(audio_bytes).hexdigest()


def preprocess_audio(
    audio_bytes: bytes,
    content_type: str = "audio/webm",
    target_sample_rate: int = 16000,
    apply_filters: bool = True,
) -> tuple[bytes, str]:
    """Convert audio to 16 kHz mono WAV with high-pass and loudnorm filters.

    Returns:
        tuple[bytes, str]: (processed_audio_bytes, format_str) e.g. (wav_bytes, "wav")
    """
    if not audio_bytes:
        return b"", "wav"

    ffmpeg_bin = get_ffmpeg_binary()
    if not ffmpeg_bin:
        logger.warning("ffmpeg binary not found. Passing raw audio through without preprocessing.")
        fmt = "webm" if "webm" in content_type else "wav"
        return audio_bytes, fmt

    # Determine input extension
    ext = "webm"
    if "wav" in content_type:
        ext = "wav"
    elif "mp4" in content_type or "m4a" in content_type:
        ext = "mp4"
    elif "ogg" in content_type:
        ext = "ogg"
    elif "mp3" in content_type:
        ext = "mp3"

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as in_file:
        in_path = in_file.name
        in_file.write(audio_bytes)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out_file:
        out_path = out_file.name

    try:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            in_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(target_sample_rate),
        ]
        if apply_filters:
            # High-pass filter at 80 Hz cuts rumble/air noise; loudnorm normalizes speech loudness
            cmd.extend(["-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11"])

        cmd.append(out_path)

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )

        if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            with open(out_path, "rb") as f:
                processed_bytes = f.read()
            logger.info(
                "Audio preprocessing successful: in=%d bytes -> out=%d bytes (16kHz mono WAV)",
                len(audio_bytes),
                len(processed_bytes),
            )
            return processed_bytes, "wav"
        else:
            logger.warning(
                "ffmpeg preprocessing returned non-zero code %d: %s. Using original bytes.",
                result.returncode,
                result.stderr.decode(errors="ignore")[:300],
            )
            return audio_bytes, ext
    except Exception as exc:
        logger.warning("Error during audio preprocessing: %s. Using original bytes.", exc)
        return audio_bytes, ext
    finally:
        for p in (in_path, out_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

