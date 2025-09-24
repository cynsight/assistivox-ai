# gui/components/markdown_handler.py
from PySide6.QtGui import QTextDocument

class MarkdownHandler:
    """
    Utility class for handling Markdown conversion for text editors
    
    This class provides methods to convert between Markdown and rich text
    without replacing the existing text editor.
    """
    
    def markdown_to_rich_text(document, markdown_text):
        """
        Convert Markdown to rich text and load it into a QTextDocument
        
        Args:
            document: The QTextDocument to load content into
            markdown_text: The Markdown text to convert
        """
        from PySide6.QtGui import QTextCursor, QTextBlockFormat, QTextCharFormat, QFont
        from PySide6.QtCore import Qt
        
        # First convert normally
        document.setMarkdown(
            markdown_text,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
        )
        
        # Find and style PAGE BREAK lines
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        
        block = document.begin()
        while block.isValid():
            text = block.text()
            if text.startswith('PAGE BREAK '):
                # Move cursor to this block
                cursor.setPosition(block.position())
                
                # Set block format for centering and borders
                block_format = QTextBlockFormat()
                block_format.setAlignment(Qt.AlignCenter)
                block_format.setTopMargin(5)
                block_format.setBottomMargin(20)
                cursor.setBlockFormat(block_format)
                
                # Select all text in the block and make it bold
                cursor.select(QTextCursor.BlockUnderCursor)
                char_format = QTextCharFormat()
                char_format.setFontWeight(QFont.Bold)
                cursor.setCharFormat(char_format)
            
            block = block.next()
        
        cursor.endEditBlock()

    @staticmethod
    def rich_text_to_markdown(document):
        """
        Convert the content of a QTextDocument to Markdown
        
        Args:
            document: The QTextDocument to convert
            
        Returns:
            str: The Markdown representation of the document
        """
        return document.toMarkdown(
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
        )
    
    @staticmethod
    def is_markdown_file(filepath):
        """
        Check if a file is a Markdown file based on extension
        
        Args:
            filepath: Path to the file to check
            
        Returns:
            bool: True if it's a Markdown file, False otherwise
        """
        if not filepath:
            return False
            
        markdown_extensions = ['.md', '.markdown', '.mdown', '.mdwn']
        return any(filepath.lower().endswith(ext) for ext in markdown_extensions)
