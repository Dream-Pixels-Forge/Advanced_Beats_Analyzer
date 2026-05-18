# Advanced Beat Analyzer for Blender

<p align="center">
  <img src="https://github.com/user-attachments/assets/4c519785-a6f6-44f7-8e22-ab5a02f65d74" alt="Advanced Beat Analyzer icon" width="128"/>
</p>

<p align="center">
  <strong>Professional audio beat detection &amp; audio-reactive animation tools for Blender 5.1+</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#features">Features</a> &bull;
  <a href="#api--architecture">Architecture</a> &bull;
  <a href="#contributing">Contributing</a>
</p>

---

![Panel screenshot](https://github.com/user-attachments/assets/b435c449-8d65-416d-8e1b-78c7e63c2213)

## Why Advanced Beat Analyzer?

Advanced Beat Analyzer turns audio analysis into a one-click workflow. Select a WAV file, hit **Analyze**, and instantly get timeline markers at every detected beat — categorized by strength. Then bake that audio energy directly into **Shader Nodes** (AVS — Audio Values to Shader) or **Geometry Nodes** (AVG — Audio Value to Geometry) to drive any parameter in real time.

| Use Case | How It Helps |
|----------|-------------|
| Motion Design | Drive material emission, scale, and color with beat intensity |
| Video Editing | Auto-place markers for camera cuts synced to music |
| Music Videos | Generate audio-reactive geometry and shaders instantly |
| Live Visuals | Real-time parameter feedback from audio amplitude |

---

## Features

### Beat Detection Engine

| Method | Description |
|--------|-------------|
| **Energy Based** | Classic RMS energy peak detection |
| **Spectral Flux** | Frequency-domain onset detection |
| **Complex** | Combined energy + spectral for highest accuracy |
| **Adaptive Threshold** | Dynamic sensitivity that adjusts to the track |

- Configurable frequency bands (Bass / Mid / High / Custom range)
- Noise reduction with adjustable gate
- Beat refinement pass for sub-frame accuracy
- Automatic BPM calculation

### Audio Baking

- **Bake to AVS** (Audio Values to Shader) — Creates a Value node in the Shader Editor driven by audio amplitude, connected to a Noise Texture → Color Ramp → Principled BSDF emission pipeline.
- **Bake to AVG** (Audio Value to Geometry) — Creates a Value node inside a Geometry Nodes modifier, driving a 4D Noise Texture's W input for procedural audio-reactive geometry.
- Envelope and Limits modifiers auto-applied with configurable smoothing.

### Marker Management

- Three strength tiers: **Strong**, **Medium**, **Weak**
- Toggle visibility per tier
- Jump between beats with Prev/Next navigation
- Bind cameras to markers for automatic shot switching
- Export analysis results to JSON

### Sequencer Integration

- Audio file auto-loaded into the Video Sequence Editor
- Mute/unmute toggle from the panel
- Frame-accurate sync between markers and audio strip

---

## Installation

### From the Blender Extensions Platform (recommended)

1. Open **Edit → Preferences → Extensions**
2. Search for "Advanced Beat Analyzer"
3. Click **Install**

### Manual Install

1. Download the latest release `.zip` from the [Releases](https://github.com/Dream-Pixels-Forge/Advanced_Beats_Analyzer/releases) page
2. In Blender: **Edit → Preferences → Extensions → Install from Disk…**
3. Select the downloaded `.zip`
4. Enable the extension

> **Requirement:** Blender **5.1.0** or newer.

---

## Quick Start

1. Open the **Beat Analyzer** tab in the 3D Viewport sidebar (`N` panel)
2. Set the **Audio File** path to a `.wav` file
3. Choose a detection method and frequency band
4. Click **Analyze Audio** — markers appear on your timeline
5. Select an object, then click:
   - **Bake to AVS** (Audio Values to Shader) to drive shader materials
   - **Bake to AVG** (Audio Value to Geometry) to drive geometry nodes
6. Play the animation and watch your scene react to the music!

---

## Screenshots

| Shader Setup (AVS) | Geometry Setup (AVG) |
|:---:|:---:|
| ![Shader](https://github.com/user-attachments/assets/2d7117a8-becc-444f-8de6-68b5a58f2a76) | ![Geometry](https://github.com/user-attachments/assets/723758ed-f2c9-4dec-807e-94ab0dc53b2b) |

---

## Video Tutorials

- [Getting Started with Advanced Beat Analyzer](https://www.youtube.com/watch?v=QTTjQioLz_w)
- [Audio-Reactive Geometry Nodes](https://youtu.be/N5Qw3c2WVOU?si=AMfLOAKN5X2Lapvz)

---

## Advanced Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Sensitivity | Lower = more beats detected | 1.3 |
| Min/Max BPM | Constrains detection range | 60–180 |
| Analysis Window | FFT window size in ms | 50 |
| Noise Reduction | Gate quieter sections | 0.2 |
| Beat Refinement | Sub-frame peak alignment | On |
| Threading | Background analysis | On |
| Caching | Reuse results for same settings | On |

---

## API & Architecture

This addon follows Blender extension best practices with a clean multi-file package layout:

```
advanced_beat_analyzer/
├── __init__.py              # Registration only (no bl_info)
├── blender_manifest.toml    # Extension metadata (Blender 5.1+ standard)
├── properties.py            # All PropertyGroup definitions
├── core/
│   ├── analyzer.py          # Pure-Python DSP engine (no bpy imports)
│   └── cache.py             # LRU analysis cache
├── operators/
│   ├── analyze.py           # Modal threaded beat analysis
│   ├── bake.py              # AVS / AVG audio baking
│   ├── markers.py           # Marker navigation & management
│   └── audio.py             # Mute toggle & JSON export
└── ui/
    └── panels.py            # 3D Viewport sidebar panel
```

**Key design decisions:**
- The DSP engine (`core/analyzer.py`) has **zero Blender imports** — it can be unit-tested with plain Python + NumPy.
- Thread-safe settings are passed via a `@dataclass` copy, not a live Blender `PropertyGroup` reference.
- All operator context overrides use `context.temp_override()` (the only supported method since Blender 4.0).
- Node tree group sockets use the `interface` API (`tree.interface.new_socket()`).

---

## Performance Tips

- **Enable threading** for faster analysis on multi-core systems
- **Enable caching** to avoid re-analyzing the same file with the same settings
- **Narrow the frequency band** (e.g., Bass Only) for more focused detection
- **Increase the analysis window** for smoother detection at the cost of timing precision
- **Convert audio to mono WAV** before analysis for faster processing

---

## Known Limitations

- **WAV format only** — convert MP3/FLAC/OGG to WAV first (e.g., with Audacity or FFmpeg)
- Large files (>10 min) may take several seconds to analyze
- The `graph.sound_to_samples` operator requires a Graph Editor area to be available

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Analysis is slow | Enable Threading in Advanced Settings |
| Beats are missed | Lower the Sensitivity value |
| Too many markers | Raise Sensitivity or filter by strength |
| Geometry disappears after bake | Ensure Group Input/Output are type Geometry |
| "No audio file" error | Use an absolute path or Blender-relative `//` path |

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-improvement`)
3. Follow the existing code style (type hints, SPDX headers, docstrings)
4. Submit a Pull Request

---

## Credits

Created by **Dimona Patrick** — [Dream Pixels Forge](https://github.com/Dream-Pixels-Forge)

Version 3.0.0 | Blender 5.1+

## License

This extension is released under the [GPL-3.0-or-later](LICENSE) license.
