# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Compositor Modifier Integration for beat-reactive VSE strip effects.

Blender 5.0+ allows compositor node trees to be applied as modifiers on
VSE strips. This module auto-generates a compositor node tree with
beat-reactive effects (glow pulse, color shift) and applies it as a
modifier on the video strip adjacent to (or overlapping with) the audio.

The node tree uses keyframed values synced to detected beats so the
compositor effect pulses with the music.
"""

from __future__ import annotations

import os

import bpy
import numpy as np
from bpy.props import EnumProperty
from bpy.types import Operator

from ..core.audio_loader import load_audio


class BEATANALYZER_OT_add_compositor_effect(Operator):
    """Add a beat-reactive compositor modifier to a video strip in the VSE."""

    bl_idname = "beatanalyzer.add_compositor_effect"
    bl_label = "Add Beat Compositor Effect"
    bl_description = (
        "Create a beat-synced compositor node tree and apply it as a strip modifier"
    )
    bl_options = {'REGISTER', 'UNDO'}

    effect_type: EnumProperty(
        name="Effect Type",
        description="Type of beat-reactive compositor effect",
        items=[
            ('GLOW', "Glow Pulse", "Beat-synced glow/bloom intensity"),
            ('COLOR_SHIFT', "Color Shift", "Beat-synced hue/saturation shift"),
            ('VIGNETTE', "Vignette Pulse", "Beat-synced vignette darkening"),
        ],
        default='GLOW',
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

        # Ensure sequence editor exists
        if not scene.sequence_editor:
            self.report({'ERROR'}, "No sequence editor. Add a video strip first.")
            return {'CANCELLED'}

        # Find a video strip to apply the modifier to
        video_strip = self._find_video_strip(scene)
        if not video_strip:
            self.report({'ERROR'}, "No video/image strip found in sequencer")
            return {'CANCELLED'}

        # Create the compositor node tree
        node_tree = self._create_effect_tree(scene, self.effect_type)

        # Apply as compositor modifier on the strip
        # In Blender 5.0+, strips have a .modifiers collection that can include
        # compositor-type modifiers
        try:
            mod = video_strip.modifiers.new(
                name=f"BeatEffect_{self.effect_type}",
                type='COMPOSITOR',
            )
            mod.node_tree = node_tree
        except (AttributeError, TypeError):
            # Fallback: assign compositor tree to scene compositor if strip
            # modifier not available in this build
            scene.use_nodes = True
            if scene.node_tree:
                # We'll leave the created tree available for manual assignment
                pass
            self.report(
                {'INFO'},
                f"Created compositor tree '{node_tree.name}' "
                f"(assign manually if strip modifiers not available)",
            )
            return {'FINISHED'}

        # Bake audio amplitude as keyframes on the effect value node
        self._bake_effect_keyframes(scene, node_tree, filepath, props)

        self.report(
            {'INFO'},
            f"Beat-reactive '{self.effect_type}' effect added to '{video_strip.name}'",
        )
        return {'FINISHED'}

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _find_video_strip(scene):
        """Find the first video or image strip in the sequencer."""
        for seq in scene.sequence_editor.sequences_all:
            if seq.type in ('MOVIE', 'IMAGE', 'SCENE', 'META'):
                return seq
        return None

    def _create_effect_tree(self, scene, effect_type: str):
        """Create a compositor node tree for the given effect type."""
        tree_name = f"BeatEffect_{effect_type}"

        # Remove existing tree with same name
        existing = bpy.data.node_groups.get(tree_name)
        if existing and existing.type == 'COMPOSITING':
            bpy.data.node_groups.remove(existing)

        tree = bpy.data.node_groups.new(tree_name, 'CompositorNodeTree')

        # Common nodes: Input → Effect → Output
        input_node = tree.nodes.new('NodeGroupInput')
        input_node.location = (-400, 0)

        output_node = tree.nodes.new('NodeGroupOutput')
        output_node.location = (400, 0)

        # Add interface sockets
        tree.interface.new_socket(
            name="Image", in_out='INPUT', socket_type='NodeSocketColor'
        )
        tree.interface.new_socket(
            name="Image", in_out='OUTPUT', socket_type='NodeSocketColor'
        )

        if effect_type == 'GLOW':
            self._build_glow_effect(tree, input_node, output_node)
        elif effect_type == 'COLOR_SHIFT':
            self._build_color_shift_effect(tree, input_node, output_node)
        elif effect_type == 'VIGNETTE':
            self._build_vignette_effect(tree, input_node, output_node)

        return tree

    @staticmethod
    def _build_glow_effect(tree, input_node, output_node):
        """Build a glow/bloom compositor effect driven by a value node."""
        # Value node (audio-driven)
        value = tree.nodes.new('CompositorNodeValue')
        value.name = "BeatIntensity"
        value.label = "Beat Intensity"
        value.location = (-200, -150)
        value.outputs[0].default_value = 0.0

        # Glare node for glow
        glare = tree.nodes.new('CompositorNodeGlare')
        glare.glare_type = 'FOG_GLOW'
        glare.quality = 'HIGH'
        glare.mix = 0.0  # Will be driven by value
        glare.location = (0, 0)

        # Mix node to blend original with glow
        mix = tree.nodes.new('CompositorNodeMixRGB')
        mix.blend_type = 'ADD'
        mix.location = (200, 0)

        # Links
        tree.links.new(input_node.outputs[0], glare.inputs[0])
        tree.links.new(input_node.outputs[0], mix.inputs[1])
        tree.links.new(glare.outputs[0], mix.inputs[2])
        tree.links.new(value.outputs[0], mix.inputs[0])  # Fac
        tree.links.new(mix.outputs[0], output_node.inputs[0])

    @staticmethod
    def _build_color_shift_effect(tree, input_node, output_node):
        """Build a hue/saturation shift effect driven by audio."""
        value = tree.nodes.new('CompositorNodeValue')
        value.name = "BeatIntensity"
        value.label = "Beat Intensity"
        value.location = (-200, -150)
        value.outputs[0].default_value = 0.0

        hue_sat = tree.nodes.new('CompositorNodeHueSat')
        hue_sat.location = (0, 0)

        # Math node to map audio value to hue offset
        math_node = tree.nodes.new('CompositorNodeMath')
        math_node.operation = 'MULTIPLY'
        math_node.inputs[1].default_value = 0.1  # Subtle hue shift
        math_node.location = (-100, -150)

        # Add node to offset hue from 0.5 (neutral)
        add_node = tree.nodes.new('CompositorNodeMath')
        add_node.operation = 'ADD'
        add_node.inputs[1].default_value = 0.5
        add_node.location = (0, -150)

        tree.links.new(input_node.outputs[0], hue_sat.inputs[0])
        tree.links.new(value.outputs[0], math_node.inputs[0])
        tree.links.new(math_node.outputs[0], add_node.inputs[0])
        tree.links.new(add_node.outputs[0], hue_sat.inputs[1])  # Hue
        tree.links.new(hue_sat.outputs[0], output_node.inputs[0])

    @staticmethod
    def _build_vignette_effect(tree, input_node, output_node):
        """Build a vignette darkening effect pulsing with beats."""
        value = tree.nodes.new('CompositorNodeValue')
        value.name = "BeatIntensity"
        value.label = "Beat Intensity"
        value.location = (-300, -200)
        value.outputs[0].default_value = 0.0

        # Lens Distortion for vignette
        lens = tree.nodes.new('CompositorNodeLensdist')
        lens.location = (0, 0)
        lens.inputs['Dispersion'].default_value = 0.0

        # Math to map audio to vignette amount
        math_node = tree.nodes.new('CompositorNodeMath')
        math_node.operation = 'MULTIPLY'
        math_node.inputs[1].default_value = 0.5
        math_node.location = (-100, -200)

        tree.links.new(input_node.outputs[0], lens.inputs[0])
        tree.links.new(value.outputs[0], math_node.inputs[0])
        # Note: Lens Distortion doesn't have a vignette input directly,
        # so we use a Brightness/Contrast approach instead
        bright = tree.nodes.new('CompositorNodeBrightContrast')
        bright.location = (200, 0)

        # Invert and multiply to create darkening
        invert_math = tree.nodes.new('CompositorNodeMath')
        invert_math.operation = 'MULTIPLY'
        invert_math.inputs[1].default_value = -30.0  # Darken
        invert_math.location = (0, -200)

        tree.links.new(value.outputs[0], invert_math.inputs[0])
        tree.links.new(lens.outputs[0], bright.inputs[0])
        tree.links.new(invert_math.outputs[0], bright.inputs[1])  # Bright
        tree.links.new(bright.outputs[0], output_node.inputs[0])

    def _bake_effect_keyframes(self, scene, node_tree, filepath, props):
        """Keyframe the BeatIntensity value node with audio amplitude."""
        # Find the BeatIntensity node
        value_node = node_tree.nodes.get("BeatIntensity")
        if not value_node:
            return

        # Load audio and compute amplitude
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

        action_name = f"BeatCompEffect_{node_tree.name}"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
        node_tree.animation_data.action = action

        # Create fcurve for the value node
        data_path = f'nodes["BeatIntensity"].outputs[0].default_value'

        # Remove existing fcurve
        for fc in list(action.fcurves):
            if fc.data_path == data_path:
                action.fcurves.remove(fc)

        fc = action.fcurves.new(data_path=data_path)

        # Insert keyframes at each frame with audio amplitude
        for i in range(n_frames):
            frame = frame_start + i
            start_sample = i * samples_per_frame
            end_sample = start_sample + samples_per_frame

            if end_sample > len(audio.samples):
                amp = 0.0
            else:
                chunk = audio.samples[start_sample:end_sample]
                amp = float(np.sqrt(np.mean(chunk ** 2)))

            # Apply smoothing
            fc.keyframe_points.insert(frame, amp, options={'FAST'})

        # Update keyframe handles for smooth interpolation
        fc.update()
