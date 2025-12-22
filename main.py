# taxi_calculator_overlay.py
# One-file app: GTA 5 RP Taxi Calculator Overlay
# UI styled like modern dashboard (dark sidebar + light cards)
#
# deps:
#   pip install PySide6 matplotlib pynput
#
# run:
#   python taxi_calculator_overlay.py

from __future__ import annotations

import os
import sys
import sqlite3
import threading
import traceback
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from pynput import keyboard as pynput_keyboard


APP_NAME = "Калькулятор Таксиста"
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taxi_calc.db")


# ------------------------------- Utils -------------------------------

def now_local() -> datetime:
    return datetime.now()

def fmt_money(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    return f"{sign}{x:,.0f}".replace(",", " ")

def fmt_duration(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:d}ч {m:02d}м"
    if m > 0:
        return f"{m:d}м {s:02d}с"
    return f"{s:d}с"

def safe_float(text: str) -> Optional[float]:
    t = text.strip().replace(" ", "").replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except Exception:
        return None

def day_key(d: date) -> str:
    return d.strftime("%d-%m-%Y")

def parse_day_key(s: str) -> date:
    return datetime.strptime(s, "%d-%m-%Y").date()


# ------------------------------- DB Layer -------------------------------

class DB:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _exec(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            self.conn.commit()
            return cur

    def _query(self, sql: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()

    def _init_schema(self):
        self._exec("PRAGMA journal_mode=WAL;")

        self._exec("""
        CREATE TABLE IF NOT EXISTS days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_text TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        """)

        self._exec("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            status TEXT NOT NULL,
            FOREIGN KEY(day_id) REFERENCES days(id) ON DELETE CASCADE
        );
        """)

        self._exec("""
        CREATE TABLE IF NOT EXISTS ops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,      -- IN / OUT
            amount REAL NOT NULL,
            comment TEXT NOT NULL,
            FOREIGN KEY(shift_id) REFERENCES shifts(id) ON DELETE CASCADE
        );
        """)

        self._exec("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

        defaults = {
            "hotkey_toggle": "<ctrl>+<alt>+h",
            "hotkey_quick_income": "<ctrl>+<alt>+i",
            "hotkey_quick_expense": "<ctrl>+<alt>+o",
            "hotkey_screenshot": "<ctrl>+<alt>+p",
            "ui_compact": "0",  # overlay compact mode
        }
        for k, v in defaults.items():
            if self.get_setting(k) is None:
                self.set_setting(k, v)

        self.ensure_day(date.today())

    def get_setting(self, key: str) -> Optional[str]:
        rows = self._query("SELECT value FROM settings WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    def set_setting(self, key: str, value: str):
        self._exec("""
        INSERT INTO settings(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))

    def ensure_day(self, d: date) -> int:
        dtxt = day_key(d)
        rows = self._query("SELECT id FROM days WHERE day_text=?", (dtxt,))
        if rows:
            return int(rows[0]["id"])
        cur = self._exec("INSERT INTO days(day_text, created_at) VALUES(?, ?)", (dtxt, now_local().isoformat()))
        return int(cur.lastrowid)

    def list_days_desc(self) -> List[Tuple[int, str]]:
        rows = self._query("SELECT id, day_text FROM days ORDER BY id DESC")
        return [(int(r["id"]), str(r["day_text"])) for r in rows]

    def get_day_id_by_text(self, day_text: str) -> Optional[int]:
        rows = self._query("SELECT id FROM days WHERE day_text=?", (day_text,))
        return int(rows[0]["id"]) if rows else None

    def get_active_shift(self) -> Optional[sqlite3.Row]:
        rows = self._query("""
        SELECT s.*, d.day_text
        FROM shifts s
        JOIN days d ON d.id=s.day_id
        WHERE s.status='ACTIVE'
        ORDER BY s.id DESC
        LIMIT 1
        """)
        return rows[0] if rows else None

    def start_shift(self, day_id: int) -> int:
        self._exec("UPDATE shifts SET status='CLOSED', ended_at=COALESCE(ended_at, ?) WHERE status='ACTIVE'", (now_local().isoformat(),))
        cur = self._exec("INSERT INTO shifts(day_id, started_at, status) VALUES(?, ?, 'ACTIVE')", (day_id, now_local().isoformat()))
        return int(cur.lastrowid)

    def end_shift(self, shift_id: int):
        self._exec("UPDATE shifts SET status='CLOSED', ended_at=? WHERE id=?", (now_local().isoformat(), shift_id))

    def list_shifts_for_day(self, day_id: int) -> List[sqlite3.Row]:
        return self._query("SELECT s.* FROM shifts s WHERE s.day_id=? ORDER BY s.id DESC", (day_id,))

    def list_shifts_in_range(self, day_from: str, day_to: str) -> List[sqlite3.Row]:
        days = self._query("SELECT id, day_text FROM days")
        d_from = parse_day_key(day_from)
        d_to = parse_day_key(day_to)
        ids: List[int] = []
        for r in days:
            dt = parse_day_key(str(r["day_text"]))
            if d_from <= dt <= d_to:
                ids.append(int(r["id"]))
        if not ids:
            return []
        placeholders = ",".join(["?"] * len(ids))
        return self._query(f"""
        SELECT s.*, d.day_text
        FROM shifts s
        JOIN days d ON d.id=s.day_id
        WHERE s.day_id IN ({placeholders})
        ORDER BY s.id DESC
        """, tuple(ids))

    def add_op(self, shift_id: int, kind: str, amount: float, comment: str):
        self._exec("INSERT INTO ops(shift_id, ts, kind, amount, comment) VALUES(?, ?, ?, ?, ?)",
                   (shift_id, now_local().isoformat(), kind, amount, comment))

    def list_ops_for_shift(self, shift_id: int) -> List[sqlite3.Row]:
        return self._query("SELECT * FROM ops WHERE shift_id=? ORDER BY id DESC", (shift_id,))

    def sums_for_shift(self, shift_id: int) -> Tuple[float, float]:
        rows = self._query("""
        SELECT
          SUM(CASE WHEN kind='IN' THEN amount ELSE 0 END) AS inc,
          SUM(CASE WHEN kind='OUT' THEN amount ELSE 0 END) AS exp
        FROM ops
        WHERE shift_id=?
        """, (shift_id,))
        inc = float(rows[0]["inc"] or 0.0)
        exp = float(rows[0]["exp"] or 0.0)
        return inc, exp

    def sums_for_day(self, day_id: int) -> Tuple[float, float, int]:
        rows = self._query("""
        SELECT
          SUM(CASE WHEN o.kind='IN' THEN o.amount ELSE 0 END) AS inc,
          SUM(CASE WHEN o.kind='OUT' THEN o.amount ELSE 0 END) AS exp
        FROM shifts s
        LEFT JOIN ops o ON o.shift_id=s.id
        WHERE s.day_id=?
        """, (day_id,))
        inc = float(rows[0]["inc"] or 0.0)
        exp = float(rows[0]["exp"] or 0.0)

        shifts = self._query("SELECT started_at, ended_at, status FROM shifts WHERE day_id=?", (day_id,))
        total_sec = 0
        now = now_local()
        for s in shifts:
            st = datetime.fromisoformat(str(s["started_at"]))
            en = datetime.fromisoformat(str(s["ended_at"])) if s["ended_at"] else now
            total_sec += max(0, int((en - st).total_seconds()))
        return inc, exp, total_sec


# ------------------------------- UI Components -------------------------------

class Card(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

class MetricCard(Card):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        self.title = QtWidgets.QLabel(title)
        self.title.setObjectName("CardTitle")
        self.value = QtWidgets.QLabel("—")
        self.value.setObjectName("CardValue")
        self.sub = QtWidgets.QLabel("")
        self.sub.setObjectName("CardSub")

        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set_value(self, text: str, sub: str = ""):
        self.value.setText(text)
        self.sub.setText(sub)

class PillButton(QtWidgets.QPushButton):
    def __init__(self, text: str, primary: bool = True, parent=None):
        super().__init__(text, parent)
        self.setObjectName("BtnPrimary" if primary else "BtnGhost")
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

class MplChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 3), dpi=100)
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = self.fig.add_subplot(111)
        self.fig.tight_layout()

    def clear(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.fig.tight_layout()

    def draw_bars(self, labels: List[str], inc: List[float], exp: List[float], profit: List[float]):
        self.clear()
        ax = self.ax
        x = list(range(len(labels)))
        w = 0.28
        ax.bar([i - w for i in x], inc, width=w, label="Доход")
        ax.bar(x, exp, width=w, label="Расход")
        ax.bar([i + w for i in x], profit, width=w, label="Прибыль")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.grid(True, axis="y", alpha=0.25)
        ax.legend(loc="upper left")
        self.fig.tight_layout()
        self.draw()

    def draw_pie(self, labels: List[str], values: List[float], title: str):
        self.clear()
        ax = self.ax
        if not values or sum(values) <= 0:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            ax.axis("off")
            self.draw()
            return
        ax.pie(values, labels=labels, autopct=lambda p: f"{p:.0f}%" if p >= 5 else "")
        ax.set_title(title)
        self.fig.tight_layout()
        self.draw()


class HotkeyCaptureDialog(QtWidgets.QDialog):
    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Назначить хоткей")
        self.setModal(True)
        self.resize(520, 190)

        self.result_hotkey: Optional[str] = None
        self._pressed: set[str] = set()

        title = QtWidgets.QLabel("Нажмите комбинацию (Ctrl/Alt/Shift + клавиша). Esc — отмена.")
        title.setWordWrap(True)
        cur = QtWidgets.QLabel(f"Текущий: {current}")
        cur.setObjectName("Muted")
        self.live = QtWidgets.QLabel("Новая: —")
        self.live.setObjectName("HotkeyLive")

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        btns.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(title)
        lay.addWidget(cur)
        lay.addWidget(self.live)
        lay.addStretch(1)
        lay.addWidget(btns)

        self.installEventFilter(self)

    def _norm_key(self, e: QtGui.QKeyEvent) -> Optional[str]:
        k = e.key()
        if k == QtCore.Qt.Key_Escape:
            return "ESC"
        if k == QtCore.Qt.Key_Control:
            return "<ctrl>"
        if k == QtCore.Qt.Key_Alt:
            return "<alt>"
        if k == QtCore.Qt.Key_Shift:
            return "<shift>"
        if k in (QtCore.Qt.Key_Meta,):
            return "<cmd>"

        text = (e.text() or "").lower().strip()
        if text:
            if len(text) == 1:
                return text
            return text

        if QtCore.Qt.Key_F1 <= k <= QtCore.Qt.Key_F35:
            return f"f{k - QtCore.Qt.Key_F1 + 1}"
        if k == QtCore.Qt.Key_Space:
            return "space"
        if k == QtCore.Qt.Key_Tab:
            return "tab"
        if k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            return "enter"
        return None

    def _compose(self) -> Optional[str]:
        mods = [m for m in ["<ctrl>", "<alt>", "<shift>", "<cmd>"] if m in self._pressed]
        keys = [k for k in sorted(self._pressed) if k not in ("<ctrl>", "<alt>", "<shift>", "<cmd>")]
        if not keys:
            return None
        return "+".join(mods + keys[:1])

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress:
            k = self._norm_key(event)
            if k == "ESC":
                self.reject()
                return True
            if k:
                self._pressed.add(k)
                hk = self._compose()
                if hk:
                    self.live.setText(f"Новая: {hk}")
                    if any(m in self._pressed for m in ("<ctrl>", "<alt>", "<shift>", "<cmd>")):
                        self.result_hotkey = hk
                        self.accept()
                return True
        if event.type() == QtCore.QEvent.KeyRelease:
            k = self._norm_key(event)
            if k and k in self._pressed:
                self._pressed.remove(k)
            return True
        return super().eventFilter(obj, event)


# ------------------------------- Global Hotkeys -------------------------------

class GlobalHotkeys(QtCore.QObject):
    triggered = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self._listener: Optional[pynput_keyboard.GlobalHotKeys] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, action_to_hotkey: Dict[str, str]):
        self.stop()

        hotkey_to_action: Dict[str, str] = {}
        for action, hk in action_to_hotkey.items():
            hk = (hk or "").strip()
            if hk:
                hotkey_to_action[hk] = action

        def make_cb(action_name: str):
            def _cb():
                self.triggered.emit(action_name)
            return _cb

        try:
            callbacks = {hk: make_cb(action) for hk, action in hotkey_to_action.items()}
            self._listener = pynput_keyboard.GlobalHotKeys(callbacks)
        except Exception:
            self._listener = None
            return

        def run():
            try:
                if self._listener:
                    self._listener.start()
                    self._listener.join()
            except Exception:
                pass

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            pass
        self._listener = None
        self._thread = None


# ------------------------------- Main Window (Dashboard UI) -------------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1060, 680)

        # overlay
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # state
        self.current_day_text: str = day_key(date.today())
        self.active_shift_id: Optional[int] = None

        # central layout: sidebar + content (stack)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        self.stack = QtWidgets.QStackedWidget()

        self.page_shift = self._build_page_shift()
        self.page_analytics = self._build_page_analytics()
        self.page_settings = self._build_page_settings()

        self.stack.addWidget(self.page_shift)
        self.stack.addWidget(self.page_analytics)
        self.stack.addWidget(self.page_settings)

        root.addWidget(self.sidebar, 0)
        root.addWidget(self.stack, 1)

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

        self.hotkeys = GlobalHotkeys()
        self.hotkeys.triggered.connect(self.on_hotkey_action)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_shift_summary_only)
        self.timer.start()

        self.apply_styles()
        self.reload_state_from_db()
        self.restart_hotkeys_from_settings()

        # compact mode from settings
        self.apply_compact_mode(self.db.get_setting("ui_compact") == "1")

    # ------------------------- UI: Sidebar / Topbar helpers -------------------------

    def _build_sidebar(self) -> QtWidgets.QWidget:
        w = QtWidgets.QFrame()
        w.setObjectName("Sidebar")
        w.setFixedWidth(230)

        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(14)

        brand = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel("◆")
        logo.setObjectName("BrandLogo")
        name = QtWidgets.QLabel("TaxiCalc")
        name.setObjectName("BrandName")
        brand.addWidget(logo, 0)
        brand.addWidget(name, 1)
        brand.addStretch(1)
        lay.addLayout(brand)

        lay.addSpacing(4)

        self.btn_nav_shift = QtWidgets.QPushButton("  Смена")
        self.btn_nav_analytics = QtWidgets.QPushButton("  Аналитика")
        self.btn_nav_settings = QtWidgets.QPushButton("  Настройки")

        for b in (self.btn_nav_shift, self.btn_nav_analytics, self.btn_nav_settings):
            b.setObjectName("NavBtn")
            b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            b.setCheckable(True)
            b.setAutoExclusive(True)

        self.btn_nav_shift.setChecked(True)

        self.btn_nav_shift.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_nav_analytics.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_nav_settings.clicked.connect(lambda: self.stack.setCurrentIndex(2))

        lay.addWidget(self.btn_nav_shift)
        lay.addWidget(self.btn_nav_analytics)
        lay.addWidget(self.btn_nav_settings)

        lay.addStretch(1)

        # quick overlay actions
        self.btn_toggle_visible = QtWidgets.QPushButton("Скрыть / Показать")
        self.btn_toggle_visible.setObjectName("NavBtnAlt")
        self.btn_toggle_visible.clicked.connect(self.toggle_visibility)

        self.btn_screenshot = QtWidgets.QPushButton("Скрин в буфер")
        self.btn_screenshot.setObjectName("NavBtnAlt")
        self.btn_screenshot.clicked.connect(self.screenshot_to_clipboard)

        lay.addWidget(self.btn_toggle_visible)
        lay.addWidget(self.btn_screenshot)

        hint = QtWidgets.QLabel("Hotkey: Ctrl+Alt+H\n(настраивается)")
        hint.setObjectName("SidebarHint")
        lay.addWidget(hint)

        return w

    def _topbar(self, title: str) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("Topbar")
        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        t = QtWidgets.QLabel(title)
        t.setObjectName("TopTitle")

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search (необязательно)")
        self.search.setObjectName("Search")
        self.search.setClearButtonEnabled(True)

        self.lbl_day = QtWidgets.QLabel("—")
        self.lbl_day.setObjectName("DayPill")

        self.btn_new_day = PillButton("Новый день", primary=False)
        self.btn_new_day.clicked.connect(self.on_new_day)

        self.btn_top = PillButton("Always On Top", primary=False)
        self.btn_top.clicked.connect(self.on_toggle_always_on_top)

        self.btn_compact = PillButton("Компактный режим", primary=False)
        self.btn_compact.clicked.connect(self.toggle_compact_mode)

        lay.addWidget(t, 0)
        lay.addStretch(1)
        lay.addWidget(self.search, 2)
        lay.addWidget(self.lbl_day, 0)
        lay.addWidget(self.btn_new_day, 0)
        lay.addWidget(self.btn_top, 0)
        lay.addWidget(self.btn_compact, 0)
        return bar

    # ------------------------- Page: Shift -------------------------

    def _build_page_shift(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._topbar("Смена"))

        content = QtWidgets.QWidget()
        content.setObjectName("Content")
        lay = QtWidgets.QVBoxLayout(content)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        # metric row
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)
        self.card_status = MetricCard("Смена")
        self.card_inc = MetricCard("Доход")
        self.card_exp = MetricCard("Расход")
        self.card_profit = MetricCard("Прибыль")
        self.card_time = MetricCard("Время")
        for c in (self.card_status, self.card_inc, self.card_exp, self.card_profit, self.card_time):
            row.addWidget(c)
        lay.addLayout(row)

        # actions + inputs grid
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        left = Card()
        llay = QtWidgets.QVBoxLayout(left)
        llay.setContentsMargins(16, 16, 16, 16)
        llay.setSpacing(10)

        title = QtWidgets.QLabel("Управление сменой")
        title.setObjectName("BlockTitle")
        llay.addWidget(title)

        btns = QtWidgets.QHBoxLayout()
        self.btn_start_shift = PillButton("Начать смену", primary=True)
        self.btn_end_shift = PillButton("Завершить смену", primary=False)
        self.btn_start_shift.clicked.connect(self.on_start_shift)
        self.btn_end_shift.clicked.connect(self.on_end_shift)
        btns.addWidget(self.btn_start_shift)
        btns.addWidget(self.btn_end_shift)
        llay.addLayout(btns)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.kind_combo = QtWidgets.QComboBox()
        self.kind_combo.addItems(["Доход", "Расход"])
        self.kind_combo.currentIndexChanged.connect(self.on_kind_changed)

        self.amount_edit = QtWidgets.QLineEdit()
        self.amount_edit.setPlaceholderText("Сумма (например 500)")
        self.amount_edit.returnPressed.connect(self.on_add_operation)

        self.comment_combo = QtWidgets.QComboBox()
        self.other_comment = QtWidgets.QLineEdit()
        self.other_comment.setPlaceholderText("Комментарий для 'Другое'")
        self.other_comment.setEnabled(False)
        self.comment_combo.currentIndexChanged.connect(self.on_comment_changed)

        self.btn_add = PillButton("Добавить (Enter)", primary=True)
        self.btn_add.clicked.connect(self.on_add_operation)

        form.addWidget(QtWidgets.QLabel("Тип"), 0, 0)
        form.addWidget(self.kind_combo, 0, 1)
        form.addWidget(QtWidgets.QLabel("Сумма"), 1, 0)
        form.addWidget(self.amount_edit, 1, 1)
        form.addWidget(QtWidgets.QLabel("Комментарий"), 2, 0)
        form.addWidget(self.comment_combo, 2, 1)
        form.addWidget(self.other_comment, 3, 0, 1, 2)
        form.addWidget(self.btn_add, 4, 0, 1, 2)

        llay.addLayout(form)
        llay.addStretch(1)

        right = Card()
        rlay = QtWidgets.QVBoxLayout(right)
        rlay.setContentsMargins(16, 16, 16, 16)
        rlay.setSpacing(10)
        rtitle = QtWidgets.QLabel("Операции текущей смены")
        rtitle.setObjectName("BlockTitle")
        rlay.addWidget(rtitle)

        self.ops_table = QtWidgets.QTableWidget(0, 4)
        self.ops_table.setHorizontalHeaderLabels(["Время", "Тип", "Сумма", "Комментарий"])
        self.ops_table.horizontalHeader().setStretchLastSection(True)
        self.ops_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.ops_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.ops_table.verticalHeader().setVisible(False)

        rlay.addWidget(self.ops_table)

        grid.addWidget(left, 0, 0)
        grid.addWidget(right, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)

        lay.addLayout(grid)

        outer.addWidget(content, 1)

        self._load_comment_presets()
        return page

    def _load_comment_presets(self):
        self.comment_combo.blockSignals(True)
        self.comment_combo.clear()
        if self.kind_combo.currentText() == "Доход":
            self.comment_combo.addItems(["Чай", "Согласно тарифу", "Другое"])
        else:
            self.comment_combo.addItems(["Аренда авто", "Ремонт", "Заправка", "Штраф", "Другое"])
        self.comment_combo.blockSignals(False)
        self.on_comment_changed()

    def on_kind_changed(self):
        self._load_comment_presets()

    def on_comment_changed(self):
        is_other = (self.comment_combo.currentText() == "Другое")
        self.other_comment.setEnabled(is_other)
        if not is_other:
            self.other_comment.setText("")

    # ------------------------- Page: Analytics -------------------------

    def _build_page_analytics(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._topbar("Аналитика"))

        content = QtWidgets.QWidget()
        content.setObjectName("Content")
        lay = QtWidgets.QVBoxLayout(content)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        # filters card
        flt = Card()
        fl = QtWidgets.QGridLayout(flt)
        fl.setContentsMargins(16, 16, 16, 16)
        fl.setHorizontalSpacing(10)
        fl.setVerticalSpacing(10)

        self.date_from = QtWidgets.QDateEdit()
        self.date_to = QtWidgets.QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_to.setCalendarPopup(True)
        self.date_from.setDate(QtCore.QDate.currentDate().addDays(-6))
        self.date_to.setDate(QtCore.QDate.currentDate())

        self.day_pick = QtWidgets.QComboBox()
        self.shift_pick = QtWidgets.QComboBox()
        self.btn_refresh_analytics = PillButton("Обновить", primary=True)
        self.btn_refresh_analytics.clicked.connect(self.refresh_analytics)

        fl.addWidget(QtWidgets.QLabel("Период:"), 0, 0)
        fl.addWidget(self.date_from, 0, 1)
        fl.addWidget(QtWidgets.QLabel("—"), 0, 2)
        fl.addWidget(self.date_to, 0, 3)
        fl.addWidget(QtWidgets.QLabel("День:"), 1, 0)
        fl.addWidget(self.day_pick, 1, 1, 1, 2)
        fl.addWidget(QtWidgets.QLabel("Смена:"), 1, 3)
        fl.addWidget(self.shift_pick, 1, 4)
        fl.addWidget(self.btn_refresh_analytics, 0, 4)

        lay.addWidget(flt)

        # metrics grid
        mrow = QtWidgets.QHBoxLayout()
        mrow.setSpacing(12)
        self.a_inc = MetricCard("Доход")
        self.a_exp = MetricCard("Расход")
        self.a_profit = MetricCard("Прибыль")
        self.a_shifts = MetricCard("Смен")
        self.a_time = MetricCard("Время")
        self.a_inc_h = MetricCard("Доход/час")
        self.a_profit_h = MetricCard("Прибыль/час")
        self.a_avg = MetricCard("Средн. прибыль/смена")
        for c in (self.a_inc, self.a_exp, self.a_profit, self.a_shifts, self.a_time, self.a_inc_h, self.a_profit_h, self.a_avg):
            mrow.addWidget(c)
        lay.addLayout(mrow)

        # charts row
        crow = QtWidgets.QHBoxLayout()
        crow.setSpacing(12)

        c1 = Card()
        c1l = QtWidgets.QVBoxLayout(c1)
        c1l.setContentsMargins(16, 16, 16, 16)
        c1l.setSpacing(10)
        t1 = QtWidgets.QLabel("Доход / Расход / Прибыль по дням")
        t1.setObjectName("BlockTitle")
        self.chart_main = MplChart()
        c1l.addWidget(t1)
        c1l.addWidget(self.chart_main)

        c2 = Card()
        c2l = QtWidgets.QVBoxLayout(c2)
        c2l.setContentsMargins(16, 16, 16, 16)
        c2l.setSpacing(10)
        t2 = QtWidgets.QLabel("Структура расходов")
        t2.setObjectName("BlockTitle")
        self.chart_pie = MplChart()
        c2l.addWidget(t2)
        c2l.addWidget(self.chart_pie)

        crow.addWidget(c1, 2)
        crow.addWidget(c2, 1)

        lay.addLayout(crow, 1)

        # tables row
        brow = QtWidgets.QHBoxLayout()
        brow.setSpacing(12)

        sh_card = Card()
        shl = QtWidgets.QVBoxLayout(sh_card)
        shl.setContentsMargins(16, 16, 16, 16)
        shl.setSpacing(10)
        shl.addWidget(self._block_title("Смены"))

        self.table_shifts = QtWidgets.QTableWidget(0, 8)
        self.table_shifts.setHorizontalHeaderLabels(["День", "ID", "Старт", "Финиш", "Доход", "Расход", "Прибыль", "Длит."])
        self.table_shifts.horizontalHeader().setStretchLastSection(True)
        self.table_shifts.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_shifts.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_shifts.verticalHeader().setVisible(False)
        self.table_shifts.itemSelectionChanged.connect(self.on_shift_table_selected)
        shl.addWidget(self.table_shifts)

        ops_card = Card()
        opl = QtWidgets.QVBoxLayout(ops_card)
        opl.setContentsMargins(16, 16, 16, 16)
        opl.setSpacing(10)
        opl.addWidget(self._block_title("Операции выбранной смены"))

        self.table_ops = QtWidgets.QTableWidget(0, 4)
        self.table_ops.setHorizontalHeaderLabels(["Время", "Тип", "Сумма", "Комментарий"])
        self.table_ops.horizontalHeader().setStretchLastSection(True)
        self.table_ops.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_ops.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_ops.verticalHeader().setVisible(False)
        opl.addWidget(self.table_ops)

        brow.addWidget(sh_card, 2)
        brow.addWidget(ops_card, 1)

        lay.addLayout(brow, 2)

        outer.addWidget(content, 1)
        return page

    def _block_title(self, text: str) -> QtWidgets.QLabel:
        t = QtWidgets.QLabel(text)
        t.setObjectName("BlockTitle")
        return t

    # ------------------------- Page: Settings -------------------------

    def _build_page_settings(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._topbar("Настройки"))

        content = QtWidgets.QWidget()
        content.setObjectName("Content")
        lay = QtWidgets.QVBoxLayout(content)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        hk = Card()
        hkl = QtWidgets.QGridLayout(hk)
        hkl.setContentsMargins(16, 16, 16, 16)
        hkl.setHorizontalSpacing(10)
        hkl.setVerticalSpacing(12)

        title = self._block_title("Горячие клавиши (глобальные)")
        hkl.addWidget(title, 0, 0, 1, 3)

        self.hk_toggle_lbl = QtWidgets.QLabel("—")
        self.hk_income_lbl = QtWidgets.QLabel("—")
        self.hk_expense_lbl = QtWidgets.QLabel("—")
        self.hk_shot_lbl = QtWidgets.QLabel("—")
        for lbl in (self.hk_toggle_lbl, self.hk_income_lbl, self.hk_expense_lbl, self.hk_shot_lbl):
            lbl.setObjectName("MonoPill")

        def mk_btn(key: str) -> QtWidgets.QPushButton:
            b = PillButton("Изменить", primary=False)
            b.clicked.connect(lambda: self.change_hotkey(key))
            return b

        hkl.addWidget(QtWidgets.QLabel("Показать / скрыть"), 1, 0)
        hkl.addWidget(self.hk_toggle_lbl, 1, 1)
        hkl.addWidget(mk_btn("hotkey_toggle"), 1, 2)

        hkl.addWidget(QtWidgets.QLabel("Быстро добавить доход"), 2, 0)
        hkl.addWidget(self.hk_income_lbl, 2, 1)
        hkl.addWidget(mk_btn("hotkey_quick_income"), 2, 2)

        hkl.addWidget(QtWidgets.QLabel("Быстро добавить расход"), 3, 0)
        hkl.addWidget(self.hk_expense_lbl, 3, 1)
        hkl.addWidget(mk_btn("hotkey_quick_expense"), 3, 2)

        hkl.addWidget(QtWidgets.QLabel("Скрин окна в буфер"), 4, 0)
        hkl.addWidget(self.hk_shot_lbl, 4, 1)
        hkl.addWidget(mk_btn("hotkey_screenshot"), 4, 2)

        lay.addWidget(hk)

        misc = Card()
        ml = QtWidgets.QVBoxLayout(misc)
        ml.setContentsMargins(16, 16, 16, 16)
        ml.setSpacing(10)
        ml.addWidget(self._block_title("Оверлей / удобство"))

        info = QtWidgets.QLabel(
            "• Окно поверх GTA 5 (Always On Top)\n"
            "• Хоткеи работают глобально\n"
            "• Компактный режим — удобнее во время активной игры\n"
        )
        info.setObjectName("Muted")
        ml.addWidget(info)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.btn_restart_hotkeys = PillButton("Перезапустить хоткеи", primary=False)
        self.btn_restart_hotkeys.clicked.connect(self.restart_hotkeys_from_settings)
        row.addWidget(self.btn_restart_hotkeys)
        ml.addLayout(row)

        lay.addWidget(misc)
        lay.addStretch(1)

        outer.addWidget(content, 1)
        return page

    # ------------------------- Styling -------------------------

    def apply_styles(self):
        # Dashboard feel: dark sidebar, light content, white cards with soft border + radius
        self.setStyleSheet("""
        QMainWindow { background: #0B1020; }
        QWidget { font-family: "Segoe UI", Arial; font-size: 10.5pt; }

        /* Sidebar */
        QFrame#Sidebar {
            background: #0F1530;
            border-right: 1px solid rgba(255,255,255,0.06);
        }
        QLabel#BrandLogo { color: #6D5EF6; font-size: 18pt; font-weight: 900; }
        QLabel#BrandName { color: #EAF0FF; font-size: 12pt; font-weight: 800; }
        QPushButton#NavBtn {
            text-align: left;
            padding: 10px 12px;
            border-radius: 12px;
            color: rgba(234,240,255,0.78);
            background: transparent;
            border: 1px solid transparent;
        }
        QPushButton#NavBtn:hover { background: rgba(255,255,255,0.06); }
        QPushButton#NavBtn:checked {
            background: rgba(109,94,246,0.18);
            border: 1px solid rgba(109,94,246,0.28);
            color: #EAF0FF;
        }
        QPushButton#NavBtnAlt {
            text-align: left;
            padding: 10px 12px;
            border-radius: 12px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.08);
            color: rgba(234,240,255,0.85);
        }
        QPushButton#NavBtnAlt:hover { background: rgba(255,255,255,0.09); }
        QLabel#SidebarHint { color: rgba(234,240,255,0.55); font-size: 9pt; }

        /* Content */
        QWidget#Content { background: #F4F6FB; }
        QFrame#Topbar {
            background: #F4F6FB;
            border-bottom: 1px solid rgba(10,15,30,0.08);
        }
        QLabel#TopTitle { color: #0B1020; font-size: 14pt; font-weight: 900; }
        QLineEdit#Search {
            background: #FFFFFF;
            border: 1px solid rgba(10,15,30,0.12);
            border-radius: 12px;
            padding: 8px 12px;
            color: #0B1020;
        }
        QLabel#DayPill {
            background: rgba(109,94,246,0.10);
            border: 1px solid rgba(109,94,246,0.22);
            border-radius: 12px;
            padding: 7px 10px;
            color: #2A2F45;
            font-weight: 700;
        }

        /* Buttons */
        QPushButton#BtnPrimary {
            background: #6D5EF6;
            color: #FFFFFF;
            border: 0;
            padding: 9px 12px;
            border-radius: 12px;
            font-weight: 800;
        }
        QPushButton#BtnPrimary:hover { background: #5D50E7; }
        QPushButton#BtnPrimary:pressed { background: #4D41D6; }

        QPushButton#BtnGhost {
            background: #FFFFFF;
            color: #2A2F45;
            border: 1px solid rgba(10,15,30,0.12);
            padding: 9px 12px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#BtnGhost:hover { background: rgba(255,255,255,0.85); }

        /* Cards */
        QFrame#Card {
            background: #FFFFFF;
            border: 1px solid rgba(10,15,30,0.10);
            border-radius: 16px;
        }
        QLabel#CardTitle { color: rgba(42,47,69,0.72); font-size: 9.5pt; font-weight: 700; }
        QLabel#CardValue { color: #0B1020; font-size: 20pt; font-weight: 900; }
        QLabel#CardSub { color: rgba(42,47,69,0.55); font-size: 9pt; }

        QLabel#BlockTitle { color: #0B1020; font-size: 11.5pt; font-weight: 900; }
        QLabel#Muted { color: rgba(42,47,69,0.65); }
        QLabel#HotkeyLive { font-size: 12pt; font-weight: 900; color: #0B1020; }
        QLabel#MonoPill {
            background: rgba(10,15,30,0.05);
            border: 1px solid rgba(10,15,30,0.10);
            border-radius: 12px;
            padding: 7px 10px;
            color: #0B1020;
            font-family: "Consolas";
        }

        /* Inputs / tables */
        QLineEdit, QComboBox, QDateEdit {
            background: #FFFFFF;
            border: 1px solid rgba(10,15,30,0.12);
            border-radius: 12px;
            padding: 8px 10px;
            color: #0B1020;
        }
        QComboBox::drop-down { border: 0; }
        QTableWidget {
            background: #FFFFFF;
            border: 1px solid rgba(10,15,30,0.10);
            border-radius: 14px;
            gridline-color: rgba(10,15,30,0.08);
            color: #0B1020;
        }
        QHeaderView::section {
            background: rgba(10,15,30,0.03);
            border: 0;
            padding: 8px;
            color: rgba(42,47,69,0.75);
            font-weight: 800;
        }
        """)

    # ------------------------- Overlay actions -------------------------

    def on_toggle_always_on_top(self):
        is_on = bool(self.windowFlags() & QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, not is_on)
        self.show()
        self.toast("Always On Top: " + ("ВКЛ" if not is_on else "ВЫКЛ"))

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def screenshot_to_clipboard(self):
        pix = self.grab()
        QtWidgets.QApplication.clipboard().setPixmap(pix)
        self.toast("Скриншот окна → буфер")

    # compact mode (overlay-friendly)
    def toggle_compact_mode(self):
        is_compact = (self.db.get_setting("ui_compact") == "1")
        self.apply_compact_mode(not is_compact)

    def apply_compact_mode(self, compact: bool):
        self.db.set_setting("ui_compact", "1" if compact else "0")
        if compact:
            self.sidebar.setFixedWidth(190)
            self.resize(860, 560)
        else:
            self.sidebar.setFixedWidth(230)
            self.resize(1060, 680)
        self.toast("Компактный режим: " + ("ВКЛ" if compact else "ВЫКЛ"))

    # ------------------------- Hotkeys -------------------------

    def restart_hotkeys_from_settings(self):
        mapping = {
            "toggle": self.db.get_setting("hotkey_toggle") or "",
            "quick_income": self.db.get_setting("hotkey_quick_income") or "",
            "quick_expense": self.db.get_setting("hotkey_quick_expense") or "",
            "screenshot": self.db.get_setting("hotkey_screenshot") or "",
        }
        self.hotkeys.start(mapping)
        self.reload_hotkeys_labels()

    def on_hotkey_action(self, action: str):
        try:
            if action == "toggle":
                self.toggle_visibility()
            elif action == "quick_income":
                self.open_quick_add(kind="IN")
            elif action == "quick_expense":
                self.open_quick_add(kind="OUT")
            elif action == "screenshot":
                self.screenshot_to_clipboard()
        except Exception:
            traceback.print_exc()

    # ------------------------- Business logic: Shift -------------------------

    def on_new_day(self):
        self.current_day_text = day_key(date.today())
        self.db.ensure_day(date.today())
        self.reload_state_from_db()
        self.toast("Новый день: " + self.current_day_text)

    def on_start_shift(self):
        day_id = self.db.get_day_id_by_text(self.current_day_text)
        if day_id is None:
            day_id = self.db.ensure_day(parse_day_key(self.current_day_text))
        self.active_shift_id = self.db.start_shift(day_id)
        self.reload_state_from_db()
        self.toast("Смена начата")

    def on_end_shift(self):
        active = self.db.get_active_shift()
        if not active:
            self.toast("Активной смены нет", error=True)
            return
        sid = int(active["id"])
        self.db.end_shift(sid)

        inc, exp = self.db.sums_for_shift(sid)
        profit = inc - exp
        st = datetime.fromisoformat(str(active["started_at"]))
        en = now_local()
        dur = int((en - st).total_seconds())

        QtWidgets.QMessageBox.information(
            self,
            "Итог смены",
            "Смена завершена.\n\n"
            f"Доход: {fmt_money(inc)}\n"
            f"Расход: {fmt_money(exp)}\n"
            f"Чистая прибыль: {fmt_money(profit)}\n"
            f"Длительность: {fmt_duration(dur)}\n"
        )
        self.reload_state_from_db()
        self.refresh_analytics()

    def on_add_operation(self):
        active = self.db.get_active_shift()
        if not active:
            self.toast("Сначала начните смену", error=True)
            return

        amount = safe_float(self.amount_edit.text())
        if amount is None or amount <= 0:
            self.toast("Введите корректную сумму", error=True)
            return

        kind = "IN" if self.kind_combo.currentText() == "Доход" else "OUT"

        comment = self.comment_combo.currentText()
        if comment == "Другое":
            comment = self.other_comment.text().strip()
            if not comment:
                self.toast("Введите комментарий для 'Другое'", error=True)
                return

        sid = int(active["id"])
        self.db.add_op(sid, kind, float(amount), comment)

        self.amount_edit.setText("")
        self.amount_edit.setFocus(QtCore.Qt.TabFocusReason)
        self.reload_state_from_db()

    def open_quick_add(self, kind: str):
        active = self.db.get_active_shift()
        if not active:
            self.toast("Нет активной смены", error=True)
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Быстрый ввод: " + ("Доход" if kind == "IN" else "Расход"))
        dlg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        dlg.setModal(False)
        dlg.resize(420, 240)

        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        a = QtWidgets.QLineEdit()
        a.setPlaceholderText("Сумма")
        a.setFocus()

        c = QtWidgets.QComboBox()
        if kind == "IN":
            c.addItems(["Чай", "Согласно тарифу", "Другое"])
        else:
            c.addItems(["Аренда авто", "Ремонт", "Заправка", "Штраф", "Другое"])

        o = QtWidgets.QLineEdit()
        o.setPlaceholderText("Комментарий для 'Другое'")
        o.setEnabled(False)

        def on_c():
            o.setEnabled(c.currentText() == "Другое")
            if not o.isEnabled():
                o.setText("")
        c.currentIndexChanged.connect(on_c)
        on_c()

        btn = PillButton("Сохранить", primary=True)
        btn.setDefault(True)

        def save():
            amount = safe_float(a.text())
            if amount is None or amount <= 0:
                self.toast("Некорректная сумма", error=True)
                return
            comment = c.currentText()
            if comment == "Другое":
                comment = o.text().strip()
                if not comment:
                    self.toast("Введите комментарий", error=True)
                    return
            self.db.add_op(int(active["id"]), kind, float(amount), comment)
            dlg.accept()
            self.reload_state_from_db()

        btn.clicked.connect(save)
        a.returnPressed.connect(save)

        v.addWidget(a)
        v.addWidget(c)
        v.addWidget(o)
        v.addWidget(btn)

        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ------------------------- Analytics -------------------------

    def refresh_analytics_filters(self):
        days = self.db.list_days_desc()
        cur_day = self.current_day_text

        self.day_pick.blockSignals(True)
        self.day_pick.clear()
        self.day_pick.addItem("— (все дни периода) —", userData=None)
        for did, dtxt in days:
            self.day_pick.addItem(dtxt, userData=did)
        idx = self.day_pick.findText(cur_day)
        self.day_pick.setCurrentIndex(idx if idx >= 0 else 0)
        self.day_pick.blockSignals(False)

        self.day_pick.currentIndexChanged.connect(self.refresh_shift_pick_for_selected_day)
        self.refresh_shift_pick_for_selected_day()

    def refresh_shift_pick_for_selected_day(self):
        did = self.day_pick.currentData()
        self.shift_pick.blockSignals(True)
        self.shift_pick.clear()
        self.shift_pick.addItem("— (все смены) —", userData=None)
        if did is not None:
            shifts = self.db.list_shifts_for_day(int(did))
            for s in shifts:
                sid = int(s["id"])
                st = datetime.fromisoformat(str(s["started_at"])).strftime("%H:%M")
                en = datetime.fromisoformat(str(s["ended_at"])).strftime("%H:%M") if s["ended_at"] else "—"
                status = "Активна" if s["status"] == "ACTIVE" else "Закрыта"
                self.shift_pick.addItem(f"#{sid} • {st}–{en} • {status}", userData=sid)
        self.shift_pick.blockSignals(False)

    def refresh_analytics(self):
        d_from = self.date_from.date().toPython()
        d_to = self.date_to.date().toPython()
        if d_from > d_to:
            d_from, d_to = d_to, d_from

        did = self.day_pick.currentData()
        sid = self.shift_pick.currentData()

        if sid is not None:
            shifts = self.db._query("""
                SELECT s.*, d.day_text
                FROM shifts s JOIN days d ON d.id=s.day_id
                WHERE s.id=?
            """, (int(sid),))
        elif did is not None:
            shifts = self.db._query("""
                SELECT s.*, d.day_text
                FROM shifts s JOIN days d ON d.id=s.day_id
                WHERE s.day_id=?
                ORDER BY s.id DESC
            """, (int(did),))
        else:
            shifts = self.db.list_shifts_in_range(day_key(d_from), day_key(d_to))

        total_inc = total_exp = 0.0
        total_sec = 0
        shift_count = 0
        expense_by_comment: Dict[str, float] = {}

        for s in shifts:
            sid0 = int(s["id"])
            inc, exp = self.db.sums_for_shift(sid0)
            total_inc += inc
            total_exp += exp

            st = datetime.fromisoformat(str(s["started_at"]))
            en = datetime.fromisoformat(str(s["ended_at"])) if s["ended_at"] else now_local()
            total_sec += max(0, int((en - st).total_seconds()))
            shift_count += 1

            for o in self.db.list_ops_for_shift(sid0):
                if o["kind"] == "OUT":
                    c = str(o["comment"])
                    expense_by_comment[c] = expense_by_comment.get(c, 0.0) + float(o["amount"])

        profit = total_inc - total_exp
        hours = total_sec / 3600.0 if total_sec > 0 else 0.0
        inc_h = (total_inc / hours) if hours > 0 else 0.0
        profit_h = (profit / hours) if hours > 0 else 0.0
        avg_profit = (profit / shift_count) if shift_count > 0 else 0.0

        self.a_inc.set_value(fmt_money(total_inc))
        self.a_exp.set_value(fmt_money(total_exp))
        self.a_profit.set_value(fmt_money(profit))
        self.a_shifts.set_value(str(shift_count))
        self.a_time.set_value(fmt_duration(total_sec))
        self.a_inc_h.set_value(fmt_money(inc_h))
        self.a_profit_h.set_value(fmt_money(profit_h))
        self.a_avg.set_value(fmt_money(avg_profit))

        # chart by days (if not single shift)
        labels: List[str] = []
        incs: List[float] = []
        exps: List[float] = []
        pros: List[float] = []

        if sid is None:
            dd = d_from
            while dd <= d_to:
                txt = day_key(dd)
                did0 = self.db.get_day_id_by_text(txt)
                if did0 is not None:
                    inc_d, exp_d, _ = self.db.sums_for_day(int(did0))
                else:
                    inc_d, exp_d = 0.0, 0.0
                if did is None or (self.day_pick.currentText() == txt):
                    labels.append(txt[:5])  # DD-MM
                    incs.append(inc_d)
                    exps.append(exp_d)
                    pros.append(inc_d - exp_d)
                dd += timedelta(days=1)

        if labels:
            self.chart_main.draw_bars(labels, incs, exps, pros)
        else:
            self.chart_main.clear()
            self.chart_main.ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            self.chart_main.ax.axis("off")
            self.chart_main.draw()

        pairs = sorted(expense_by_comment.items(), key=lambda x: x[1], reverse=True)[:10]
        pie_labels = [p[0] for p in pairs]
        pie_vals = [p[1] for p in pairs]
        self.chart_pie.draw_pie(pie_labels, pie_vals, "Расходы")

        self._fill_shifts_table(shifts)

    def _fill_shifts_table(self, shifts: List[sqlite3.Row]):
        self.table_shifts.setRowCount(len(shifts))
        for i, s in enumerate(shifts):
            sid = int(s["id"])
            day_txt = str(s["day_text"]) if "day_text" in s.keys() else "—"
            st = datetime.fromisoformat(str(s["started_at"]))
            en = datetime.fromisoformat(str(s["ended_at"])) if s["ended_at"] else now_local()

            inc, exp = self.db.sums_for_shift(sid)
            profit = inc - exp
            dur = int((en - st).total_seconds())

            vals = [
                day_txt,
                str(sid),
                st.strftime("%H:%M:%S"),
                en.strftime("%H:%M:%S") if s["ended_at"] else "—",
                fmt_money(inc),
                fmt_money(exp),
                fmt_money(profit),
                fmt_duration(dur),
            ]
            for c, v in enumerate(vals):
                self.table_shifts.setItem(i, c, QtWidgets.QTableWidgetItem(v))

        self.table_shifts.resizeColumnsToContents()
        self.table_ops.setRowCount(0)

    def on_shift_table_selected(self):
        items = self.table_shifts.selectedItems()
        if not items:
            return
        sid_item = self.table_shifts.item(items[0].row(), 1)
        if not sid_item:
            return
        try:
            sid = int(sid_item.text())
        except Exception:
            return

        ops = self.db.list_ops_for_shift(sid)
        self.table_ops.setRowCount(len(ops))
        for i, o in enumerate(ops):
            ts = datetime.fromisoformat(str(o["ts"])).strftime("%H:%M:%S")
            kind = "Доход" if o["kind"] == "IN" else "Расход"
            amt = fmt_money(float(o["amount"]))
            com = str(o["comment"])
            self.table_ops.setItem(i, 0, QtWidgets.QTableWidgetItem(ts))
            self.table_ops.setItem(i, 1, QtWidgets.QTableWidgetItem(kind))
            self.table_ops.setItem(i, 2, QtWidgets.QTableWidgetItem(amt))
            self.table_ops.setItem(i, 3, QtWidgets.QTableWidgetItem(com))
        self.table_ops.resizeColumnsToContents()

    # ------------------------- Settings / hotkeys UI -------------------------

    def reload_hotkeys_labels(self):
        self.hk_toggle_lbl.setText(self.db.get_setting("hotkey_toggle") or "—")
        self.hk_income_lbl.setText(self.db.get_setting("hotkey_quick_income") or "—")
        self.hk_expense_lbl.setText(self.db.get_setting("hotkey_quick_expense") or "—")
        self.hk_shot_lbl.setText(self.db.get_setting("hotkey_screenshot") or "—")

    def change_hotkey(self, setting_key: str):
        current = self.db.get_setting(setting_key) or ""
        dlg = HotkeyCaptureDialog(current, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_hotkey:
            self.db.set_setting(setting_key, dlg.result_hotkey)
            self.reload_hotkeys_labels()
            self.restart_hotkeys_from_settings()
            self.toast("Хоткей сохранён: " + dlg.result_hotkey)

    # ------------------------- Data refresh -------------------------

    def reload_state_from_db(self):
        days = self.db.list_days_desc()
        if days:
            if self.db.get_day_id_by_text(self.current_day_text) is None:
                self.current_day_text = days[0][1]
        else:
            self.current_day_text = day_key(date.today())
            self.db.ensure_day(date.today())

        self.lbl_day.setText(self.current_day_text)

        active = self.db.get_active_shift()
        self.active_shift_id = int(active["id"]) if active else None

        self.refresh_shift_ui()
        self.refresh_analytics_filters()
        self.refresh_analytics()
        self.reload_hotkeys_labels()

    def refresh_shift_summary_only(self):
        active = self.db.get_active_shift()
        if not active:
            if self.active_shift_id is not None:
                self.reload_state_from_db()
            return

        sid = int(active["id"])
        inc, exp = self.db.sums_for_shift(sid)
        profit = inc - exp
        st = datetime.fromisoformat(str(active["started_at"]))
        dur = int((now_local() - st).total_seconds())

        self.card_status.set_value(f"Активна • #{sid}", "Shift")
        self.card_inc.set_value(fmt_money(inc))
        self.card_exp.set_value(fmt_money(exp))
        self.card_profit.set_value(fmt_money(profit))
        self.card_time.set_value(fmt_duration(dur))

    def refresh_shift_ui(self):
        active = self.db.get_active_shift()
        if not active:
            self.card_status.set_value("Нет активной", "Shift")
            self.card_inc.set_value("0")
            self.card_exp.set_value("0")
            self.card_profit.set_value("0")
            self.card_time.set_value("0с")
            self.btn_start_shift.setEnabled(True)
            self.btn_end_shift.setEnabled(False)
            self.ops_table.setRowCount(0)
            return

        sid = int(active["id"])
        inc, exp = self.db.sums_for_shift(sid)
        profit = inc - exp
        st = datetime.fromisoformat(str(active["started_at"]))
        dur = int((now_local() - st).total_seconds())

        self.card_status.set_value(f"Активна • #{sid}", "Shift")
        self.card_inc.set_value(fmt_money(inc))
        self.card_exp.set_value(fmt_money(exp))
        self.card_profit.set_value(fmt_money(profit))
        self.card_time.set_value(fmt_duration(dur))

        self.btn_start_shift.setEnabled(False)
        self.btn_end_shift.setEnabled(True)

        ops = self.db.list_ops_for_shift(sid)
        self.ops_table.setRowCount(len(ops))
        for i, r in enumerate(ops):
            ts = datetime.fromisoformat(str(r["ts"])).strftime("%H:%M:%S")
            kind = "Доход" if r["kind"] == "IN" else "Расход"
            amt = fmt_money(float(r["amount"]))
            com = str(r["comment"])
            self.ops_table.setItem(i, 0, QtWidgets.QTableWidgetItem(ts))
            self.ops_table.setItem(i, 1, QtWidgets.QTableWidgetItem(kind))
            self.ops_table.setItem(i, 2, QtWidgets.QTableWidgetItem(amt))
            self.ops_table.setItem(i, 3, QtWidgets.QTableWidgetItem(com))
        self.ops_table.resizeColumnsToContents()

    # ------------------------- UX helpers -------------------------

    def toast(self, msg: str, error: bool = False):
        self.status.showMessage(msg, 3500)
        if error:
            QtWidgets.QApplication.beep()

    def closeEvent(self, e: QtGui.QCloseEvent):
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        super().closeEvent(e)


# ------------------------------- Entry -------------------------------

def main():
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    db = DB(DB_FILE)
    w = MainWindow(db)

    screen = app.primaryScreen().availableGeometry()
    w.resize(1060, 680)
    w.move(screen.center() - w.rect().center())

    w.show()
    w.raise_()
    w.activateWindow()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
