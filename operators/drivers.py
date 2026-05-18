# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Driver Expression Generator for non-destructive, keyframe-free audio reactivity.

Instead of baking keyframes, this module:
1. Stores the per-frame amplitude curve in a scene-level custom property
2. Registers a driver namespace function `audio_value(frame)` that reads from it
3. Creates drivers on user-chosen properties with the expression `audio_value(frame)`

Benefits over keyframe baking:
- Non-destructive: no keyframes pollute the timeline
- Re-evaluates dynamically if frame rate changes
- Can be connected to ANY animatable property
- Easy to remove (just delete the driver)
"""

from __future__ import annotations

import os

import bpy
import numpy as np
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from ..core.audio_loader import load_audio


# ── Module-level amplitude data store ───────────────────────────────────────

# Global dict keyed by scene name → numpy array of per-frame amplitudes
_amplitude_curves: dict[str, np.ndarray] = {}


def audio_value(frame: float) -> float:
    """Driver namespace function: returns audio amplitude at the given frame.

    This function is registered in bpy.app.driver_namespace so it can be
    called from any driver expression as: audio_value(frame)
    """
    # Try to find the curve for the active scene
    try:
        scene_name = bpy.context.scene.name
    except Exception:
        return 0.0

    curve = _amplitude_curves.get(scene_name)
    if curve is None:
        return 0.0

    idx = int(frame) - 1  # frame 1 → index 0
    if idx < 0 or idx >= len(curve):
        return 0.0
    return float(curve[idx])


def register_driver_namespace() -> None:
    """Register audio_value in the driver namespace."""
    bpy.app.driver_namespace["audio_value"] = audio_value


def unregister_driver_namespace() -> None:
    """Remove audio_value from the driver namespace."""
    bpy.app.driver_namespace.pop("audio_value", None)


# ── Operator: Generate Amplitude Curve ──────────────────────────────────────

class BEATANALYZER_OT_generate_amplitude_curve(Operator):
    """Pre-compute per-frame audio amplitude and store it for driver use."""

    bl_idname = "beatanalyzer.generate_amplitude_curve"
    bl_label = "Generate Amplitude Curve"
    bl_description = (
        "Compute per-frame audio amplitude for use with driver expressions"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        scene = context.scene

        if not props.audio_file:
            self.report({'ERROR'}, "No audio file selected")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)
        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            return {'CANCELLED'}

        # Load audio
        try:
            audio = load_audio(filepath)
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to load audio: {exc}")
            return {'CANCELLED'}

        # Compute per-frame RMS amplitude
        fps = scene.render.fps
        frame_start = scene.frame_start
        frame_end = scene.frame_end
        n_frames = frame_end - frame_start + 1

        samples_per_frame = int(audio.sample_rate / fps)
        amplitudes = np.zeros(n_frames, dtype=np.float64)

        for i in range(n_frames):
            start_sample = i * samples_per_frame
            end_sample = start_sample + samples_per_frame
            if end_sample > len(audio.samples):
                break
            chunk = audio.samples[start_sample:end_sample]
            amplitudes[i] = np.sqrt(np.mean(chunk ** 2))  # RMS

        # Normalize to [0, 1]
        max_amp = amplitudes.max()
        if max_amp > 0:
            amplitudes /= max_amp

        # Apply smoothing
        if props.bake_smoothing > 0:
            kernel_size = max(3, int(props.bake_smoothing * 10))
            if kernel_size % 2 == 0:
                kernel_size += 1
            kernel = np.ones(kernel_size) / kernel_size
            amplitudes = np.convolve(amplitudes, kernel, mode='same')

        # Store in module-level dict
        _amplitude_curves[scene.name] = amplitudes

        # Also store as a scene custom property for persistence
        scene["beat_analyzer_amplitude_frames"] = n_frames
        # Store as a string representation for file save/load
        scene["beat_analyzer_amplitude_data"] = amplitudes.tobytes().hex()

        # Ensure driver namespace is registered
        register_driver_namespace()

        self.report(
            {'INFO'},
            f"Amplitude curve generated: {n_frames} frames, "
            f"use audio_value(frame) in driver expressions",
        )
        return {'FINISHED'}


# ── Operator: Add Audio Driver to Property ──────────────────────────────────

class BEATANALYZER_OT_add_audio_driver(Operator):
    """Add a driver expression using audio_value(frame) to a property."""

    bl_idname = "beatanalyzer.add_audio_driver"
    bl_label = "Add Audio Driver"
    bl_description = "Add audio_value(frame) driver to selected object property"
    bl_options = {'REGISTER', 'UNDO'}

    target_property: EnumProperty(
        name="Target Property",
        description="Which property to drive with audio",
        items=[
            ('SCALE_X', "Scale X", "Drive X scale with audio"),
            ('SCALE_Y', "Scale Y", "Drive Y scale with audio"),
            ('SCALE_Z', "Scale Z", "Drive Z scale with audio"),
            ('SCALE_ALL', "Scale All", "Drive all scale axes with audio"),
            ('LOC_Z', "Location Z", "Drive Z location with audio"),
            ('EMISSION', "Emission Strength", "Drive material emission strength"),
        ],
        default='SCALE_Z',
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        scene = context.scene

        # Ensure amplitude curve exists
        if scene.name not in _amplitude_curves:
            self.report({'ERROR'}, "Generate amplitude curve first!")
            return {'CANCELLED'}

        # Ensure driver function is registered
        register_driver_namespace()

        prop = self.target_property

        if prop.startswith('SCALE'):
            indices = {'SCALE_X': [0], 'SCALE_Y': [1], 'SCALE_Z': [2],
                       'SCALE_ALL': [0, 1, 2]}
            for idx in indices[prop]:
                self._add_driver(obj, "scale", idx,
                                 "1.0 + audio_value(frame)")

        elif prop == 'LOC_Z':
            self._add_driver(obj, "location", 2,
                             "audio_value(frame)")

        elif prop == 'EMISSION':
            if obj.active_material and obj.active_material.node_tree:
                # Find Principled BSDF and drive Emission Strength
                for node in obj.active_material.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        input_socket = node.inputs['Emission Strength']
                        self._add_driver_to_socket(
                            obj.active_material.node_tree,
                            input_socket,
                            "audio_value(frame) * 5.0",
                        )
                        break
                else:
                    self.report({'WARNING'}, "No Principled BSDF found in material")
                    return {'CANCELLED'}
            else:
                self.report({'WARNING'}, "No material with nodes on active object")
                return {'CANCELLED'}

        self.report({'INFO'}, f"Audio driver added to {prop}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    @staticmethod
    def _add_driver(obj, data_path: str, index: int, expression: str) -> None:
        """Add a driver with audio_value expression to an object property."""
        obj.driver_remove(data_path, index)
        fc = obj.driver_add(data_path, index)
        driver = fc.driver
        driver.type = 'SCRIPTED'
        driver.expression = expression

        # Add 'frame' variable
        var = driver.variables.new()
        var.name = "frame"
        var.type = 'SINGLE_PROP'
        var.targets[0].id_type = 'SCENE'
        var.targets[0].id = bpy.context.scene
        var.targets[0].data_path = "frame_current"

    @staticmethod
    def _add_driver_to_socket(node_tree, socket, expression: str) -> None:
        """Add a driver to a node socket's default_value."""
        data_path = f'nodes["{socket.node.name}"].inputs[{socket.node.inputs.find(socket.name)}].default_value'
        node_tree.driver_remove(data_path)
        fc = node_tree.driver_add(data_path)
        driver = fc.driver
        driver.type = 'SCRIPTED'
        driver.expression = expression

        var = driver.variables.new()
        var.name = "frame"
        var.type = 'SINGLE_PROP'
        var.targets[0].id_type = 'SCENE'
        var.targets[0].id = bpy.context.scene
        var.targets[0].data_path = "frame_current"


# ── Operator: Remove Audio Drivers ──────────────────────────────────────────

class BEATANALYZER_OT_remove_audio_drivers(Operator):
    """Remove all audio_value drivers from the active object."""

    bl_idname = "beatanalyzer.remove_audio_drivers"
    bl_label = "Remove Audio Drivers"
    bl_description = "Remove all audio_value() drivers from the active object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        removed = 0

        # Check object animation data for drivers
        if obj.animation_data:
            for fc in list(obj.animation_data.drivers):
                if fc.driver and "audio_value" in fc.driver.expression:
                    obj.animation_data.drivers.remove(fc)
                    removed += 1

        # Check material node tree drivers
        if obj.active_material and obj.active_material.node_tree:
            tree = obj.active_material.node_tree
            if tree.animation_data:
                for fc in list(tree.animation_data.drivers):
                    if fc.driver and "audio_value" in fc.driver.expression:
                        tree.animation_data.drivers.remove(fc)
                        removed += 1

        if removed > 0:
            self.report({'INFO'}, f"Removed {removed} audio driver(s)")
        else:
            self.report({'WARNING'}, "No audio drivers found")
        return {'FINISHED'}
