# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Audio-Reactive Volume Geometry Nodes setup.

Blender 5.0+ Geometry Nodes supports volumes natively (density grids,
velocity fields, dilation/erosion nodes). This module creates a Geometry
Nodes modifier that drives volume density dilation with an audio Value
node, producing a pulsing volumetric aura that expands/contracts with
the beat.

Node tree structure:
  GroupInput(Geometry) ─┐
                        ├─► Mesh to Volume ─► Volume to Mesh ─► GroupOutput
  AudioValue ─► Math(Multiply) ─► Dilation input on Mesh to Volume
"""

from __future__ import annotations

import os

import bpy
from bpy.types import Operator

from .bake import _get_graph_editor_area, _bake_sound_to_fcurve


class BEATANALYZER_OT_setup_audio_volume(Operator):
    """Create an audio-reactive volume effect using Geometry Nodes."""

    bl_idname = "beatanalyzer.setup_audio_volume"
    bl_label = "Audio-Reactive Volume"
    bl_description = (
        "Create a Geometry Nodes setup where audio amplitude drives "
        "volume density/dilation for pulsing fog effects"
    )
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

        # Create or find the volume geometry nodes modifier
        geo_tree = self._ensure_volume_tree(obj)
        value_node = self._get_audio_value_node(geo_tree)

        # Set up animation on the value node
        fcurve = self._setup_fcurve(geo_tree, value_node)
        if not fcurve:
            self.report({'ERROR'}, "Could not create F-Curve for volume audio baking")
            return {'CANCELLED'}

        # Bake audio to the fcurve
        area, original_type = _get_graph_editor_area(context)
        try:
            _bake_sound_to_fcurve(context, area, filepath)
        except Exception as exc:
            self.report({'ERROR'}, f"Sound bake failed: {exc}")
            return {'CANCELLED'}
        finally:
            if original_type:
                area.type = original_type

        self.report({'INFO'}, "Audio-reactive volume setup created!")
        return {'FINISHED'}

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_volume_tree(obj) -> bpy.types.NodeTree:
        """Create or get a Geometry Nodes modifier with a volume pipeline."""
        # Look for existing audio volume modifier
        geo_mod = None
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.name == "Audio Volume":
                geo_mod = mod
                break

        if not geo_mod:
            geo_mod = obj.modifiers.new(name="Audio Volume", type='NODES')

        if geo_mod.node_group and geo_mod.node_group.name == "AudioVolumeTree":
            return geo_mod.node_group

        # Create new node tree
        tree = bpy.data.node_groups.new("AudioVolumeTree", 'GeometryNodeTree')
        geo_mod.node_group = tree

        # Define interface sockets
        tree.interface.new_socket(
            name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry'
        )
        tree.interface.new_socket(
            name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry'
        )

        # Create nodes
        group_in = tree.nodes.new('NodeGroupInput')
        group_in.location = (-600, 0)

        group_out = tree.nodes.new('NodeGroupOutput')
        group_out.location = (600, 0)

        # Audio Value Node
        value_node = tree.nodes.new('ShaderNodeValue')
        value_node.label = "Audio Volume Drive"
        value_node.name = "Audio Volume Drive"
        value_node.location = (-400, -200)
        value_node.outputs[0].default_value = 0.0

        # Math: Multiply audio value for dilation scale
        math_mult = tree.nodes.new('ShaderNodeMath')
        math_mult.operation = 'MULTIPLY'
        math_mult.inputs[1].default_value = 2.0  # Amplify for visible effect
        math_mult.location = (-200, -200)

        # Math: Add base offset so volume exists even at 0 amplitude
        math_add = tree.nodes.new('ShaderNodeMath')
        math_add.operation = 'ADD'
        math_add.inputs[1].default_value = 0.1  # Minimum density
        math_add.location = (0, -200)

        # Mesh to Volume node (Blender 5.0+ volume support in geo nodes)
        mesh_to_vol = tree.nodes.new('GeometryNodeMeshToVolume')
        mesh_to_vol.location = (0, 0)
        mesh_to_vol.resolution_mode = 'VOXEL_SIZE'
        # Set default voxel size
        mesh_to_vol.inputs['Voxel Size'].default_value = 0.1

        # Volume to Mesh (to visualize in viewport)
        vol_to_mesh = tree.nodes.new('GeometryNodeVolumeToMesh')
        vol_to_mesh.location = (300, 0)
        vol_to_mesh.resolution_mode = 'VOXEL_SIZE'
        vol_to_mesh.inputs['Voxel Size'].default_value = 0.15

        # Join Geometry to combine original + volume mesh
        join = tree.nodes.new('GeometryNodeJoinGeometry')
        join.location = (450, 0)

        # ── Links ───────────────────────────────────────────────────────
        # Audio value chain
        tree.links.new(value_node.outputs[0], math_mult.inputs[0])
        tree.links.new(math_mult.outputs[0], math_add.inputs[0])

        # Volume pipeline
        tree.links.new(group_in.outputs['Geometry'], mesh_to_vol.inputs['Mesh'])
        tree.links.new(math_add.outputs[0], mesh_to_vol.inputs['Density'])
        tree.links.new(mesh_to_vol.outputs['Volume'], vol_to_mesh.inputs['Volume'])

        # Combine original geometry with volume mesh
        tree.links.new(group_in.outputs['Geometry'], join.inputs['Geometry'])
        tree.links.new(vol_to_mesh.outputs['Mesh'], join.inputs['Geometry'])
        tree.links.new(join.outputs['Geometry'], group_out.inputs['Geometry'])

        return tree

    @staticmethod
    def _get_audio_value_node(tree):
        """Return the Audio Volume Drive value node."""
        for node in tree.nodes:
            if node.name == "Audio Volume Drive":
                return node
        return None

    @staticmethod
    def _setup_fcurve(tree, value_node):
        """Set up an fcurve on the audio value node for sound baking."""
        if not tree.animation_data:
            tree.animation_data_create()

        action_name = f"AudioVolume_{tree.name}"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
        tree.animation_data.action = action

        # Remove existing fcurves for this node
        for fc in list(action.fcurves):
            if value_node.name in fc.data_path:
                action.fcurves.remove(fc)

        # Insert initial keyframe
        value_node.outputs[0].default_value = 0.0
        value_node.outputs[0].keyframe_insert(data_path="default_value", frame=1)

        # Find the created fcurve
        for fc in action.fcurves:
            if "default_value" in fc.data_path and value_node.name in fc.data_path:
                fc.select = True
                fc.hide = False
                return fc
        return None
