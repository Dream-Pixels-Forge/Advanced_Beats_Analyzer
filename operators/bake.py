# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Operators for baking audio to shader (AVS) and geometry (AVG) value nodes."""

from __future__ import annotations

import os

import bpy
from bpy.types import Operator


# ── Shared Utilities ────────────────────────────────────────────────────────

def _get_graph_editor_area(context):
    """Return a GRAPH_EDITOR area, creating a temporary one if needed."""
    for area in context.screen.areas:
        if area.type == 'GRAPH_EDITOR':
            return area, None

    # Temporarily convert current area
    area = context.area
    original = area.type
    area.type = 'GRAPH_EDITOR'
    return area, original


def _bake_sound_to_fcurve(context, area, filepath: str) -> None:
    """Call graph.sound_to_samples with proper temp_override."""
    with context.temp_override(area=area):
        bpy.ops.graph.sound_to_samples(filepath=filepath)


# ── Shader Bake ─────────────────────────────────────────────────────────────

class BEATANALYZER_OT_bake_to_shader(Operator):
    """Bake audio amplitude to an Audio Value Shader (AVS) node."""

    bl_idname = "beatanalyzer.bake_to_shader"
    bl_label = "Bake to AVS"
    bl_description = "Bake audio to a shader value node for material animation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        obj = context.active_object

        if not props.audio_file or not os.path.isfile(bpy.path.abspath(props.audio_file)):
            self.report({'WARNING'}, "No valid audio file selected.")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)

        # Ensure material
        if not obj.active_material:
            mat = bpy.data.materials.new(name="Audio Visualizer")
            mat.use_nodes = True
            obj.active_material = mat
        else:
            obj.active_material.use_nodes = True

        tree = obj.active_material.node_tree
        value_node = self._find_or_create_node(tree)

        # Keyframe & fcurve setup
        fcurve = self._setup_fcurve(tree, value_node)
        if not fcurve:
            self.report({'ERROR'}, "Could not create F-Curve for audio baking")
            return {'CANCELLED'}

        area, original_type = _get_graph_editor_area(context)
        try:
            _bake_sound_to_fcurve(context, area, filepath)
            self._add_modifiers(fcurve, props)
        except Exception as exc:
            self.report({'ERROR'}, f"Bake failed: {exc}")
            return {'CANCELLED'}
        finally:
            if original_type:
                area.type = original_type

        self.report({'INFO'}, "Audio baked to shader value node successfully!")
        return {'FINISHED'}

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _find_or_create_node(tree):
        for node in tree.nodes:
            if node.type == 'VALUE' and node.label == "Audio Value Shader":
                return node

        # Create full node setup
        value = tree.nodes.new('ShaderNodeValue')
        value.label = "Audio Value Shader"
        value.name = "Audio Value Shader"
        value.location = (-600, 0)

        noise = tree.nodes.new('ShaderNodeTexNoise')
        noise.location = (-400, 0)

        ramp = tree.nodes.new('ShaderNodeValToRGB')
        ramp.location = (-200, 0)
        ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
        ramp.color_ramp.elements[1].color = (1, 1, 1, 1)

        principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)
        principled.inputs['Emission Strength'].default_value = 1.0

        output = tree.nodes.new('ShaderNodeOutputMaterial')
        output.location = (200, 0)

        tree.links.new(value.outputs[0], noise.inputs['Scale'])
        tree.links.new(noise.outputs['Fac'], ramp.inputs[0])
        tree.links.new(ramp.outputs[0], principled.inputs['Emission Color'])
        tree.links.new(principled.outputs[0], output.inputs[0])

        return value

    @staticmethod
    def _setup_fcurve(tree, value_node):
        if not tree.animation_data:
            tree.animation_data_create()

        action = bpy.data.actions.new(name=f"AudioAnim_{value_node.name}")
        tree.animation_data.action = action

        # Remove pre-existing fcurves for this node
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

    @staticmethod
    def _add_modifiers(fcurve, props):
        for mod in list(fcurve.modifiers):
            fcurve.modifiers.remove(mod)

        env = fcurve.modifiers.new('ENVELOPE')
        env.reference_value = 0.5
        if props.bake_smoothing > 0:
            env.influence = props.bake_smoothing / 10.0

        lim = fcurve.modifiers.new('LIMITS')
        lim.mute = False
        lim.min_y = 0.0
        lim.max_y = 5.0


# ── Geometry Bake ───────────────────────────────────────────────────────────

class BEATANALYZER_OT_bake_to_geometry(Operator):
    """Bake audio amplitude to an Audio Value Geometry (AVG) node."""

    bl_idname = "beatanalyzer.bake_to_geometry"
    bl_label = "Bake to AVG"
    bl_description = "Bake audio to a geometry nodes value node"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        obj = context.active_object

        if not props.audio_file or not os.path.isfile(bpy.path.abspath(props.audio_file)):
            self.report({'WARNING'}, "No valid audio file selected.")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)

        geo_tree = self._ensure_geometry_tree(obj)
        value_node = self._find_or_create_node(geo_tree)

        fcurve = self._setup_fcurve(geo_tree, value_node)
        if not fcurve:
            self.report({'ERROR'}, "Could not create F-Curve for audio baking")
            return {'CANCELLED'}

        area, original_type = _get_graph_editor_area(context)
        try:
            _bake_sound_to_fcurve(context, area, filepath)
            self._add_modifiers(fcurve, props)
        except Exception as exc:
            self.report({'ERROR'}, f"Bake failed: {exc}")
            return {'CANCELLED'}
        finally:
            if original_type:
                area.type = original_type

        self.report({'INFO'}, "Audio baked to geometry value node successfully!")
        return {'FINISHED'}

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_geometry_tree(obj):
        """Return a GeometryNodeTree, creating modifier+group if needed."""
        geo_mod = None
        for mod in obj.modifiers:
            if mod.type == 'NODES':
                geo_mod = mod
                break

        if not geo_mod:
            geo_mod = obj.modifiers.new(name="Audio Visualizer", type='NODES')

        if not geo_mod.node_group:
            tree = bpy.data.node_groups.new("Audio Visualizer", 'GeometryNodeTree')
            # Blender 4.0+ / 5.x uses node_tree.interface for sockets
            tree.interface.new_socket(
                name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry'
            )
            tree.interface.new_socket(
                name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry'
            )
            geo_mod.node_group = tree

        return geo_mod.node_group

    @staticmethod
    def _find_or_create_node(tree):
        for node in tree.nodes:
            if node.type == 'VALUE' and node.label == "Audio Value Geometry":
                return node

        # Ensure group I/O nodes
        group_in = group_out = None
        for node in tree.nodes:
            if node.type == 'GROUP_INPUT':
                group_in = node
            elif node.type == 'GROUP_OUTPUT':
                group_out = node

        if not group_in:
            group_in = tree.nodes.new('NodeGroupInput')
            group_in.location = (-600, 0)
        if not group_out:
            group_out = tree.nodes.new('NodeGroupOutput')
            group_out.location = (400, 0)

        # Pass-through link
        if not any(
            lnk.from_node == group_in and lnk.to_node == group_out
            for lnk in tree.links
        ):
            if 'Geometry' in group_in.outputs and 'Geometry' in group_out.inputs:
                tree.links.new(group_in.outputs['Geometry'], group_out.inputs['Geometry'])

        value = tree.nodes.new('ShaderNodeValue')
        value.label = "Audio Value Geometry"
        value.name = "Audio Value Geometry"
        value.location = (-400, -300)

        noise = tree.nodes.new('ShaderNodeTexNoise')
        noise.noise_dimensions = '4D'
        noise.location = (-200, -300)

        tree.links.new(value.outputs[0], noise.inputs['W'])
        return value

    @staticmethod
    def _setup_fcurve(tree, value_node):
        if not tree.animation_data:
            tree.animation_data_create()

        action = bpy.data.actions.new(name=f"AudioAnim_{value_node.name}")
        tree.animation_data.action = action

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

    @staticmethod
    def _add_modifiers(fcurve, props):
        for mod in list(fcurve.modifiers):
            fcurve.modifiers.remove(mod)

        env = fcurve.modifiers.new('ENVELOPE')
        env.reference_value = 0.0
        if props.bake_smoothing > 0:
            env.influence = props.bake_smoothing / 20.0

        lim = fcurve.modifiers.new('LIMITS')
        lim.mute = False
        lim.min_y = -2.0
        lim.max_y = 2.0
