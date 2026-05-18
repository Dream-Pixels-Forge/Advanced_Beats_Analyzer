# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Light Path Intensity - Audio-Driven Lighting Atmosphere.

Blender 5.1 adds the ability to control Light Path node intensity
globally. This module modulates indirect lighting intensity based on
audio amplitude, creating a club-lighting feel where bass hits dim
indirect light (dramatic) and high-energy sections brighten the scene.

Implementation approach:
- Creates a World shader node setup with a Light Path node
- Uses a Value node (audio-driven) to control the indirect light
  contribution via a Mix Shader between full and reduced environment
- Keyframes the value node with audio amplitude (inverted for dimming
  on beats, or normal for brightening)
"""

from __future__ import annotations

import os

import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty
from bpy.types import Operator

from ..core.audio_loader import load_audio


class BEATANALYZER_OT_setup_light_path_audio(Operator):
    """Modulate indirect lighting intensity with audio amplitude."""

    bl_idname = "beatanalyzer.setup_light_path_audio"
    bl_label = "Audio Lighting Atmosphere"
    bl_description = (
        "Control indirect lighting intensity with audio for "
        "club-lighting or dramatic atmosphere effects"
    )
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="Lighting Mode",
        description="How audio affects indirect lighting",
        items=[
            ('DIM_ON_BEAT', "Dim on Beat", "Bass hits darken indirect light (dramatic)"),
            ('BRIGHT_ON_BEAT', "Brighten on Beat", "Beats increase scene brightness"),
            ('PULSE', "Pulse", "Oscillate between dim and bright on beats"),
        ],
        default='DIM_ON_BEAT',
    )

    intensity_range: FloatProperty(
        name="Effect Intensity",
        description="How much the lighting changes (0=subtle, 1=extreme)",
        default=0.6,
        min=0.1,
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

        # Set up the world shader
        world = self._ensure_world(scene)
        tree = world.node_tree
        value_node = self._build_light_path_setup(tree)

        # Bake audio to the value node
        self._bake_lighting_keyframes(
            scene, tree, filepath, props, self.mode, self.intensity_range
        )

        self.report(
            {'INFO'},
            f"Audio lighting atmosphere created [{self.mode}]",
        )
        return {'FINISHED'}

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_world(scene):
        """Ensure scene has a world with use_nodes enabled."""
        if not scene.world:
            scene.world = bpy.data.worlds.new("AudioWorld")
        scene.world.use_nodes = True
        return scene.world

    @staticmethod
    def _build_light_path_setup(tree):
        """Build world shader with Light Path intensity control.

        Returns the audio Value node for keyframing.
        """
        tree.nodes.clear()

        # Background (full environment)
        bg_full = tree.nodes.new('ShaderNodeBackground')
        bg_full.label = "Full Environment"
        bg_full.inputs['Strength'].default_value = 1.0
        bg_full.inputs['Color'].default_value = (0.05, 0.05, 0.08, 1.0)
        bg_full.location = (-400, 200)

        # Background (dimmed/reduced)
        bg_dim = tree.nodes.new('ShaderNodeBackground')
        bg_dim.label = "Dimmed Environment"
        bg_dim.inputs['Strength'].default_value = 0.1
        bg_dim.inputs['Color'].default_value = (0.02, 0.02, 0.04, 1.0)
        bg_dim.location = (-400, -100)

        # Light Path node (controls what type of ray is being evaluated)
        light_path = tree.nodes.new('ShaderNodeLightPath')
        light_path.location = (-600, 0)

        # Audio Value node
        audio_val = tree.nodes.new('ShaderNodeValue')
        audio_val.name = "AudioLightIntensity"
        audio_val.label = "Audio Light Intensity"
        audio_val.outputs[0].default_value = 0.0
        audio_val.location = (-600, -300)

        # Math: combine Light Path indirect flag with audio value
        # We want: on indirect rays, use audio to control contribution
        math_mult = tree.nodes.new('ShaderNodeMath')
        math_mult.operation = 'MULTIPLY'
        math_mult.location = (-200, -200)

        # Mix Shader: blend between full and dimmed based on audio
        mix_shader = tree.nodes.new('ShaderNodeMixShader')
        mix_shader.location = (0, 100)

        # World Output
        output = tree.nodes.new('ShaderNodeOutputWorld')
        output.location = (200, 100)

        # Links
        # Light Path "Is Diffuse Ray" → multiply with audio
        tree.links.new(light_path.outputs['Is Diffuse Ray'], math_mult.inputs[0])
        tree.links.new(audio_val.outputs[0], math_mult.inputs[1])

        # Mix factor: audio × light_path_indirect
        tree.links.new(math_mult.outputs[0], mix_shader.inputs['Fac'])
        tree.links.new(bg_full.outputs[0], mix_shader.inputs[1])
        tree.links.new(bg_dim.outputs[0], mix_shader.inputs[2])

        # Output
        tree.links.new(mix_shader.outputs[0], output.inputs[0])

        return audio_val

    @staticmethod
    def _bake_lighting_keyframes(
        scene, node_tree, filepath, props,
        mode: str, intensity_range: float,
    ):
        """Keyframe the audio lighting value node."""
        value_node = node_tree.nodes.get("AudioLightIntensity")
        if not value_node:
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

        # Ensure animation data
        if not node_tree.animation_data:
            node_tree.animation_data_create()

        action_name = "AudioLightPath_Action"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
        node_tree.animation_data.action = action

        data_path = 'nodes["AudioLightIntensity"].outputs[0].default_value'

        # Remove existing
        for fc in list(action.fcurves):
            if fc.data_path == data_path:
                action.fcurves.remove(fc)

        fc = action.fcurves.new(data_path=data_path)

        for i in range(n_frames):
            frame = frame_start + i
            start_sample = i * samples_per_frame
            end_sample = start_sample + samples_per_frame

            if end_sample > len(audio.samples):
                amp = 0.0
            else:
                chunk = audio.samples[start_sample:end_sample]
                amp = float(np.sqrt(np.mean(chunk ** 2)))

            # Apply mode
            if mode == 'DIM_ON_BEAT':
                # Invert: high amplitude → high mix factor → more dimming
                value = amp * intensity_range
            elif mode == 'BRIGHT_ON_BEAT':
                # Normal: high amplitude → high value but we invert mix
                value = (1.0 - amp) * intensity_range
            else:  # PULSE
                # Oscillate around 0.5
                value = 0.5 + (amp - 0.5) * intensity_range

            fc.keyframe_points.insert(frame, value, options={'FAST'})

        fc.update()
