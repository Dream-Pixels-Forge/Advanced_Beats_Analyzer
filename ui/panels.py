# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Main sidebar panel for the Beat Analyzer addon."""

from bpy.types import Panel


class BEATANALYZER_PT_main_panel(Panel):
    """Advanced Beat Analyzer panel in the 3D View sidebar."""

    bl_label = "Advanced Beat Analyzer"
    bl_idname = "BEATANALYZER_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Beat Analyzer"

    def draw(self, context):
        layout = self.layout
        props = context.scene.beat_analyzer_props

        # ── Audio Source ────────────────────────────────────────────────
        box = layout.box()
        box.label(text="Audio Source", icon='SOUND')
        box.prop(props, "audio_file")
        if props.audio_file:
            icon = 'MUTE_IPO_OFF' if props.audio_muted else 'SPEAKER'
            box.operator(
                "beatanalyzer.toggle_mute",
                text="Toggle Mute",
                icon=icon,
                depress=props.audio_muted,
            )

        # ── Analysis Settings ───────────────────────────────────────────
        box = layout.box()
        box.label(text="Analysis Settings", icon='SETTINGS')
        box.prop(props, "detection_method")
        box.prop(props, "frequency_bands")
        if props.frequency_bands == 'CUSTOM':
            box.prop(props, "custom_freq_low")
            box.prop(props, "custom_freq_high")
        box.prop(props, "sensitivity")

        # ── Advanced ────────────────────────────────────────────────────
        box = layout.box()
        box.prop(props, "advanced_settings", icon='PREFERENCES')
        if props.advanced_settings:
            box.prop(props, "min_bpm")
            box.prop(props, "max_bpm")
            box.prop(props, "analysis_window")
            box.prop(props, "noise_reduction")
            box.prop(props, "beat_refinement")
            box.prop(props, "use_threading")
            box.prop(props, "use_cache")
            box.prop(props, "debug_mode")
            col = box.column()
            col.prop(props, "strong_beat_threshold")
            col.prop(props, "medium_beat_threshold")

        # ── Analyze Button ──────────────────────────────────────────────
        layout.operator("beatanalyzer.analyze", icon='PLAY')

        # ── Markers ─────────────────────────────────────────────────────
        box = layout.box()
        box.label(text="Marker Settings", icon='MARKER')
        box.prop(props, "marker_prefix")
        col = box.column(align=True)
        col.label(text="Show Beats:")
        row = col.row(align=True)
        row.prop(props, "show_strong_beats", toggle=True)
        row.prop(props, "show_medium_beats", toggle=True)
        row.prop(props, "show_weak_beats", toggle=True)
        box.operator("beatanalyzer.update_marker_visibility", icon='FILE_REFRESH')

        row = box.row(align=True)
        row.operator("beatanalyzer.prev_marker", icon='PREV_KEYFRAME')
        row.operator("beatanalyzer.next_marker", icon='NEXT_KEYFRAME')

        if context.active_object and context.active_object.type == 'CAMERA':
            box.operator("beatanalyzer.bind_camera", icon='CAMERA_DATA')

        if context.scene.timeline_markers:
            box.operator("beatanalyzer.clear_markers", icon='X')

        # ── Audio Baking ────────────────────────────────────────────────
        row = layout.row(align=True)
        row.operator("beatanalyzer.bake_to_shader", text="Bake to AVS", icon='SHADING_RENDERED')
        row.operator("beatanalyzer.bake_to_geometry", text="Bake to AVG", icon='GEOMETRY_NODES')

        # ── Non-Destructive Audio Layer (NLA) ───────────────────────────
        box = layout.box()
        box.label(text="Animation Layers", icon='NLA')
        box.operator("beatanalyzer.bake_to_nla_layer", icon='NLA_PUSHDOWN')
        row = box.row(align=True)
        row.operator("beatanalyzer.toggle_audio_layer", icon='HIDE_OFF')
        row.operator("beatanalyzer.remove_audio_layer", icon='TRASH')

        # ── Driver Expressions ──────────────────────────────────────────
        box = layout.box()
        box.label(text="Audio Drivers", icon='DRIVER')
        box.operator("beatanalyzer.generate_amplitude_curve", icon='FCURVE')
        box.operator("beatanalyzer.add_audio_driver", icon='ADD')
        box.operator("beatanalyzer.remove_audio_drivers", icon='X')

        # ── Compositor Effects ──────────────────────────────────────────
        box = layout.box()
        box.label(text="Compositor Effects", icon='NODE_COMPOSITING')
        box.operator("beatanalyzer.add_compositor_effect", icon='SHADERFX')

        # ── Volume Effects ──────────────────────────────────────────────
        box = layout.box()
        box.label(text="Volume Effects", icon='VOLUME_DATA')
        box.operator("beatanalyzer.setup_audio_volume", icon='MOD_FLUID')

        # ── Armature / Bone Audio ───────────────────────────────────────
        box = layout.box()
        box.label(text="Armature Audio", icon='ARMATURE_DATA')
        box.operator("beatanalyzer.audio_bone_driver", icon='BONE_DATA')
        box.operator("beatanalyzer.setup_bone_info_geonodes", icon='MESH_DATA')

        # ── Beat-Synced Transitions (VSE) ───────────────────────────────
        box = layout.box()
        box.label(text="VSE Transitions", icon='SEQ_SEQUENCER')
        box.operator("beatanalyzer.beat_synced_transitions", icon='ARROW_LEFTRIGHT')

        # ── Raycast NPR Effects ─────────────────────────────────────────
        box = layout.box()
        box.label(text="NPR Shader Effects", icon='MATSHADERBALL')
        box.operator("beatanalyzer.setup_raycast_npr", icon='LIGHT_SUN')

        # ── Real-Time Preview ───────────────────────────────────────────
        box = layout.box()
        box.label(text="Real-Time Preview", icon='PLAY')
        row = box.row(align=True)
        row.operator("beatanalyzer.enable_realtime_preview", icon='RESTRICT_VIEW_OFF')
        row.operator("beatanalyzer.disable_realtime_preview", icon='PAUSE')

        # ── SDF Typography ──────────────────────────────────────────────
        box = layout.box()
        box.label(text="SDF Typography", icon='FONT_DATA')
        box.operator("beatanalyzer.setup_mask_sdf", icon='SORTALPHA')

        # ── Index Switch Effects ────────────────────────────────────────
        box = layout.box()
        box.label(text="Effect Switching", icon='NODE_SEL')
        box.operator("beatanalyzer.setup_index_switch", icon='LINENUMBERS_ON')

        # ── Light Path Audio Atmosphere ─────────────────────────────────
        box = layout.box()
        box.label(text="Lighting Atmosphere", icon='LIGHT')
        box.operator("beatanalyzer.setup_light_path_audio", icon='OUTLINER_OB_LIGHT')

        # ── Bundle Cross-Object Sync ────────────────────────────────────
        box = layout.box()
        box.label(text="Cross-Object Sync", icon='LINKED')
        box.operator("beatanalyzer.setup_audio_conductor", icon='OUTLINER_OB_SPEAKER')
        box.operator("beatanalyzer.setup_audio_listener", icon='OUTLINER_OB_MESH')

        # ── Results ─────────────────────────────────────────────────────
        if props.total_beats > 0:
            box = layout.box()
            box.label(text="Analysis Results", icon='INFO')
            box.label(text=f"Total Beats: {props.total_beats}")
            box.label(text=f"Average BPM: {props.average_bpm:.1f}")
            box.label(text=f"Duration: {props.audio_duration:.2f}s")
            box.label(text=f"Last Analysis: {props.last_analysis_time}")

            if props.debug_mode and props.debug_info:
                box.label(text="Debug Info:", icon='CONSOLE')
                for line in props.debug_info.split('\n'):
                    box.label(text=line)

            box.operator("beatanalyzer.export", icon='EXPORT')
