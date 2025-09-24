# File: gui/file_explorer/file_explorer_dialog.py
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFileSystemModel,
    QTreeView, QListView, QSplitter, QPushButton, QLineEdit,
    QFileDialog, QLabel, QWidget, QListWidget, QListWidgetItem, QMenu,
    QInputDialog
)
from PySide6.QtCore import Qt, QDir, QModelIndex, Signal, QSize, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

class FavoritesListWidget(QListWidget):
    """Custom QListWidget that handles Ctrl+Click for renaming"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_dialog = None  # Will be set by parent

    def set_file_dialog(self, dialog):
        """Set reference to the file dialog for callbacks"""
        self.file_dialog = dialog

    def mousePressEvent(self, event):
        """Handle mouse press events, including Ctrl+Click for renaming"""
        if (event.button() == Qt.LeftButton and
            event.modifiers() == Qt.ControlModifier):

            item = self.itemAt(event.pos())
            if item and self.file_dialog:
                self.file_dialog.start_rename_favorite(item)
                return

        # Call parent implementation for normal clicks
        super().mousePressEvent(event)

class FileExplorerDialog(QDialog):
    """Custom file explorer dialog for opening and saving files with accessibility features"""
    
    fileSelected = Signal(str)  # Signal emitted when a file is selected
    
    def __init__(self, parent=None, start_dir=None, mode="open", config=None, assistivox_dir=None, save_here_mode=False, file_format=None):
        super().__init__(parent)
        
        # Set dialog properties
        self.setWindowTitle("File Explorer" if mode == "open" else "Save File")
        self.setMinimumSize(800, 500)
        
        # Set initial directory
        if start_dir is None:
            start_dir = str(Path.home())
        self.current_dir = start_dir
        
        # Mode can be "open" or "save"
        self.mode = mode

        # Store config references
        self.config = config
        self.assistivox_dir = assistivox_dir

        # Load divider position from config
        self.divider_position = self.load_divider_position()
        
        # Load favorites from config
        self.favorites = self.load_favorites()

        # Save-here mode for the save flow
        self.save_here_mode = save_here_mode
        self.file_format = file_format  # 'markdown' or 'text'
        self.filename_dialog_active = False  # Track if filename dialog is showing
        self.rename_mode_active = False  # Track if we're renaming a favorite

        # Setup UI
        self.setup_ui()

        # Navigate to initial directory
        self.navigate_to(self.current_dir)

        # Add keyboard shortcuts
        self.setup_shortcuts()

    def setup_ui(self):
        """Set up the user interface components"""
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Path navigation bar
        nav_layout = QHBoxLayout()

        # "Up" button
        self.up_button = QPushButton("↑")
        self.up_button.setToolTip("Go to parent directory")
        self.up_button.clicked.connect(self.go_to_parent)
        nav_layout.addWidget(self.up_button)

        # Path display and edit
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path")
        self.path_edit.returnPressed.connect(self.path_changed)
        nav_layout.addWidget(self.path_edit)

        # Favorite button with heart icon
        self.favorite_button = QPushButton("♡ Favorite")
        self.favorite_button.setToolTip("Add/Remove from favorites")
        self.favorite_button.clicked.connect(self.toggle_favorite)
        nav_layout.addWidget(self.favorite_button)

        main_layout.addLayout(nav_layout)

        # Splitter for tree and list views
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Create file system model
        self.model = QFileSystemModel()
        self.model.setRootPath(QDir.rootPath())
        
        # Left column splitter for tree view and future bottom panel
        self.left_splitter = QSplitter(Qt.Vertical)
        
        # Top panel - Folder tree view
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(QDir.rootPath()))
        
        # Hide all columns except name
        for i in range(1, self.model.columnCount()):
            self.tree_view.hideColumn(i)
        
        # Connect signals
        self.tree_view.clicked.connect(self.folder_selected)
        
        # Connect keyboard events
        self.tree_view.keyPressEvent = self.tree_view_key_press_event

        # Bottom panel - Favorites list
        self.bottom_panel = QWidget()
        self.setup_favorites_panel()

        # Add both panels to the left splitter
        self.left_splitter.addWidget(self.tree_view)
        self.left_splitter.addWidget(self.bottom_panel)
        
        # Set initial splitter proportions based on config
        self.set_divider_position()
        
        # Connect splitter movement to save config
        self.left_splitter.splitterMoved.connect(self.on_divider_moved)

        # File list view (right pane)
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setWrapping(True)
        self.list_view.setViewMode(QListView.IconMode)
        self.list_view.setIconSize(QSize(48, 48))
        self.list_view.setGridSize(QSize(90, 90))
        self.list_view.setSpacing(10)
        
        # Connect signals
        self.list_view.doubleClicked.connect(self.item_double_clicked)
        
        # Add views to splitter
        self.splitter.addWidget(self.left_splitter)
        self.splitter.addWidget(self.list_view)
        
        # Set splitter proportions (30% left, 70% right)
        self.splitter.setSizes([200, 400])
        
        main_layout.addWidget(self.splitter)
        
        # Bottom section - buttons
        bottom_layout = QHBoxLayout()

        # Save Here button for save_here_mode
        if self.save_here_mode:
            self.save_here_button = QPushButton("Save Here (Spacebar)")
            self.save_here_button.clicked.connect(self.save_here_action)
            bottom_layout.addWidget(self.save_here_button)
    
            # Add separator
            bottom_layout.addStretch()
        elif self.mode == "save":
            # Original filename input for traditional save mode
            bottom_layout.addWidget(QLabel("File name:"))
            self.filename_edit = QLineEdit()
            bottom_layout.addWidget(self.filename_edit)
            bottom_layout.addStretch()        

        # Cancel and Open/Save buttons
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        action_button_text = "Open" if self.mode == "open" else "Save"
        self.action_button = QPushButton(action_button_text)
        self.action_button.clicked.connect(self.accept_selection)
        
        bottom_layout.addWidget(self.cancel_button)
        bottom_layout.addWidget(self.action_button)
        
        main_layout.addLayout(bottom_layout)
    
    def navigate_to(self, path):
        """Navigate to the specified directory path"""
        # Update path display
        self.path_edit.setText(path)

        # Update current directory
        self.current_dir = path

        # Update tree view to show the folder
        tree_index = self.model.index(path)
        self.tree_view.setCurrentIndex(tree_index)
        self.tree_view.expand(tree_index)

        # Update list view to show folder contents
        self.list_view.setRootIndex(self.model.index(path))

        # Update favorite button state
        self.update_favorite_button()

    def path_changed(self):
        """Handle path entry changes"""
        new_path = self.path_edit.text()
        if os.path.exists(new_path) and os.path.isdir(new_path):
            self.navigate_to(new_path)
        else:
            # Reset to current path if invalid
            self.path_edit.setText(self.current_dir)
    
    def go_to_parent(self):
        """Navigate to parent directory"""
        parent = os.path.dirname(self.current_dir)
        if parent and os.path.exists(parent):
            self.navigate_to(parent)
    
    def folder_selected(self, index):
        """Handle folder selection in tree view"""
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.navigate_to(path)
    
    def item_double_clicked(self, index):
        """Handle double click on items in list view"""
        path = self.model.filePath(index)
        if os.path.isdir(path):
            # Navigate to folder
            self.navigate_to(path)
        elif self.mode == "open" and os.path.isfile(path):
            # Select file and close dialog
            self.fileSelected.emit(path)
            self.accept()
    
    def accept_selection(self):
        """Handle the Open/Save button click"""
        if self.mode == "open":
            # Get currently selected item in list view
            indexes = self.list_view.selectedIndexes()
            if indexes:
                path = self.model.filePath(indexes[0])
                if os.path.isfile(path):
                    self.fileSelected.emit(path)
                    self.accept()
                    return
                
            # If no file selected or selection is not a file, show error or open directory
            self.navigate_to(self.current_dir)
        else:  # Save mode
            filename = self.filename_edit.text()
            if filename:
                # Combine current directory with filename
                full_path = os.path.join(self.current_dir, filename)
                self.fileSelected.emit(full_path)
                self.accept()

    def setup_shortcuts(self):
        """Set up keyboard shortcuts for the file explorer dialog"""
        # Alt+Up Arrow to go to parent directory
        self.parent_shortcut = QShortcut(QKeySequence("Alt+Up"), self)
        self.parent_shortcut.activated.connect(self.go_to_parent_safe)
    
        # Control+Alt+F to add current folder to favorites
        self.add_favorite_shortcut = QShortcut(QKeySequence("Ctrl+Alt+F"), self)
        self.add_favorite_shortcut.activated.connect(self.toggle_favorite)
    
        # Alt+Return to speak current item name
        self.speak_item_shortcut = QShortcut(QKeySequence("Alt+Return"), self)
        self.speak_item_shortcut.activated.connect(self.speak_current_item)

        # Spacebar for "Save Here" in save_here_mode
        if self.save_here_mode:
            self.save_here_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
            self.save_here_shortcut.activated.connect(self.save_here_action)

    def go_to_parent_safe(self):
        """Navigate to parent directory safely, handling root directory case"""
        # Get parent directory
        parent = os.path.dirname(self.current_dir)

        # Check if we're already at root (parent is same as current or empty)
        if parent == self.current_dir or not parent:
            # We're at root, do nothing (no error)
            return

        # Check if parent exists
        if os.path.exists(parent):
            self.navigate_to(parent)

    def setup_favorites_panel(self):
        """Set up the favorites panel with proper styling"""
        # Create layout for favorites panel
        favorites_layout = QVBoxLayout(self.bottom_panel)
        favorites_layout.setContentsMargins(5, 5, 5, 5)

        # Title label
        title_label = QLabel("Favorites")
        title_label.setStyleSheet("font-weight: bold; padding: 2px;")
        favorites_layout.addWidget(title_label)

        # Favorites list widget
        self.favorites_list = FavoritesListWidget()
        self.favorites_list.set_file_dialog(self)
        self.favorites_list.itemDoubleClicked.connect(self.navigate_to_favorite)

        # Connect right-click context menu
        self.favorites_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self.show_favorites_context_menu)
    
        # Connect keyboard events
        self.favorites_list.keyPressEvent = self.favorites_key_press_event

        favorites_layout.addWidget(self.favorites_list)

        # Help text label (shown when no favorites)
        self.help_label = QLabel("Add folders to favorites by clicking the ♡ Favorite button above or pressing Crtl+Alt+f.\n\nThe separator above can be dragged to resize or collapse this panel.\n\nRename: Ctrl+click or Ctrl+Return\nRemove: Right-click → Remove")
        self.help_label.setWordWrap(True)
        self.help_label.setAlignment(Qt.AlignTop)
        favorites_layout.addWidget(self.help_label)

        # Apply dark mode styling to match tree view
        self.apply_favorites_styling()

        # Populate favorites list
        self.refresh_favorites_list()

    def apply_favorites_styling(self):
        """Apply styling to match the tree view"""
        # Get the current dark mode setting
        dark_mode = True
        if self.config and "appearance" in self.config:
            dark_mode = self.config["appearance"].get("dark_mode", True)

        if dark_mode:
            style = """
                QWidget {
                    background-color: #2D2D30;
                    color: #E1E1E1;
                }
                QLabel {
                    color: #E1E1E1;
                    font-size: 11pt;
                }
                QListWidget {
                    background-color: #1E1E1E;
                    color: #E1E1E1;
                    border: 1px solid #3E3E42;
                    font-size: 11pt;
                }
                QListWidget::item {
                    padding: 3px;
                    border-bottom: 1px solid #3E3E42;
                }
                QListWidget::item:hover {
                    background-color: #3E3E42;
                }
                QListWidget::item:selected {
                    background-color: #007ACC;
                }
            """
        else:
            style = """
                QWidget {
                    background-color: #F0F0F0;
                    color: #333333;
                }
                QLabel {
                    color: #333333;
                    font-size: 11pt;
                }
                QListWidget {
                    background-color: #FFFFFF;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    font-size: 11pt;
                }
                QListWidget::item {
                    padding: 3px;
                    border-bottom: 1px solid #CCCCCC;
                }
                QListWidget::item:hover {
                    background-color: #E1E1E1;
                }
                QListWidget::item:selected {
                    background-color: #0078D4;
                    color: white;
                }
            """

        self.bottom_panel.setStyleSheet(style)

    def load_favorites(self):
        """Load favorites list from config"""
        if self.config and "file_settings" in self.config:
            favorites_data = self.config["file_settings"].get("favorites", [])
            # Handle both old format (list of strings) and new format (list of objects)
            if favorites_data and isinstance(favorites_data[0], str):
                # Convert old format to new format
                return [{"path": path, "nickname": None} for path in favorites_data]
            return favorites_data
        return []

    def save_favorites(self):
        """Save favorites list to config"""
        if self.config:
            # Ensure file_settings section exists
            if "file_settings" not in self.config:
                self.config["file_settings"] = {}

            # Update favorites
            self.config["file_settings"]["favorites"] = self.favorites

            # Save config if we have access to assistivox_dir
            if self.assistivox_dir:
                try:
                    import json
                    config_path = self.assistivox_dir / "config.json"
                    with open(config_path, 'w') as f:
                        json.dump(self.config, f, indent=2)
                except Exception as e:
                    print(f"Error saving favorites to config: {e}")

    def update_favorite_button(self):
        """Update the favorite button icon and text based on current directory"""
        current_path = os.path.normpath(self.current_dir)
        is_favorite = any(os.path.normpath(fav["path"]) == current_path for fav in self.favorites)

        if is_favorite:
            self.favorite_button.setText("♥ Favorite")
            self.favorite_button.setToolTip("Remove from favorites")
        else:
            self.favorite_button.setText("♡ Favorite")
            self.favorite_button.setToolTip("Add to favorites")

    def toggle_favorite(self):
        """Toggle the current directory in favorites"""
        current_path = os.path.normpath(self.current_dir)

        # Check if current path is in favorites
        is_favorite = False
        for i, fav in enumerate(self.favorites):
            if os.path.normpath(fav["path"]) == current_path:
                # Remove from favorites
                self.favorites.pop(i)
                is_favorite = True
                break

        if not is_favorite:
            # Add to favorites with last 2 path segments as default name
            path_parts = Path(current_path).parts
            if len(path_parts) >= 2:
                default_name = f"{path_parts[-2]}/{path_parts[-1]}"
            else:
                default_name = path_parts[-1] if path_parts else current_path

            self.favorites.append({
                "path": current_path,
                "nickname": None
            })

        # Save favorites and update UI
        self.save_favorites()
        self.update_favorite_button()
        self.refresh_favorites_list()

    def speak_current_item(self):
        """Speak the name of the currently focused item using TTS"""
        # Check if TTS is configured
        if not self.config or "tts_models" not in self.config or "selected" not in self.config["tts_models"]:
            return  # TTS not configured, silently return
    
        item_name = None
    
        # Check which widget has focus and get the current item name
        focused_widget = self.focusWidget() 
    
        if focused_widget == self.tree_view:
            # Get current item from tree view
            current_index = self.tree_view.currentIndex()
            if current_index.isValid():
                item_name = self.model.fileName(current_index)
    
        elif focused_widget == self.favorites_list:
            # Get current item from favorites list
            current_item = self.favorites_list.currentItem()
            if current_item:
                item_name = current_item.text()
    
        elif focused_widget == self.list_view:
            # Get current item from list view (expanded panel)
            current_index = self.list_view.currentIndex()
            if current_index.isValid():
                item_name = self.model.fileName(current_index)
    
        # If we have an item name, speak it
        if item_name:
            self._speak_text(item_name)

    def _speak_text(self, text):
        """Helper method to speak text using the current TTS configuration"""
        if not self.config or not self.assistivox_dir:
            return

        try:
            # Check if TTS is configured
            if "tts_models" not in self.config or "selected" not in self.config["tts_models"]:
                return  # TTS not configured, silently return

            # Create a temporary QTextEdit and TTSManager just like ReadOnlyTTSWidget does
            from PySide6.QtWidgets import QTextEdit
            from gui.tts.tts_manager import TTSManager

            # Create a temporary text edit widget
            temp_text_edit = QTextEdit()
            temp_text_edit.setPlainText(text)

            # Create a TTSManager with the temporary text edit (same as ReadOnlyTTSWidget)
            temp_tts_manager = TTSManager(temp_text_edit, self.config, self.assistivox_dir)
    
            # Use toggle_speech to speak the text (same as ReadOnlyTTSWidget)
            temp_tts_manager.toggle_speech()

            # Store reference so it doesn't get garbage collected during speech
            self._temp_tts_components = (temp_text_edit, temp_tts_manager)
    
        except Exception as e:
            # Silently handle TTS errors - don't interrupt user workflow
            print(f"TTS error: {e}")
            pass

    def refresh_favorites_list(self):
        """Refresh the favorites list widget"""
        self.favorites_list.clear()

        if not self.favorites:
            # Show help text when no favorites
            self.help_label.show()
            self.favorites_list.hide()
            return

        # Hide help text and show list when we have favorites
        self.help_label.hide()
        self.favorites_list.show()

        for fav_data in self.favorites:
            if os.path.exists(fav_data["path"]):
                # Use nickname if available, otherwise use last 2 path segments
                if fav_data["nickname"]:
                    display_name = fav_data["nickname"]
                else:
                    path_parts = Path(fav_data["path"]).parts
                    if len(path_parts) >= 2:
                        display_name = f"{path_parts[-2]}/{path_parts[-1]}"
                    else:
                        display_name = path_parts[-1] if path_parts else fav_data["path"]

                item = QListWidgetItem(display_name)
                item.setData(Qt.UserRole, fav_data["path"])  # Store full path
                item.setToolTip(fav_data["path"])

                # Store whether this item has a nickname for context menu
                item.setData(Qt.UserRole + 1, fav_data["nickname"] is not None)

                self.favorites_list.addItem(item)

    def navigate_to_favorite(self, item):
        """Navigate to a selected favorite directory"""
        # Check if we're in edit mode (has a widget)
        if self.favorites_list.itemWidget(item):
            return  # Don't navigate while editing

        favorite_path = item.data(Qt.UserRole)
        if favorite_path and os.path.exists(favorite_path):
            self.navigate_to(favorite_path)

    def show_favorites_context_menu(self, position):
        """Show context menu for favorites list"""
        item = self.favorites_list.itemAt(position)
        if not item:
            return

        menu = QMenu()
        rename_action = menu.addAction("Rename")
        remove_action = menu.addAction("Remove")

        action = menu.exec(self.favorites_list.mapToGlobal(position))

        if action == rename_action:
            self.start_rename_favorite(item)
        elif action == remove_action:
            self.remove_favorite(item)

    def favorites_key_press_event(self, event):
        """Handle key press events in favorites list"""
        # Handle Return key for navigation and renaming
        if event.key() == Qt.Key_Return:
            if event.modifiers() == Qt.ControlModifier:
                # Ctrl+Return for renaming
                current_item = self.favorites_list.currentItem()
                if current_item:
                    self.start_rename_favorite(current_item)
                return
            else:
                # Plain Return for navigation
                current_item = self.favorites_list.currentItem()
                if current_item:
                    self.navigate_to_favorite(current_item)
                return

        # Call original key press event for other keys
        QListWidget.keyPressEvent(self.favorites_list, event)

    def start_rename_favorite(self, item):
        """Start renaming a favorite item"""
        if not item:
            return
    
        # Set rename mode active
        self.rename_mode_active = True
    
        # Create line edit for renaming
        edit = QLineEdit()
        edit.setText(item.text())
        edit.selectAll()
    
        # Store original text and path
        original_text = item.text()
        favorite_path = item.data(Qt.UserRole)
    
        def finish_rename():
            self.rename_mode_active = False  # RENAME COMPLETION FIX
            new_name = edit.text().strip()
    
            # Remove the edit widget first
            self.favorites_list.removeItemWidget(item)
    
            # Find the favorite data
            for fav_data in self.favorites:
                if fav_data["path"] == favorite_path:
                    if new_name:
                        # Validate the name (basic check for invalid characters)
                        try:
                            # Simple validation - reject names with problematic characters
                            if any(char in new_name for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']):
                                # Invalid characters, don't change anything
                                break
                            fav_data["nickname"] = new_name
                        except:
                            # Any error, don't change anything
                            break
                    else:
                        # Empty name, revert to A/B format
                        fav_data["nickname"] = None
    
                    # Save and refresh
                    self.save_favorites()
                    self.refresh_favorites_list()
                    break
    
        def cancel_rename():
            self.rename_mode_active = False  # RENAME COMPLETION FIX
            # Remove the edit widget
            try:
                self.favorites_list.removeItemWidget(item)
            except:
                pass  # Widget might already be removed
    
        # Connect return key to finish
        edit.returnPressed.connect(finish_rename)
    
        # Handle escape key
        def key_press_event(event):
            if event.key() == Qt.Key_Escape:
                cancel_rename()
                return
            # Call original key press event for other keys
            QLineEdit.keyPressEvent(edit, event)
    
        edit.keyPressEvent = key_press_event
    
        # Handle focus loss (but don't auto-save on focus loss to avoid conflicts)
        def focus_out_event(event):
            cancel_rename()
            QLineEdit.focusOutEvent(edit, event)
    
        edit.focusOutEvent = focus_out_event
    
        # Set the edit widget for this item
        self.favorites_list.setItemWidget(item, edit)
        edit.setFocus()
    
    def remove_favorite(self, item):
        """Remove a favorite from the list"""
        favorite_path = item.data(Qt.UserRole)
    
        # Remove from favorites list
        self.favorites = [fav for fav in self.favorites if fav["path"] != favorite_path]
    
        # Save and refresh
        self.save_favorites()
        self.update_favorite_button()
        self.refresh_favorites_list()
    
    def load_divider_position(self):
        """Load divider position from config or return default"""
        if self.config and "file_settings" in self.config and "file_divider" in self.config["file_settings"]:
            divider_value = self.config["file_settings"]["file_divider"]
            # Validate range (15% to 85%)
            if isinstance(divider_value, (int, float)) and 15 <= divider_value <= 85:
                return divider_value
            else:
                # Invalid value, use default and update config
                self.save_divider_position(70)
                return 70

        # No config found or file_settings missing, use default
        self.save_divider_position(70)
        return 70

    def save_divider_position(self, percentage):
        """Save divider position to config"""
        if self.config:
            # Ensure file_settings section exists
            if "file_settings" not in self.config:
                self.config["file_settings"] = {}
            
            # Update divider position
            self.config["file_settings"]["file_divider"] = percentage
            
            # Save config if we have access to assistivox_dir
            if self.assistivox_dir:
                try:
                    import json
                    config_path = self.assistivox_dir / "config.json"
                    with open(config_path, 'w') as f:
                        json.dump(self.config, f, indent=2)
                except Exception as e:
                    print(f"Error saving divider position to config: {e}")

    def on_divider_moved(self, pos, index):
        """Handle splitter movement and save new position to config"""
        # Get current sizes
        sizes = self.left_splitter.sizes()
        if len(sizes) >= 2 and sum(sizes) > 0:
            # Calculate percentage for top panel
            total_height = sum(sizes)
            top_percentage = (sizes[0] / total_height) * 100

            # Clamp to valid range
            top_percentage = max(15, min(85, top_percentage))

            # Update our stored value
            self.divider_position = top_percentage

            # Save to config
            self.save_divider_position(top_percentage)

            # Debug print to see if this is being called
            print(f"Divider moved to: {top_percentage:.1f}%")

    def save_divider_position(self, percentage):
        """Save divider position to config"""
        # Check if we have access to config through parent
        if hasattr(self.parent(), 'config') and self.parent().config:
            config = self.parent().config
            
            # Ensure file_settings section exists
            if "file_settings" not in config:
                config["file_settings"] = {}
            
            # Update divider position
            config["file_settings"]["file_divider"] = percentage
            
            # Save config if we have access to assistivox_dir
            if hasattr(self.parent(), 'assistivox_dir') and self.parent().assistivox_dir:
                try:
                    import json
                    config_path = self.parent().assistivox_dir / "config.json"
                    with open(config_path, 'w') as f:
                        json.dump(config, f, indent=2)
                except Exception as e:
                    print(f"Error saving divider position to config: {e}")

    def resizeEvent(self, event):
        """Handle window resize to maintain divider proportion"""
        super().resizeEvent(event)
        # Reset divider position after resize to maintain percentage
        if hasattr(self, 'left_splitter') and hasattr(self, 'divider_position'):
            QTimer.singleShot(0, self.set_divider_position)

    def set_divider_position(self):
        """Set the splitter position based on the divider percentage"""
        # Get total height of the left splitter
        total_height = 400  # Default height, will be adjusted when shown
        
        # Calculate sizes based on percentage
        top_height = int(total_height * (self.divider_position / 100))
        bottom_height = total_height - top_height
        
        # Set splitter sizes
        self.left_splitter.setSizes([top_height, bottom_height])

    def tree_view_key_press_event(self, event):
        """Handle key press events in tree view"""
        # Handle Return key for navigation
        if event.key() == Qt.Key_Return:
            current_index = self.tree_view.currentIndex()
            if current_index.isValid():
                path = self.model.filePath(current_index)
                if os.path.isdir(path):
                    self.navigate_to(path)
                return
        
        # Call original key press event for other keys
        QTreeView.keyPressEvent(self.tree_view, event)

    def show_save_here_dialog(self):
        """Show dialog to get filename for saving in current directory"""
        from PySide6.QtWidgets import QInputDialog

        # Get appropriate extension based on format
        if self.file_format == "markdown":
            extension = ".md"
        elif self.file_format == "pdf":
            extension = ".pdf"
        else:
            extension = ".txt"

        # Check if there's an original PDF to suggest filename from
        suggested_name = f"document{extension}"
        if hasattr(self, 'original_pdf_name') and self.original_pdf_name:
            # Use PDF name but with appropriate extension
            pdf_name = Path(self.original_pdf_name).stem
            suggested_name = f"{pdf_name}{extension}"

        # Show input dialog
        filename, ok = QInputDialog.getText(
            self,
            "Save Document",
            f"Enter filename for {self.file_format} file:",
            text=suggested_name
        )

        if ok and filename.strip():
            # Ensure proper extension
            filename = filename.strip()
            if self.file_format == "markdown" and not filename.lower().endswith('.md'):
                filename += '.md'
            elif self.file_format == "pdf" and not filename.lower().endswith('.pdf'):
                filename += '.pdf'
            elif self.file_format == "text" and not filename.lower().endswith('.txt'):
                filename += '.txt'
    
            # Combine with current directory
            full_path = os.path.join(self.current_dir, filename)
            self.fileSelected.emit(full_path)
            self.accept()

    def save_here_action(self):
        """Handle the Save Here action (spacebar or button)"""
        if self.save_here_mode:
            self.show_save_here_dialog()

    def start_rename_favorite(self, item):
        """Start renaming a favorite item"""
        self.rename_mode_active = True
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.favorites_list.editItem(item)

    def keyPressEvent(self, event):
        """Handle key press events for the dialog"""
        # In save_here_mode, spacebar triggers save action
        if self.save_here_mode and event.key() == Qt.Key_Space and not self.rename_mode_active:
            self.save_here_action()
            event.accept()
            return

        # Handle rename mode - don't interfere with text input
        if self.rename_mode_active:
            super().keyPressEvent(event)
            return

        # Normal navigation behavior
        super().keyPressEvent(event)

