# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Beat analysis operator (modal, threaded)."""

from __future__ import annotations

import os
import threading
from datetime import datetime

import bpy
from bpy.types import Operator

from ..core.analyzer import AnalysisSettings, AudioAnalyzer, AnalysisResult
from ..core.cache import analysis_cache


class _AnalysisThread(threading.Thread):
    """Background thread that runs the analysis engine."""

    def __init__(self, file_path: str, settings: AnalysisSettings) -> None:
        super().__init__(daemon=True)
        self.file_path = file_path
        self.settings = settings
        self.result: AnalysisResult | None = None
        self.progress: float = 0.0
        self.error: str | None = None

    def run(self) -> None:
        try:
            analyzer = AudioAnalyzer(self.settings)
            self.result = analyzer.analyze_file(
                self.file_path,
                progress_callback=self._on_progress,
            )
        except Exception as exc:
            self.error = str(exc)

    def _on_progress(self, value: float) -> None:
        self.progress = value


class BEATANALYZER_OT_analyze(Operator):
    """Perform beat analysis on the selected audio file."""

    bl_idname = "beatanalyzer.analyze"
    bl_label = "Analyze Audio"
    bl_description = "Run beat detection on the selected audio file (WAV, MP3, FLAC, OGG)"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _thread: _AnalysisThread | None = None

    # ── Modal loop ──────────────────────────────────────────────────────

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._thread and self._thread.is_alive():
            context.window_manager.progress_update(int(self._thread.progress))
            return {'RUNNING_MODAL'}

        # Thread finished
        context.window_manager.progress_end()
        context.window_manager.event_timer_remove(self._timer)

        if self._thread.error:
            self.report({'ERROR'}, self._thread.error)
            self._thread = None
            return {'CANCELLED'}

        if self._thread.result:
            self._apply_results(context, self._thread.result)

        self._thread = None
        return {'FINISHED'}

    # ── Execute ─────────────────────────────────────────────────────────

    def execute(self, context):
        props = context.scene.beat_analyzer_props

        if not props.audio_file:
            self.report({'ERROR'}, "No audio file selected")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)
        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            return {'CANCELLED'}

        # Ensure audio is in the sequencer
        self._ensure_audio_in_sequencer(context, filepath)

        # Check cache
        settings_dict = self._settings_dict(props)
        if props.use_cache:
            cached = analysis_cache.get(filepath, settings_dict)
            if cached is not None:
                self._apply_results(context, cached)
                return {'FINISHED'}

        # Clear existing markers
        self._clear_markers(context)

        # Build thread-safe settings copy
        settings = AnalysisSettings(
            detection_method=props.detection_method,
            frequency_bands=props.frequency_bands,
            custom_freq_low=props.custom_freq_low,
            custom_freq_high=props.custom_freq_high,
            sensitivity=props.sensitivity,
            min_bpm=props.min_bpm,
            max_bpm=props.max_bpm,
            analysis_window=props.analysis_window,
            noise_reduction=props.noise_reduction,
            beat_refinement=props.beat_refinement,
            strong_beat_threshold=props.strong_beat_threshold,
            medium_beat_threshold=props.medium_beat_threshold,
        )

        self._thread = _AnalysisThread(filepath, settings)
        self._thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.progress_begin(0, 100)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _settings_dict(props) -> dict:
        return {
            "detection_method": props.detection_method,
            "frequency_bands": props.frequency_bands,
            "sensitivity": props.sensitivity,
            "noise_reduction": props.noise_reduction,
            "analysis_window": props.analysis_window,
            "min_bpm": props.min_bpm,
            "max_bpm": props.max_bpm,
        }

    @staticmethod
    def _clear_markers(context) -> None:
        markers = context.scene.timeline_markers
        while markers:
            markers.remove(markers[0])

    def _apply_results(self, context, result: AnalysisResult) -> None:
        props = context.scene.beat_analyzer_props
        scene = context.scene

        for t, strength in result.beats:
            show = (
                (strength == "strong" and props.show_strong_beats)
                or (strength == "medium" and props.show_medium_beats)
                or (strength == "weak" and props.show_weak_beats)
            )
            if show:
                frame = int(t * scene.render.fps)
                scene.timeline_markers.new(
                    f"{props.marker_prefix}{frame}_{strength}", frame=frame
                )

        props.total_beats = len(result.beats)
        props.average_bpm = result.bpm
        props.audio_duration = result.duration
        props.last_analysis_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if props.debug_mode:
            props.debug_info = (
                f"Sample Rate: {result.sample_rate} Hz\n"
                f"Channels: {result.channels}\n"
                f"Duration: {result.duration:.2f}s\n"
                f"Total Beats: {props.total_beats}\n"
                f"Average BPM: {props.average_bpm:.1f}"
            )

        if props.use_cache:
            filepath = bpy.path.abspath(props.audio_file)
            analysis_cache.put(filepath, self._settings_dict(props), result)

    def _ensure_audio_in_sequencer(self, context, filepath: str) -> None:
        """Add the audio file to the VSE if not already present."""
        scene = context.scene
        props = scene.beat_analyzer_props

        if not scene.sequence_editor:
            scene.sequence_editor_create()

        for seq in scene.sequence_editor.sequences_all:
            if seq.type == 'SOUND' and seq.sound and seq.sound.filepath == props.audio_file:
                seq.mute = props.audio_muted
                return

        try:
            strip = scene.sequence_editor.sequences.new_sound(
                name=os.path.basename(filepath),
                filepath=filepath,
                channel=1,
                frame_start=1,
            )
            strip.mute = props.audio_muted
        except Exception as exc:
            print(f"[BeatAnalyzer] Could not add audio to sequencer: {exc}")
