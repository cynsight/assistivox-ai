# gui/components/pdf_converter.py
import docker
import os
import shutil
from pathlib import Path

class PDFConverter:
    """
    Simple class for converting markdown documents to PDF using Docker
    """
    
    def __init__(self):
        """Initialize the PDF converter"""
        try:
            self.docker_client = docker.from_env()
            self.docker_image = 'jmaupetit/md2pdf'
        except Exception as e:
            print(f"Docker initialization error: {e}")
            self.docker_client = None
        
    def is_docker_available(self):
        """Check if Docker is available and running"""
        if not self.docker_client:
            return False
        try:
            self.docker_client.ping()
            return True
        except Exception:
            return False
    
    def convert_markdown_to_pdf(self, markdown_content, output_pdf_path):
        """
        Convert markdown content to PDF file using cache directory
        
        Args:
            markdown_content (str): The markdown content to convert
            output_pdf_path (str): Path where the PDF should be saved
            
        Returns:
            bool: True if conversion successful, False otherwise
        """
        try:
            if not self.docker_client:
                raise Exception("Docker client not available")
            
            # Pull image if needed
            try:
                self.docker_client.images.pull(self.docker_image)
            except Exception as e:
                print(f"Warning: Could not pull Docker image: {e}")
            
            # Create cache directory
            cache_dir = Path.home() / ".assistivox" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Write markdown to cache
            temp_md_file = cache_dir / "temp_document.md"
            with open(temp_md_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            print(f"Wrote markdown to: {temp_md_file}")
            
            # Run Docker with cache directory mounted
            print("Running Docker conversion...")
            result = self.docker_client.containers.run(
                image=self.docker_image,
                command=['temp_document.md', 'temp_document.pdf'],
                volumes={str(cache_dir): {'bind': '/app', 'mode': 'rw'}},
                working_dir='/app',
                remove=True,
                stdout=True,
                stderr=True
            )
            
            print(f"Docker output: {result.decode('utf-8') if result else 'No output'}")
            
            # Check if PDF was created
            temp_pdf_file = cache_dir / "temp_document.pdf"
            if temp_pdf_file.exists():
                # Copy to final destination
                output_path = Path(output_pdf_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(temp_pdf_file, output_path)
                
                print(f"PDF successfully created: {output_pdf_path}")
                
                # Clean up temp files
                temp_md_file.unlink(missing_ok=True)
                temp_pdf_file.unlink(missing_ok=True)
                
                return True
            else:
                print("PDF file was not created by Docker")
                return False
                
        except Exception as e:
            print(f"Error converting markdown to PDF: {e}")
            return False
