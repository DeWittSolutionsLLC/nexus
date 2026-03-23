"""Theme — JARVIS Holographic HUD color palette and typography for Nexus."""

COLORS = {
    # Deep space backgrounds
    "bg_primary":     "#050A18",
    "bg_secondary":   "#0A1228",
    "bg_tertiary":    "#0F1E3C",
    "bg_input":       "#0D1930",
    "bg_card":        "#081325",

    # JARVIS cyan accent
    "accent":         "#00D4FF",
    "accent_hover":   "#00AACC",
    "accent_dim":     "#005580",

    # Text hierarchy
    "text_primary":   "#E8F4FF",
    "text_secondary": "#7EC8E3",
    "text_muted":     "#3A6B85",
    "text_dim":       "#1A3A55",

    # Status indicators
    "success":        "#00FF88",
    "warning":        "#FFB800",
    "error":          "#FF3030",
    "info":           "#00D4FF",

    # Borders
    "border":         "#1A3A5C",
    "border_active":  "#00D4FF",

    # Chat bubbles
    "user_bubble":    "#003870",
    "bot_bubble":     "#080F22",

    # System stat bars
    "cpu_bar":        "#00D4FF",
    "ram_bar":        "#00FF88",
    "disk_bar":       "#FFB800",

    # Tag / badge colors
    "tag_blue":       "#003870",
    "tag_green":      "#003820",
    "tag_amber":      "#382800",
    "tag_red":        "#380808",
}

FONTS = {
    "heading":      ("Segoe UI", 18, "bold"),
    "subheading":   ("Segoe UI", 14, "bold"),
    "body":         ("Segoe UI", 13),
    "small":        ("Segoe UI", 11),
    "mono":         ("Cascadia Code", 12),
    "mono_small":   ("Cascadia Code", 10),
    "chat_input":   ("Segoe UI", 14),
    "hud":          ("Cascadia Code", 10),
    "title":        ("Segoe UI", 26, "bold"),
    "label":        ("Segoe UI", 10, "bold"),
    "jarvis":       ("Segoe UI", 22, "bold"),
    "table_header": ("Segoe UI", 10, "bold"),
    "table_body":   ("Segoe UI", 11),
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
}
