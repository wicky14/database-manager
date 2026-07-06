from pathlib import Path
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

RESOURCE_DIR = Path(__file__).parent / "resources"

_SEMANTIC_COLORS = {
    "run": "#22c55e",
    "stop": "#ef4444",
    "delete": "#ef4444",
}

_BRAND_COLORS = {
    "postgresql": "#336791",
    "mysql": "#00758F",
    "sqlite": "#003B57",
    "sqlserver": "#CC2927",
    "icon": "#4a9eff",
}


class IconManager:
    _cache: dict[str, QIcon] = {}
    _theme_color = "#cdd6f4"

    @classmethod
    def set_theme_color(cls, color: str):
        if color != cls._theme_color:
            cls._theme_color = color
            cls._cache.clear()

    @classmethod
    def get_icon(cls, name: str) -> QIcon:
        if name in cls._cache:
            return cls._cache[name]

        if name in _SEMANTIC_COLORS:
            color = _SEMANTIC_COLORS[name]
        elif name in _BRAND_COLORS:
            color = _BRAND_COLORS[name]
        else:
            color = cls._theme_color

        cls._cache[name] = cls._render_icon(name, color)
        return cls._cache[name]

    @classmethod
    def _render_icon(cls, name: str, color: str) -> QIcon:
        path = RESOURCE_DIR / f"{name}.svg"
        if not path.exists():
            return QIcon()

        svg = path.read_text().replace("currentColor", color)
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))

        default_size = renderer.defaultSize()
        if default_size.isValid() and not default_size.isNull():
            w, h = default_size.width(), default_size.height()
        else:
            w, h = 24, 24

        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)
