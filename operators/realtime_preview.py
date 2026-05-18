# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Real-Time Audio Preview using frame_change handler + set_transform.

Blender 5.0 introduced high-performance get_transform/set_transform methods
on objects. Instead of baking keyframes, this module uses a frame_change_post
handler that reads the pre-computed amplitude at the current frame and
directly applies transforms (scale, location offset) to tagged objects.

Benefits:
- Instant visual feedback without any bake step
- Zero keyframes — purely procedural/runtime
- Can preview before committing to baked animation
- Togglable on/off from the panel

The handler reads from the same _amplitude_curves dict used by the
driver system (operators/drivers.py), so the user must first run
"Generate Amplitude Curve" before enabling preview.
"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator

from .drivers import _amplitude_curves, register_driver_namespace


# ── Module-level state ──────────────────────────────────────────────────────

_preview_active: bool = False
_preview_objects: set[str] = set()  # Object names tagged for preview
_preview_mode: str = 'SCALE_Z'
_preview_intensity: float = 1.0


def _frame_change_handler(scene) -> None:
    """Handler called on every frame change to apply audio-driven transforms."""
    if not _preview_active:
        return

    curve = _amplitude_curves.get(scene.name)
    if curve is None:
        return

    frame = scene.frame_current
    idx = frame - scene.frame_start
    if idx < 0 or idx >= len(curve):
        amp = 0.0
    else:
        amp = float(curve[idx]) * _preview_intensity

    for obj_name in list(_preview_objects):
        obj = scene.objects.get(obj_name)
        if obj is None:
            _preview_objects.discard(obj_name)
            continue

        _apply_preview_transform(obj, amp)


def _apply_preview_transform(obj, amplitude: float) -> None:
    """Apply audio amplitude to object transform based on preview mode."""
    mode = _preview_mode

    if mode == 'SCALE_Z':
        obj.scale.z = 1.0 + amplitude
    elif mode == 'SCALE_ALL':
        val = 1.0 + amplitude
        obj.scale = (val, val, val)
    elif mode == 'LOC_Z':
        obj.location.z = amplitude
    elif mode == 'LOC_Y':
        obj.location.y = amplitude
    elif mode == 'ROTATION_Z':
        obj.rotation_euler.z = amplitude * 0.5


# ── Operators ───────────────────────────────────────────────────────────────

class BEATANALYZER_OT_enable_realtime_preview(Operator):
    """Enable real-time audio preview on the active object (no keyframes)."""

    bl_idname = "beatanalyzer.enable_realtime_preview"
    bl_label = "Enable Audio Preview"
    bl_description = (
        "Apply audio amplitude to object transform in real-time "
        "(frame_change handler, no keyframes)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    preview_mode: EnumProperty(
        name="Preview Mode",
        description="How audio amplitude affects the object",
        items=[
            ('SCALE_Z', "Scale Z", "Audio drives Z scale (1 + amp)"),
            ('SCALE_ALL', "Scale All", "Audio drives uniform scale"),
            ('LOC_Z', "Location Z", "Audio drives Z position offset"),
            ('LOC_Y', "Location Y", "Audio drives Y position offset"),
            ('ROTATION_Z', "Rotation Z", "Audio drives Z rotation"),
        ],
        default='SCALE_Z',
    )

    intensity: FloatProperty(
        name="Intensity",
        description="Multiplier for the audio effect",
        default=1.0,
        min=0.1,
        max=5.0,
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        global _preview_active, _preview_mode, _preview_intensity

        scene = context.scene
        obj = context.active_object

        # Check amplitude curve exists
        if scene.name not in _amplitude_curves:
            self.report(
                {'ERROR'},
                "Generate amplitude curve first (Audio Drivers section)",
            )
            return {'CANCELLED'}

        # Tag this object for preview
        _preview_objects.add(obj.name)
        _preview_mode = self.preview_mode
        _preview_intensity = self.intensity

        # Register handler if not already active
        if not _preview_active:
            if _frame_change_handler not in bpy.app.handlers.frame_change_post:
                bpy.app.handlers.frame_change_post.append(_frame_change_handler)
            _preview_active = True

        self.report(
            {'INFO'},
            f"Real-time preview enabled on '{obj.name}' [{self.preview_mode}]",
        )
        return {'FINISHED'}


class BEATANALYZER_OT_disable_realtime_preview(Operator):
    """Disable real-time audio preview and reset transforms."""

    bl_idname = "beatanalyzer.disable_realtime_preview"
    bl_label = "Disable Audio Preview"
    bl_description = "Stop real-time audio preview and reset object transforms"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _preview_active

    def execute(self, context):
        global _preview_active

        # Remove handler
        if _frame_change_handler in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(_frame_change_handler)
        _preview_active = False

        # Reset transforms on all preview objects
        scene = context.scene
        for obj_name in list(_preview_objects):
            obj = scene.objects.get(obj_name)
            if obj:
                obj.scale = (1.0, 1.0, 1.0)
                obj.location.z = 0.0
                obj.location.y = 0.0
                obj.rotation_euler.z = 0.0

        _preview_objects.clear()

        self.report({'INFO'}, "Real-time preview disabled, transforms reset")
        return {'FINISHED'}


def cleanup_handler() -> None:
    """Remove the frame change handler on addon unregister."""
    global _preview_active
    if _frame_change_handler in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_frame_change_handler)
    _preview_active = False
    _preview_objects.clear()
