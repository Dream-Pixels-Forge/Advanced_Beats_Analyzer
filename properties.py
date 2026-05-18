# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""PropertyGroup definitions for the Beat Analyzer addon."""

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


class BeatAnalyzerProperties(PropertyGroup):
    """Scene-level properties for the Beat Analyzer addon."""

    # ── Audio File ──────────────────────────────────────────────────────
    audio_file: StringProperty(
        name="Audio File",
        description="Path to the audio file (WAV, MP3, FLAC, OGG supported)",
        default="",
        subtype='FILE_PATH',
    )

    audio_muted: BoolProperty(
        name="Mute Audio",
        description="Mute/unmute the audio playback in the sequencer",
        default=False,
    )

    # ── Detection Method ────────────────────────────────────────────────
    detection_method: EnumProperty(
        name="Detection Method",
        description="Algorithm used for beat detection",
        items=[
            ('ENERGY', "Energy Based", "Classic energy-based beat detection"),
            ('SPECTRAL', "Spectral Flux", "Detection using spectral flux"),
            ('COMPLEX', "Complex Detection", "Combined energy and spectral analysis"),
            ('ADAPTIVE', "Adaptive Threshold", "Adaptive threshold detection"),
        ],
        default='COMPLEX',
    )

    # ── Frequency Bands ─────────────────────────────────────────────────
    frequency_bands: EnumProperty(
        name="Frequency Bands",
        description="Frequency range to analyze",
        items=[
            ('ALL', "All Frequencies", "Analyze full spectrum"),
            ('BASS', "Bass Only", "Focus on 20-250 Hz"),
            ('MID', "Mid Range", "Focus on 250-2000 Hz"),
            ('HIGH', "High Range", "Focus on 2000-20000 Hz"),
            ('CUSTOM', "Custom Range", "Define custom frequency range"),
        ],
        default='ALL',
    )

    custom_freq_low: FloatProperty(
        name="Low Frequency",
        description="Lower bound of custom frequency range (Hz)",
        default=20.0, min=20.0, max=20000.0, unit='NONE',
    )

    custom_freq_high: FloatProperty(
        name="High Frequency",
        description="Upper bound of custom frequency range (Hz)",
        default=20000.0, min=20.0, max=20000.0, unit='NONE',
    )

    # ── Analysis Parameters ─────────────────────────────────────────────
    sensitivity: FloatProperty(
        name="Sensitivity",
        description="Beat detection sensitivity (lower = more beats detected)",
        default=1.3, min=0.1, max=2.0,
    )

    min_bpm: IntProperty(
        name="Minimum BPM",
        description="Minimum beats per minute to detect",
        default=60, min=30, max=300,
    )

    max_bpm: IntProperty(
        name="Maximum BPM",
        description="Maximum beats per minute to detect",
        default=180, min=30, max=300,
    )

    analysis_window: IntProperty(
        name="Analysis Window",
        description="Size of analysis window in milliseconds",
        default=50, min=10, max=200,
    )

    # ── Advanced Settings ───────────────────────────────────────────────
    advanced_settings: BoolProperty(
        name="Advanced Settings",
        description="Show advanced analysis settings",
        default=False,
    )

    use_threading: BoolProperty(
        name="Use Threading",
        description="Use multi-threading for faster analysis",
        default=True,
    )

    use_cache: BoolProperty(
        name="Use Cache",
        description="Cache analysis results for repeated analysis",
        default=True,
    )

    noise_reduction: FloatProperty(
        name="Noise Reduction",
        description="Background noise reduction amount (0=off, 1=max)",
        default=0.2, min=0.0, max=1.0,
    )

    beat_refinement: BoolProperty(
        name="Beat Refinement",
        description="Additional processing to refine beat positions",
        default=True,
    )

    debug_mode: BoolProperty(
        name="Debug Mode",
        description="Show additional debug information in results",
        default=False,
    )

    # ── Beat Strength Thresholds ────────────────────────────────────────
    strong_beat_threshold: FloatProperty(
        name="Strong Beat Threshold",
        description="Threshold for strong beat detection",
        default=1.5, min=1.0, max=3.0,
    )

    medium_beat_threshold: FloatProperty(
        name="Medium Beat Threshold",
        description="Threshold for medium beat detection",
        default=1.2, min=1.0, max=3.0,
    )

    # ── Marker Settings ─────────────────────────────────────────────────
    marker_prefix: StringProperty(
        name="Marker Prefix",
        description="Prefix for beat marker names",
        default="Beat_",
    )

    show_strong_beats: BoolProperty(
        name="Strong Beats",
        description="Show markers for strong beats",
        default=True,
    )

    show_medium_beats: BoolProperty(
        name="Medium Beats",
        description="Show markers for medium beats",
        default=True,
    )

    show_weak_beats: BoolProperty(
        name="Weak Beats",
        description="Show markers for weak beats",
        default=True,
    )

    # ── Audio Baking ────────────────────────────────────────────────────
    bake_smoothing: FloatProperty(
        name="Smoothing",
        description="Smoothing factor for audio baking (0=none, 1=max)",
        default=0.5, min=0.0, max=1.0,
    )

    # ── Analysis Results (read-only display) ────────────────────────────
    total_beats: IntProperty(default=0)
    average_bpm: FloatProperty(default=0.0)
    audio_duration: FloatProperty(default=0.0)
    last_analysis_time: StringProperty(default="Never")
    debug_info: StringProperty(default="No analysis performed yet")
