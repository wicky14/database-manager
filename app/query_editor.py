import sqlparse
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit, QMenu, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QRect, QStringListModel, QSize
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QFont, QColor,
    QKeySequence, QShortcut, QTextCursor,
    QPainter, QTextFormat, QAction,
)
from PySide6.QtWidgets import QCompleter, QTextEdit
import re


SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES", "UPDATE", "SET",
    "DELETE", "CREATE", "ALTER", "DROP", "TABLE", "INDEX", "VIEW", "TRIGGER",
    "FUNCTION", "PROCEDURE", "IF", "EXISTS", "NOT", "NULL", "AND", "OR",
    "IN", "LIKE", "BETWEEN", "IS", "AS", "ON", "JOIN", "LEFT", "RIGHT",
    "INNER", "OUTER", "FULL", "CROSS", "ORDER", "BY", "GROUP", "HAVING",
    "LIMIT", "OFFSET", "UNION", "ALL", "DISTINCT", "CASE", "WHEN", "THEN",
    "ELSE", "END", "BEGIN", "COMMIT", "ROLLBACK", "RETURNS", "LANGUAGE",
    "IMMUTABLE", "STABLE", "VOLATILE", "CALLED", "CONTAINS", "MODIFIES",
    "SECURITY", "DEFINER", "INVOKER", "LEAKPROOF", "PARALLEL", "SAFE",
    "RESTRICTED", "UNSAFE", "COST", "ROWS", "SETOF", "RECORD", "TABLE",
    "COLUMN", "CONSTRAINT", "PRIMARY", "KEY", "FOREIGN", "REFERENCES",
    "CASCADE", "RESTRICT", "DEFAULT", "CHECK", "UNIQUE", "AUTO_INCREMENT",
    "SERIAL", "BIGSERIAL", "SMALLSERIAL", "CHARACTER", "VARYING", "TEXT",
    "INTEGER", "INT", "SMALLINT", "BIGINT", "REAL", "FLOAT", "DOUBLE",
    "PRECISION", "NUMERIC", "DECIMAL", "BOOLEAN", "DATE", "TIME", "TIMESTAMP",
    "WITH", "WITHOUT", "ZONE", "TYPE", "ENUM", "ARRAY", "JSON", "JSONB",
    "USING", "GRANT", "REVOKE", "EXPLAIN", "ANALYZE", "VACUUM", "TRUNCATE",
    "REINDEX", "CLUSTER", "COPY", "LISTEN", "NOTIFY", "PREPARE", "EXECUTE",
    "DEALLOCATE", "DECLARE", "CURSOR", "FETCH", "CLOSE", "MOVE", "OPEN",
    "RETURN", "RETURNS", "CALL", "DO", "PERFORM", "RAISE", "EXCEPTION",
    "WHILE", "LOOP", "FOR", "FOREACH", "REPEAT", "UNTIL", "EXIT", "CONTINUE",
}


_COMMENT_STATE = 1


class SqlHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, colors=None):
        super().__init__(parent)
        self._colors = colors or {}
        self._comment_fmt = QTextCharFormat()
        self._comment_fmt.setForeground(QColor(self._colors.get("comment", "#5c6370")))
        self._comment_fmt.setFontItalic(True)
        self._rules = []
        self._build_rules()

    def _build_rules(self):
        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor(self._colors.get("keyword", "#c678dd")))
        keyword_fmt.setFontWeight(QFont.Weight.Bold)

        func_fmt = QTextCharFormat()
        func_fmt.setForeground(QColor(self._colors.get("function", "#61afef")))

        string_fmt = QTextCharFormat()
        string_fmt.setForeground(QColor(self._colors.get("string", "#98c379")))

        number_fmt = QTextCharFormat()
        number_fmt.setForeground(QColor(self._colors.get("number", "#d19a66")))

        op_fmt = QTextCharFormat()
        op_fmt.setForeground(QColor(self._colors.get("operator", "#56b6c2")))

        self._rules = [
            (r"'[^']*'", string_fmt),
            (r'"[^"]*"', string_fmt),
            (r"\b\d+\.?\d*\b", number_fmt),
            (r"\b[A-Za-z_]\w*(?=\s*\()", func_fmt),
        ]

        kw_pattern = r"\b(" + "|".join(sorted(SQL_KEYWORDS, key=len, reverse=True)) + r")\b"
        self._rules.append((kw_pattern, keyword_fmt, True))

        self._rules.append((r"--[^\n]*", self._comment_fmt))
        self._rules.append((r"/\*.*?\*/", self._comment_fmt))

        self._op_pattern = r"[=<>!+\-*/%&|^~]+"
        self._op_fmt = op_fmt

        self._op_pattern = r"[=<>!+\-*/%&|^~]+"

    def highlightBlock(self, text):
        for rule in self._rules[:-2]:
            pattern, fmt = rule[0], rule[1]
            for match in re.finditer(pattern, text, re.IGNORECASE):
                self.setFormat(match.start(), match.end() - match.start(), fmt)

        for match in re.finditer(self._op_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self._op_fmt)

        for rule in self._rules[-2:]:
            pattern, fmt = rule[0], rule[1]
            for match in re.finditer(pattern, text, re.IGNORECASE):
                self.setFormat(match.start(), match.end() - match.start(), fmt)

        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() == _COMMENT_STATE:
            start = 0
        else:
            idx = text.find("/*")
            if idx < 0:
                return
            start = idx

        end = text.find("*/", start + 2)
        if end >= 0:
            self.setFormat(start, end + 2 - start, self._comment_fmt)
        else:
            self.setFormat(start, len(text) - start, self._comment_fmt)
            self.setCurrentBlockState(_COMMENT_STATE)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.get_line_number_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


class QueryEditor(QPlainTextEdit):
    query_requested = Signal(str)

    def __init__(self, colors=None, parent=None):
        super().__init__(parent)
        self._colors = colors or {}
        self._schema_cache = None
        self._completer = None
        self._setup_editor()
        self._setup_completer()
        self._setup_shortcuts()

    def _setup_editor(self):
        font = QFont("JetBrains Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setUndoRedoEnabled(True)

        self._highlighter = SqlHighlighter(self.document(), self._colors)

        self._line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_width()

    def _setup_completer(self):
        self._completer = QCompleter([], self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._completer.activated.connect(self._insert_completion)

    def _setup_shortcuts(self):
        run_shortcut = QShortcut(QKeySequence("F5"), self)
        run_shortcut.activated.connect(self._run_query)

        run_alt = QShortcut(QKeySequence("Ctrl+Return"), self)
        run_alt.activated.connect(self._run_query)

        fmt_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        fmt_shortcut.activated.connect(self._format_sql)

        comment_shortcut = QShortcut(QKeySequence("Ctrl+/"), self)
        comment_shortcut.activated.connect(self._toggle_comment)

    def _toggle_comment(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            cursor.setPosition(start)
            lines = []
            while cursor.position() < end:
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                pos = cursor.position()
                block_end = pos + cursor.block().length() - 1
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                text = cursor.selectedText()
                if text.startswith("-- "):
                    new_text = text[3:]
                elif text.startswith("--"):
                    new_text = text[2:]
                else:
                    new_text = f"-- {text}"
                lines.append((pos, new_text))
                cursor.setPosition(min(block_end + 1, self.document().characterCount() - 1))
            for pos, new_text in reversed(lines):
                c = self.textCursor()
                c.setPosition(pos)
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                c.insertText(new_text)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            pos = cursor.position()
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            text = cursor.selectedText()
            if text.startswith("-- "):
                cursor.insertText(text[3:])
            elif text.startswith("--"):
                cursor.insertText(text[2:])
            else:
                cursor.insertText(f"-- {text}")

    def set_schema(self, tables: list[str], views: list[str],
                   routines: list[str], columns_map: dict[str, list[str]]):
        words = list(SQL_KEYWORDS)
        words.extend(tables)
        words.extend(views)
        words.extend(routines)
        for table, cols in columns_map.items():
            for col in cols:
                words.append(f"{table}.{col}")
                words.append(col)
        words = sorted(set(words))
        self._completer.setModel(QStringListModel(words))

    def _run_query(self):
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            sql = selected.replace("\u2029", "\n").replace("\u2028", "\n")
        else:
            sql = self.toPlainText()
        sql = sql.strip()
        if sql:
            self.query_requested.emit(sql)

    def _format_sql(self):
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            formatted = sqlparse.format(selected, reindent=True, keyword_case='upper')
            cursor.insertText(formatted)
        else:
            text = self.toPlainText()
            formatted = sqlparse.format(text, reindent=True, keyword_case='upper')
            self.setPlainText(formatted)

    def _insert_completion(self, text):
        cursor = self.textCursor()
        line = cursor.block().text()
        col = cursor.columnNumber()
        before = line[:col]
        match = re.search(r'[a-zA-Z_][a-zA-Z0-9_.]*$', before)
        if match:
            prefix = match.group()
            if '.' in prefix and '.' in text:
                text = text.split('.', 1)[1]
                dot_idx = prefix.rfind('.')
                after_dot = prefix[dot_idx + 1:]
                start = cursor.position() - len(after_dot)
                cursor.setPosition(start)
                cursor.movePosition(QTextCursor.MoveOperation.Right,
                                    QTextCursor.MoveMode.KeepAnchor, len(after_dot))
            else:
                start = cursor.position() - len(prefix)
                cursor.setPosition(start)
                cursor.movePosition(QTextCursor.MoveOperation.Right,
                                    QTextCursor.MoveMode.KeepAnchor, len(prefix))
            cursor.insertText(text)
        else:
            cursor.insertText(text)

    def _highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(self._colors.get("comment", "#5c6370"))
            line_color.setAlpha(40)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def get_line_number_width(self):
        digits = len(str(max(1, self.blockCount())))
        width = 8 + self.fontMetrics().horizontalAdvance("9") * digits
        return width

    def paint_line_numbers(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(self._colors.get("comment", "#5c6370")).lighter(180))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(self._colors.get("comment", "#5c6370")))
                painter.drawText(
                    0, top, self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    def _update_line_number_width(self):
        self.setViewportMargins(self._line_number_area.sizeHint().width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(),
                                          self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self._line_number_area.sizeHint().width(), cr.height())
        )

    def keyPressEvent(self, event):
        if self._completer and self._completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape,
                               Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                event.ignore()
                return

        super().keyPressEvent(event)

        if self._completer:
            cursor = self.textCursor()
            line = cursor.block().text()
            col = cursor.columnNumber()
            before = line[:col]
            match = re.search(r'[a-zA-Z_][a-zA-Z0-9_.]*$', before)
            prefix = match.group() if match else ""
            if len(prefix) >= 1:
                self._completer.setCompletionPrefix(prefix)
                if self._completer.completionCount() > 0:
                    cr = self.cursorRect()
                    cr.setWidth(self._completer.popup().sizeHintForColumn(0)
                                + self._completer.popup().verticalScrollBar().sizeHint().width())
                    self._completer.complete(cr)
                else:
                    self._completer.popup().hide()
            else:
                self._completer.popup().hide()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        run_action = QAction("Run Query (F5)", self)
        run_action.triggered.connect(self._run_query)
        menu.addAction(run_action)

        format_action = QAction("Format SQL", self)
        format_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        format_action.triggered.connect(self._format_sql)
        menu.addAction(format_action)

        menu.addSeparator()

        cut_action = QAction("Cut", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(self.cut)
        menu.addAction(cut_action)

        copy_action = QAction("Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)

        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self.paste)
        menu.addAction(paste_action)

        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(select_all_action)

        menu.exec(event.globalPos())

    def clear_schema(self):
        self._completer.setModel(QStringListModel([]))
