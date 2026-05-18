# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Pure-Python audio analysis engine (no Blender dependency).

This module contains all the DSP logic for beat detection. It can be
tested independently of Blender by passing a simple settings namespace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .audio_loader import AudioData, load_audio


@dataclass
class AnalysisSettings:
    """Plain-object mirror of BeatAnalyzerProperties for thread-safe access."""

    detection_method: str = "COMPLEX"
    frequency_bands: str = "ALL"
    custom_freq_low: float = 20.0
    custom_freq_high: float = 20000.0
    sensitivity: float = 1.3
    min_bpm: int = 60
    max_bpm: int = 180
    analysis_window: int = 50
    noise_reduction: float = 0.2
    beat_refinement: bool = True
    strong_beat_threshold: float = 1.5
    medium_beat_threshold: float = 1.2


@dataclass
class AnalysisResult:
    """Container for analysis output."""

    beats: list[tuple[float, str]] = field(default_factory=list)
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bpm: float = 0.0


ProgressCallback = Callable[[float], None] | None


class AudioAnalyzer:
    """Stateless audio analysis engine."""

    def __init__(self, settings: AnalysisSettings) -> None:
        self._s = settings
        self._sample_rate: int = 0
        self._window_size: int = 1024
        self._hop_length: int = 512

    # ── Public API ──────────────────────────────────────────────────────

    def analyze_file(
        self, file_path: str, progress_callback: ProgressCallback = None
    ) -> AnalysisResult:
        """Run full analysis on an audio file (any supported format) and return results."""
        audio = load_audio(file_path)
        self._sample_rate = audio.sample_rate
        self._channels = audio.channels
        data = audio.samples

        data = self._apply_frequency_filter(data)

        if self._s.noise_reduction > 0:
            data = self._apply_noise_reduction(data)

        method = self._s.detection_method
        if method == "ENERGY":
            beats = self._energy_detection(data, progress_callback)
        elif method == "SPECTRAL":
            beats = self._spectral_flux_detection(data, progress_callback)
        elif method == "COMPLEX":
            beats = self._complex_detection(data, progress_callback)
        else:
            beats = self._adaptive_detection(data, progress_callback)

        if self._s.beat_refinement:
            beats = self._refine_beats(data, beats)

        duration = len(data) / self._sample_rate
        bpm = len(beats) * 60.0 / duration if beats and duration > 0 else 0.0

        return AnalysisResult(
            beats=beats,
            duration=duration,
            sample_rate=self._sample_rate,
            channels=self._channels,
            bpm=bpm,
        )

    # ── I/O (removed - now uses audio_loader module) ────────────────────

    # ── Frequency Filtering ─────────────────────────────────────────────

    def _apply_frequency_filter(self, data: np.ndarray) -> np.ndarray:
        if self._s.frequency_bands == "ALL":
            return data

        fft_data = np.fft.rfft(data)
        freqs = np.fft.rfftfreq(len(data), 1.0 / self._sample_rate)

        band = self._s.frequency_bands
        if band == "BASS":
            mask = (freqs >= 20) & (freqs <= 250)
        elif band == "MID":
            mask = (freqs >= 250) & (freqs <= 2000)
        elif band == "HIGH":
            mask = (freqs >= 2000) & (freqs <= 20000)
        elif band == "CUSTOM":
            mask = (freqs >= self._s.custom_freq_low) & (freqs <= self._s.custom_freq_high)
        else:
            mask = np.ones_like(freqs, dtype=bool)

        fft_data[~mask] = 0
        return np.fft.irfft(fft_data)

    # ── Noise Reduction ─────────────────────────────────────────────────

    def _apply_noise_reduction(self, data: np.ndarray) -> np.ndarray:
        frame_len = 2048
        energies = [
            np.sum(data[i : i + frame_len] ** 2)
            for i in range(0, len(data) - frame_len, frame_len)
        ]
        threshold = np.percentile(energies, 10)

        clean = data.copy()
        gate = np.abs(clean) < (threshold * self._s.noise_reduction)
        clean[gate] *= 1.0 - self._s.noise_reduction
        return clean

    # ── Detection Algorithms ────────────────────────────────────────────

    def _energy_detection(
        self, data: np.ndarray, cb: ProgressCallback
    ) -> list[tuple[float, str]]:
        win = int(self._s.analysis_window * self._sample_rate / 1000)
        hop = win // 2
        energies = []

        for i in range(0, len(data) - win, hop):
            if cb:
                cb(i / len(data) * 100.0)
            energies.append(np.sum(data[i : i + win] ** 2))

        energies = np.array(energies)
        thresh = np.mean(energies) * self._s.sensitivity
        beats = []

        for i in range(1, len(energies) - 1):
            if energies[i] > thresh and energies[i] > energies[i - 1] and energies[i] > energies[i + 1]:
                t = (i * hop) / self._sample_rate
                beats.append((t, self._strength(energies[i] / thresh)))
        return beats

    def _spectral_flux_detection(
        self, data: np.ndarray, cb: ProgressCallback
    ) -> list[tuple[float, str]]:
        spec = self._spectrogram(data, cb)
        flux = np.maximum(np.diff(spec, axis=0), 0).sum(axis=1)
        flux /= flux.max() if flux.max() > 0 else 1.0

        thresh = np.mean(flux) * self._s.sensitivity
        beats = []
        for i in range(1, len(flux) - 1):
            if flux[i] > thresh and flux[i] > flux[i - 1] and flux[i] > flux[i + 1]:
                t = (i * self._hop_length) / self._sample_rate
                beats.append((t, self._strength(flux[i] / thresh)))
        return beats

    def _complex_detection(
        self, data: np.ndarray, cb: ProgressCallback
    ) -> list[tuple[float, str]]:
        e_beats = self._energy_detection(data, lambda p: cb(p / 2) if cb else None)
        s_beats = self._spectral_flux_detection(data, lambda p: cb(50 + p / 2) if cb else None)

        all_beats = sorted(e_beats + s_beats, key=lambda x: x[0])
        min_dist = 60.0 / self._s.max_bpm
        filtered = []
        last_t = -min_dist

        for t, s in all_beats:
            if t - last_t >= min_dist:
                filtered.append((t, s))
                last_t = t
        return filtered

    def _adaptive_detection(
        self, data: np.ndarray, cb: ProgressCallback
    ) -> list[tuple[float, str]]:
        win = int(self._s.analysis_window * self._sample_rate / 1000)
        hop = win // 2
        energies = []

        for i in range(0, len(data) - win, hop):
            if cb:
                cb(i / len(data) * 100.0)
            energies.append(np.sum(data[i : i + win] ** 2))

        energies = np.array(energies)
        kernel = int(2 * self._sample_rate / hop)
        kernel = kernel if kernel % 2 == 1 else kernel + 1
        threshold = np.array([
            np.mean(energies[max(0, i - kernel // 2) : min(len(energies), i + kernel // 2)]) * self._s.sensitivity
            for i in range(len(energies))
        ])

        beats = []
        for i in range(1, len(energies) - 1):
            if energies[i] > threshold[i] and energies[i] > energies[i - 1] and energies[i] > energies[i + 1]:
                t = (i * hop) / self._sample_rate
                beats.append((t, self._strength(energies[i] / threshold[i])))
        return beats

    # ── Helpers ─────────────────────────────────────────────────────────

    def _spectrogram(self, data: np.ndarray, cb: ProgressCallback) -> np.ndarray:
        window = np.hanning(self._window_size)
        frames = []
        for i in range(0, len(data) - self._window_size, self._hop_length):
            if cb:
                cb(i / len(data) * 100.0)
            frames.append(np.abs(np.fft.rfft(data[i : i + self._window_size] * window)))
        return np.array(frames)

    def _strength(self, ratio: float) -> str:
        if ratio >= self._s.strong_beat_threshold:
            return "strong"
        if ratio >= self._s.medium_beat_threshold:
            return "medium"
        return "weak"

    def _refine_beats(
        self, data: np.ndarray, beats: list[tuple[float, str]]
    ) -> list[tuple[float, str]]:
        if not beats:
            return beats

        win = int(0.05 * self._sample_rate)
        refined = []

        for t, s in beats:
            center = int(t * self._sample_rate)
            lo = max(0, center - win // 2)
            hi = min(len(data), center + win // 2)
            seg = data[lo:hi]
            if len(seg) > 0:
                peak = lo + int(np.argmax(seg ** 2))
                refined.append((peak / self._sample_rate, s))

        refined.sort(key=lambda x: x[0])

        min_dist = 60.0 / self._s.max_bpm
        filtered = []
        last_t = -min_dist
        for t, s in refined:
            if t - last_t >= min_dist:
                filtered.append((t, s))
                last_t = t
        return filtered
