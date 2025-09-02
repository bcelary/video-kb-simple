"""Tests for the ANSI converter module."""

import pytest

from video_kb_simple.ansi_converter import ANSIConverter, ansi_to_rich


class TestANSIConverter:
    """Test the ANSIConverter class."""

    @pytest.fixture
    def converter(self):
        """Create a fresh ANSIConverter instance for each test."""
        return ANSIConverter()

    def test_basic_colors(self, converter):
        """Test basic ANSI foreground color conversion."""
        # Red
        assert converter.convert("\033[31mHello\033[0m") == "[red]Hello[/]"
        # Green
        assert converter.convert("\033[32mWorld\033[0m") == "[green]World[/]"
        # Blue
        assert converter.convert("\033[34mTest\033[0m") == "[blue]Test[/]"

    def test_bright_colors(self, converter):
        """Test ANSI bright color conversion."""
        # Bright red
        assert converter.convert("\033[91mError\033[0m") == "[bright_red]Error[/]"
        # Bright green
        assert converter.convert("\033[92mSuccess\033[0m") == "[bright_green]Success[/]"
        # Bright blue
        assert converter.convert("\033[94mInfo\033[0m") == "[bright_blue]Info[/]"

    def test_background_colors(self, converter):
        """Test ANSI background color conversion."""
        # Red background
        assert converter.convert("\033[41mText\033[0m") == "[red]Text[/]"
        # Green background
        assert converter.convert("\033[42mText\033[0m") == "[green]Text[/]"

    def test_text_styles(self, converter):
        """Test ANSI text style conversion."""
        # Bold
        assert converter.convert("\033[1mBold\033[0m") == "[bold]Bold[/]"
        # Underline
        assert converter.convert("\033[4mUnderlined\033[0m") == "[underline]Underlined[/]"

    def test_combined_styles(self, converter):
        """Test combined ANSI styles."""
        # Bold red
        result = converter.convert("\033[1;31mBold Red\033[0m")
        assert "[bold]" in result
        assert "[red]" in result
        assert result.count("[/]") == 2  # Should close both bold and color

    def test_multiple_sequences(self, converter):
        """Test multiple ANSI sequences in one string."""
        text = "Normal \033[32mgreen\033[0m and \033[31mred\033[0m text"
        result = converter.convert(text)
        assert "[green]green[/]" in result
        assert "[red]red[/]" in result
        assert "Normal " in result
        assert " and " in result
        assert " text" in result

    def test_reset_sequence(self, converter):
        """Test ANSI reset sequence handling."""
        # Reset in middle of text
        assert converter.convert("\033[32mGreen\033[0mNormal") == "[green]Green[/]Normal"

    def test_no_ansi_sequences(self, converter):
        """Test text without ANSI sequences."""
        text = "Plain text without colors"
        assert converter.convert(text) == text

    def test_empty_string(self, converter):
        """Test empty string handling."""
        assert converter.convert("") == ""

    def test_partial_sequences(self, converter):
        """Test handling of incomplete ANSI sequences."""
        # Missing escape character
        text = "[32mNot ANSI[0m"
        assert converter.convert(text) == text  # Should remain unchanged

    def test_256_color_codes(self, converter):
        """Test 256-color ANSI codes."""
        # 256-color foreground
        result = converter.convert("\033[38;5;196mColor\033[0m")
        assert "[color(196)]Color[/]" in result

        # 256-color background
        result = converter.convert("\033[48;5;21mColor\033[0m")
        assert "[on color(21)]Color[/]" in result

    def test_complex_ansi_string(self, converter):
        """Test complex ANSI string similar to yt-dlp output."""
        complex_text = "Downloading item \033[0;32m69\033[0m of \033[0;94m180\033[0m"
        result = converter.convert(complex_text)

        # Should contain the converted colors
        assert "[green]69[/]" in result
        assert "[bright_blue]180[/]" in result
        assert "Downloading item " in result
        assert " of " in result

    def test_consecutive_colors(self, converter):
        """Test consecutive color changes without reset."""
        text = "\033[31mRed\033[32mGreen\033[34mBlue\033[0m"
        result = converter.convert(text)

        # Should properly close and open tags
        assert "[red]Red[/]" in result
        assert "[green]Green[/]" in result
        assert "[blue]Blue[/]" in result


class TestANSIToRichFunction:
    """Test the ansi_to_rich convenience function."""

    def test_basic_conversion(self):
        """Test basic conversion with convenience function."""
        text = "\033[32mGreen Text\033[0m"
        result = ansi_to_rich(text)
        assert result == "[green]Green Text[/]"

    def test_multiple_colors(self):
        """Test multiple colors with convenience function."""
        text = "\033[31mRed\033[0m and \033[34mBlue\033[0m"
        result = ansi_to_rich(text)
        assert "[red]Red[/]" in result
        assert "[blue]Blue[/]" in result

    def test_empty_input(self):
        """Test empty input with convenience function."""
        assert ansi_to_rich("") == ""

    def test_no_ansi_input(self):
        """Test input without ANSI codes."""
        text = "Plain text"
        assert ansi_to_rich(text) == text


class TestANSIRichIntegration:
    """Test ANSI converter integration with Rich console."""

    def test_rich_rendering(self):
        """Test that converted ANSI renders correctly with Rich."""
        from io import StringIO

        from rich.console import Console

        output_buffer = StringIO()
        console = Console(file=output_buffer, width=80)

        # Convert ANSI text
        ansi_text = "Status: \033[32mOK\033[0m"
        rich_text = ansi_to_rich(ansi_text)

        # Render with Rich
        console.print(f"[bold]System:[/bold] {rich_text}")

        # Check that it doesn't raise errors (basic integration test)
        output = output_buffer.getvalue()
        assert len(output) > 0

    def test_embedded_markup(self):
        """Test that converted ANSI can be embedded in other Rich markup."""
        from io import StringIO

        from rich.console import Console

        output_buffer = StringIO()
        console = Console(file=output_buffer, width=80)

        # Convert ANSI text
        ansi_text = "\033[32mSuccess\033[0m"
        rich_text = ansi_to_rich(ansi_text)

        # Embed in other markup
        console.print(f"[bold cyan]Result:[/bold cyan] {rich_text} [dim]- Complete[/dim]")

        # Should not raise markup errors
        output = output_buffer.getvalue()
        assert len(output) > 0
