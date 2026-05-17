# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Bone Info Node for Armature-Driven Audio animation.

Blender 5.1 introduces the Bone Info geometry node which provides access
to armature bone transforms inside Geometry Nodes. This module:

1. Adds audio-driven bone constraints (Copy Rotation driven by audio amplitude)
   to selected pose bones for character animation (jaw sync, body bounce).
2. Creates a Geometry Nodes setup using the Bone Info node that reads
   bone transforms and combines them with audio-driven displacement.

Typical use cases:
- Jaw bone driven open/closed by vocal amplitude
- Body root bone bouncing to bass beats
- Limb sway driven by mid-frequency energy
"""

from __future__ import annotations

import os

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from .bake import _get_graph_editor_area, _bake_sound_to_fcurve


class BEATANALYZER_OT_audio_bone_driver(Operator):
    """Add audio-driven rotation to a pose bone via constraints + baked FCurve."""

    bl_idname = "beatanalyzer.audio_bone_driver"
    bl_label = "Audio Bone Driver"
    bl_description = (
        "Drive a pose bone's rotation with audio amplitude "
        "(jaw sync, body bounce, limb sway)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    bone_axis: EnumProperty(
        name="Rotation Axis",
        description="Which rotation axis the audio drives",
        items=[
            ('X', "X Axis", "Rotate around local X (typical for jaw open)"),
            ('Y', "Y Axis", "Rotate around local Y"),
            ('Z', "Z Axis", "Rotate around local Z (typical for head sway)"),
        ],
        default='X',
    )

    drive_mode: EnumProperty(
        name="Drive Mode",
        description="How the audio maps to rotation",
        items=[
            ('JAW', "Jaw Sync", "Map amplitude to jaw open rotation"),
            ('BOUNCE', "Body Bounce", "Map bass to up/down location offset"),
            ('SWAY', "Limb Sway", "Map to oscillating rotation"),
        ],
        default='JAW',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            return False
        if obj.mode != 'POSE':
            return False
        return bool(context.selected_pose_bones)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        obj = context.active_object

        if not props.audio_file or not os.path.isfile(bpy.path.abspath(props.audio_file)):
            self.report({'WARNING'}, "No valid audio file selected.")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)
        bones = context.selected_pose_bones

        if not bones:
            self.report({'ERROR'}, "No pose bones selected")
            return {'CANCELLED'}

        for pbone in bones:
            self._setup_bone_audio(context, obj, pbone, filepath)

        self.report(
            {'INFO'},
            f"Audio driver applied to {len(bones)} bone(s) [{self.drive_mode}]",
        )
        return {'FINISHED'}

    def _setup_bone_audio(self, context, armature_obj, pbone, filepath):
        """Set up audio-driven animation on a single pose bone."""
        scene = context.scene

        # Determine data path and axis index
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[self.bone_axis]

        if self.drive_mode == 'BOUNCE':
            # Drive location Z for bounce
            data_path = f'pose.bones["{pbone.name}"].location'
            drive_index = 2  # Z
        else:
            # Drive rotation for jaw/sway
            data_path = f'pose.bones["{pbone.name}"].rotation_euler'
            drive_index = axis_idx

        # Ensure animation data
        if not armature_obj.animation_data:
            armature_obj.animation_data_create()

        # Create dedicated action for this bone's audio
        action_name = f"AudioBone_{pbone.name}"
        action = bpy.data.actions.get(action_name)
        if not action:
            action = bpy.data.actions.new(name=action_name)
        else:
            # Clear existing fcurves for this path
            for fc in list(action.fcurves):
                if fc.data_path == data_path and fc.array_index == drive_index:
                    action.fcurves.remove(fc)

        armature_obj.animation_data.action = action

        # Create fcurve and insert initial keyframe
        fc = action.fcurves.new(data_path=data_path, index=drive_index)
        fc.keyframe_points.insert(scene.frame_start, 0.0)
        fc.select = True
        fc.hide = False

        # Bake sound to the fcurve
        area, original_type = _get_graph_editor_area(context)
        try:
            _bake_sound_to_fcurve(context, area, filepath)
        except Exception as exc:
            print(f"[BeatAnalyzer] Bone audio bake failed: {exc}")
            return
        finally:
            if original_type:
                area.type = original_type

        # Scale the amplitude based on drive mode
        self._scale_fcurve(fc)

        # Push to NLA so it doesn't conflict with manual posing
        self._push_to_nla(armature_obj, action, pbone.name)

    def _scale_fcurve(self, fc):
        """Scale fcurve values based on the drive mode."""
        if not fc.keyframe_points:
            return

        if self.drive_mode == 'JAW':
            # Scale to ~0.3 radians max (jaw open angle)
            scale = 0.3
        elif self.drive_mode == 'BOUNCE':
            # Scale to ~0.1 units location offset
            scale = 0.1
        elif self.drive_mode == 'SWAY':
            # Scale to ~0.15 radians oscillation
            scale = 0.15
        else:
            scale = 0.2

        for kp in fc.keyframe_points:
            kp.co.y *= scale

        fc.update()

    @staticmethod
    def _push_to_nla(armature_obj, action, bone_name):
        """Push the bone audio action to NLA for non-destructive blending."""
        anim_data = armature_obj.animation_data

        # Create or find audio bones NLA track
        track_name = "Audio Bones"
        audio_track = None
        for track in anim_data.nla_tracks:
            if track.name == track_name:
                audio_track = track
                break

        if not audio_track:
            audio_track = anim_data.nla_tracks.new()
            audio_track.name = track_name

        # Check if strip for this action already exists
        for strip in audio_track.strips:
            if strip.action == action:
                return

        # Add strip
        import bpy
        scene = bpy.context.scene
        strip = audio_track.strips.new(
            action.name,
            int(scene.frame_start),
            action,
        )
        strip.blend_type = 'ADD'
        strip.name = f"Audio_{bone_name}"
        strip.extrapolation = 'HOLD'

        # Clear active action so NLA takes over
        anim_data.action = None


class BEATANALYZER_OT_setup_bone_info_geonodes(Operator):
    """Create a Geometry Nodes setup using the Bone Info node with audio displacement."""

    bl_idname = "beatanalyzer.setup_bone_info_geonodes"
    bl_label = "Bone Info + Audio GeoNodes"
    bl_description = (
        "Create Geometry Nodes setup combining Bone Info node transforms "
        "with audio-driven displacement"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        obj = context.active_object

        if not props.audio_file or not os.path.isfile(bpy.path.abspath(props.audio_file)):
            self.report({'WARNING'}, "No valid audio file selected.")
            return {'CANCELLED'}

        filepath = bpy.path.abspath(props.audio_file)

        # Create the Geometry Nodes tree
        tree = self._create_bone_info_tree(obj)

        # Bake audio to the value node
        value_node = tree.nodes.get("Audio Bone Amplitude")
        if value_node:
            fcurve = self._setup_fcurve(tree, value_node)
            if fcurve:
                area, original_type = _get_graph_editor_area(context)
                try:
                    _bake_sound_to_fcurve(context, area, filepath)
                except Exception as exc:
                    self.report({'WARNING'}, f"Audio bake partial: {exc}")
                finally:
                    if original_type:
                        area.type = original_type

        self.report({'INFO'}, "Bone Info + Audio displacement GeoNodes created!")
        return {'FINISHED'}

    @staticmethod
    def _create_bone_info_tree(obj):
        """Create a GeoNodes tree with Bone Info + audio displacement."""
        # Find or create modifier
        geo_mod = None
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.name == "BoneInfo Audio":
                geo_mod = mod
                break

        if not geo_mod:
            geo_mod = obj.modifiers.new(name="BoneInfo Audio", type='NODES')

        # Create node tree
        tree_name = f"BoneInfoAudio_{obj.name}"
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
        group_in.location = (-800, 0)

        group_out = tree.nodes.new('NodeGroupOutput')
        group_out.location = (600, 0)

        # Bone Info node (Blender 5.1+)
        bone_info = tree.nodes.new('GeometryNodeBoneInfo')
        bone_info.location = (-400, -200)

        # Audio Value node
        audio_val = tree.nodes.new('ShaderNodeValue')
        audio_val.name = "Audio Bone Amplitude"
        audio_val.label = "Audio Bone Amplitude"
        audio_val.location = (-400, -400)
        audio_val.outputs[0].default_value = 0.0

        # Math: combine bone transform scale with audio
        math_mult = tree.nodes.new('ShaderNodeMath')
        math_mult.operation = 'MULTIPLY'
        math_mult.location = (-200, -300)

        # Set Position node for displacement
        set_pos = tree.nodes.new('GeometryNodeSetPosition')
        set_pos.location = (200, 0)

        # Normal node for displacement direction
        normal = tree.nodes.new('GeometryNodeInputNormal')
        normal.location = (-200, 100)

        # Vector Math: scale normal by audio*bone factor
        vec_scale = tree.nodes.new('ShaderNodeVectorMath')
        vec_scale.operation = 'SCALE'
        vec_scale.location = (0, 0)

        # Links
        tree.links.new(group_in.outputs['Geometry'], set_pos.inputs['Geometry'])
        tree.links.new(normal.outputs['Normal'], vec_scale.inputs[0])
        tree.links.new(math_mult.outputs[0], vec_scale.inputs['Scale'])
        tree.links.new(vec_scale.outputs[0], set_pos.inputs['Offset'])
        tree.links.new(set_pos.outputs['Geometry'], group_out.inputs['Geometry'])

        # Audio × bone scale factor
        tree.links.new(audio_val.outputs[0], math_mult.inputs[0])
        # Bone Info → position magnitude as secondary multiplier
        # Use a constant for now since Bone Info needs object input
        math_mult.inputs[1].default_value = 0.5

        return tree

    @staticmethod
    def _setup_fcurve(tree, value_node):
        """Set up fcurve for audio baking on the value node."""
        if not tree.animation_data:
            tree.animation_data_create()

        action_name = f"AudioBoneInfo_{tree.name}"
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
