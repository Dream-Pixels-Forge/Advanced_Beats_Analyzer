# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Marker navigation and management operators."""

import bpy
from bpy.types import Operator


class BEATANALYZER_OT_next_marker(Operator):
    """Jump to the next beat marker on the timeline."""

    bl_idname = "beatanalyzer.next_marker"
    bl_label = "Next Beat Marker"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.screen.marker_jump(next=True)
        return {'FINISHED'}


class BEATANALYZER_OT_prev_marker(Operator):
    """Jump to the previous beat marker on the timeline."""

    bl_idname = "beatanalyzer.prev_marker"
    bl_label = "Previous Beat Marker"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.screen.marker_jump(next=False)
        return {'FINISHED'}


class BEATANALYZER_OT_bind_camera(Operator):
    """Bind the active camera to the marker at the current frame."""

    bl_idname = "beatanalyzer.bind_camera"
    bl_label = "Bind Camera to Marker"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'CAMERA'

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current

        marker = next(
            (m for m in scene.timeline_markers if m.frame == frame), None
        )
        if not marker:
            self.report({'ERROR'}, "No marker at current frame")
            return {'CANCELLED'}

        marker.camera = context.active_object
        scene.camera = context.active_object
        self.report({'INFO'}, f"Camera bound to marker '{marker.name}'")
        return {'FINISHED'}


class BEATANALYZER_OT_update_marker_visibility(Operator):
    """Rebuild markers based on current visibility toggles."""

    bl_idname = "beatanalyzer.update_marker_visibility"
    bl_label = "Update Marker Visibility"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.beat_analyzer_props
        prefix = props.marker_prefix

        # Collect markers to keep
        keep = []
        for marker in scene.timeline_markers:
            if not marker.name.startswith(prefix):
                keep.append((marker.name, marker.frame))
                continue
            strength = marker.name.rsplit("_", 1)[-1]
            visible = (
                (strength == "strong" and props.show_strong_beats)
                or (strength == "medium" and props.show_medium_beats)
                or (strength == "weak" and props.show_weak_beats)
            )
            if visible:
                keep.append((marker.name, marker.frame))

        # Rebuild
        while scene.timeline_markers:
            scene.timeline_markers.remove(scene.timeline_markers[0])

        for name, frame in keep:
            scene.timeline_markers.new(name, frame=frame)

        return {'FINISHED'}


class BEATANALYZER_OT_clear_markers(Operator):
    """Remove all beat markers from the timeline."""

    bl_idname = "beatanalyzer.clear_markers"
    bl_label = "Clear Beat Markers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        markers = context.scene.timeline_markers
        while markers:
            markers.remove(markers[0])
        return {'FINISHED'}
