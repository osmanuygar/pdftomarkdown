import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict


class PDFToMarkdownConverter:
    def __init__(self, pdf_path: str, font_size_tolerance: float = 0.5):
        """
        Initialize PDF to Markdown converter

        Args:
            pdf_path: Path to PDF file
            font_size_tolerance: Tolerance for font size normalization (default: 0.5pt)
        """
        self.pdf_path = Path(pdf_path)
        self.doc = fitz.open(str(self.pdf_path))
        self.images_dir = None
        self.headings = []
        self.font_sizes = defaultdict(int)
        self.font_size_tolerance = font_size_tolerance
        self.normalized_font_map = {}  # Maps actual sizes to normalized sizes

    def normalize_font_size(self, size: float) -> float:
        """
        Normalize font sizes to handle slight variations
        Groups similar sizes together (e.g., 24.0, 24.2, 24.5 → 24.0)
        """
        # Round to nearest 0.5 or use tolerance
        if self.font_size_tolerance >= 1.0:
            normalized = round(size)
        else:
            normalized = round(size / self.font_size_tolerance) * self.font_size_tolerance

        return round(normalized, 1)

    def is_bold(self, font_name: str, font_flags: int) -> bool:
        """Detect if text is bold based on font name and flags"""
        bold_keywords = ['bold', 'heavy', 'black', 'semibold', 'demibold']
        font_lower = font_name.lower()

        # Check font name
        has_bold_name = any(keyword in font_lower for keyword in bold_keywords)

        # Check font flags (bit 16 is bold flag in PDF)
        has_bold_flag = bool(font_flags & (1 << 16))

        return has_bold_name or has_bold_flag

    def is_italic(self, font_name: str, font_flags: int) -> bool:
        """Detect if text is italic based on font name and flags"""
        italic_keywords = ['italic', 'oblique', 'slant']
        font_lower = font_name.lower()

        # Check font name
        has_italic_name = any(keyword in font_lower for keyword in italic_keywords)

        # Check font flags (bit 6 is italic flag in PDF)
        has_italic_flag = bool(font_flags & (1 << 6))

        return has_italic_name or has_italic_flag

    def detect_table(self, blocks: List[Dict]) -> Optional[List[List[str]]]:
        """
        Detect if blocks form a table structure
        Returns table data if detected, None otherwise
        """
        # Group blocks by Y coordinate (rows)
        rows = defaultdict(list)

        for block in blocks:
            if "lines" not in block:
                continue

            bbox = block["bbox"]
            y_pos = round(bbox[1], 1)  # Top Y coordinate

            for line in block["lines"]:
                text = ""
                for span in line["spans"]:
                    text += span["text"] + " "
                text = text.strip()

                if text:
                    x_pos = round(line["bbox"][0], 1)  # Left X coordinate
                    rows[y_pos].append((x_pos, text))

        # Check if we have aligned columns (table-like structure)
        if len(rows) < 2:
            return None

        # Sort rows by Y position
        sorted_rows = sorted(rows.items())

        # Check for consistent column positions
        x_positions = defaultdict(int)
        for y_pos, cells in sorted_rows:
            for x_pos, text in cells:
                x_positions[x_pos] += 1

        # If we have at least 2 consistent columns appearing in multiple rows
        common_x_positions = [x for x, count in x_positions.items() if count >= 2]

        if len(common_x_positions) >= 2:
            # Build table
            table_data = []
            for y_pos, cells in sorted_rows:
                row = [""] * len(common_x_positions)
                cells_sorted = sorted(cells, key=lambda x: x[0])

                for x_pos, text in cells_sorted:
                    # Find closest column
                    closest_col = min(range(len(common_x_positions)),
                                      key=lambda i: abs(common_x_positions[i] - x_pos))
                    row[closest_col] = text

                table_data.append(row)

            return table_data if len(table_data) >= 2 else None

        return None

    def format_table_markdown(self, table_data: List[List[str]]) -> str:
        """Convert table data to Markdown table format"""
        if not table_data:
            return ""

        # Calculate column widths
        num_cols = max(len(row) for row in table_data)
        col_widths = [0] * num_cols

        for row in table_data:
            for i, cell in enumerate(row):
                if i < num_cols:
                    col_widths[i] = max(col_widths[i], len(cell))

        # Build markdown table
        lines = []

        # Header row (first row)
        if table_data:
            header = "| " + " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(table_data[0])) + " |"
            lines.append(header)

            # Separator
            separator = "|" + "|".join("-" * (w + 2) for w in col_widths) + "|"
            lines.append(separator)

            # Data rows
            for row in table_data[1:]:
                row_str = "| " + " | ".join(cell.ljust(col_widths[i]) if i < len(row) else " " * col_widths[i]
                                            for i in range(num_cols)) + " |"
                lines.append(row_str)

        return "\n".join(lines)

    def analyze_font_sizes(self):
        """Analyze font sizes in the document to determine heading levels"""
        raw_sizes = defaultdict(int)

        for page in self.doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            size = span["size"]
                            normalized = self.normalize_font_size(size)
                            raw_sizes[size] += 1
                            self.font_sizes[normalized] += 1
                            self.normalized_font_map[size] = normalized

        # Sort normalized font sizes to determine heading hierarchy
        sorted_sizes = sorted(self.font_sizes.keys(), reverse=True)

        # Map font sizes to markdown heading levels
        self.size_to_heading = {}
        heading_level = 1
        for size in sorted_sizes[:6]:  # Max 6 heading levels
            if self.font_sizes[size] > 2:  # Only if used more than twice
                self.size_to_heading[size] = heading_level
                heading_level += 1

    def is_code_block(self, font_name: str, text: str) -> bool:
        """Detect if text is likely code based on font and content"""
        code_fonts = ['courier', 'mono', 'consola', 'code']

        # Check if font is monospace
        is_monospace = any(cf in font_name.lower() for cf in code_fonts)

        # Check if text contains code-like patterns
        code_patterns = [
            r'^\s*(def|class|import|from|if|for|while|return)\s+',
            r'[\{\}\[\]\(\);]',
            r'^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*=',
            r'^\s*//|^\s*#|^\s*/\*',
        ]
        has_code_pattern = any(re.search(pattern, text) for pattern in code_patterns)

        return is_monospace or has_code_pattern

    def extract_images(self, page_num: int, page) -> List[str]:
        """Extract images from a page and save them"""
        if self.images_dir is None:
            self.images_dir = self.pdf_path.parent / f"{self.pdf_path.stem}_images"
            self.images_dir.mkdir(exist_ok=True)

        image_refs = []
        image_list = page.get_images()

        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = self.doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            # Save image
            image_filename = f"page_{page_num + 1}_img_{img_index + 1}.{image_ext}"
            image_path = self.images_dir / image_filename

            with open(image_path, "wb") as img_file:
                img_file.write(image_bytes)

            # Return relative path for markdown
            image_refs.append(f"{self.images_dir.name}/{image_filename}")

        return image_refs

    def generate_toc(self) -> str:
        """Generate Table of Contents from headings"""
        if not self.headings:
            return ""

        toc = "## Table of Contents\n\n"
        for level, text in self.headings:
            indent = "  " * (level - 1)
            # Create GitHub-friendly anchor
            anchor = text.lower()
            anchor = re.sub(r'[^\w\s-]', '', anchor)
            anchor = re.sub(r'[-\s]+', '-', anchor)
            toc += f"{indent}- [{text}](#{anchor})\n"

        return toc + "\n"

    def convert_to_markdown(self, include_toc: bool = True, detect_tables: bool = True) -> str:
        """Convert PDF to Markdown"""
        self.analyze_font_sizes()

        markdown_content = []
        in_code_block = False
        code_buffer = []

        for page_num, page in enumerate(self.doc):
            # Extract images first
            images = self.extract_images(page_num, page)

            # Get text with formatting
            blocks = page.get_text("dict")["blocks"]

            # Try to detect table first
            if detect_tables:
                table_data = self.detect_table(blocks)
                if table_data:
                    markdown_content.append("\n" + self.format_table_markdown(table_data) + "\n")
                    # Add images after table
                    for img_ref in images:
                        markdown_content.append(f"\n![Image]({img_ref})\n")
                    continue  # Skip normal processing for this page

            for block in blocks:
                if "lines" not in block:
                    continue

                for line in block["lines"]:
                    line_text = ""
                    current_font_size = None
                    current_font_name = ""
                    is_bold_text = False
                    is_italic_text = False

                    # Process each span in the line
                    formatted_spans = []

                    for span in line["spans"]:
                        text = span["text"].strip()
                        if not text:
                            continue

                        font_size = self.normalize_font_size(span["size"])
                        font_name = span["font"]
                        font_flags = span.get("flags", 0)

                        current_font_size = font_size
                        current_font_name = font_name

                        # Detect formatting
                        span_is_bold = self.is_bold(font_name, font_flags)
                        span_is_italic = self.is_italic(font_name, font_flags)

                        # Apply markdown formatting
                        formatted_text = text
                        if span_is_bold and span_is_italic:
                            formatted_text = f"***{text}***"
                        elif span_is_bold:
                            formatted_text = f"**{text}**"
                        elif span_is_italic:
                            formatted_text = f"*{text}*"

                        formatted_spans.append(formatted_text)

                        # Track overall line formatting
                        if span_is_bold:
                            is_bold_text = True
                        if span_is_italic:
                            is_italic_text = True

                    line_text = " ".join(formatted_spans)

                    if not line_text:
                        continue

                    # Check if this is a code block
                    if self.is_code_block(current_font_name, line_text):
                        if not in_code_block:
                            in_code_block = True
                            markdown_content.append("```")
                        # Remove markdown formatting from code
                        clean_code = line_text.replace("**", "").replace("*", "")
                        code_buffer.append(clean_code)
                    else:
                        # Close code block if we were in one
                        if in_code_block:
                            markdown_content.extend(code_buffer)
                            markdown_content.append("```\n")
                            code_buffer = []
                            in_code_block = False

                        # Check if this is a heading
                        if current_font_size in self.size_to_heading:
                            heading_level = self.size_to_heading[current_font_size]
                            heading_marker = "#" * heading_level
                            # Remove formatting from headings (already emphasized by #)
                            clean_heading = line_text.replace("**", "").replace("*", "")
                            markdown_line = f"{heading_marker} {clean_heading}"
                            self.headings.append((heading_level, clean_heading))
                        else:
                            # Check for list patterns
                            list_pattern = r'^(\s*)([-•*]|\d+\.)\s+'
                            if re.match(list_pattern, line_text):
                                markdown_line = line_text
                            else:
                                markdown_line = line_text

                        markdown_content.append(markdown_line)

            # Add images at the end of the page
            for img_ref in images:
                markdown_content.append(f"\n![Image]({img_ref})\n")

        # Close any remaining code block
        if in_code_block:
            markdown_content.extend(code_buffer)
            markdown_content.append("```\n")

        # Combine everything
        full_content = "\n\n".join(markdown_content)

        # Add TOC at the beginning if requested
        if include_toc and self.headings:
            toc = self.generate_toc()
            full_content = toc + full_content

        return full_content

    def save_markdown(self, output_path: str = None, include_toc: bool = True, detect_tables: bool = True):
        """Convert and save to markdown file"""
        if output_path is None:
            output_path = self.pdf_path.parent / f"{self.pdf_path.stem}.md"

        markdown_content = self.convert_to_markdown(include_toc=include_toc, detect_tables=detect_tables)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        return output_path


def convert_pdf_cli(pdf_path: str, output_path: str = None, include_toc: bool = True, detect_tables: bool = True):
    """CLI function to convert PDF to Markdown"""
    converter = PDFToMarkdownConverter(pdf_path)
    output_file = converter.save_markdown(output_path, include_toc, detect_tables)
    print(f"✅ Conversion complete!")
    print(f"📄 Markdown file: {output_file}")
    if converter.images_dir and converter.images_dir.exists():
        print(f"🖼️  Images saved to: {converter.images_dir}")
    return str(output_file)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_to_markdown.py <pdf_file> [output_file]")
        sys.exit(1)

    pdf_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    convert_pdf_cli(pdf_file, output_file)