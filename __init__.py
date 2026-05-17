bl_info = {
    "name": "Advanced Beat Analyzer",
    "author": "Dimona Patrick",
    "version": (2, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Beat Analyzer",
    "description": "Advanced audio beat analysis with shader and geometry nodes support",
    "warning": "",
    "doc_url": "",
    "category": "Animation",
}

import bpy
import wave
import os
import time
import json
import numpy as np
import threading
from datetime import datetime
from bpy.props import (
    FloatProperty,
    StringProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    PointerProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
)


# ---------- Version Compatibility Helpers ----------

def get_blender_version():
    """Return the current Blender version as a tuple (major, minor, patch)."""
    return bpy.app.version


def get_principled_emission_input_name():
    """Return the correct Principled BSDF emission color input name for this Blender version.
    In Blender 4.0+ the input is called 'Emission Color'.
    In earlier versions it was called 'Emission'.
    """
    if get_blender_version() >= (4, 0, 0):
        return 'Emission Color'
    return 'Emission'


def force_depsgraph_update(context):
    """Force a dependency graph update (replaces deprecated sequence_editor.update())."""
    context.scene.frame_set(context.scene.frame_current)


# ---------- End Helpers ----------


def toggle_audio_mute_state(context):
    bpy.ops.beatanalyzer.toggle_mute()


def set_audio_mute_state(context, mute_state):
    props = context.scene.beat_analyzer_props
    scene = context.scene

    if scene.sequence_editor:
        for sequence in scene.sequence_editor.sequences_all:
            if sequence.type == 'SOUND' and sequence.sound.filepath == props.audio_file:
                sequence.mute = mute_state
                props.audio_muted = mute_state

                # Update channel if needed
                if hasattr(sequence, 'channel'):
                    for channel in scene.sequence_editor.channels:
                        if channel.index == sequence.channel:
                            channel.mute = mute_state
                            break

                # Force update using depsgraph (sequence_editor.update() removed in 4.x)
                force_depsgraph_update(context)
                break


class BeatAnalyzerCache:
    """Cache system for storing analysis results"""
    _cache = {}
    _max_cache_size = 10

    @staticmethod
    def get_cache_key(file_path, settings):
        """Generate unique cache key based on file path and settings"""
        settings_hash = hash(frozenset(settings.items()))
        return f"{file_path}_{settings_hash}"

    @staticmethod
    def get_cached_result(file_path, settings):
        """Retrieve cached analysis results"""
        cache_key = BeatAnalyzerCache.get_cache_key(file_path, settings)
        return BeatAnalyzerCache._cache.get(cache_key)

    @staticmethod
    def store_result(file_path, settings, result):
        """Store analysis results in cache"""
        cache_key = BeatAnalyzerCache.get_cache_key(file_path, settings)
        if len(BeatAnalyzerCache._cache) >= BeatAnalyzerCache._max_cache_size:
            oldest_key = next(iter(BeatAnalyzerCache._cache))
            del BeatAnalyzerCache._cache[oldest_key]
        BeatAnalyzerCache._cache[cache_key] = result


class BeatAnalyzerProperties(PropertyGroup):
    """Properties for the Beat Analyzer addon"""

    # Audio File Settings
    audio_file: StringProperty(
        name="Audio File",
        description="Path to audio file",
        default="",
        subtype='FILE_PATH'
    )

    audio_muted: BoolProperty(
        name="Mute Audio",
        description="Mute/unmute the audio playback",
        default=False
    )

    # Analysis Method Settings
    detection_method: EnumProperty(
        name="Detection Method",
        description="Method used for beat detection",
        items=[
            ('ENERGY', "Energy Based", "Classic energy-based beat detection"),
            ('SPECTRAL', "Spectral Flux", "Detection using spectral flux"),
            ('COMPLEX', "Complex Detection", "Combined energy and spectral analysis"),
            ('ADAPTIVE', "Adaptive Threshold", "Adaptive threshold detection")
        ],
        default='COMPLEX'
    )

    frequency_bands: EnumProperty(
        name="Frequency Bands",
        description="Analyze specific frequency ranges",
        items=[
            ('ALL', "All Frequencies", "Analyze full spectrum"),
            ('BASS', "Bass Only", "Focus on low frequencies (20-250Hz)"),
            ('MID', "Mid Range", "Focus on mid frequencies (250-2000Hz)"),
            ('HIGH', "High Range", "Focus on high frequencies (2000-20000Hz)"),
            ('CUSTOM', "Custom Range", "Define custom frequency range")
        ],
        default='ALL'
    )

    custom_freq_low: FloatProperty(
        name="Low Frequency",
        description="Lower bound of frequency range (Hz)",
        default=20.0,
        min=20.0,
        max=20000.0
    )

    custom_freq_high: FloatProperty(
        name="High Frequency",
        description="Upper bound of frequency range (Hz)",
        default=20000.0,
        min=20.0,
        max=20000.0
    )

    # Analysis Parameters
    sensitivity: FloatProperty(
        name="Sensitivity",
        description="Beat detection sensitivity (lower = more beats)",
        default=1.3,
        min=0.1,
        max=2.0
    )

    min_bpm: IntProperty(
        name="Minimum BPM",
        description="Minimum beats per minute to detect",
        default=60,
        min=30,
        max=300
    )

    max_bpm: IntProperty(
        name="Maximum BPM",
        description="Maximum beats per minute to detect",
        default=180,
        min=30,
        max=300
    )

    analysis_window: IntProperty(
        name="Analysis Window",
        description="Size of analysis window in milliseconds",
        default=50,
        min=10,
        max=200
    )

    # Advanced Settings
    advanced_settings: BoolProperty(
        name="Advanced Settings",
        description="Show advanced analysis settings",
        default=False
    )

    use_threading: BoolProperty(
        name="Use Threading",
        description="Use multi-threading for analysis (faster but may be less stable)",
        default=True
    )

    use_cache: BoolProperty(
        name="Use Cache",
        description="Cache analysis results for faster repeated analysis",
        default=True
    )

    noise_reduction: FloatProperty(
        name="Noise Reduction",
        description="Reduce background noise (0 = off, 1 = maximum)",
        default=0.2,
        min=0.0,
        max=1.0
    )

    beat_refinement: BoolProperty(
        name="Beat Refinement",
        description="Additional processing to refine beat positions",
        default=True
    )

    debug_mode: BoolProperty(
        name="Debug Mode",
        description="Show additional debug information",
        default=False
    )

    # Beat Strength Settings
    strong_beat_threshold: FloatProperty(
        name="Strong Beat Threshold",
        description="Threshold for strong beat detection",
        default=1.5,
        min=1.0,
        max=3.0
    )

    medium_beat_threshold: FloatProperty(
        name="Medium Beat Threshold",
        description="Threshold for medium beat detection",
        default=1.2,
        min=1.0,
        max=3.0
    )

    # Marker Settings
    marker_prefix: StringProperty(
        name="Marker Prefix",
        description="Prefix for marker names",
        default="Beat_"
    )

    show_strong_beats: BoolProperty(
        name="Strong Beats",
        description="Show markers for strong beats",
        default=True
    )

    show_medium_beats: BoolProperty(
        name="Medium Beats",
        description="Show markers for medium beats",
        default=True
    )

    show_weak_beats: BoolProperty(
        name="Weak Beats",
        description="Show markers for weak beats",
        default=True
    )

    # Audio Baking Settings
    bake_to_noise: BoolProperty(
        name="Bake to Noise",
        description="Bake audio amplitude to noise texture W parameter",
        default=False
    )

    noise_texture_name: StringProperty(
        name="Noise Texture Name",
        description="Name of the noise texture to create/update",
        default="Audio_Noise"
    )

    bake_smoothing: FloatProperty(
        name="Smoothing",
        description="Smoothing factor for audio baking",
        default=0.5,
        min=0.0,
        max=1.0
    )

    bake_target: EnumProperty(
        name="Bake Target",
        description="Where to use the baked noise texture",
        items=[
            ('BOTH', "Both", "Use in both Shader and Geometry Nodes"),
            ('SHADER', "Shader", "Use in Shader Editor only"),
            ('GEOMETRY', "Geometry", "Use in Geometry Nodes only")
        ],
        default='BOTH'
    )

    create_shader_group: BoolProperty(
        name="Create Shader Group",
        description="Create a shader node group for easy audio visualization",
        default=True
    )

    shader_group_name: StringProperty(
        name="Shader Group Name",
        description="Name of the shader node group to create",
        default="Audio_Visualizer"
    )

    low_freq: FloatProperty(
        name="Low Frequency",
        description="Low frequency cutoff",
        default=20.0,
        min=1.0,
        max=20000.0
    )

    high_freq: FloatProperty(
        name="High Frequency",
        description="High frequency cutoff",
        default=20000.0,
        min=1.0,
        max=20000.0
    )

    attack_time: FloatProperty(
        name="Attack Time",
        description="Attack time for sound baking",
        default=0.005,
        min=0.001,
        max=1.0
    )

    release_time: FloatProperty(
        name="Release Time",
        description="Release time for sound baking",
        default=0.2,
        min=0.001,
        max=1.0
    )

    # Analysis Results Storage
    total_beats: IntProperty(default=0)
    average_bpm: FloatProperty(default=0.0)
    audio_duration: FloatProperty(default=0.0)
    last_analysis_time: StringProperty(default="Never")
    debug_info: StringProperty(default="No analysis performed yet")


class AudioAnalysisThread(threading.Thread):
    """Thread class for handling audio analysis in the background"""
    def __init__(self, file_path, props):
        threading.Thread.__init__(self)
        self.file_path = file_path
        self.props = props
        self.results = None
        self.progress = 0
        self.is_cancelled = False
        self.error = None

    def run(self):
        try:
            analyzer = AudioAnalyzer(self.props)
            self.results = analyzer.analyze_file(
                self.file_path,
                progress_callback=self.update_progress
            )
        except Exception as e:
            self.error = str(e)

    def update_progress(self, progress):
        self.progress = progress

    def cancel(self):
        self.is_cancelled = True


class AudioAnalyzer:
    """Main audio analysis class"""
    def __init__(self, props):
        self.props = props
        self.sample_rate = 0
        self.channels = 0
        self.window_size = 1024
        self.hop_length = 512

    def analyze_file(self, file_path, progress_callback=None):
        """Main analysis function"""
        try:
            # Read audio file
            with wave.open(file_path, 'rb') as wf:
                self.sample_rate = wf.getframerate()
                self.channels = wf.getnchannels()
                n_frames = wf.getnframes()
                audio_data = wf.readframes(n_frames)

                # Convert to numpy array
                data = np.frombuffer(audio_data, dtype=np.int16)
                if self.channels == 2:
                    data = data.reshape(-1, 2).mean(axis=1)

                # Normalize
                data = data / np.iinfo(np.int16).max

            # Apply frequency band filtering
            data = self.apply_frequency_filter(data)

            # Apply noise reduction if enabled
            if self.props.noise_reduction > 0:
                data = self.apply_noise_reduction(data)

            # Get beats based on selected method
            if self.props.detection_method == 'ENERGY':
                beats = self.energy_based_detection(data, progress_callback)
            elif self.props.detection_method == 'SPECTRAL':
                beats = self.spectral_flux_detection(data, progress_callback)
            elif self.props.detection_method == 'COMPLEX':
                beats = self.complex_detection(data, progress_callback)
            else:  # ADAPTIVE
                beats = self.adaptive_threshold_detection(data, progress_callback)

            # Refine beat positions if enabled
            if self.props.beat_refinement:
                beats = self.refine_beats(data, beats)

            # Calculate audio statistics
            duration = len(data) / self.sample_rate
            bpm = len(beats) * 60 / duration if beats else 0

            return {
                'beats': beats,
                'audio_info': {
                    'duration': duration,
                    'sample_rate': self.sample_rate,
                    'channels': self.channels,
                    'bpm': bpm
                }
            }

        except Exception as e:
            raise RuntimeError(f"Analysis failed: {str(e)}")

    def apply_frequency_filter(self, data):
        """Apply frequency band filtering based on settings"""
        if self.props.frequency_bands == 'ALL':
            return data

        # Calculate FFT
        fft_data = np.fft.rfft(data)
        freqs = np.fft.rfftfreq(len(data), 1 / self.sample_rate)

        # Create frequency mask
        if self.props.frequency_bands == 'BASS':
            mask = (freqs >= 20) & (freqs <= 250)
        elif self.props.frequency_bands == 'MID':
            mask = (freqs >= 250) & (freqs <= 2000)
        elif self.props.frequency_bands == 'HIGH':
            mask = (freqs >= 2000) & (freqs <= 20000)
        elif self.props.frequency_bands == 'CUSTOM':
            mask = (freqs >= self.props.custom_freq_low) & (freqs <= self.props.custom_freq_high)
        else:
            mask = np.ones_like(freqs, dtype=bool)

        # Apply mask and inverse FFT
        fft_data[~mask] = 0
        return np.fft.irfft(fft_data)

    def apply_noise_reduction(self, data):
        """Apply noise reduction to the audio data"""
        if self.props.noise_reduction <= 0:
            return data

        # Estimate noise profile from the quietest sections
        frame_length = 2048
        noise_profile = []
        for i in range(0, len(data) - frame_length, frame_length):
            frame = data[i:i + frame_length]
            frame_energy = np.sum(frame ** 2)
            noise_profile.append(frame_energy)

        noise_threshold = np.percentile(noise_profile, 10)

        # Apply noise gate with smoothing
        data_clean = data.copy()
        mask = abs(data_clean) < (noise_threshold * self.props.noise_reduction)
        data_clean[mask] = data_clean[mask] * (1 - self.props.noise_reduction)

        return data_clean

    def energy_based_detection(self, data, progress_callback):
        """Classic energy-based beat detection"""
        beats = []
        window_size = int(self.props.analysis_window * self.sample_rate / 1000)
        hop_length = window_size // 2

        # Calculate energy for each window
        energies = []
        for i in range(0, len(data) - window_size, hop_length):
            if progress_callback:
                progress = (i / len(data)) * 100
                progress_callback(progress)

            window = data[i:i + window_size]
            energy = np.sum(window ** 2)
            energies.append(energy)

        # Find peaks in energy
        energies = np.array(energies)
        threshold = np.mean(energies) * self.props.sensitivity

        for i in range(1, len(energies) - 1):
            if energies[i] > threshold and energies[i] > energies[i-1] and energies[i] > energies[i+1]:
                beat_time = (i * hop_length) / self.sample_rate
                beat_strength = energies[i] / threshold
                beats.append((beat_time, self.categorize_beat_strength(beat_strength)))

        return beats

    def spectral_flux_detection(self, data, progress_callback):
        """Beat detection using spectral flux"""
        spectrogram = self.compute_spectrogram(data, progress_callback)

        # Calculate spectral flux
        flux = np.diff(spectrogram, axis=0)
        flux = np.maximum(flux, 0)
        flux = np.sum(flux, axis=1)

        # Normalize flux
        flux = flux / np.max(flux)

        # Find peaks
        threshold = np.mean(flux) * self.props.sensitivity
        beats = []

        for i in range(1, len(flux) - 1):
            if flux[i] > threshold and flux[i] > flux[i-1] and flux[i] > flux[i+1]:
                beat_time = (i * self.hop_length) / self.sample_rate
                beat_strength = flux[i] / threshold
                beats.append((beat_time, self.categorize_beat_strength(beat_strength)))

        return beats

    def complex_detection(self, data, progress_callback):
        """Combined energy and spectral analysis"""
        energy_beats = self.energy_based_detection(data, lambda p: progress_callback(p / 2))
        spectral_beats = self.spectral_flux_detection(data, lambda p: progress_callback(50 + p / 2))

        # Combine and sort beats
        all_beats = energy_beats + spectral_beats
        all_beats.sort(key=lambda x: x[0])

        # Remove duplicates and close beats
        min_beat_distance = 60 / self.props.max_bpm
        filtered_beats = []
        last_beat_time = -min_beat_distance

        for beat_time, strength in all_beats:
            if beat_time - last_beat_time >= min_beat_distance:
                filtered_beats.append((beat_time, strength))
                last_beat_time = beat_time

        return filtered_beats

    def adaptive_threshold_detection(self, data, progress_callback):
        """Beat detection with adaptive thresholding"""
        window_size = int(self.props.analysis_window * self.sample_rate / 1000)
        hop_length = window_size // 2

        # Calculate local energy
        energies = []
        for i in range(0, len(data) - window_size, hop_length):
            if progress_callback:
                progress = (i / len(data)) * 100
                progress_callback(progress)

            window = data[i:i + window_size]
            energy = np.sum(window ** 2)
            energies.append(energy)

        energies = np.array(energies)

        # Calculate adaptive threshold
        kernel_size = int(2 * self.sample_rate / hop_length)
        kernel_size = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
        threshold = np.zeros_like(energies)

        for i in range(len(energies)):
            start = max(0, i - kernel_size // 2)
            end = min(len(energies), i + kernel_size // 2)
            threshold[i] = np.mean(energies[start:end]) * self.props.sensitivity

        # Find beats
        beats = []
        for i in range(1, len(energies) - 1):
            if (energies[i] > threshold[i] and
                energies[i] > energies[i-1] and
                energies[i] > energies[i+1]):
                beat_time = (i * hop_length) / self.sample_rate
                beat_strength = energies[i] / threshold[i]
                beats.append((beat_time, self.categorize_beat_strength(beat_strength)))

        return beats

    def categorize_beat_strength(self, strength):
        """Categorize beat strength based on thresholds"""
        if strength >= self.props.strong_beat_threshold:
            return 'strong'
        elif strength >= self.props.medium_beat_threshold:
            return 'medium'
        return 'weak'

    def compute_spectrogram(self, data, progress_callback=None):
        """Compute spectrogram using STFT"""
        spectrogram = []
        window = np.hanning(self.window_size)

        for i in range(0, len(data) - self.window_size, self.hop_length):
            if progress_callback:
                progress = (i / len(data)) * 100
                progress_callback(progress)

            windowed = data[i:i + self.window_size] * window
            spectrum = np.abs(np.fft.rfft(windowed))
            spectrogram.append(spectrum)

        return np.array(spectrogram)

    def refine_beats(self, data, beats):
        """Refine beat positions by looking for local maxima"""
        if not beats:
            return beats

        refined_beats = []
        window_size = int(0.05 * self.sample_rate)  # 50ms window

        for beat_time, strength in beats:
            center_idx = int(beat_time * self.sample_rate)
            start_idx = max(0, center_idx - window_size // 2)
            end_idx = min(len(data), center_idx + window_size // 2)

            window = data[start_idx:end_idx]

            if len(window) > 0:
                local_energies = window ** 2
                max_energy_idx = np.argmax(local_energies)
                refined_time = (start_idx + max_energy_idx) / self.sample_rate
                refined_beats.append((refined_time, strength))

        refined_beats.sort(key=lambda x: x[0])

        # Remove beats that are too close together
        min_beat_distance = 60 / self.props.max_bpm
        filtered_beats = []
        last_beat_time = -min_beat_distance

        for beat_time, strength in refined_beats:
            if beat_time - last_beat_time >= min_beat_distance:
                filtered_beats.append((beat_time, strength))
                last_beat_time = beat_time

        return filtered_beats



class BEATANALYZER_OT_analyze(Operator):
    bl_idname = "beatanalyzer.analyze"
    bl_label = "Analyze Audio"
    bl_description = "Perform beat analysis on selected audio file"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _analysis_thread = None

    def modal(self, context, event):
        if event.type == 'TIMER':
            if self._analysis_thread and self._analysis_thread.is_alive():
                # Update progress bar
                wm = context.window_manager
                wm.progress_update(self._analysis_thread.progress)
                return {'RUNNING_MODAL'}

            elif self._analysis_thread:
                # Analysis completed
                wm = context.window_manager
                wm.progress_end()

                if self._analysis_thread.error:
                    self.report({'ERROR'}, self._analysis_thread.error)
                    return {'CANCELLED'}

                if self._analysis_thread.results:
                    self.apply_results(context, self._analysis_thread.results)

                wm.event_timer_remove(self._timer)
                self._analysis_thread = None
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def clear_markers(self, context):
        """Helper function to safely clear markers"""
        scene = context.scene

        # Direct method to remove markers
        while scene.timeline_markers:
            scene.timeline_markers.remove(scene.timeline_markers[0])

    def execute(self, context):
        props = context.scene.beat_analyzer_props

        if not props.audio_file:
            self.report({'ERROR'}, "No audio file selected")
            return {'CANCELLED'}

        if not os.path.exists(props.audio_file):
            self.report({'ERROR'}, f"File not found: {props.audio_file}")
            return {'CANCELLED'}

        # Add audio to sequencer
        self.add_audio_to_sequencer(context)

        # Check cache first
        if props.use_cache:
            settings = self.get_analysis_settings(props)
            cached_result = BeatAnalyzerCache.get_cached_result(props.audio_file, settings)
            if cached_result:
                self.apply_results(context, cached_result)
                return {'FINISHED'}

        # Clear existing markers using direct method
        self.clear_markers(context)

        # Start analysis thread
        self._analysis_thread = AudioAnalysisThread(props.audio_file, props)
        self._analysis_thread.start()

        # Start modal timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.progress_begin(0, 100)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def add_audio_to_sequencer(self, context):
        """Add audio file to the VSE sequencer.
        
        Uses the direct sequences API (preferred) with a fallback to
        context.temp_override (Blender 4.0+) instead of the removed
        dict-based context override.
        """
        scene = context.scene
        props = scene.beat_analyzer_props

        # Create sequence editor if it doesn't exist
        if not scene.sequence_editor:
            scene.sequence_editor_create()

        # Check if audio already exists
        for seq in scene.sequence_editor.sequences_all:
            if seq.type == 'SOUND' and seq.sound.filepath == props.audio_file:
                seq.mute = props.audio_muted
                return  # Audio already exists

        try:
            # Primary method: Direct API (works in all Blender 3.0+ versions)
            sequence_editor = scene.sequence_editor
            soundstrip = sequence_editor.sequences.new_sound(
                name=os.path.basename(props.audio_file),
                filepath=props.audio_file,
                channel=1,
                frame_start=1
            )
            soundstrip.mute = props.audio_muted

        except Exception as e:
            print(f"Direct method failed: {str(e)}")
            try:
                # Fallback: Use operator with context.temp_override (Blender 4.0+)
                # Find a sequence editor area, or temporarily change one
                sequence_area = None
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'SEQUENCE_EDITOR':
                            sequence_area = area
                            break
                    if sequence_area:
                        break

                if not sequence_area and context.area:
                    sequence_area = context.area

                if sequence_area:
                    with context.temp_override(
                        window=context.window,
                        area=sequence_area,
                        region=sequence_area.regions[0] if sequence_area.regions else context.region,
                    ):
                        bpy.ops.sequencer.sound_strip_add(
                            filepath=props.audio_file,
                            frame_start=1,
                            channel=1
                        )

                    # Set mute state for newly added audio
                    for seq in scene.sequence_editor.sequences_all:
                        if seq.type == 'SOUND' and seq.sound.filepath == props.audio_file:
                            seq.mute = props.audio_muted
                            break

            except Exception as e:
                print(f"temp_override method failed: {str(e)}")
                # Final attempt: Most basic approach (only works if context is already correct)
                try:
                    bpy.ops.sequencer.sound_strip_add(
                        filepath=props.audio_file,
                        frame_start=1,
                        channel=1
                    )

                    # Set mute state
                    for seq in scene.sequence_editor.sequences_all:
                        if seq.type == 'SOUND' and seq.sound.filepath == props.audio_file:
                            seq.mute = props.audio_muted
                            break

                except Exception as e:
                    print(f"All methods failed: {str(e)}")
                    self.report({'ERROR'}, "Failed to add audio to sequencer")

    def get_analysis_settings(self, props):
        return {
            'detection_method': props.detection_method,
            'frequency_bands': props.frequency_bands,
            'sensitivity': props.sensitivity,
            'noise_reduction': props.noise_reduction,
            'analysis_window': props.analysis_window,
            'min_bpm': props.min_bpm,
            'max_bpm': props.max_bpm
        }

    def apply_results(self, context, results):
        props = context.scene.beat_analyzer_props
        scene = context.scene

        # Create markers for beats
        for time, strength in results['beats']:
            if ((strength == 'strong' and props.show_strong_beats) or
                (strength == 'medium' and props.show_medium_beats) or
                (strength == 'weak' and props.show_weak_beats)):
                frame = int(time * scene.render.fps)
                marker_name = f"{props.marker_prefix}{frame}_{strength}"
                marker = scene.timeline_markers.new(marker_name, frame=frame)

        # Update properties with results
        props.total_beats = len(results['beats'])
        props.average_bpm = results['audio_info']['bpm']
        props.audio_duration = results['audio_info']['duration']
        props.last_analysis_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Update debug info
        if props.debug_mode:
            props.debug_info = (
                f"Sample Rate: {results['audio_info']['sample_rate']} Hz\n"
                f"Channels: {results['audio_info']['channels']}\n"
                f"Duration: {results['audio_info']['duration']:.2f} seconds\n"
                f"Total Beats: {props.total_beats}\n"
                f"Average BPM: {props.average_bpm:.1f}"
            )

        # Cache results if enabled
        if props.use_cache:
            settings = self.get_analysis_settings(props)
            BeatAnalyzerCache.store_result(props.audio_file, settings, results)



class BEATANALYZER_OT_bake_to_shader(Operator):
    bl_idname = "beatanalyzer.bake_to_shader"
    bl_label = "Bake to AVS"
    bl_description = "Bake audio to Audio Value Shader node"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def find_or_create_value_setup(self, context, target_type):
        obj = context.active_object
        value_nodes = []
        node_trees = []

        # Handle Material Nodes (Shader Editor)
        if not obj.active_material:
            mat = bpy.data.materials.new(name="Audio Visualizer")
            mat.use_nodes = True
            obj.active_material = mat
        else:
            mat = obj.active_material
            mat.use_nodes = True

        shader_tree = mat.node_tree
        value_node = None

        # Check existing material nodes
        for node in shader_tree.nodes:
            if node.type == 'VALUE' and node.label == "Audio Value Shader":
                value_node = node
                break

        # If not found, create new setup
        if not value_node:
            # Create nodes
            value_node = shader_tree.nodes.new('ShaderNodeValue')
            value_node.label = "Audio Value Shader"
            value_node.name = "Audio Value Shader"

            noise_tex = shader_tree.nodes.new('ShaderNodeTexNoise')
            color_ramp = shader_tree.nodes.new('ShaderNodeValToRGB')
            principled = shader_tree.nodes.new('ShaderNodeBsdfPrincipled')
            output = shader_tree.nodes.new('ShaderNodeOutputMaterial')

            # Position nodes
            value_node.location = (-600, 0)
            noise_tex.location = (-400, 0)
            color_ramp.location = (-200, 0)
            principled.location = (0, 0)
            output.location = (200, 0)

            # Link nodes
            shader_tree.links.new(value_node.outputs[0], noise_tex.inputs['Scale'])
            shader_tree.links.new(noise_tex.outputs['Fac'], color_ramp.inputs[0])

            # Use version-aware emission input name
            emission_input = get_principled_emission_input_name()
            shader_tree.links.new(color_ramp.outputs[0], principled.inputs[emission_input])
            shader_tree.links.new(principled.outputs[0], output.inputs[0])

            # Set up default color ramp
            color_ramp.color_ramp.elements[0].position = 0.0
            color_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
            color_ramp.color_ramp.elements[1].position = 1.0
            color_ramp.color_ramp.elements[1].color = (1, 1, 1, 1)

            # Set up Principled BSDF
            principled.inputs['Emission Strength'].default_value = 1.0

        value_nodes.append(value_node)
        node_trees.append(shader_tree)

        return value_nodes, node_trees

    def execute(self, context):
        props = context.scene.beat_analyzer_props

        # Basic checks
        if not context.active_object:
            self.report({'WARNING'}, "No active object selected. Please select an object first.")
            return {'CANCELLED'}

        if not props.audio_file or not os.path.exists(props.audio_file):
            self.report({'WARNING'}, "No valid audio file selected.")
            return {'CANCELLED'}

        try:
            # Find or create value nodes for shader only
            value_nodes, node_trees = self.find_or_create_value_setup(context, 'SHADER')

            if not value_nodes:
                self.report({'WARNING'}, "Could not create or find shader value node")
                return {'CANCELLED'}

            value_node = value_nodes[0]
            node_tree = node_trees[0]

            # Ensure animation data exists
            if not node_tree.animation_data:
                node_tree.animation_data_create()

            # Create or get action
            action_name = f"AudioAnimation_{value_node.name}"
            action = bpy.data.actions.new(name=action_name)
            node_tree.animation_data.action = action

            # Clear existing fcurves for this node
            fcurves = action.fcurves
            for fc in fcurves[:]:
                if value_node.name in fc.data_path:
                    fcurves.remove(fc)

            # Insert keyframe at frame 1
            value_node.outputs[0].default_value = 0
            value_node.outputs[0].keyframe_insert(data_path="default_value", frame=1)

            # Get the created fcurve
            fcurve = None
            for fc in action.fcurves:
                if "default_value" in fc.data_path and value_node.name in fc.data_path:
                    fcurve = fc
                    break

            if not fcurve:
                self.report({'ERROR'}, "Could not create F-Curve for audio baking")
                return {'CANCELLED'}

            # Make the fcurve active and visible
            fcurve.select = True
            fcurve.hide = False

            # Get the graph editor
            screen = context.screen
            if not screen:
                self.report({'ERROR'}, "No screen found")
                return {'CANCELLED'}

            # Find or create a temporary graph editor area
            temp_area = None
            original_type = None

            for area in screen.areas:
                if area.type == 'GRAPH_EDITOR':
                    temp_area = area
                    break

            if not temp_area:
                temp_area = context.area
                original_type = temp_area.type
                temp_area.type = 'GRAPH_EDITOR'

            try:
                # Bake sound to fcurve using context.temp_override (Blender 4.0+)
                with context.temp_override(area=temp_area):
                    bpy.ops.graph.sound_to_samples(
                        filepath=props.audio_file
                    )

                # Add modifiers
                # Clear existing modifiers
                for mod in fcurve.modifiers:
                    fcurve.modifiers.remove(mod)

                # Add shader-specific modifiers
                env_mod = fcurve.modifiers.new('ENVELOPE')
                env_mod.reference_value = 0.5
                if props.bake_smoothing > 0:
                    smooth_amount = props.bake_smoothing / 10.0
                    env_mod.influence = smooth_amount

                limit_mod = fcurve.modifiers.new('LIMITS')
                limit_mod.mute = False
                limit_mod.min_y = 0.0
                limit_mod.max_y = 5.0

            finally:
                # Restore original area type if we changed it
                if original_type:
                    temp_area.type = original_type

            self.report({'INFO'}, "Audio baked to shader value node successfully!")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Operation failed: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {'CANCELLED'}



class BEATANALYZER_OT_bake_to_geometry(Operator):
    bl_idname = "beatanalyzer.bake_to_geometry"
    bl_label = "Bake to AVG"
    bl_description = "Bake audio to Audio Value Geometry node"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def find_or_create_value_setup(self, context, target_type):
        obj = context.active_object
        value_nodes = []
        node_trees = []

        # Handle Geometry Nodes
        # Check if geometry nodes modifier exists
        geo_mod = None
        for mod in obj.modifiers:
            if mod.type == 'NODES':
                geo_mod = mod
                break

        if not geo_mod:
            # Create new geometry nodes modifier
            geo_mod = obj.modifiers.new(name="Audio Visualizer", type='NODES')

        if not geo_mod.node_group:
            # Create new node group if none exists
            geo_mod.node_group = bpy.data.node_groups.new("Audio Visualizer", 'GeometryNodeTree')

            # In Blender 4.0+ we need to use the interface API to define group sockets
            geo_tree = geo_mod.node_group
            if hasattr(geo_tree, 'interface'):
                # Blender 4.0+ interface-based socket definition
                geo_tree.interface.new_socket(
                    name="Geometry",
                    in_out='INPUT',
                    socket_type='NodeSocketGeometry'
                )
                geo_tree.interface.new_socket(
                    name="Geometry",
                    in_out='OUTPUT',
                    socket_type='NodeSocketGeometry'
                )
            else:
                # Blender 3.x fallback
                geo_tree.inputs.new('NodeSocketGeometry', "Geometry")
                geo_tree.outputs.new('NodeSocketGeometry', "Geometry")

        geo_tree = geo_mod.node_group
        value_node = None

        # Check existing geometry nodes
        for node in geo_tree.nodes:
            if node.type == 'VALUE' and node.label == "Audio Value Geometry":
                value_node = node
                break

        # If not found, create new setup
        if not value_node:
            # Find or create input/output nodes
            group_in = None
            group_out = None
            for node in geo_tree.nodes:
                if node.type == 'GROUP_INPUT':
                    group_in = node
                elif node.type == 'GROUP_OUTPUT':
                    group_out = node

            if not group_in:
                group_in = geo_tree.nodes.new('NodeGroupInput')
                group_in.location = (-600, 0)

            if not group_out:
                group_out = geo_tree.nodes.new('NodeGroupOutput')
                group_out.location = (400, 0)

            # Create audio visualization nodes
            value_node = geo_tree.nodes.new('ShaderNodeValue')
            value_node.label = "Audio Value Geometry"
            value_node.name = "Audio Value Geometry"

            noise_tex = geo_tree.nodes.new('ShaderNodeTexNoise')
            noise_tex.noise_dimensions = '4D'  # Set to 4D mode

            # Position the new nodes
            value_node.location = (-400, -300)
            noise_tex.location = (-200, -300)

            # Connect only the audio value to noise W input
            geo_tree.links.new(value_node.outputs[0], noise_tex.inputs['W'])

            # If there's no connection between group in/out, create default pass-through
            if not any(link.from_node == group_in and link.to_node == group_out
                      for link in geo_tree.links):
                # Create default geometry pass-through
                if 'Geometry' in group_in.outputs and 'Geometry' in group_out.inputs:
                    geo_tree.links.new(group_in.outputs['Geometry'],
                                     group_out.inputs['Geometry'])

        value_nodes.append(value_node)
        node_trees.append(geo_tree)

        return value_nodes, node_trees

    def execute(self, context):
        props = context.scene.beat_analyzer_props

        # Basic checks
        if not context.active_object:
            self.report({'WARNING'}, "No active object selected. Please select an object first.")
            return {'CANCELLED'}

        if not props.audio_file or not os.path.exists(props.audio_file):
            self.report({'WARNING'}, "No valid audio file selected.")
            return {'CANCELLED'}

        try:
            # Find or create value nodes for geometry only
            value_nodes, node_trees = self.find_or_create_value_setup(context, 'GEOMETRY')

            if not value_nodes:
                self.report({'WARNING'}, "Could not create or find geometry value node")
                return {'CANCELLED'}

            value_node = value_nodes[0]
            node_tree = node_trees[0]

            # Ensure animation data exists
            if not node_tree.animation_data:
                node_tree.animation_data_create()

            # Create or get action
            action_name = f"AudioAnimation_{value_node.name}"
            action = bpy.data.actions.new(name=action_name)
            node_tree.animation_data.action = action

            # Clear existing fcurves for this node
            fcurves = action.fcurves
            for fc in fcurves[:]:
                if value_node.name in fc.data_path:
                    fcurves.remove(fc)

            # Insert keyframe at frame 1
            value_node.outputs[0].default_value = 0
            value_node.outputs[0].keyframe_insert(data_path="default_value", frame=1)

            # Get the created fcurve
            fcurve = None
            for fc in action.fcurves:
                if "default_value" in fc.data_path and value_node.name in fc.data_path:
                    fcurve = fc
                    break

            if not fcurve:
                self.report({'ERROR'}, "Could not create F-Curve for audio baking")
                return {'CANCELLED'}

            # Make the fcurve active and visible
            fcurve.select = True
            fcurve.hide = False

            # Get the graph editor
            screen = context.screen
            if not screen:
                self.report({'ERROR'}, "No screen found")
                return {'CANCELLED'}

            # Find or create a temporary graph editor area
            temp_area = None
            original_type = None

            for area in screen.areas:
                if area.type == 'GRAPH_EDITOR':
                    temp_area = area
                    break

            if not temp_area:
                temp_area = context.area
                original_type = temp_area.type
                temp_area.type = 'GRAPH_EDITOR'

            try:
                # Bake sound to fcurve using context.temp_override (Blender 4.0+)
                with context.temp_override(area=temp_area):
                    bpy.ops.graph.sound_to_samples(
                        filepath=props.audio_file
                    )

                # Add modifiers
                # Clear existing modifiers
                for mod in fcurve.modifiers:
                    fcurve.modifiers.remove(mod)

                # Add geometry-specific modifiers
                env_mod = fcurve.modifiers.new('ENVELOPE')
                env_mod.reference_value = 0.0
                if props.bake_smoothing > 0:
                    smooth_amount = props.bake_smoothing / 20.0
                    env_mod.influence = smooth_amount

                limit_mod = fcurve.modifiers.new('LIMITS')
                limit_mod.mute = False
                limit_mod.min_y = -2.0
                limit_mod.max_y = 2.0

            finally:
                # Restore original area type if we changed it
                if original_type:
                    temp_area.type = original_type

            self.report({'INFO'}, "Audio baked to geometry value node successfully!")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Operation failed: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return {'CANCELLED'}



class BEATANALYZER_OT_toggle_mute(Operator):
    bl_idname = "beatanalyzer.toggle_mute"
    bl_label = "Toggle Audio Mute"
    bl_description = "Toggle mute state of the analyzed audio"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        scene = context.scene

        if not scene.sequence_editor:
            self.report({'ERROR'}, "No sequence editor found")
            return {'CANCELLED'}

        # Find and toggle audio
        found_audio = False
        for seq in scene.sequence_editor.sequences_all:
            if seq.type == 'SOUND' and seq.sound.filepath == props.audio_file:
                seq.mute = not seq.mute  # Toggle mute state
                props.audio_muted = seq.mute  # Update property to match
                found_audio = True
                break

        if not found_audio:
            self.report({'WARNING'}, "No audio found to toggle")
            return {'CANCELLED'}

        return {'FINISHED'}


class BEATANALYZER_OT_export(Operator):
    bl_idname = "beatanalyzer.export"
    bl_label = "Export Analysis"
    bl_description = "Export beat analysis data to JSON file"

    filepath: StringProperty(
        subtype='FILE_PATH',
        default="beat_analysis.json"
    )

    def execute(self, context):
        props = context.scene.beat_analyzer_props
        scene = context.scene

        export_data = {
            'file_info': {
                'audio_file': props.audio_file,
                'analysis_date': props.last_analysis_time,
                'duration': props.audio_duration,
                'total_beats': props.total_beats,
                'average_bpm': props.average_bpm
            },
            'analysis_settings': {
                'detection_method': props.detection_method,
                'frequency_bands': props.frequency_bands,
                'sensitivity': props.sensitivity,
                'noise_reduction': props.noise_reduction,
                'analysis_window': props.analysis_window
            },
            'beats': [
                {
                    'frame': marker.frame,
                    'time': marker.frame / scene.render.fps,
                    'name': marker.name,
                    'strength': marker.name.split('_')[-1]
                }
                for marker in scene.timeline_markers
            ]
        }

        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)
            self.report({'INFO'}, f"Analysis exported to {self.filepath}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class BEATANALYZER_OT_next_marker(Operator):
    bl_idname = "beatanalyzer.next_marker"
    bl_label = "Next Beat Marker"
    bl_description = "Go to next beat marker"

    def execute(self, context):
        bpy.ops.screen.marker_jump(next=True)
        return {'FINISHED'}


class BEATANALYZER_OT_prev_marker(Operator):
    bl_idname = "beatanalyzer.prev_marker"
    bl_label = "Previous Beat Marker"
    bl_description = "Go to previous beat marker"

    def execute(self, context):
        bpy.ops.screen.marker_jump(next=False)
        return {'FINISHED'}


class BEATANALYZER_OT_bind_camera(Operator):
    bl_idname = "beatanalyzer.bind_camera"
    bl_label = "Bind Camera to Marker"
    bl_description = "Bind selected camera to current marker"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'CAMERA'

    def execute(self, context):
        scene = context.scene
        current_frame = scene.frame_current

        # Find marker at current frame
        current_marker = None
        for marker in scene.timeline_markers:
            if marker.frame == current_frame:
                current_marker = marker
                break

        if not current_marker:
            self.report({'ERROR'}, "No marker at current frame")
            return {'CANCELLED'}

        # Bind camera using native Blender property
        current_marker.camera = context.active_object

        # Set scene camera to active camera
        scene.camera = context.active_object

        self.report({'INFO'}, f"Camera bound to marker {current_marker.name}")
        return {'FINISHED'}


class BEATANALYZER_OT_update_marker_visibility(Operator):
    bl_idname = "beatanalyzer.update_marker_visibility"
    bl_label = "Update Marker Visibility"
    bl_description = "Update the visibility of beat markers"

    def execute(self, context):
        scene = context.scene
        props = scene.beat_analyzer_props

        # Store markers data
        markers_data = []
        for marker in scene.timeline_markers:
            if marker.name.startswith(props.marker_prefix):
                strength = marker.name.split('_')[-1]
                if ((strength == 'strong' and props.show_strong_beats) or
                    (strength == 'medium' and props.show_medium_beats) or
                    (strength == 'weak' and props.show_weak_beats)):
                    markers_data.append((marker.name, marker.frame))

        # Clear markers using direct method
        while scene.timeline_markers:
            scene.timeline_markers.remove(scene.timeline_markers[0])

        # Restore visible markers
        for name, frame in markers_data:
            scene.timeline_markers.new(name, frame=frame)

        return {'FINISHED'}


class BEATANALYZER_OT_clear_markers(Operator):
    bl_idname = "beatanalyzer.clear_markers"
    bl_label = "Clear Beat Markers"
    bl_description = "Remove all beat markers"

    def execute(self, context):
        scene = context.scene

        # Clear markers using direct method
        while scene.timeline_markers:
            scene.timeline_markers.remove(scene.timeline_markers[0])

        return {'FINISHED'}


class BEATANALYZER_PT_main_panel(Panel):
    bl_label = "Advanced Beat Analyzer"
    bl_idname = "BEATANALYZER_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Beat Analyzer'

    def draw(self, context):
        layout = self.layout
        props = context.scene.beat_analyzer_props

        # File selection
        box = layout.box()
        box.label(text="Audio Source", icon='SOUND')
        box.prop(props, "audio_file")
        if props.audio_file:
            row = box.row(align=True)
            # Add mute toggle button with dynamic icon
            icon = 'MUTE_IPO_OFF' if props.audio_muted else 'SPEAKER'
            row.operator("beatanalyzer.toggle_mute",
                        text="Toggle Mute",
                        icon=icon,
                        depress=props.audio_muted)

        # Analysis settings
        box = layout.box()
        box.label(text="Analysis Settings", icon='SETTINGS')
        box.prop(props, "detection_method")
        box.prop(props, "frequency_bands")

        if props.frequency_bands == 'CUSTOM':
            box.prop(props, "custom_freq_low")
            box.prop(props, "custom_freq_high")

        box.prop(props, "sensitivity")

        # Advanced settings
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

        # Analyze button
        layout.operator("beatanalyzer.analyze", icon='PLAY')

        # Marker settings
        box = layout.box()
        box.label(text="Marker Settings", icon='MARKER')
        box.prop(props, "marker_prefix")

        # Marker visibility
        col = box.column(align=True)
        col.label(text="Show Beats:")
        row = col.row(align=True)
        row.prop(props, "show_strong_beats", toggle=True)
        row.prop(props, "show_medium_beats", toggle=True)
        row.prop(props, "show_weak_beats", toggle=True)
        box.operator("beatanalyzer.update_marker_visibility", icon='FILE_REFRESH')

        # Navigation and camera
        row = box.row(align=True)
        row.operator("beatanalyzer.prev_marker", icon='PREV_KEYFRAME')
        row.operator("beatanalyzer.next_marker", icon='NEXT_KEYFRAME')

        # Camera binding
        if context.active_object and context.active_object.type == 'CAMERA':
            box.operator("beatanalyzer.bind_camera", icon='CAMERA_DATA')

        # Clear markers
        if context.scene.timeline_markers:
            box.operator("beatanalyzer.clear_markers", icon='X')

        # Audio baking
        row = layout.row(align=True)
        row.operator("beatanalyzer.bake_to_shader", text="Bake to AVS", icon='SHADING_RENDERED')
        row.operator("beatanalyzer.bake_to_geometry", text="Bake to AVG", icon='GEOMETRY_NODES')

        # Results
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


# Registration
classes = (
    BeatAnalyzerProperties,
    BEATANALYZER_OT_analyze,
    BEATANALYZER_OT_export,
    BEATANALYZER_OT_next_marker,
    BEATANALYZER_OT_prev_marker,
    BEATANALYZER_OT_bind_camera,
    BEATANALYZER_OT_update_marker_visibility,
    BEATANALYZER_OT_clear_markers,
    BEATANALYZER_OT_bake_to_shader,
    BEATANALYZER_OT_bake_to_geometry,
    BEATANALYZER_OT_toggle_mute,
    BEATANALYZER_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.beat_analyzer_props = bpy.props.PointerProperty(type=BeatAnalyzerProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.beat_analyzer_props


if __name__ == "__main__":
    register()
