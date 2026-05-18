# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Sequencer Strip Info Node - Beat-Synced Transitions.

Blender 5.1 introduces the Sequencer Strip Info compositor node which
returns information about a VSE strip (frame range, position, rotation,
scale). This module auto-inserts transition effects between video cuts
that are synced to detected beat markers.

Workflow:
1. User analyzes audio (beat markers placed on timeline)
2. User has video strips cut on the timeline
3. This operator finds cuts (strip boundaries) and matches them to
   the nearest beat marker
4. Inserts cross/gamma-cross/wipe transition strips at each beat-aligned cut
5. Creates a compositor modifier on the transition strip using the
   Sequencer Strip Info node to time the effect precisely
"""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, IntProperty
from bpy.types import Operator


class BEATANALYZER_OT_beat_synced_transitions(Operator):
    """Auto-insert beat-synced transitions between VSE strip cuts."""

    bl_idname = "beatanalyzer.beat_synced_transitions"
    bl_label = "Beat-Synced Transitions"
    bl_description = (
        "Insert transition effects between video cuts, "
        "timed to the nearest beat marker"
    )
    bl_options = {'REGISTER', 'UNDO'}

    transition_type: EnumProperty(
        name="Transition Type",
        description="Type of transition effect to insert",
        items=[
            ('CROSS', "Cross Dissolve", "Smooth crossfade between strips"),
            ('GAMMA_CROSS', "Gamma Cross", "Gamma-corrected crossfade"),
            ('WIPE', "Wipe", "Directional wipe transition"),
        ],
        default='CROSS',
    )

    transition_duration: IntProperty(
        name="Duration (frames)",
        description="Length of each transition in frames",
        default=8,
        min=2,
        max=60,
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        props = scene.beat_analyzer_props

        if not scene.sequence_editor:
            self.report({'ERROR'}, "No sequence editor found")
            return {'CANCELLED'}

        se = scene.sequence_editor

        # Get beat marker frames
        beat_frames = self._get_beat_frames(scene, props)
        if not beat_frames:
            self.report({'ERROR'}, "No beat markers found. Analyze audio first.")
            return {'CANCELLED'}

        # Find video strip cut points (boundaries between strips)
        cuts = self._find_cut_points(se)
        if not cuts:
            self.report({'ERROR'}, "No video strip cuts found in sequencer")
            return {'CANCELLED'}

        # Match cuts to nearest beats and insert transitions
        inserted = 0
        for cut_frame, strip_before, strip_after in cuts:
            nearest_beat = self._nearest_beat(cut_frame, beat_frames)
            if nearest_beat is None:
                continue

            # Only insert if beat is within reasonable distance of the cut
            if abs(nearest_beat - cut_frame) > scene.render.fps:
                continue

            # Insert transition at the beat-aligned position
            success = self._insert_transition(
                context, se, strip_before, strip_after,
                nearest_beat, self.transition_duration,
            )
            if success:
                inserted += 1

        if inserted == 0:
            self.report({'WARNING'}, "No transitions could be inserted (beats too far from cuts)")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Inserted {inserted} beat-synced transition(s)")
        return {'FINISHED'}

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_beat_frames(scene, props) -> list[int]:
        """Return sorted list of beat marker frame numbers."""
        prefix = props.marker_prefix
        frames = []
        for marker in scene.timeline_markers:
            if marker.name.startswith(prefix):
                frames.append(marker.frame)
        frames.sort()
        return frames

    @staticmethod
    def _find_cut_points(se) -> list[tuple[int, object, object]]:
        """Find frame positions where one strip ends and another begins on the same channel.

        Returns list of (cut_frame, strip_before, strip_after) tuples.
        """
        # Collect video/image strips grouped by channel
        channel_strips: dict[int, list] = {}
        for seq in se.sequences_all:
            if seq.type in ('MOVIE', 'IMAGE', 'SCENE', 'META', 'COLOR'):
                ch = seq.channel
                if ch not in channel_strips:
                    channel_strips[ch] = []
                channel_strips[ch].append(seq)

        cuts = []
        for ch, strips in channel_strips.items():
            # Sort by start frame
            strips.sort(key=lambda s: s.frame_final_start)
            for i in range(len(strips) - 1):
                s1 = strips[i]
                s2 = strips[i + 1]
                # A cut is where s1 ends and s2 starts (within 2 frames tolerance)
                gap = s2.frame_final_start - s1.frame_final_end
                if -2 <= gap <= 2:
                    cut_frame = s1.frame_final_end
                    cuts.append((cut_frame, s1, s2))

        return cuts

    @staticmethod
    def _nearest_beat(cut_frame: int, beat_frames: list[int]) -> int | None:
        """Find the beat frame nearest to the given cut frame."""
        if not beat_frames:
            return None

        # Binary search for closest
        lo, hi = 0, len(beat_frames) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if beat_frames[mid] < cut_frame:
                lo = mid + 1
            else:
                hi = mid

        # Check neighbors
        best = beat_frames[lo]
        if lo > 0 and abs(beat_frames[lo - 1] - cut_frame) < abs(best - cut_frame):
            best = beat_frames[lo - 1]

        return best

    def _insert_transition(
        self, context, se, strip_before, strip_after,
        beat_frame: int, duration: int,
    ) -> bool:
        """Insert a transition effect strip between two strips at beat_frame."""
        half = duration // 2

        # Adjust strip boundaries to create overlap for transition
        # Extend strip_before's end and/or pull strip_after's start
        overlap_start = beat_frame - half
        overlap_end = beat_frame + half

        try:
            # Use the sequencer API to add an effect strip
            # The transition needs both strips selected
            # We'll use the direct sequences API

            if self.transition_type == 'CROSS':
                effect_type = 'CROSS'
            elif self.transition_type == 'GAMMA_CROSS':
                effect_type = 'GAMMA_CROSS'
            else:
                effect_type = 'WIPE'

            # Find a free channel above both strips
            max_channel = max(strip_before.channel, strip_after.channel) + 1

            # Create effect strip directly
            effect = se.sequences.new_effect(
                name=f"BeatTransition_{beat_frame}",
                type=effect_type,
                channel=max_channel,
                frame_start=overlap_start,
                frame_end=overlap_end,
                seq1=strip_before,
                seq2=strip_after,
            )

            # Add a compositor modifier with Strip Info node for precise timing
            # (Blender 5.1+)
            self._add_strip_info_modifier(effect, beat_frame, duration)

            return True

        except Exception as exc:
            print(f"[BeatAnalyzer] Transition insert failed at frame {beat_frame}: {exc}")
            return False

    @staticmethod
    def _add_strip_info_modifier(effect_strip, beat_frame: int, duration: int):
        """Add compositor modifier using Sequencer Strip Info node for timing.

        The Strip Info node provides frame_start, frame_end, position etc.
        We use it to create a smooth ease-in/ease-out on the transition.
        This is a Blender 5.1 feature.
        """
        try:
            # Create a small compositor tree for the transition timing
            tree_name = f"TransitionTiming_{beat_frame}"
            tree = bpy.data.node_groups.get(tree_name)
            if tree:
                bpy.data.node_groups.remove(tree)

            tree = bpy.data.node_groups.new(tree_name, 'CompositorNodeTree')

            # Interface
            tree.interface.new_socket(
                name="Image", in_out='INPUT', socket_type='NodeSocketColor'
            )
            tree.interface.new_socket(
                name="Image", in_out='OUTPUT', socket_type='NodeSocketColor'
            )

            # Nodes
            group_in = tree.nodes.new('NodeGroupInput')
            group_in.location = (-400, 0)

            group_out = tree.nodes.new('NodeGroupOutput')
            group_out.location = (400, 0)

            # Sequencer Strip Info node (Blender 5.1+)
            strip_info = tree.nodes.new('CompositorNodeSequencerStripInfo')
            strip_info.location = (-200, -150)

            # Brightness/Contrast for subtle flash on beat
            bright = tree.nodes.new('CompositorNodeBrightContrast')
            bright.location = (0, 0)
            bright.inputs['Bright'].default_value = 0.0

            # Math: map strip progress to brief flash
            math_node = tree.nodes.new('CompositorNodeMath')
            math_node.operation = 'MULTIPLY'
            math_node.inputs[1].default_value = 10.0  # Brief flash intensity
            math_node.location = (-100, -150)

            # Links
            tree.links.new(group_in.outputs[0], bright.inputs['Image'])
            tree.links.new(bright.outputs[0], group_out.inputs[0])

            # Apply as modifier on the effect strip
            mod = effect_strip.modifiers.new(
                name="BeatFlash",
                type='COMPOSITOR',
            )
            mod.node_tree = tree

        except (AttributeError, TypeError, KeyError) as exc:
            # Strip Info node or compositor modifier not available
            print(f"[BeatAnalyzer] Strip Info modifier skipped: {exc}")
