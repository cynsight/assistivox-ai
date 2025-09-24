# gui/components/asvx_handler.py
import re
from pathlib import Path
from PySide6.QtGui import QTextDocument

class ASVXHandler:
    """
    Handler for ASVX (Assistivox Format) documents
    
    ASVX is the native document format that combines markdown content
    with semantic structure tags for accessibility and document management.
    """
    
    @staticmethod
    def is_asvx_file(filepath):
        """
        Check if a file is an ASVX file based on extension
        
        Args:
            filepath: Path to the file to check
            
        Returns:
            bool: True if it's an ASVX file, False otherwise
        """
        if not filepath:
            return False
        
        return filepath.lower().endswith('.asvx')
    
    @staticmethod
    def asvx_to_rich_text(document, asvx_content):
        """
        Convert ASVX content to rich text and load it into a QTextDocument
        
        Args:
            document: The QTextDocument to load content into
            asvx_content: The ASVX content to convert
            
        Returns:
            dict: Metadata extracted from ASVX tags (e.g., PDF path)
        """
        from gui.components.markdown_handler import MarkdownHandler
        from PySide6.QtGui import QTextCursor, QTextBlockFormat, QTextCharFormat, QFont
        from PySide6.QtCore import Qt
        
        # Parse ASVX content into chunks and metadata
        chunks, metadata = ASVXHandler._parse_asvx_content(asvx_content)
        
        # Clear the document
        document.clear()
        
        # Create cursor for building document
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        
        page_counter = 1  # For pages without num attribute
        previous_page_num = None
        first_page_encountered = False
        
        for chunk in chunks:
            chunk_type = chunk['type']
            chunk_content = chunk['content']
            
            if chunk_type == 'pdf_tag':
                # PDF tags don't get added to the document content
                # They're stored in metadata only
                continue
            elif chunk_type == 'page_tag':
                # Get page number from num attribute or use sequential counter
                if 'num' in chunk_content and chunk_content['num']:
                    try:
                        current_page_num = int(chunk_content['num'])
                    except (ValueError, TypeError):
                        current_page_num = page_counter
                        page_counter += 1
                else:
                    current_page_num = page_counter
                    page_counter += 1
                
                if not first_page_encountered:
                    # First page tag - just display "PAGE X" at the beginning
                    first_page_encountered = True
                    
                    # Create block format for first page
                    block_format = QTextBlockFormat()
                    block_format.setAlignment(Qt.AlignCenter)
                    block_format.setTopMargin(5)
                    block_format.setBottomMargin(20)
                    
                    # Create character format for first page
                    char_format = QTextCharFormat()
                    char_format.setFontWeight(QFont.Bold)
                    
                    # Insert formatted text
                    cursor.setBlockFormat(block_format)
                    cursor.setCharFormat(char_format)
                    cursor.insertText(f"PAGE {current_page_num}")
                    
                    # Add spacing after first page
                    cursor.insertText("\n")
                    
                else:
                    # Subsequent page tags - show page transition
                    
                    # Add spacing before page transition
                    cursor.insertText("\n")
                    
                    # Above the horizontal rule: previous page number
                    prev_block_format = QTextBlockFormat()
                    prev_block_format.setAlignment(Qt.AlignCenter)
                    prev_block_format.setTopMargin(20)
                    prev_block_format.setBottomMargin(5)
                    
                    prev_char_format = QTextCharFormat()
                    prev_char_format.setFontWeight(QFont.Bold)
                    
                    cursor.setBlockFormat(prev_block_format)
                    cursor.setCharFormat(prev_char_format)
                    cursor.insertText(f"PAGE {previous_page_num}")
                    
                    # Add horizontal rule
                    cursor.insertHtml('<hr/>')
                    cursor.insertText("\n")
                    
                    # Below the horizontal rule: current page number
                    curr_block_format = QTextBlockFormat()
                    curr_block_format.setAlignment(Qt.AlignCenter)
                    curr_block_format.setTopMargin(5)
                    curr_block_format.setBottomMargin(20)
                    
                    curr_char_format = QTextCharFormat()
                    curr_char_format.setFontWeight(QFont.Bold)
                    
                    cursor.setBlockFormat(curr_block_format)
                    cursor.setCharFormat(curr_char_format)
                    cursor.insertText(f"PAGE {current_page_num}")
                    
                    # Add spacing after current page
                    cursor.insertText("\n")
                
                previous_page_num = current_page_num
                
            elif chunk_type == 'markdown':
                # Add markdown content
                if chunk_content.strip():
                    # Reset to default formatting for content
                    default_block_format = QTextBlockFormat()
                    default_char_format = QTextCharFormat()
                    cursor.setBlockFormat(default_block_format)
                    cursor.setCharFormat(default_char_format)
        
                    # Use MarkdownHandler instead of insertHtml to preserve editor font
                    temp_doc = QTextDocument()
                    MarkdownHandler.markdown_to_rich_text(temp_doc, chunk_content)
                    
                    # Copy content without HTML styling that changes fonts
                    temp_cursor = QTextCursor(temp_doc)
                    temp_cursor.select(QTextCursor.Document)
                    cursor.insertFragment(temp_cursor.selection())

        cursor.endEditBlock()
        
        return metadata
    
    @staticmethod
    def rich_text_to_asvx(document, metadata=None):
        """
        Convert the content of a QTextDocument to ASVX format
        
        Args:
            document: The QTextDocument to convert
            metadata: Optional metadata dict (e.g., PDF path)
            
        Returns:
            str: The ASVX representation of the document
        """
        from gui.components.markdown_handler import MarkdownHandler
        
        # Get markdown from the document
        markdown_content = MarkdownHandler.rich_text_to_markdown(document)
        
        # Build ASVX content
        asvx_content = ""
        
        # Add PDF tag if metadata contains PDF path
        if metadata and 'pdf_path' in metadata and metadata['pdf_path']:
            asvx_content += "{asvx|pdf:" + metadata['pdf_path'] + "}\n\n"
        
        # Convert markdown with PAGE BREAK markers to ASVX format
        asvx_content += ASVXHandler._convert_markdown_to_asvx_pages(markdown_content)
        
        return asvx_content
    
    @staticmethod
    def _parse_asvx_content(asvx_content):
        """
        Parse ASVX content into chunks and extract metadata
        
        Args:
            asvx_content: Raw ASVX content string
            
        Returns:
            tuple: (chunks_list, metadata_dict)
        """
        chunks = []
        metadata = {}
        
        lines = asvx_content.split('\n')
        current_chunk = ""
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped_line = line.strip()
            
            # Check for ASVX tags
            if stripped_line.startswith('{asvx|') and stripped_line.endswith('}'):
                # Save any accumulated content as markdown chunk
                if current_chunk.strip():
                    chunks.append({
                        'type': 'markdown',
                        'content': current_chunk.rstrip('\n')  # Remove trailing newlines
                    })
                    current_chunk = ""
                
                # Parse the tag
                tag_content = stripped_line[6:-1]  # Remove {asvx| and }
                
                if tag_content.startswith('pdf:'):
                    # PDF tag: {asvx|pdf:/path/to/file.pdf}
                    pdf_path = tag_content[4:].strip()
                    metadata['pdf_path'] = pdf_path
                    chunks.append({
                        'type': 'pdf_tag',
                        'content': pdf_path
                    })
                elif tag_content.startswith('page'):
                    # Page tag: {asvx|page|num:24} or {asvx|page}
                    page_info = {}
                    if '|' in tag_content:
                        # Parse attributes like num:24
                        parts = tag_content.split('|')
                        for part in parts[1:]:  # Skip 'page' part
                            if ':' in part:
                                key, value = part.split(':', 1)
                                page_info[key.strip()] = value.strip()
                    
                    chunks.append({
                        'type': 'page_tag',
                        'content': page_info
                    })
            else:
                # Regular content line - add to current chunk
                current_chunk += line + '\n'
            
            i += 1
        
        # Add any remaining content as final markdown chunk
        if current_chunk.strip():
            chunks.append({
                'type': 'markdown',
                'content': current_chunk.rstrip('\n')  # Remove trailing newlines
            })
        
        return chunks, metadata
    
    @staticmethod
    def _convert_markdown_to_asvx_pages(markdown_content):
        """
        Convert markdown with PAGE BREAK markers back to ASVX page tags
        
        Args:
            markdown_content: Markdown content with PAGE BREAK markers
            
        Returns:
            str: ASVX content with proper page tags
        """
        if not markdown_content.strip():
            return ""
        
        lines = markdown_content.split('\n')
        asvx_lines = []
        page_number = 1
        first_page_added = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check for PAGE BREAK pattern: "PAGE BREAK X"
            page_break_match = re.match(r'^PAGE BREAK (\d+)$', line.strip())
            if page_break_match:
                # This is a page break line
                page_num = int(page_break_match.group(1))
                
                # Add page tag
                asvx_lines.append(f"{{asvx|page|num:{page_num}}}")
                asvx_lines.append("")  # Add blank line after page tag
                
                # Skip the horizontal rule line if it exists before the PAGE BREAK
                if i > 0 and lines[i-1].strip() == '---':
                    # Remove the last added horizontal rule line
                    if asvx_lines and asvx_lines[-3] == '---':
                        asvx_lines.pop(-3)
                
                # Skip any following empty lines
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
            
            # Check if we need to add the first page tag
            if not first_page_added and line.strip() and not line.strip().startswith('#'):
                # We have content and haven't added first page tag yet
                asvx_lines.insert(0, "{asvx|page|num:1}")
                asvx_lines.insert(1, "")
                first_page_added = True
            
            # Add regular line
            asvx_lines.append(line)
            i += 1
        
        # If we have content but no page tags were added, add the first page tag
        if not first_page_added and any(line.strip() for line in asvx_lines):
            asvx_lines.insert(0, "{asvx|page|num:1}")
            asvx_lines.insert(1, "")
        
        return '\n'.join(asvx_lines)
