# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Audio mute toggle and JSON export operators."""

from __future__ import annotations

import json

import bpy
from bpy.props import StringProperty
from bpy.types import Operator


class BEATANALYZER_OT_toggle_mute(Operator):
    """Toggle mute state of the analyzed audio strip in the sequencer."""

    bl_idname = "beatanalyzer.toggle_mute"
    bl_label = "Toggle Audio Mute"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        se = context.scene.sequence_editor

        if not se:
            self.report({'ERROR'}, "No sequence editor found")
            return {'CANCELLED'}

        for seq in se.sequences_all:
            if seq.type == 'SOUND' and seq.sound and seq.sound.filepath == props.audio_file:
                seq.mute = not seq.mute
                props.audio_muted = seq.mute
                return {'FINISHED'}

        self.report({'WARNING'}, "Audio strip not found in sequencer")
        return {'CANCELLED'}


class BEATANALYZER_OT_export(Operator):
    """Export beat analysis data to a JSON file."""

    bl_idname = "beatanalyzer.export"
    bl_label = "Export Analysis"
    bl_options = {'REGISTER'}

    filepath: StringProperty(subtype='FILE_PATH', default="beat_analysis.json")

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        scene = context.scene

        data = {
            "file_info": {
                "audio_file": props.audio_file,
                "analysis_date": props.last_analysis_time,
                "duration": props.audio_duration,
                "total_beats": props.total_beats,
                "average_bpm": props.average_bpm,
            },
            "analysis_settings": {
                "detection_method": props.detection_method,
                "frequency_bands": props.frequency_bands,
                "sensitivity": props.sensitivity,
                "noise_reduction": props.noise_reduction,
                "analysis_window": props.analysis_window,
            },
            "beats": [
                {
                    "frame": m.frame,
                    "time": m.frame / scene.render.fps,
                    "name": m.name,
                    "strength": m.name.rsplit("_", 1)[-1],
                }
                for m in scene.timeline_markers
                if m.name.startswith(props.marker_prefix)
            ],
        }

        try:
            with open(self.filepath, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            self.report({'INFO'}, f"Exported to {self.filepath}")
        except OSError as exc:
            self.report({'ERROR'}, f"Export failed: {exc}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
