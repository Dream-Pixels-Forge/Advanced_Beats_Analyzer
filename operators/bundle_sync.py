# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Bundle Nodes - Cross-Object Audio Sync.

Blender 5.1 introduces Get Bundle Item and Store Bundle Item geometry
nodes for passing data between node trees. This module:

1. Designates one object as the "Audio Conductor" which analyzes audio
   once and stores per-frame amplitude in a Bundle attribute
2. Other objects ("listeners") use Get Bundle Item to read the shared
   amplitude and react to it

This allows a single analysis to drive many objects without duplicating
FCurves or bake data — one conductor, many consumers.

Implementation:
- The conductor object gets a Geometry Nodes modifier that:
  - Reads the audio Value node (baked FCurve)
  - Stores it via Store Bundle Item node with a named key
- Listener objects get a Geometry Nodes modifier that:
  - Uses Get Bundle Item to read the amplitude
  - Applies it as displacement/scale via Set Position
"""

from __future__ import annotations

import os

import bpy
from bpy.types import Operator

from .bake import _get_graph_editor_area, _bake_sound_to_fcurve


# Key name used to store/retrieve audio amplitude in bundles
_BUNDLE_KEY = "audio_amplitude"


class BEATANALYZER_OT_setup_audio_conductor(Operator):
    """Set up the active object as an Audio Conductor (stores amplitude in Bundle)."""

    bl_idname = "beatanalyzer.setup_audio_conductor"
    bl_label = "Set as Audio Conductor"
    bl_description = (
        "Designate this object as the audio conductor that stores "
        "amplitude data for other objects to read via Bundle nodes"
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

        # Create the conductor geometry nodes tree
        tree = self._create_conductor_tree(obj)

        # Bake audio to the value node
        value_node = tree.nodes.get("ConductorAudioValue")
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

        # Tag the object as conductor via custom property
        obj["beat_analyzer_role"] = "conductor"

        self.report(
            {'INFO'},
            f"'{obj.name}' set as Audio Conductor "
            f"(other objects can read via Get Bundle Item)",
        )
        return {'FINISHED'}

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _create_conductor_tree(obj):
        """Create GeoNodes tree that stores audio amplitude in a Bundle."""
        # Find or create modifier
        geo_mod = None
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.name == "Audio Conductor":
                geo_mod = mod
                break

        if not geo_mod:
            geo_mod = obj.modifiers.new(name="Audio Conductor", type='NODES')

        # Create node tree
        tree_name = f"AudioConductor_{obj.name}"
        tree = bpy.data.node_groups.get(tree_name)
        if tree:
            bpy.data.node_groups.remove(tree)

        tree = bpy.data.node_groups.new(tree_name, 'GeometryNodeTree')
        geo_mod.node_group = tree

        # Interface
        tree.interface.new_socket(
            name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry'
        )
        tree.interface.new_socket(
            name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry'
        )

        # Nodes
        group_in = tree.nodes.new('NodeGroupInput')
        group_in.location = (-600, 0)

        group_out = tree.nodes.new('NodeGroupOutput')
        group_out.location = (400, 0)

        # Audio Value (will be keyframed with amplitude)
        audio_val = tree.nodes.new('ShaderNodeValue')
        audio_val.name = "ConductorAudioValue"
        audio_val.label = "Audio Amplitude"
        audio_val.location = (-400, -200)
        audio_val.outputs[0].default_value = 0.0

        # Store Bundle Item node (Blender 5.1+)
        store_bundle = tree.nodes.new('GeometryNodeStoreBundleItem')
        store_bundle.location = (0, 0)

        # Set the bundle key name
        # The Store Bundle Item node stores a value with a named key
        # that other objects can retrieve with Get Bundle Item
        if hasattr(store_bundle, 'inputs'):
            # Connect geometry pass-through
            tree.links.new(group_in.outputs['Geometry'], store_bundle.inputs['Geometry'])
            # Connect audio value to the Value input
            tree.links.new(audio_val.outputs[0], store_bundle.inputs['Value'])

        # Output
        tree.links.new(store_bundle.outputs['Geometry'], group_out.inputs['Geometry'])

        return tree

    @staticmethod
    def _setup_fcurve(tree, value_node):
        """Set up fcurve for the conductor's audio value node."""
        if not tree.animation_data:
            tree.animation_data_create()

        action_name = f"AudioConductor_{tree.name}"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
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


class BEATANALYZER_OT_setup_audio_listener(Operator):
    """Set up the active object as an Audio Listener (reads amplitude from Bundle)."""

    bl_idname = "beatanalyzer.setup_audio_listener"
    bl_label = "Set as Audio Listener"
    bl_description = (
        "Make this object read audio amplitude from the conductor's "
        "Bundle and react with displacement"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj:
            return False
        # Check that a conductor exists in the scene
        return any(
            o.get("beat_analyzer_role") == "conductor"
            for o in context.scene.objects
        )

    def execute(self, context):
        obj = context.active_object
        scene = context.scene

        # Find the conductor object
        conductor = None
        for o in scene.objects:
            if o.get("beat_analyzer_role") == "conductor":
                conductor = o
                break

        if not conductor:
            self.report({'ERROR'}, "No Audio Conductor found in scene")
            return {'CANCELLED'}

        # Create listener geometry nodes tree
        self._create_listener_tree(obj, conductor)

        # Tag as listener
        obj["beat_analyzer_role"] = "listener"

        self.report(
            {'INFO'},
            f"'{obj.name}' now listening to conductor '{conductor.name}'",
        )
        return {'FINISHED'}

    @staticmethod
    def _create_listener_tree(obj, conductor):
        """Create GeoNodes tree that reads amplitude from Bundle and displaces."""
        geo_mod = None
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.name == "Audio Listener":
                geo_mod = mod
                break

        if not geo_mod:
            geo_mod = obj.modifiers.new(name="Audio Listener", type='NODES')

        tree_name = f"AudioListener_{obj.name}"
        tree = bpy.data.node_groups.get(tree_name)
        if tree:
            bpy.data.node_groups.remove(tree)

        tree = bpy.data.node_groups.new(tree_name, 'GeometryNodeTree')
        geo_mod.node_group = tree

        # Interface
        tree.interface.new_socket(
            name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry'
        )
        tree.interface.new_socket(
            name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry'
        )

        # Nodes
        group_in = tree.nodes.new('NodeGroupInput')
        group_in.location = (-600, 0)

        group_out = tree.nodes.new('NodeGroupOutput')
        group_out.location = (600, 0)

        # Get Bundle Item node (Blender 5.1+)
        get_bundle = tree.nodes.new('GeometryNodeGetBundleItem')
        get_bundle.location = (-200, -200)

        # Object Info node to reference the conductor
        obj_info = tree.nodes.new('GeometryNodeObjectInfo')
        obj_info.inputs['Object'].default_value = conductor
        obj_info.location = (-400, -200)

        # Normal for displacement direction
        normal = tree.nodes.new('GeometryNodeInputNormal')
        normal.location = (-200, 100)

        # Vector Math: scale normal by bundle amplitude
        vec_scale = tree.nodes.new('ShaderNodeVectorMath')
        vec_scale.operation = 'SCALE'
        vec_scale.location = (0, 0)

        # Math: amplify the bundle value
        amplify = tree.nodes.new('ShaderNodeMath')
        amplify.operation = 'MULTIPLY'
        amplify.inputs[1].default_value = 0.5  # Displacement intensity
        amplify.location = (0, -200)

        # Set Position for displacement
        set_pos = tree.nodes.new('GeometryNodeSetPosition')
        set_pos.location = (300, 0)

        # Links
        tree.links.new(group_in.outputs['Geometry'], set_pos.inputs['Geometry'])

        # Get Bundle → amplify → scale normal → offset
        tree.links.new(get_bundle.outputs['Value'], amplify.inputs[0])
        tree.links.new(amplify.outputs[0], vec_scale.inputs['Scale'])
        tree.links.new(normal.outputs['Normal'], vec_scale.inputs[0])
        tree.links.new(vec_scale.outputs[0], set_pos.inputs['Offset'])

        # Output
        tree.links.new(set_pos.outputs['Geometry'], group_out.inputs['Geometry'])

        return tree
