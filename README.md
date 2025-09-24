# Assistivox™ AI

A voice-enabled document productivity suite designed for technical workers who need visual or motor accessibility solutions. Transforms documents into accessible content using local AI models, enabling professional work that traditional accessibility tools cannot adequately support.

## Key Features

- **100% Local Processing**: All AI models run on your machine - no cloud dependencies
- **Advanced Document Vision**: Extract text from PDFs, images, and complex layouts  
- **Professional TTS**: High-quality speech synthesis optimized for extended listening
- **Real-time Dictation**: Offline speech-to-text with multiple engine options
- **Cross-platform**: Windows, macOS, and Linux support

## Quick Start

### Prerequisites
Install system dependencies for your platform:
- **Audio**: PortAudio (for speech features)
- **OCR**: Tesseract (for document processing) 
- **TTS**: Docker (for premium Kokoro voices, optional)

See [full installation guide](https://assistivox.ai) for platform-specific instructions.

### Installation

```bash
git clone https://github.com/cynsight/assistivox-ai.git
cd assistivox-ai
python setup-assistivox.py
```

**Requirements**: 10GB free storage, 5-20 minute installation time. Creates virtual environment, downloads basic AI models automatically, and installs a desktop shortcut.

## Documentation

Complete documentation and guides available at: **https://assistivox.ai**

## System Requirements

- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 10GB for full AI model suite
- **GPU**: Optional (NVIDIA with CUDA for acceleration)

## Privacy

All processing occurs locally. No user data transmitted to external services. Documents and voice data never leave your control.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Beta Notice

Currently in beta with manual dependency installation required for full AI capabilities. Simplified installation coming in future releases.
