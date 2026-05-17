# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Shader Raycast Node - Audio-Reactive NPR Effects.

Blender 5.1 introduces a Raycast shader node that casts rays against
scene geometry in both Cycles and EEVEE. Combined with the audio Value
node, this enables:

- Beat-pulsing inner glow (raycast inward from surface)
- Audio-reactive outline thickness (raycast along normals)
- Rhythm-driven subsurface reveal (X-ray synced to bass hits)

This module creates a material node setup combining the Raycast node
with the audio-driven Value node for NPR/stylized effects.
"""

from __future__ import annotations

import os

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from .bake import _get_graph_editor_area, _bake_sound_to_fcurve


class BEATANALYZER_OT_setup_raycast_npr(Operator):
    """Create an audio-reactive NPR shader using the Raycast node."""

    bl_idname = "beatanalyzer.setup_raycast_npr"
    bl_label = "Audio Raycast NPR"
    bl_description = (
        "Create NPR shader effects using the Raycast node (5.1) "
        "driven by audio amplitude"
    )
    bl_options = {'REGISTER', 'UNDO'}

    effect_mode: EnumProperty(
        name="NPR Effect",
        description="Type of audio-reactive NPR effect",
        items=[
            ('INNER_GLOW', "Inner Glow", "Beat-pulsing inner glow via inward raycast"),
            ('OUTLINE', "Audio Outline", "Outline thickness modulated by audio"),
            ('XRAY', "X-Ray Reveal", "Subsurface X-ray synced to beats"),
        ],
        default='INNER_GLOW',
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        obj = context.active_object

        if not props.audio_file or not os.path.isfile(bpy.path.abspath(props.audio_file)):
            self.report({'WARNING'}, "No valid audio file selected.")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)

        # Ensure material
        if not obj.active_material:
            mat = bpy.data.materials.new(name="Audio NPR")
            mat.use_nodes = True
            obj.active_material = mat
        else:
            obj.active_material.use_nodes = True

        mat = obj.active_material
        tree = mat.node_tree

        # Build the selected NPR effect
        value_node = self._build_effect(tree, self.effect_mode)

        # Bake audio to the value node
        if value_node:
            fcurve = self._setup_fcurve(tree, value_node)
            if fcurve:
                area, original_type = _get_graph_editor_area(context)
                try:
                    _bake_sound_to_fcurve(context, area, filepath)
                except Exception as exc:
                    self.report({'WARNING'}, f"Audio bake issue: {exc}")
                finally:
                    if original_type:
                        area.type = original_type

        self.report({'INFO'}, f"Audio NPR effect '{self.effect_mode}' created!")
        return {'FINISHED'}

    # ── Effect Builders ─────────────────────────────────────────────────

    def _build_effect(self, tree, mode: str):
        """Build the shader node setup for the given NPR mode."""
        # Clear existing nodes
        tree.nodes.clear()

        if mode == 'INNER_GLOW':
            return self._build_inner_glow(tree)
        elif mode == 'OUTLINE':
            return self._build_outline(tree)
        elif mode == 'XRAY':
            return self._build_xray(tree)
        return None

    @staticmethod
    def _build_inner_glow(tree):
        """Inner glow: raycast inward, use hit distance for glow intensity.

        Audio modulates glow brightness on beat hits.
        """
        # Audio Value
        audio_val = tree.nodes.new('ShaderNodeValue')
        audio_val.name = "Audio NPR Value"
        audio_val.label = "Audio NPR Value"
        audio_val.location = (-800, -200)
        audio_val.outputs[0].default_value = 0.0

        # Geometry node for position/normal
        geometry = tree.nodes.new('ShaderNodeNewGeometry')
        geometry.location = (-800, 200)

        # Vector Math: invert normal for inward ray
        invert = tree.nodes.new('ShaderNodeVectorMath')
        invert.operation = 'SCALE'
        invert.inputs['Scale'].default_value = -1.0
        invert.location = (-600, 200)

        # Raycast node (Blender 5.1+)
        raycast = tree.nodes.new('ShaderNodeRaycast')
        raycast.location = (-400, 200)

        # Math: map hit distance to glow factor
        map_range = tree.nodes.new('ShaderNodeMapRange')
        map_range.inputs['From Min'].default_value = 0.0
        map_range.inputs['From Max'].default_value = 0.5
        map_range.inputs['To Min'].default_value = 1.0
        map_range.inputs['To Max'].default_value = 0.0
        map_range.location = (-200, 200)

        # Multiply glow by audio amplitude
        multiply = tree.nodes.new('ShaderNodeMath')
        multiply.operation = 'MULTIPLY'
        multiply.location = (0, 100)

        # Emission for glow
        emission = tree.nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = (0.2, 0.8, 1.0, 1.0)
        emission.location = (200, 200)

        # Base Principled BSDF
        principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (200, -100)

        # Mix Shader: blend base + glow
        mix_shader = tree.nodes.new('ShaderNodeMixShader')
        mix_shader.location = (400, 100)

        # Output
        output = tree.nodes.new('ShaderNodeOutputMaterial')
        output.location = (600, 100)

        # Links
        tree.links.new(geometry.outputs['Normal'], invert.inputs[0])
        tree.links.new(geometry.outputs['Position'], raycast.inputs['Origin'])
        tree.links.new(invert.outputs[0], raycast.inputs['Direction'])
        tree.links.new(raycast.outputs['Distance'], map_range.inputs['Value'])
        tree.links.new(map_range.outputs[0], multiply.inputs[0])
        tree.links.new(audio_val.outputs[0], multiply.inputs[1])
        tree.links.new(multiply.outputs[0], mix_shader.inputs['Fac'])
        tree.links.new(multiply.outputs[0], emission.inputs['Strength'])
        tree.links.new(principled.outputs[0], mix_shader.inputs[1])
        tree.links.new(emission.outputs[0], mix_shader.inputs[2])
        tree.links.new(mix_shader.outputs[0], output.inputs[0])

        return audio_val

    @staticmethod
    def _build_outline(tree):
        """Audio-modulated outline: raycast along normal, use distance for edge detection.

        Audio amplitude controls outline visibility/thickness.
        """
        # Audio Value
        audio_val = tree.nodes.new('ShaderNodeValue')
        audio_val.name = "Audio NPR Value"
        audio_val.label = "Audio NPR Value"
        audio_val.location = (-800, -200)
        audio_val.outputs[0].default_value = 0.0

        # Geometry
        geometry = tree.nodes.new('ShaderNodeNewGeometry')
        geometry.location = (-800, 200)

        # Raycast along normal
        raycast = tree.nodes.new('ShaderNodeRaycast')
        raycast.location = (-400, 200)

        # Compare distance to threshold for edge detection
        compare = tree.nodes.new('ShaderNodeMath')
        compare.operation = 'LESS_THAN'
        compare.location = (-200, 200)

        # Audio controls the threshold (edge width)
        threshold = tree.nodes.new('ShaderNodeMath')
        threshold.operation = 'MULTIPLY'
        threshold.inputs[1].default_value = 0.3  # Base threshold
        threshold.location = (-400, -100)

        # Black for outline
        outline_color = tree.nodes.new('ShaderNodeEmission')
        outline_color.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
        outline_color.inputs['Strength'].default_value = 0.0
        outline_color.location = (0, 300)

        # Base material
        principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, -100)

        # Mix based on edge
        mix_shader = tree.nodes.new('ShaderNodeMixShader')
        mix_shader.location = (300, 100)

        output = tree.nodes.new('ShaderNodeOutputMaterial')
        output.location = (500, 100)

        # Links
        tree.links.new(geometry.outputs['Position'], raycast.inputs['Origin'])
        tree.links.new(geometry.outputs['Normal'], raycast.inputs['Direction'])
        tree.links.new(audio_val.outputs[0], threshold.inputs[0])
        tree.links.new(threshold.outputs[0], compare.inputs[1])
        tree.links.new(raycast.outputs['Distance'], compare.inputs[0])
        tree.links.new(compare.outputs[0], mix_shader.inputs['Fac'])
        tree.links.new(principled.outputs[0], mix_shader.inputs[1])
        tree.links.new(outline_color.outputs[0], mix_shader.inputs[2])
        tree.links.new(mix_shader.outputs[0], output.inputs[0])

        return audio_val

    @staticmethod
    def _build_xray(tree):
        """X-Ray reveal: raycast inward, show internal structure on beats.

        Audio amplitude controls the transparency/X-ray reveal depth.
        """
        # Audio Value
        audio_val = tree.nodes.new('ShaderNodeValue')
        audio_val.name = "Audio NPR Value"
        audio_val.label = "Audio NPR Value"
        audio_val.location = (-800, -300)
        audio_val.outputs[0].default_value = 0.0

        # Geometry
        geometry = tree.nodes.new('ShaderNodeNewGeometry')
        geometry.location = (-800, 200)

        # Invert normal for inward raycast
        invert = tree.nodes.new('ShaderNodeVectorMath')
        invert.operation = 'SCALE'
        invert.inputs['Scale'].default_value = -1.0
        invert.location = (-600, 200)

        # Raycast inward
        raycast = tree.nodes.new('ShaderNodeRaycast')
        raycast.location = (-400, 200)

        # Map distance to reveal factor
        map_range = tree.nodes.new('ShaderNodeMapRange')
        map_range.inputs['From Min'].default_value = 0.0
        map_range.inputs['From Max'].default_value = 1.0
        map_range.inputs['To Min'].default_value = 0.0
        map_range.inputs['To Max'].default_value = 1.0
        map_range.location = (-200, 200)

        # Multiply by audio for beat-synced reveal
        multiply = tree.nodes.new('ShaderNodeMath')
        multiply.operation = 'MULTIPLY'
        multiply.location = (0, 0)

        # Surface material
        principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
        principled.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
        principled.location = (200, 200)

        # X-ray emission (internal reveal)
        xray_emission = tree.nodes.new('ShaderNodeEmission')
        xray_emission.inputs['Color'].default_value = (0.0, 1.0, 0.5, 1.0)
        xray_emission.location = (200, -100)

        # Mix based on audio × depth
        mix_shader = tree.nodes.new('ShaderNodeMixShader')
        mix_shader.location = (400, 100)

        # Transparent for X-ray look
        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
        transparent.location = (200, -300)

        # Final mix: opaque vs transparent based on audio
        final_mix = tree.nodes.new('ShaderNodeMixShader')
        final_mix.location = (600, 100)

        output = tree.nodes.new('ShaderNodeOutputMaterial')
        output.location = (800, 100)

        # Links
        tree.links.new(geometry.outputs['Normal'], invert.inputs[0])
        tree.links.new(geometry.outputs['Position'], raycast.inputs['Origin'])
        tree.links.new(invert.outputs[0], raycast.inputs['Direction'])
        tree.links.new(raycast.outputs['Distance'], map_range.inputs['Value'])
        tree.links.new(map_range.outputs[0], multiply.inputs[0])
        tree.links.new(audio_val.outputs[0], multiply.inputs[1])
        tree.links.new(multiply.outputs[0], mix_shader.inputs['Fac'])
        tree.links.new(principled.outputs[0], mix_shader.inputs[1])
        tree.links.new(xray_emission.outputs[0], mix_shader.inputs[2])
        tree.links.new(audio_val.outputs[0], final_mix.inputs['Fac'])
        tree.links.new(mix_shader.outputs[0], final_mix.inputs[1])
        tree.links.new(transparent.outputs[0], final_mix.inputs[2])
        tree.links.new(final_mix.outputs[0], output.inputs[0])

        return audio_val

    # ── FCurve Setup ────────────────────────────────────────────────────

    @staticmethod
    def _setup_fcurve(tree, value_node):
        """Set up an fcurve for audio baking on the value node."""
        if not tree.animation_data:
            tree.animation_data_create()

        action_name = f"AudioNPR_{tree.id_data.name}"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
        tree.animation_data.action = action

        # Remove existing fcurves for this node
        for fc in list(action.fcurves):
            if value_node.name in fc.data_path:
                action.fcurves.remove(fc)

        value_node.outputs[0].default_value = 0.0
        value_node.outputs[0].keyframe_insert(data_path="default_value", frame=1)

        for fc in action.fcurves:
            if "default_value" in fc.data_path and value_node.name in fc.data_path:
                fc.select = True
                fc.hide = False
                return fc
        return None
