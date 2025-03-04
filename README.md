# Advanced Beat Analyzer for Blender

![Advanced_Beat_Analyzer_icon](https://github.com/user-attachments/assets/4c519785-a6f6-44f7-8e22-ab5a02f65d74)

## Overview
Advanced Beat Analyzer is a powerful Blender addon designed specifically for motion designers and video editors. It provides professional-grade audio analysis and visualization tools, making it easier to create audio-reactive animations and synchronize visual elements with music.

![Screenshot 2025-03-04 011009](https://github.com/user-attachments/assets/b435c449-8d65-416d-8e1b-78c7e63c2213)


## Key Features
- 🎵 Two dedicated audio value nodes:
  - AVS (Audio Value Shader) for material animations
  - AVG (Audio Value Geometry) for geometry nodes
- 🎨 Audio-reactive animations for both Shader and Geometry Nodes
- 🎬 Real-time audio visualization
- 🎭 Independent control over shader and geometry animations
- ⚡ Optimized audio baking system
- 🔧 Customizable smoothing and limits

## Perfect for
- Motion Designers
- Video Editors
- 3D Animators
- Music Video Creators
- Live Visual Artists
- Anyone working with audio-driven animations
  
![Screenshot 2025-03-01 004133](https://github.com/user-attachments/assets/2d7117a8-becc-444f-8de6-68b5a58f2a76)
![Screenshot 2025-03-01 005452](https://github.com/user-attachments/assets/723758ed-f2c9-4dec-807e-94ab0dc53b2b)

## Installation
1. Download the `advanced_beat_analyzer.zip` file
2. Open Blender and go to Edit > Preferences > Add-ons
3. Click "Install" and select the downloaded file
4. Enable the addon by checking the box

## Quick Start Guide
1. Open the Beat Analyzer panel in the 3D View sidebar
2. Select your audio file
3. Choose analysis settings:
   - Detection method
   - Frequency bands
   - Sensitivity
4. Click "Analyze Audio"
5. Choose your target:
   - Click "Bake to AVS" for material animations
   - Click "Bake to AVG" for geometry animations
6. Adjust smoothing settings if needed
7. Use the generated animations in your nodes

## Youtube Exemples
https://youtu.be/N5Qw3c2WVOU?si=AMfLOAKN5X2Lapvz

## Features in Detail

### Beat Analysis
- Four detection methods:
  - Energy Based (classic)
  - Spectral Flux (frequency-based)
  - Complex Detection (combined)
  - Adaptive Threshold (dynamic)
- Customizable frequency bands
- Noise reduction
- Beat refinement
- BPM detection

### Marker Management
- Automatic beat markers
- Three strength levels (strong, medium, weak)
- Easy navigation between beats
- Camera binding to markers
- Customizable marker visibility

### Audio Visualization
- Bake audio to noise textures
- Use in Geometry Nodes
- Shader node group creation
- Real-time preview
- Smoothing controls

### Motion Design Tools
- Pre-built shader node groups
- Audio-reactive material templates
- Geometry nodes compatibility
- Customizable parameters
- Real-time feedback

### Video Editing Features
- Automatic audio sync
- Timeline markers
- Camera switching
- Export capabilities
- Audio muting control

## Advanced Settings
- Custom frequency ranges
- Sensitivity adjustment
- Noise reduction
- Beat refinement
- Threading options
- Caching system

## Workflow Integration
### For Motion Designers
- Create audio-reactive materials
- Drive parameters with beat intensity
- Automatic keyframe generation
- Real-time visualization feedback

### For Video Editors
- Automatic beat detection
- Easy camera switching
- Timeline organization
- Export capabilities

## Performance Tips
- Enable threading for faster analysis
- Use caching for repeated analysis
- Adjust window size for precision
- Choose appropriate frequency bands

## Technical Requirements
- Blender 3.0 or newer
- Python 3.7+
- Supported audio formats: WAV

## Known Limitations
- WAV format only (convert other formats first)
- Large files may require more processing time
- Real-time preview may affect performance

## Troubleshooting
- If analysis is slow, enable threading
- If beats are missed, adjust sensitivity
- If markers are cluttered, use visibility options
- If performance issues, disable real-time preview

## Updates and Support
- Check for updates regularly
- Report issues on the repository
- Suggest features for future versions

## Credits
Created by Dimona Patrick
Version 2.1

## License
This addon is released under the GPL-3 License.

---

For motion designers and video editors looking to create stunning audio-reactive content, Advanced Beat Analyzer provides all the tools needed in one comprehensive package. From basic beat detection to complex audio-driven animations, this addon streamlines the workflow for creating professional audio-visual content in Blender.

