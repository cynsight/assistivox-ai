#!/usr/bin/env python3
"""
Assistivox - Main application entry point
"""

import os
import sys
import multiprocessing
from pathlib import Path

# Ensure we're using the virtual environment's Python
venv_path = Path.home() / ".assistivox" / "venv"
if venv_path.exists() and sys.prefix != str(venv_path):
    # Activate the virtual environment
    activate_this = venv_path / "bin" / "activate_this.py"
    if activate_this.exists():
        exec(open(activate_this).read(), {'__file__': activate_this})

def detect_crostini():
    """Detect if we're running in Chrome OS Crostini"""
    # Check for Crostini-specific environment variables or files
    if os.path.exists('/dev/.cros_milestone'):
        return True
    if 'SOMMELIER_VERSION' in os.environ:
        return True
    # Check if running under ChromeOS Linux container
    try:
        with open('/etc/os-release', 'r') as f:
            content = f.read()
            if 'penguin' in content.lower() or 'chromeos' in content.lower():
                return True
    except:
        pass
    return False

def main():
    """Main entry point for Assistivox"""
    # Handle multiprocessing for frozen apps
    multiprocessing.freeze_support()
    
    # Set multiprocessing start method
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        pass  # Already set
    
    # Check command line arguments
    dev_mode = '-d' in sys.argv or '--dev' in sys.argv
    
    # Detect Crostini and set appropriate backend
    if detect_crostini():
        print("Detected Chrome OS Crostini environment")
        # Try to use XCB first, but don't force it if libraries are missing
        # Instead, we'll configure Wayland with better settings
        os.environ['QT_WAYLAND_FORCE_DPI'] = 'physical'
        os.environ['QT_WAYLAND_DISABLE_WINDOWDECORATION'] = '1'
        # Reduce Wayland timeout issues
        os.environ['QT_WAYLAND_RECONNECT'] = '1'
    
    # Import Qt modules after setting environment
    from PySide6.QtWidgets import QApplication, QSplashScreen
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    # Create the application
    app = QApplication(sys.argv)
    app.setApplicationName("Assistivox")
    app.setOrganizationName("Assistivox")
    
    # Create and show splash screen immediately with icon and text
    splash_pix = QPixmap(600, 200)
    splash_pix.fill(Qt.black)

    # Create a painter to draw on the splash screen
    from PySide6.QtGui import QPainter, QFont
    painter = QPainter(splash_pix)

    # Load the PNG icon from .assistivox directory
    icon_loaded = False
    try:
        # Determine the path to the icons directory in .assistivox
        if dev_mode:
            assistivox_dir = Path.cwd() / ".assistivox"
        else:
            assistivox_dir = Path.home() / ".assistivox"
        
        icons_dir = assistivox_dir / "src" / "icons"
        icon_path = icons_dir / "assistivox-waveform_512.png"
    
        if icon_path.exists():
            icon_pixmap = QPixmap(str(icon_path))
            if not icon_pixmap.isNull():
                # Scale icon to fit height with aspect ratio maintained
                icon_height = 120
                scaled_icon = icon_pixmap.scaled(icon_height, icon_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                # Draw icon on left side with margin
                icon_x = 40
                icon_y = (splash_pix.height() - scaled_icon.height()) // 2
                painter.drawPixmap(icon_x, icon_y, scaled_icon)
                icon_loaded = True
    except Exception as e:
        print(f"Could not load icon: {e}")

    # Draw "Assistivox AI" text
    painter.setPen(Qt.white)
    font = QFont("Arial", 28, QFont.Bold)
    painter.setFont(font)

    # Position text next to icon (or centered if no icon)
    if icon_loaded:
        text_x = 200  # Position after icon with margin
    else:
        text_x = 40   # Center-left if no icon

    text_y = splash_pix.height() // 2 + 10  # Slightly below center
    painter.drawText(text_x, text_y, "Assistivox™ AI")

    painter.end()

    splash = QSplashScreen(splash_pix)
    # Set larger font for splash messages to improve accessibility
    splash_font = QFont("Arial", 15, QFont.Normal)
    splash.setFont(splash_font)
    splash.show()
    app.processEvents()  # Force splash to appear first

    splash.showMessage("Starting Assistivox AI...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()  # Show first message
    
    # Import heavy modules during splash display
    splash.showMessage("Loading interface components...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()  # Update splash message

    from gui.main_window import AssistivoxMainWindow
    
    # Create main window with progress updates
    splash.showMessage("Initializing configuration...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    app.processEvents()  # Update splash message
    
    # Create window but don't show it yet
    window = AssistivoxMainWindow(dev_mode=dev_mode, splash=splash, app=app)
    
    # Finish splash screen and show main window
    splash.finish(window)
    window.show()
    
    # Run the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
