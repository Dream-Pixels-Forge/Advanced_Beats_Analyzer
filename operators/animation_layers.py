# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Non-destructive animation layer operators using NLA + Slotted Actions.

In Blender 5.0+, Actions use a layered system (Layers → Strips → Channelbags).
Since there is currently a 1-layer-per-Action limit, we implement non-destructive
audio animation by:

1. Creating a dedicated "Audio" Action with its own layer/strip/slot
2. Pushing any existing user Action down into the NLA as a strip
3. Assigning the Audio Action as the active action
4. OR using NLA tracks to blend the audio action on top

This allows the user to mute/solo/blend the audio layer independently.
"""

from __future__ import annotations

import os

import bpy
from bpy.types import Operator


class BEATANALYZER_OT_bake_to_nla_layer(Operator):
    """Bake audio to a non-destructive NLA layer (preserves existing animation)."""

    bl_idname = "beatanalyzer.bake_to_nla_layer"
    bl_label = "Bake Audio to NLA Layer"
    bl_description = (
        "Bake audio amplitude to a separate NLA track, preserving existing animation"
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

        # ── Step 1: Ensure animation data exists ────────────────────────
        if not obj.animation_data:
            obj.animation_data_create()

        anim_data = obj.animation_data

        # ── Step 2: Push current action to NLA if it has keyframes ──────
        if anim_data.action and anim_data.action.fcurves:
            existing_action = anim_data.action
            # Create NLA track for existing animation if not already there
            has_existing_track = any(
                track.name == "User Animation"
                for track in anim_data.nla_tracks
            )
            if not has_existing_track:
                track = anim_data.nla_tracks.new()
                track.name = "User Animation"
                # Push action as NLA strip
                scene = context.scene
                frame_start = scene.frame_start
                track.strips.new(
                    existing_action.name,
                    int(frame_start),
                    existing_action,
                )
                track.mute = False

        # ── Step 3: Create dedicated Audio Action ───────────────────────
        audio_action_name = f"AudioLayer_{obj.name}"

        # Reuse existing audio action if present
        audio_action = bpy.data.actions.get(audio_action_name)
        if audio_action:
            # Clear existing fcurves in the audio action
            for fc in list(audio_action.fcurves):
                audio_action.fcurves.remove(fc)
        else:
            audio_action = bpy.data.actions.new(name=audio_action_name)

        # ── Step 4: Set up the layered action structure (5.0+ API) ──────
        # Ensure layer and strip exist in the slotted action system
        if hasattr(audio_action, 'layers'):
            # Blender 4.4+ / 5.x slotted action API
            if not audio_action.layers:
                layer = audio_action.layers.new("Audio Layer")
                layer.strips.new(type='KEYFRAME')

            # Ensure slot exists for this object
            if hasattr(audio_action, 'slots'):
                slot = None
                for s in audio_action.slots:
                    if s.name == obj.name or s.identifier == obj.name:
                        slot = s
                        break
                if not slot:
                    slot = audio_action.slots.new(for_id=obj)

        # ── Step 5: Assign audio action and bake ────────────────────────
        anim_data.action = audio_action

        # Create Z-scale fcurve as the audio-driven channel
        data_path = "scale"
        fc = audio_action.fcurves.new(data_path=data_path, index=2)  # Z scale
        fc.keyframe_points.insert(1, 1.0)  # Base scale at frame 1
        fc.select = True
        fc.hide = False

        # Bake sound to the fcurve
        area, original_type = self._get_graph_editor_area(context)
        try:
            with context.temp_override(area=area):
                bpy.ops.graph.sound_to_samples(filepath=filepath)
        except Exception as exc:
            self.report({'ERROR'}, f"Sound bake failed: {exc}")
            return {'CANCELLED'}
        finally:
            if original_type:
                area.type = original_type

        # ── Step 6: Push audio action to its own NLA track ──────────────
        # Remove audio action from active slot so it lives in NLA only
        anim_data.action = None

        # Create or find audio NLA track
        audio_track = None
        for track in anim_data.nla_tracks:
            if track.name == "Audio Layer":
                audio_track = track
                break

        if not audio_track:
            audio_track = anim_data.nla_tracks.new()
            audio_track.name = "Audio Layer"

        # Add the audio action as a strip on this track
        scene = context.scene
        strip = audio_track.strips.new(
            audio_action.name,
            int(scene.frame_start),
            audio_action,
        )
        strip.blend_type = 'ADD'  # Additive blend so it layers on top
        strip.name = "Audio Amplitude"

        # Set extrapolation to hold so audio effect persists
        strip.extrapolation = 'HOLD'

        self.report(
            {'INFO'},
            f"Audio baked to NLA layer '{audio_track.name}' "
            f"(additive blend, mutable)",
        )
        return {'FINISHED'}

    @staticmethod
    def _get_graph_editor_area(context):
        """Return a GRAPH_EDITOR area, creating a temporary one if needed."""
        for area in context.screen.areas:
            if area.type == 'GRAPH_EDITOR':
                return area, None
        area = context.area
        original = area.type
        area.type = 'GRAPH_EDITOR'
        return area, original


class BEATANALYZER_OT_toggle_audio_layer(Operator):
    """Mute/unmute the Audio NLA layer on the active object."""

    bl_idname = "beatanalyzer.toggle_audio_layer"
    bl_label = "Toggle Audio Layer"
    bl_description = "Mute or unmute the audio NLA layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or not obj.animation_data:
            return False
        return any(t.name == "Audio Layer" for t in obj.animation_data.nla_tracks)

    def execute(self, context):
        obj = context.active_object
        for track in obj.animation_data.nla_tracks:
            if track.name == "Audio Layer":
                track.mute = not track.mute
                state = "muted" if track.mute else "active"
                self.report({'INFO'}, f"Audio layer {state}")
                return {'FINISHED'}

        self.report({'WARNING'}, "Audio layer not found")
        return {'CANCELLED'}


class BEATANALYZER_OT_remove_audio_layer(Operator):
    """Remove the Audio NLA layer from the active object."""

    bl_idname = "beatanalyzer.remove_audio_layer"
    bl_label = "Remove Audio Layer"
    bl_description = "Delete the audio NLA layer and its action"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or not obj.animation_data:
            return False
        return any(t.name == "Audio Layer" for t in obj.animation_data.nla_tracks)

    def execute(self, context):
        obj = context.active_object
        anim_data = obj.animation_data

        for track in list(anim_data.nla_tracks):
            if track.name == "Audio Layer":
                # Remove strips and their actions
                for strip in list(track.strips):
                    action = strip.action
                    track.strips.remove(strip)
                    # Remove orphan action
                    if action and action.users == 0:
                        bpy.data.actions.remove(action)
                anim_data.nla_tracks.remove(track)
                self.report({'INFO'}, "Audio layer removed")
                return {'FINISHED'}

        self.report({'WARNING'}, "Audio layer not found")
        return {'CANCELLED'}
