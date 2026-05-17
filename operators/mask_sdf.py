# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Mask to SDF - Beat-Reactive Typography/Logo Animation.

Blender 5.1 introduces the Mask to SDF compositor node which converts
any image or shape into a signed distance field. By driving the SDF
threshold with audio amplitude, we get pulsing/dissolving text effects
perfectly synced to beats.

Workflow:
1. User creates a text object or imports a logo/mask
2. This operator creates a compositor node tree with:
   Render Layers → Mask to SDF → Threshold (audio-driven) → Output
3. Audio amplitude keyframes the threshold value so the text
   expands/contracts with beat energy
"""

from __future__ import annotations

import os

import bpy
import numpy as np
from bpy.props import FloatProperty
from bpy.types import Operator

from ..core.audio_loader import load_audio


class BEATANALYZER_OT_setup_mask_sdf(Operator):
    """Create beat-reactive typography/logo effect using Mask to SDF node."""

    bl_idname = "beatanalyzer.setup_mask_sdf"
    bl_label = "Beat-Reactive SDF Text"
    bl_description = (
        "Create compositor setup with Mask to SDF node where "
        "audio amplitude drives the SDF threshold for pulsing text effects"
    )
    bl_options = {'REGISTER', 'UNDO'}

    threshold_min: FloatProperty(
        name="Threshold Min",
        description="SDF threshold at zero amplitude (text smallest)",
        default=0.3,
        min=0.0,
        max=1.0,
    )

    threshold_max: FloatProperty(
        name="Threshold Max",
        description="SDF threshold at max amplitude (text largest)",
        default=0.8,
        min=0.0,
        max=1.0,
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

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

        # Enable compositor
        scene.use_nodes = True

        # Create the SDF compositor node tree
        node_tree = self._setup_compositor_sdf(scene)

        # Bake audio amplitude to the threshold value
        self._bake_threshold_keyframes(
            scene, node_tree, filepath, props,
            self.threshold_min, self.threshold_max,
        )

        self.report({'INFO'}, "Beat-reactive SDF typography effect created!")
        return {'FINISHED'}

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _setup_compositor_sdf(scene):
        """Set up the scene compositor with Mask to SDF pipeline."""
        tree = scene.node_tree

        # Clear existing nodes
        tree.nodes.clear()

        # Render Layers input
        render_layers = tree.nodes.new('CompositorNodeRLayers')
        render_layers.location = (-600, 0)

        # Mask to SDF node (Blender 5.1+)
        mask_sdf = tree.nodes.new('CompositorNodeMaskToSDF')
        mask_sdf.location = (-200, 0)

        # Value node for audio-driven threshold
        threshold_val = tree.nodes.new('CompositorNodeValue')
        threshold_val.name = "AudioSDFThreshold"
        threshold_val.label = "Audio SDF Threshold"
        threshold_val.outputs[0].default_value = 0.5
        threshold_val.location = (-400, -200)

        # Math node: compare SDF value against threshold
        compare = tree.nodes.new('CompositorNodeMath')
        compare.operation = 'GREATER_THAN'
        compare.location = (0, 0)

        # Color ramp for stylized output
        color_ramp = tree.nodes.new('CompositorNodeValToRGB')
        color_ramp.location = (200, 0)
        color_ramp.color_ramp.elements[0].position = 0.0
        color_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
        color_ramp.color_ramp.elements[1].position = 1.0
        color_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

        # Alpha Over to composite SDF result over render
        alpha_over = tree.nodes.new('CompositorNodeAlphaOver')
        alpha_over.location = (400, 0)

        # Composite output
        composite = tree.nodes.new('CompositorNodeComposite')
        composite.location = (600, 0)

        # Viewer for preview
        viewer = tree.nodes.new('CompositorNodeViewer')
        viewer.location = (600, -200)

        # Links
        # Render → Mask to SDF (use alpha channel as mask source)
        tree.links.new(render_layers.outputs['Alpha'], mask_sdf.inputs[0])

        # SDF output → compare against threshold
        tree.links.new(mask_sdf.outputs[0], compare.inputs[0])
        tree.links.new(threshold_val.outputs[0], compare.inputs[1])

        # Compare result → Color Ramp for stylization
        tree.links.new(compare.outputs[0], color_ramp.inputs['Fac'])

        # Composite: render image + SDF text overlay
        tree.links.new(render_layers.outputs['Image'], alpha_over.inputs[1])
        tree.links.new(color_ramp.outputs['Image'], alpha_over.inputs[2])

        # To output
        tree.links.new(alpha_over.outputs[0], composite.inputs[0])
        tree.links.new(alpha_over.outputs[0], viewer.inputs[0])

        return tree

    @staticmethod
    def _bake_threshold_keyframes(
        scene, node_tree, filepath, props,
        thresh_min: float, thresh_max: float,
    ):
        """Keyframe the SDF threshold value with audio amplitude."""
        # Find the threshold node
        threshold_node = node_tree.nodes.get("AudioSDFThreshold")
        if not threshold_node:
            return

        # Load audio
        try:
            audio = load_audio(filepath)
        except Exception:
            return

        fps = scene.render.fps
        frame_start = scene.frame_start
        frame_end = scene.frame_end
        n_frames = frame_end - frame_start + 1
        samples_per_frame = int(audio.sample_rate / fps)

        # Ensure animation data on the compositor tree
        if not node_tree.animation_data:
            node_tree.animation_data_create()

        action_name = "BeatSDF_Threshold"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
        node_tree.animation_data.action = action

        # Data path for the threshold value
        data_path = 'nodes["AudioSDFThreshold"].outputs[0].default_value'

        # Remove existing fcurve
        for fc in list(action.fcurves):
            if fc.data_path == data_path:
                action.fcurves.remove(fc)

        fc = action.fcurves.new(data_path=data_path)

        # Compute per-frame amplitude and map to threshold range
        for i in range(n_frames):
            frame = frame_start + i
            start_sample = i * samples_per_frame
            end_sample = start_sample + samples_per_frame

            if end_sample > len(audio.samples):
                amp = 0.0
            else:
                chunk = audio.samples[start_sample:end_sample]
                amp = float(np.sqrt(np.mean(chunk ** 2)))

            # Map amplitude [0, 1] → [thresh_min, thresh_max]
            threshold = thresh_min + amp * (thresh_max - thresh_min)
            fc.keyframe_points.insert(frame, threshold, options={'FAST'})

        fc.update()
