"""
Gradio UI for PDF to Markdown Converter
Simple web interface for converting PDF files to Markdown
"""

import gradio as gr
from pdf_to_markdown import PDFToMarkdownConverter
from pathlib import Path
import shutil
import tempfile


def convert_pdf_with_ui(pdf_file, output_filename, include_toc, detect_tables, font_tolerance):
    """
    Convert PDF to Markdown using Gradio interface

    Args:
        pdf_file: Uploaded PDF file from Gradio
        output_filename: Desired output filename (without .md extension)
        include_toc: Boolean to include Table of Contents
        detect_tables: Boolean to detect and convert tables
        font_tolerance: Font size tolerance for normalization (0.5-2.0)

    Returns:
        Tuple of (status_message, markdown_file_path, images_zip_path)
    """
    try:
        if pdf_file is None:
            return "❌ Please upload a PDF file first!", None, None

        # Create temp directory for processing
        temp_dir = Path(tempfile.mkdtemp())

        # Save uploaded PDF to temp location
        pdf_path = temp_dir / "input.pdf"
        shutil.copy(pdf_file.name, pdf_path)

        # Set output filename
        if not output_filename or output_filename.strip() == "":
            output_filename = Path(pdf_file.name).stem

        # Remove .md extension if user added it
        output_filename = output_filename.replace('.md', '')

        output_path = temp_dir / f"{output_filename}.md"

        # Convert PDF to Markdown with custom tolerance
        converter = PDFToMarkdownConverter(str(pdf_path), font_size_tolerance=font_tolerance)
        converter.save_markdown(str(output_path), include_toc=include_toc, detect_tables=detect_tables)

        # Prepare status message
        status = f"✅ **Conversion Successful!**\n\n"
        status += f"📄 **Markdown file:** `{output_filename}.md`\n"

        # Font normalization stats
        unique_fonts = len(converter.normalized_font_map)
        normalized_fonts = len(set(converter.normalized_font_map.values()))
        if unique_fonts > normalized_fonts:
            status += f"🔧 **Font sizes normalized:** {unique_fonts} → {normalized_fonts} (tolerance: {font_tolerance}pt)\n"

        # Check if images were extracted
        images_zip = None
        if converter.images_dir and converter.images_dir.exists():
            num_images = len(list(converter.images_dir.glob("*")))
            status += f"🖼️  **Images extracted:** {num_images} images\n"

            # Create zip of images
            images_zip_path = temp_dir / f"{output_filename}_images"
            shutil.make_archive(str(images_zip_path), 'zip', converter.images_dir)
            images_zip = str(images_zip_path) + '.zip'

        if converter.headings:
            status += f"📑 **Headings detected:** {len(converter.headings)}\n"

        if include_toc:
            status += "📋 **Table of Contents:** Included\n"

        if detect_tables:
            status += "📊 **Table detection:** Enabled\n"

        return status, str(output_path), images_zip

    except Exception as e:
        error_msg = f"❌ **Error during conversion:**\n\n```\n{str(e)}\n```"
        return error_msg, None, None


def create_gradio_interface():
    """Create and configure Gradio interface"""

    with gr.Blocks(title="PDF to Markdown Converter", theme=gr.themes.Soft()) as app:
        gr.Markdown(
            """
            # 📄 PDF to Markdown Converter by osmanuygar

            Convert your PDF files to GitHub-friendly Markdown format with automatic:
            ---
            """
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ Settings")

                pdf_input = gr.File(
                    label="📤 Upload PDF File",
                    file_types=[".pdf"],
                    type="filepath"
                )

                output_name = gr.Textbox(
                    label="📝 Output Filename (without .md)",
                    placeholder="readme or leave empty for auto-naming",
                    value=""
                )

                include_toc = gr.Checkbox(
                    label="📋 Include Table of Contents",
                    value=True,
                    info="Automatically generate TOC from detected headings"
                )

                detect_tables = gr.Checkbox(
                    label="📊 Detect Tables",
                    value=True,
                    info="Convert aligned text blocks to Markdown tables"
                )

                font_tolerance = gr.Slider(
                    minimum=0.5,
                    maximum=2.0,
                    value=0.5,
                    step=0.1,
                    label="🔧 Font Size Tolerance",
                    info="Higher = more aggressive normalization (groups similar fonts)"
                )

                convert_btn = gr.Button(
                    "🚀 Convert to Markdown",
                    variant="primary",
                    size="lg"
                )

            with gr.Column(scale=1):
                gr.Markdown("### 📊 Results")

                status_output = gr.Markdown(
                    label="Status",
                    value="*Upload a PDF and click Convert to start...*"
                )

                markdown_output = gr.File(
                    label="📄 Download Markdown File",
                    interactive=False
                )

                images_output = gr.File(
                    label="🖼️ Download Images (ZIP)",
                    interactive=False
                )

        gr.Markdown(
            """
            ---
            ### 💡 Tips:
            - **Heading Detection**: Larger fonts → Higher level headings (# ## ###)
            - **Font Normalization**: Groups 24.0pt, 24.2pt, 24.5pt → 24pt (reduces noise)
            - **Bold/Italic**: Automatically preserves **bold** and *italic* formatting
            - **Code Blocks**: Monospace fonts & code patterns are auto-detected
            - **Tables**: Aligned text columns are converted to Markdown tables
            - **Images**: Extracted images are saved in a separate folder
            - **TOC**: Links automatically work on GitHub/GitLab

            ### 🎚️ Font Tolerance Guide:
            - **0.5pt** (Default): Strict - only groups very similar sizes (24.0 ≈ 24.5)
            - **1.0pt**: Moderate - groups nearby sizes (24.0 ≈ 24.9)
            - **2.0pt**: Aggressive - groups wider ranges (24.0 ≈ 25.9)

            ### 🔧 Requirements:
            ```bash
            pip install PyMuPDF gradio
            ```
            """
        )

        # Connect the conversion function
        convert_btn.click(
            fn=convert_pdf_with_ui,
            inputs=[pdf_input, output_name, include_toc, detect_tables, font_tolerance],
            outputs=[status_output, markdown_output, images_output]
        )


    return app


if __name__ == "__main__":
    app = create_gradio_interface()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )