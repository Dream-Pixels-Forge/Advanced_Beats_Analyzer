# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Index Switch - Beat-Triggered Effect Switching.

Blender 5.1 adds the Index Switch compositor node which selects between
multiple inputs based on an integer index. This module:

1. Categorizes beats into strength indices (0=weak, 1=medium, 2=strong)
2. Keyframes an integer value per frame based on which beat category is active
3. Creates a compositor node tree with Index Switch driven by this integer
4. Each input on the Index Switch can be a different visual effect

This allows automatic per-beat effect variation — strong beats get one
look, medium beats another, and weak beats a third.
"""

from __future__ import annotations

import os

import bpy
import numpy as np
from bpy.types import Operator

from ..core.audio_loader import load_audio


class BEATANALYZER_OT_setup_index_switch(Operator):
    """Create compositor setup with Index Switch node driven by beat strength."""

    bl_idname = "beatanalyzer.setup_index_switch"
    bl_label = "Beat Index Switch"
    bl_description = (
        "Create compositor with Index Switch node that swaps effects "
        "based on beat strength (strong/medium/weak)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.beat_analyzer_props

        if not props.audio_file:
            self.report({'ERROR'}, "No audio file selected")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)
        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            return {'CANCELLED'}

        # Need beat markers for strength categorization
        beat_data = self._get_beat_strength_map(scene, props)
        if not beat_data:
            self.report({'ERROR'}, "No beat markers found. Analyze audio first.")
            return {'CANCELLED'}

        # Enable compositor
        scene.use_nodes = True
        tree = scene.node_tree

        # Build the Index Switch compositor setup
        self._build_index_switch_tree(tree)

        # Keyframe the index value based on beat strengths
        self._keyframe_beat_index(tree, scene, beat_data)

        self.report({'INFO'}, "Beat Index Switch compositor created!")
        return {'FINISHED'}

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_beat_strength_map(scene, props) -> list[tuple[int, int]]:
        """Return list of (frame, strength_index) from timeline markers.

        strength_index: 0=weak, 1=medium, 2=strong
        """
        prefix = props.marker_prefix
        beats = []
        for marker in scene.timeline_markers:
            if not marker.name.startswith(prefix):
                continue
            strength = marker.name.rsplit("_", 1)[-1]
            if strength == "strong":
                idx = 2
            elif strength == "medium":
                idx = 1
            else:
                idx = 0
            beats.append((marker.frame, idx))
        beats.sort(key=lambda x: x[0])
        return beats

    @staticmethod
    def _build_index_switch_tree(tree):
        """Build compositor tree with Index Switch selecting between 3 effects."""
        tree.nodes.clear()

        # Render Layers
        render = tree.nodes.new('CompositorNodeRLayers')
        render.location = (-800, 0)

        # Index value (keyframed by beat strength)
        index_val = tree.nodes.new('CompositorNodeValue')
        index_val.name = "BeatStrengthIndex"
        index_val.label = "Beat Strength Index"
        index_val.outputs[0].default_value = 0.0
        index_val.location = (-600, -300)

        # Convert float to integer for index (using Math FLOOR)
        floor_node = tree.nodes.new('CompositorNodeMath')
        floor_node.operation = 'FLOOR'
        floor_node.location = (-400, -300)

        # ── 3 Effect Branches ───────────────────────────────────────────

        # Branch 0: Weak beats → subtle desaturation
        desat = tree.nodes.new('CompositorNodeHueSat')
        desat.location = (-200, 200)
        # Reduce saturation slightly
        desat.inputs['Saturation Factor'].default_value = 0.7

        # Branch 1: Medium beats → warm color shift
        color_bal = tree.nodes.new('CompositorNodeColorBalance')
        color_bal.location = (-200, 0)
        color_bal.correction_method = 'LIFT_GAMMA_GAIN'
        color_bal.gain = (1.1, 0.95, 0.85)  # Warm shift

        # Branch 2: Strong beats → high contrast + glow
        bright = tree.nodes.new('CompositorNodeBrightContrast')
        bright.inputs['Bright'].default_value = 10.0
        bright.inputs['Contrast'].default_value = 20.0
        bright.location = (-200, -200)

        # Index Switch node (Blender 5.1+)
        index_switch = tree.nodes.new('CompositorNodeIndexSwitch')
        index_switch.location = (200, 0)

        # Composite output
        composite = tree.nodes.new('CompositorNodeComposite')
        composite.location = (500, 0)

        # Viewer
        viewer = tree.nodes.new('CompositorNodeViewer')
        viewer.location = (500, -200)

        # ── Links ───────────────────────────────────────────────────────

        # Feed render to all 3 branches
        tree.links.new(render.outputs['Image'], desat.inputs['Image'])
        tree.links.new(render.outputs['Image'], color_bal.inputs['Image'])
        tree.links.new(render.outputs['Image'], bright.inputs['Image'])

        # Connect branches to Index Switch inputs
        tree.links.new(desat.outputs['Image'], index_switch.inputs[0])
        tree.links.new(color_bal.outputs['Image'], index_switch.inputs[1])
        tree.links.new(bright.outputs['Image'], index_switch.inputs[2])

        # Index value → Index Switch selector
        tree.links.new(index_val.outputs[0], floor_node.inputs[0])
        tree.links.new(floor_node.outputs[0], index_switch.inputs['Index'])

        # Output
        tree.links.new(index_switch.outputs[0], composite.inputs[0])
        tree.links.new(index_switch.outputs[0], viewer.inputs[0])

    @staticmethod
    def _keyframe_beat_index(tree, scene, beat_data: list[tuple[int, int]]):
        """Keyframe the BeatStrengthIndex value based on beat markers."""
        index_node = tree.nodes.get("BeatStrengthIndex")
        if not index_node:
            return

        if not tree.animation_data:
            tree.animation_data_create()

        action_name = "BeatIndexSwitch_Action"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
        tree.animation_data.action = action

        data_path = 'nodes["BeatStrengthIndex"].outputs[0].default_value'

        # Remove existing
        for fc in list(action.fcurves):
            if fc.data_path == data_path:
                action.fcurves.remove(fc)

        fc = action.fcurves.new(data_path=data_path)

        # Default: index 0 (weak/no beat)
        fc.keyframe_points.insert(scene.frame_start, 0.0, options={'FAST'})

        # At each beat, set the index to the strength category
        # Hold for a few frames then return to 0
        hold_frames = 3
        for frame, strength_idx in beat_data:
            # Set strength index at beat frame
            fc.keyframe_points.insert(frame, float(strength_idx), options={'FAST'})
            # Return to 0 after hold duration
            fc.keyframe_points.insert(
                frame + hold_frames, 0.0, options={'FAST'}
            )

        # Set interpolation to CONSTANT for sharp switching
        fc.update()
        for kp in fc.keyframe_points:
            kp.interpolation = 'CONSTANT'
