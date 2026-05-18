# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Multi-format audio loader using Blender's built-in aud module.

Supports WAV, MP3, FLAC, OGG, and any format Blender can decode.
Falls back to the wave module for pure-Python environments (testing).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Supported extensions (formats aud can handle)
SUPPORTED_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".ogg", ".opus",
    ".aac", ".m4a", ".wma", ".aiff", ".aif",
}


@dataclass
class AudioData:
    """Raw audio data extracted from any supported format."""

    samples: np.ndarray  # Normalized float64 mono samples in [-1, 1]
    sample_rate: int
    channels: int
    duration: float


def load_audio_aud(file_path: str) -> AudioData:
    """Load audio using Blender's aud module (supports all Blender-decodable formats).

    This is the preferred loader when running inside Blender.
    """
    import aud  # Available inside Blender's Python environment

    sound = aud.Sound(file_path)

    # Get specs from the original sound
    specs = sound.specs
    sample_rate = specs[0]
    channels = specs[1]  # aud.Channels enum or int

    # Resample/remix to mono for analysis
    sound_mono = sound.rechannel(1)  # Convert to mono

    # Read all samples into a NumPy buffer
    # aud.Sound.data() returns a numpy-compatible buffer in Blender 5.x
    # We use the factory approach: write to a buffer
    sound_buffered = aud.Sound.buffer(sound_mono)
    buffer_data = sound_buffered.data()

    # buffer_data is a 2D numpy array (frames x channels)
    samples = np.array(buffer_data, dtype=np.float64).flatten()

    # Normalize to [-1, 1] if not already
    max_val = np.max(np.abs(samples))
    if max_val > 0 and max_val > 1.0:
        samples = samples / max_val

    duration = len(samples) / sample_rate

    return AudioData(
        samples=samples,
        sample_rate=sample_rate,
        channels=channels if isinstance(channels, int) else 1,
        duration=duration,
    )


def load_audio_wave(file_path: str) -> AudioData:
    """Fallback loader using the standard library wave module (WAV only).

    Used for unit testing outside Blender or when aud is unavailable.
    """
    import wave

    with wave.open(file_path, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    data = np.frombuffer(raw, dtype=np.int16)
    if channels == 2:
        data = data.reshape(-1, 2).mean(axis=1)

    samples = data / np.iinfo(np.int16).max
    duration = len(samples) / sample_rate

    return AudioData(
        samples=samples,
        sample_rate=sample_rate,
        channels=channels,
        duration=duration,
    )


def load_audio(file_path: str) -> AudioData:
    """Smart loader: uses aud if available (multi-format), falls back to wave.

    Args:
        file_path: Absolute path to the audio file.

    Returns:
        AudioData with normalized mono samples.

    Raises:
        RuntimeError: If the file cannot be loaded by any available method.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    # Try aud first (works for all formats inside Blender)
    try:
        return load_audio_aud(file_path)
    except (ImportError, Exception) as exc:
        # aud not available (outside Blender) or failed
        if ext == ".wav":
            # Fallback to wave module for WAV files
            try:
                return load_audio_wave(file_path)
            except Exception as wave_exc:
                raise RuntimeError(
                    f"Failed to load audio: aud error: {exc}, wave error: {wave_exc}"
                ) from wave_exc
        else:
            raise RuntimeError(
                f"Cannot load '{ext}' format: the aud module is required "
                f"(run inside Blender). Error: {exc}"
            ) from exc


def is_supported_format(file_path: str) -> bool:
    """Check if the file extension is a supported audio format."""
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS
