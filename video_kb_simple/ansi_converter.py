"""ANSI escape sequence to Rich markup converter."""

import re


class ANSIConverter:
    """Converts ANSI escape sequences to Rich markup for proper color rendering."""

    def __init__(self) -> None:
        # ANSI color code mappings to Rich colors
        self.color_map: dict[str, str] = {
            "30": "black",
            "31": "red",
            "32": "green",
            "33": "yellow",
            "34": "blue",
            "35": "magenta",
            "36": "cyan",
            "37": "white",
            "90": "bright_black",
            "91": "bright_red",
            "92": "bright_green",
            "93": "bright_yellow",
            "94": "bright_blue",
            "95": "bright_magenta",
            "96": "bright_cyan",
            "97": "bright_white",
        }

        # Background color mappings
        self.bg_map: dict[str, str] = {
            "40": "black",
            "41": "red",
            "42": "green",
            "43": "yellow",
            "44": "blue",
            "45": "magenta",
            "46": "cyan",
            "47": "white",
            "100": "bright_black",
            "101": "bright_red",
            "102": "bright_green",
            "103": "bright_yellow",
            "104": "bright_blue",
            "105": "bright_magenta",
            "106": "bright_cyan",
            "107": "bright_white",
        }

        # Style mappings
        self.style_map: dict[str, str] = {"1": "bold", "4": "underline", "7": "reverse"}

    def convert(self, text: str) -> str:
        """Convert ANSI escape sequences to Rich markup and escape literal brackets.

        Args:
            text: Text containing ANSI escape sequences and literal brackets

        Returns:
            Text with ANSI codes converted to Rich markup and literal brackets escaped
        """
        from rich.markup import escape

        # First escape all square brackets in the text
        escaped_text = escape(text)

        # Process with state tracking for proper tag management
        return self._convert_with_state_tracking(escaped_text)

    def _replace_ansi(self, match: re.Match[str]) -> str:
        """Replace ANSI escape sequence with Rich markup."""
        codes = match.group(1).split(";")
        result = []

        # Check if we have multiple style/color codes (edge case handling)
        has_multiple_styles = (
            len(
                [c for c in codes if c in self.style_map or c in self.color_map or c in self.bg_map]
            )
            > 1
        )

        i = 0
        while i < len(codes):
            code = codes[i]

            if code == "0":  # Reset
                result.append("[/]")
            elif code == "1":  # Bold
                result.append("[bold]")
            elif code == "4":  # Underline
                result.append("[underline]")
            elif code in self.color_map:  # Foreground color
                result.append(f"[{self.color_map[code]}]")
            elif code in self.bg_map:  # Background color
                result.append(f"[{self.bg_map[code]}]")
            elif code.startswith("38") and len(codes) > i + 2:  # 256-color foreground
                if codes[i + 1] == "5":  # 256-color palette
                    color_num = codes[i + 2]
                    if color_num.isdigit() and 0 <= int(color_num) <= 255:
                        result.append(f"[color({color_num})]")
                    i += 2  # Skip the next two codes
            elif (
                code.startswith("48") and len(codes) > i + 2 and codes[i + 1] == "5"
            ):  # 256-color background
                color_num = codes[i + 2]
                if color_num.isdigit() and 0 <= int(color_num) <= 255:
                    result.append(f"[on color({color_num})]")
                i += 2  # Skip the next two codes

            i += 1

        # For combined styles, add extra reset to handle edge case
        if has_multiple_styles and result and not result[-1].startswith("[/"):
            result.append("[/]")

        return "".join(result)

    def _convert_ansi_codes_with_state(
        self, codes_str: str, current_fg: list, current_bg: list, current_styles: set[str]
    ) -> str:
        """Convert ANSI code string to Rich markup with state management.

        Args:
            codes_str: ANSI codes separated by semicolons (e.g., "0;32;1")
            current_fg: Current foreground color state (mutable list for updates)
            current_bg: Current background color state (mutable list for updates)
            current_styles: Current styles set (mutable for updates)

        Returns:
            Rich markup string
        """
        codes = codes_str.split(";")
        markup_parts: list[str] = []

        i = 0
        while i < len(codes):
            code = codes[i]

            if code == "0":  # Reset - close all current styles
                if current_fg[0]:
                    markup_parts.append("[/]")
                    current_fg[0] = None
                if current_bg[0]:
                    markup_parts.append("[/]")
                    current_bg[0] = None
                for style in list(current_styles):
                    markup_parts.append("[/]")
                    current_styles.remove(style)
            elif code in self.style_map:  # Text styles
                style_name = self.style_map[code]
                if style_name not in current_styles:
                    markup_parts.append(f"[{style_name}]")
                    current_styles.add(style_name)
            elif code in self.color_map:  # Foreground colors
                color_name = self.color_map[code]
                if current_fg[0]:  # Close previous foreground color
                    markup_parts.append("[/]")
                markup_parts.append(f"[{color_name}]")
                current_fg[0] = color_name
            elif code in self.bg_map:  # Background colors
                color_name = self.bg_map[code]
                if current_bg[0]:  # Close previous background color
                    markup_parts.append("[/]")
                markup_parts.append(f"[{color_name}]")
                current_bg[0] = color_name
            elif code == "38" and i + 2 < len(codes) and codes[i + 1] == "5":  # 256-color fg
                color_num = codes[i + 2]
                if color_num.isdigit() and 0 <= int(color_num) <= 255:
                    if current_fg[0]:
                        markup_parts.append("[/]")
                    markup_parts.append(f"[color({color_num})]")
                    current_fg[0] = f"color({color_num})"
                i += 2  # Skip the next two codes
            elif code == "48" and i + 2 < len(codes) and codes[i + 1] == "5":  # 256-color bg
                color_num = codes[i + 2]
                if color_num.isdigit() and 0 <= int(color_num) <= 255:
                    if current_bg[0]:
                        markup_parts.append("[/]")
                    markup_parts.append(f"[on color({color_num})]")
                    current_bg[0] = f"on color({color_num})"
                i += 2  # Skip the next two codes

            i += 1

        return "".join(markup_parts)

    def _convert_with_state_tracking(self, text: str) -> str:
        """Convert ANSI sequences with proper state tracking for consecutive colors.

        Args:
            text: Text with escaped brackets containing ANSI sequences

        Returns:
            Text with ANSI codes converted to Rich markup with proper state management
        """
        # Pattern to match ANSI escape sequences
        ansi_pattern = re.compile(r"\033\[([0-9;]*)m")

        # Track current state using mutable objects
        current_fg: list[str | None] = [None]  # Use list to make it mutable
        current_bg: list[str | None] = [None]  # Use list to make it mutable
        current_styles: set[str] = set()

        # Process text with state tracking
        result_parts: list[str] = []
        last_end = 0

        for match in ansi_pattern.finditer(text):
            # Add text before ANSI sequence
            before_text = text[last_end : match.start()]
            if before_text:
                result_parts.append(before_text)

            # Convert ANSI sequence with state management
            ansi_codes = match.group(1)
            if ansi_codes:  # Skip empty sequences
                markup = self._convert_ansi_codes_with_state(
                    ansi_codes, current_fg, current_bg, current_styles
                )
                if markup:
                    result_parts.append(markup)

            last_end = match.end()

        # Add remaining text
        remaining = text[last_end:]
        if remaining:
            result_parts.append(remaining)

        # Close any remaining open tags
        closing_tags = []
        if current_fg[0]:
            closing_tags.append("[/]")
        if current_bg[0]:
            closing_tags.append("[/]")
        for _ in current_styles:
            closing_tags.append("[/]")

        result_parts.extend(closing_tags)

        return "".join(result_parts)

    def _convert_ansi_codes(self, codes_str: str) -> str:
        """Convert ANSI code string to Rich markup (without state management).

        Args:
            codes_str: ANSI codes separated by semicolons (e.g., "0;32;1")

        Returns:
            Rich markup string
        """
        # Create dummy state variables for compatibility
        current_fg = [None]
        current_bg = [None]
        current_styles: set[str] = set()

        return self._convert_ansi_codes_with_state(
            codes_str, current_fg, current_bg, current_styles
        )


# Convenience function for easy usage
def ansi_to_rich(text: str) -> str:
    """Convert ANSI escape sequences to Rich markup.

    Args:
        text: Text containing ANSI escape sequences

    Returns:
        Text with ANSI codes converted to Rich markup
    """
    converter = ANSIConverter()
    return converter.convert(text)
