# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Dimona Patrick

"""Advanced Beat Analyzer - Audio analysis and visualization for Blender.

This extension provides professional-grade audio beat detection and
audio-reactive animation tools for motion designers and video editors.

Note: For Blender 5.1+, metadata is sourced exclusively from
blender_manifest.toml. The legacy bl_info dict is no longer used.
"""

import bpy

from .properties import BeatAnalyzerProperties
from .operators.analyze import BEATANALYZER_OT_analyze
from .operators.bake import (
    BEATANALYZER_OT_bake_to_shader,
    BEATANALYZER_OT_bake_to_geometry,
)
from .operators.markers import (
    BEATANALYZER_OT_next_marker,
    BEATANALYZER_OT_prev_marker,
    BEATANALYZER_OT_bind_camera,
    BEATANALYZER_OT_update_marker_visibility,
    BEATANALYZER_OT_clear_markers,
)
from .operators.audio import (
    BEATANALYZER_OT_toggle_mute,
    BEATANALYZER_OT_export,
)
from .operators.animation_layers import (
    BEATANALYZER_OT_bake_to_nla_layer,
    BEATANALYZER_OT_toggle_audio_layer,
    BEATANALYZER_OT_remove_audio_layer,
)
from .operators.drivers import (
    BEATANALYZER_OT_generate_amplitude_curve,
    BEATANALYZER_OT_add_audio_driver,
    BEATANALYZER_OT_remove_audio_drivers,
    register_driver_namespace,
    unregister_driver_namespace,
)
from .operators.compositor import (
    BEATANALYZER_OT_add_compositor_effect,
)
from .operators.volumes import (
    BEATANALYZER_OT_setup_audio_volume,
)
from .operators.armature import (
    BEATANALYZER_OT_audio_bone_driver,
    BEATANALYZER_OT_setup_bone_info_geonodes,
)
from .operators.transitions import (
    BEATANALYZER_OT_beat_synced_transitions,
)
from .operators.raycast_npr import (
    BEATANALYZER_OT_setup_raycast_npr,
)
from .operators.realtime_preview import (
    BEATANALYZER_OT_enable_realtime_preview,
    BEATANALYZER_OT_disable_realtime_preview,
    cleanup_handler as _cleanup_preview_handler,
)
from .operators.mask_sdf import (
    BEATANALYZER_OT_setup_mask_sdf,
)
from .operators.index_switch import (
    BEATANALYZER_OT_setup_index_switch,
)
from .operators.light_path import (
    BEATANALYZER_OT_setup_light_path_audio,
)
from .operators.bundle_sync import (
    BEATANALYZER_OT_setup_audio_conductor,
    BEATANALYZER_OT_setup_audio_listener,
)
from .ui.panels import BEATANALYZER_PT_main_panel


# All classes to register, in dependency order (PropertyGroups first, then
# Operators, then Panels).
_classes: tuple = (
    BeatAnalyzerProperties,
    BEATANALYZER_OT_analyze,
    BEATANALYZER_OT_bake_to_shader,
    BEATANALYZER_OT_bake_to_geometry,
    BEATANALYZER_OT_next_marker,
    BEATANALYZER_OT_prev_marker,
    BEATANALYZER_OT_bind_camera,
    BEATANALYZER_OT_update_marker_visibility,
    BEATANALYZER_OT_clear_markers,
    BEATANALYZER_OT_toggle_mute,
    BEATANALYZER_OT_export,
    BEATANALYZER_OT_bake_to_nla_layer,
    BEATANALYZER_OT_toggle_audio_layer,
    BEATANALYZER_OT_remove_audio_layer,
    BEATANALYZER_OT_generate_amplitude_curve,
    BEATANALYZER_OT_add_audio_driver,
    BEATANALYZER_OT_remove_audio_drivers,
    BEATANALYZER_OT_add_compositor_effect,
    BEATANALYZER_OT_setup_audio_volume,
    BEATANALYZER_OT_audio_bone_driver,
    BEATANALYZER_OT_setup_bone_info_geonodes,
    BEATANALYZER_OT_beat_synced_transitions,
    BEATANALYZER_OT_setup_raycast_npr,
    BEATANALYZER_OT_enable_realtime_preview,
    BEATANALYZER_OT_disable_realtime_preview,
    BEATANALYZER_OT_setup_mask_sdf,
    BEATANALYZER_OT_setup_index_switch,
    BEATANALYZER_OT_setup_light_path_audio,
    BEATANALYZER_OT_setup_audio_conductor,
    BEATANALYZER_OT_setup_audio_listener,
    BEATANALYZER_PT_main_panel,
)


def register() -> None:
    """Register all addon classes and attach scene properties."""
    for cls in _classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.beat_analyzer_props = bpy.props.PointerProperty(
        type=BeatAnalyzerProperties
    )

    # Register driver namespace function
    register_driver_namespace()


def unregister() -> None:
    """Unregister all addon classes and remove scene properties."""
    _cleanup_preview_handler()
    unregister_driver_namespace()

    del bpy.types.Scene.beat_analyzer_props

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
