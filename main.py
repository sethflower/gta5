"""
Калькулятор таксиста (Desktop / Overlay) — Modern Premium UI (один файл .py)

Требуется: PySide6
pip install PySide6
python taxi_calculator.py

Обновления по вашим правкам:
✅ Анимация кнопок — ТОЛЬКО при наведении (hover), а не всегда
✅ Нижняя панель: "За всё время" + Доход / Расход / Чистая прибыль
✅ Меньше подсказок (софт не «болтает»)
✅ Операции смены — более профессиональный/удобный вывод (карточки, структура, аккуратные акценты)
✅ Комментарий: есть пункт "Другое (ввести вручную)" (нельзя удалить в настройках)
   - если выбран "Другое..." — появляется ввод комментария (InputDialog)
✅ История — более современная подача:
   - таблица слева
   - справа “карточка деталей” (кратко и по делу)
   - двойной клик открывает окно с подробностями
✅ Шрифты/размеры/цвета — выровнены под современный UI (контраст, иерархия, меньше лишнего)

Данные сохраняются в JSON (AppData).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from PySide6.QtCore import Qt, QTimer, QStandardPaths, QSize, QRectF
from PySide6.QtGui import QFont, QAction, QCursor, QPainter, QLinearGradient, QColor, QPen
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QStackedWidget,
    QFrame,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QCheckBox,
    QSpinBox,
    QInputDialog,
    QMenu,
    QTextEdit,
    QSplitter,
)


APP_NAME = "TaxiCalculatorOverlay"
DATA_FILE = "taxi_calculator_data.json"

OTHER_COMMENT_TEXT = "Другое (ввести вручную)"
HEADER_INCOME = "Комментарий (доход)"
HEADER_EXPENSE = "Комментарий (расход)"


# ---------------------------
# Utils
# ---------------------------

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def dt_to_ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def pretty_date(ymd: str) -> str:
    try:
        d = datetime.strptime(ymd, "%Y-%m-%d").date()
        return d.strftime("%d.%m.%Y")
    except Exception:
        return ymd


def dt_to_pretty(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


def dt_to_short(dt: datetime) -> str:
    # компактнее для карточек операций
    return dt.strftime("%d.%m %H:%M")


def format_money(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def parse_amount(text: str) -> Optional[int]:
    if text is None:
        return None
    t = text.strip().replace(" ", "").replace(",", "")
    if not t:
        return None
    if t[0] == "-":
        if len(t) == 1:
            return None
        if not t[1:].isdigit():
            return None
    else:
        if not t.isdigit():
            return None
    try:
        return int(t)
    except Exception:
        return None


def amount_color(amount: int) -> str:
    return "#2EE6A6" if amount >= 0 else "#FF5B77"


def amount_soft_bg(amount: int) -> str:
    return "rgba(46,230,166,0.10)" if amount >= 0 else "rgba(255,91,119,0.12)"


# ---------------------------
# Data model
# ---------------------------

@dataclass
class Operation:
    id: str
    ts: str
    amount: int
    comment: str


@dataclass
class Shift:
    id: str
    start_ts: str
    end_ts: Optional[str]
    operations: List[Operation]


def default_comments() -> Dict[str, List[str]]:
    return {
        "income": ["Заказ", "Чаевые", "Бонус", "Доставка"],
        "expense": ["Бензин", "Штраф", "Ремонт", "Еда/Кофе"],
    }


def default_data() -> Dict[str, Any]:
    return {
        "version": 1,
        "settings": {
            "comments": default_comments(),
            "overlay_always_on_top": True,
            "overlay_opacity": 92,       # 30..100
            "overlay_frameless": False,
        },
        "shifts": [],
        "active_shift_id": None,
    }


class Storage:
    def __init__(self) -> None:
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        self.dir = Path(base) / APP_NAME
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / DATA_FILE
        self.data: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            self.data = default_data()
            self._ensure_other_comment()
            self.save()
            return self.data

        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            try:
                self.path.replace(self.path.with_suffix(".broken.json"))
            except Exception:
                pass
            self.data = default_data()
            self._ensure_other_comment()
            self.save()

        # defaults
        self.data.setdefault("settings", default_data()["settings"])
        self.data["settings"].setdefault("comments", default_comments())
        self.data["settings"]["comments"].setdefault("income", default_comments()["income"])
        self.data["settings"]["comments"].setdefault("expense", default_comments()["expense"])
        self.data.setdefault("shifts", [])
        self.data.setdefault("active_shift_id", None)

        s = self.data["settings"]
        s.setdefault("overlay_always_on_top", True)
        s.setdefault("overlay_opacity", 92)
        s.setdefault("overlay_frameless", False)

        self._ensure_other_comment()
        self.save()
        return self.data

    def _ensure_other_comment(self):
        # В настройках "Другое" не храним как обычный комментарий, но гарантируем его наличие логически.
        # Поэтому тут ничего не добавляем в списки, просто место для будущих миграций.
        pass

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def shifts(self) -> List[Shift]:
        out: List[Shift] = []
        for sd in self.data.get("shifts", []):
            ops = [Operation(**od) for od in sd.get("operations", [])]
            out.append(Shift(id=sd["id"], start_ts=sd["start_ts"], end_ts=sd.get("end_ts"), operations=ops))
        return out

    def _save_shifts(self, shifts: List[Shift]) -> None:
        self.data["shifts"] = [
            {"id": s.id, "start_ts": s.start_ts, "end_ts": s.end_ts, "operations": [asdict(op) for op in s.operations]}
            for s in shifts
        ]
        self.save()

    def get_active_shift(self) -> Shift:
        sid = self.data.get("active_shift_id")
        shifts = self.shifts()

        if sid:
            for s in shifts:
                if s.id == sid:
                    return s

        new_shift = Shift(id=str(uuid.uuid4()), start_ts=now_iso(), end_ts=None, operations=[])
        shifts.append(new_shift)
        self._save_shifts(shifts)
        self.data["active_shift_id"] = new_shift.id
        self.save()
        return new_shift

    def update_shift(self, updated: Shift) -> None:
        shifts = self.shifts()
        for i, s in enumerate(shifts):
            if s.id == updated.id:
                shifts[i] = updated
                break
        else:
            shifts.append(updated)
        self._save_shifts(shifts)

    def end_shift_and_create_new(self) -> Shift:
        current = self.get_active_shift()
        if current.end_ts is None:
            current.end_ts = now_iso()
            self.update_shift(current)

        new_shift = Shift(id=str(uuid.uuid4()), start_ts=now_iso(), end_ts=None, operations=[])
        shifts = self.shifts()
        shifts.append(new_shift)
        self._save_shifts(shifts)
        self.data["active_shift_id"] = new_shift.id
        self.save()
        return new_shift

    def reset_current_shift_operations(self) -> Shift:
        current = self.get_active_shift()
        current.operations = []
        self.update_shift(current)
        return current

    def add_operation_to_active(self, amount: int, comment: str) -> Operation:
        current = self.get_active_shift()
        op = Operation(id=str(uuid.uuid4()), ts=now_iso(), amount=amount, comment=comment)
        current.operations.append(op)
        self.update_shift(current)
        return op

    def delete_operation_from_shift(self, shift_id: str, op_id: str) -> None:
        shifts = self.shifts()
        for s in shifts:
            if s.id == shift_id:
                s.operations = [op for op in s.operations if op.id != op_id]
                self.update_shift(s)
                return

    def delete_operation_from_active(self, op_id: str) -> None:
        current = self.get_active_shift()
        current.operations = [op for op in current.operations if op.id != op_id]
        self.update_shift(current)

    def find_operation(self, op_id: str) -> Optional[Tuple[Shift, Operation]]:
        for s in self.shifts():
            for op in s.operations:
                if op.id == op_id:
                    return s, op
        return None

    def get_comments(self) -> Dict[str, List[str]]:
        return self.data["settings"]["comments"]

    def set_comments(self, income: List[str], expense: List[str]) -> None:
        self.data["settings"]["comments"]["income"] = income
        self.data["settings"]["comments"]["expense"] = expense
        self.save()

    def get_overlay_settings(self) -> Dict[str, Any]:
        return {
            "always_on_top": bool(self.data["settings"].get("overlay_always_on_top", True)),
            "opacity": int(self.data["settings"].get("overlay_opacity", 92)),
            "frameless": bool(self.data["settings"].get("overlay_frameless", False)),
        }

    def set_overlay_settings(self, always_on_top: bool, opacity: int, frameless: bool) -> None:
        self.data["settings"]["overlay_always_on_top"] = bool(always_on_top)
        self.data["settings"]["overlay_opacity"] = int(opacity)
        self.data["settings"]["overlay_frameless"] = bool(frameless)
        self.save()

    def totals_all_time(self) -> Tuple[int, int, int]:
        inc = 0
        exp = 0
        for s in self.shifts():
            for op in s.operations:
                if op.amount >= 0:
                    inc += op.amount
                else:
                    exp += (-op.amount)
        return inc, exp, inc - exp

    def reset_all_history(self) -> None:
        self.data["shifts"] = []
        self.data["active_shift_id"] = None
        self.save()


# ---------------------------
# Styling
# ---------------------------

def modern_stylesheet() -> str:
    return """
    * { font-family: "Segoe UI"; color: #EAF0FF; }
    QMainWindow, QWidget { background: #060812; }

    /* Cards */
    QFrame#Card {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #101A2E, stop:1 #090E1F);
        border: 1px solid rgba(233,240,255,0.10);
        border-radius: 18px;
    }
    QFrame#SoftCard {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(233,240,255,0.08);
        border-radius: 18px;
    }

    /* Typography */
    QLabel#Title { font-size: 18px; font-weight: 900; color: #F6F9FF; }
    QLabel#Section { font-size: 14px; font-weight: 900; color: #F6F9FF; letter-spacing: 0.2px; }
    QLabel#Muted { color: rgba(233,240,255,0.62); }
    QLabel#Kpi { font-size: 32px; font-weight: 950; letter-spacing: 0.4px; }
    QLabel#KpiSmall { font-size: 14px; font-weight: 900; letter-spacing: 0.2px; }
    QLabel#Chip {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(233,240,255,0.10);
        border-radius: 999px;
        padding: 6px 10px;
        font-weight: 900;
        color: rgba(233,240,255,0.80);
    }

    /* Inputs */
    QLineEdit, QComboBox, QSpinBox, QTextEdit {
        background: rgba(0,0,0,0.30);
        border: 1px solid rgba(233,240,255,0.12);
        border-radius: 14px;
        padding: 11px 12px;
        selection-background-color: rgba(59,130,246,0.90);
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
        border: 1px solid rgba(99,102,241,0.95);
    }
    QComboBox::drop-down { border: 0px; width: 26px; }
    QComboBox QAbstractItemView {
        background: #090E1F;
        border: 1px solid rgba(233,240,255,0.12);
        selection-background-color: rgba(59,130,246,0.75);
        outline: 0;
    }

    /* Base buttons (we paint custom on shimmer buttons) */
    QPushButton {
        border-radius: 14px;
        padding: 11px 14px;
        font-weight: 900;
    }

    /* List */
    QListWidget { background: transparent; border: 0px; }
    QListWidget::item { background: transparent; border: 0px; padding: 0px; margin: 0px; }
    QListWidget::item:selected { background: transparent; }

    /* Tabs + Tables */
    QTabWidget::pane { border: 1px solid rgba(233,240,255,0.10); border-radius: 18px; background: rgba(0,0,0,0.20); }
    QTabBar::tab {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(233,240,255,0.10);
        padding: 10px 14px;
        border-top-left-radius: 14px;
        border-top-right-radius: 14px;
        margin-right: 8px;
        font-weight: 950;
        color: rgba(233,240,255,0.86);
    }
    QTabBar::tab:selected {
        background: rgba(99,102,241,0.16);
        border: 1px solid rgba(99,102,241,0.70);
        color: #F6F9FF;
    }
    QHeaderView::section {
        background: rgba(99,102,241,0.12);
        border: 1px solid rgba(233,240,255,0.10);
        padding: 8px 10px;
        font-weight: 950;
        color: rgba(233,240,255,0.92);
    }
    QTableWidget {
        background: rgba(0,0,0,0.18);
        border: 1px solid rgba(233,240,255,0.10);
        border-radius: 16px;
        gridline-color: rgba(233,240,255,0.06);
    }
    QTableWidget::item { padding: 8px 10px; }

    QSplitter::handle { background: rgba(233,240,255,0.05); }

    /* Checkbox */
    QCheckBox { spacing: 10px; font-weight: 900; }
    QCheckBox::indicator {
        width: 18px; height: 18px;
        border-radius: 6px;
        border: 1px solid rgba(233,240,255,0.12);
        background: rgba(0,0,0,0.30);
    }
    QCheckBox::indicator:checked {
        background: rgba(99,102,241,0.90);
        border: 1px solid rgba(99,102,241,0.90);
    }
    """


# ---------------------------
# Widgets
# ---------------------------

class Card(QFrame):
    def __init__(self, soft: bool = False):
        super().__init__()
        self.setObjectName("SoftCard" if soft else "Card")


class ShimmerButton(QPushButton):
    """
    “Перелив” запускается только при наведении.
    В обычном состоянии — статичный аккуратный градиент.
    """
    def __init__(self, text: str, kind: str = "primary"):
        super().__init__(text)
        self.kind = kind  # primary / danger / neutral
        self._phase = 0.0
        self._hover = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(42)

    def enterEvent(self, event):
        self._hover = True
        self._timer.start()
        self.update()
        return super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._timer.stop()
        self.update()
        return super().leaveEvent(event)

    def _tick(self):
        self._phase += 0.020
        if self._phase > 1.0:
            self._phase -= 1.0
        self.update()

    def _palette(self):
        if self.kind == "danger":
            c1 = QColor("#B42318")
            c2 = QColor("#FF5B77")
            border = QColor(255, 100, 125, 170)
            glow = QColor(255, 91, 119, 55)
        elif self.kind == "neutral":
            c1 = QColor(90, 110, 160, 85)
            c2 = QColor(140, 165, 220, 55)
            border = QColor(233, 240, 255, 70)
            glow = QColor(233, 240, 255, 22)
        else:
            c1 = QColor("#4F46E5")  # indigo
            c2 = QColor("#60A5FA")  # blue
            border = QColor(120, 140, 255, 180)
            glow = QColor(99, 102, 241, 55)

        if not self.isEnabled():
            c1 = QColor(255, 255, 255, 26)
            c2 = QColor(255, 255, 255, 18)
            border = QColor(255, 255, 255, 40)
            glow = QColor(255, 255, 255, 0)

        return c1, c2, border, glow

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 14.0

        c1, c2, border, glow = self._palette()

        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(r.adjusted(-1.0, -1.0, 1.0, 1.0), radius, radius)

        g = QLinearGradient(r.left(), r.top(), r.right(), r.bottom())

        if self._hover and self.isEnabled():
            p = self._phase
            g.setColorAt(0.0, c1)
            g.setColorAt(max(0.0, p - 0.22), c1)
            g.setColorAt(p, QColor(min(255, c2.red() + 30), min(255, c2.green() + 30), min(255, c2.blue() + 30)))
            g.setColorAt(min(1.0, p + 0.22), c2)
            g.setColorAt(1.0, c2)
        else:
            # статичный градиент
            g.setColorAt(0.0, c1)
            g.setColorAt(1.0, c2)

        painter.setBrush(g)
        painter.drawRoundedRect(r, radius, radius)

        pen = QPen(border)
        pen.setWidthF(1.15)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(r, radius, radius)

        painter.setPen(QColor("#F6F9FF") if self.isEnabled() else QColor(233, 240, 255, 120))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())


class OperationCard(QWidget):
    """
    Более профессиональная карточка операции:
    - слева: тип (IN/OUT), дата/время, комментарий
    - справа: сумма
    """
    def __init__(self, dt_str: str, comment: str, amount: int):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(12)

        # Type chip
        typ = QLabel("IN" if amount >= 0 else "OUT")
        typ.setAlignment(Qt.AlignCenter)
        typ.setStyleSheet(
            f"""
            QLabel {{
                background: {amount_soft_bg(amount)};
                border: 1px solid {amount_color(amount)};
                color: {amount_color(amount)};
                border-radius: 10px;
                min-width: 44px;
                max-width: 44px;
                padding: 7px 0px;
                font-weight: 950;
                letter-spacing: 0.6px;
            }}
            """
        )
        outer.addWidget(typ)

        mid = QVBoxLayout()
        mid.setSpacing(4)

        line1 = QLabel(dt_str)
        line1.setObjectName("Muted")
        line1.setStyleSheet("font-weight: 950; letter-spacing: 0.15px;")
        mid.addWidget(line1)

        line2 = QLabel(comment)
        line2.setWordWrap(True)
        line2.setStyleSheet("font-weight: 950; font-size: 13px; color: rgba(246,249,255,0.95);")
        mid.addWidget(line2)

        outer.addLayout(mid, 1)

        sign = "+" if amount >= 0 else ""
        amt = QLabel(f"{sign}{format_money(amount)}")
        amt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        amt.setStyleSheet(f"font-weight: 950; font-size: 15px; color: {amount_color(amount)};")
        outer.addWidget(amt)

        self.setStyleSheet("""
            OperationCard {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(233,240,255,0.10);
                border-radius: 16px;
            }
        """)


# ---------------------------
# Dialogs
# ---------------------------

class OperationDetailsDialog(QDialog):
    def __init__(self, parent: QWidget, storage: "Storage", shift: Shift, op: Operation):
        super().__init__(parent)
        self.storage = storage
        self.shift = shift
        self.op = op

        self.setWindowTitle("Операция — детали")
        self.setModal(True)
        self.resize(520, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("Операция")
        title.setObjectName("Title")
        root.addWidget(title)

        dt = iso_to_dt(op.ts)

        form = QFormLayout()
        form.addRow("Дата и время:", QLabel(dt_to_pretty(dt)))

        a = QLabel(f"{'+' if op.amount>=0 else ''}{format_money(op.amount)}")
        a.setObjectName("KpiSmall")
        a.setStyleSheet(f"color: {amount_color(op.amount)};")
        form.addRow("Сумма:", a)

        form.addRow("Комментарий:", QLabel(op.comment))
        form.addRow("Смена (начало):", QLabel(dt_to_pretty(iso_to_dt(shift.start_ts))))
        root.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch(1)

        btn_del = ShimmerButton("Удалить", kind="danger")
        btn_close = ShimmerButton("Закрыть", kind="neutral")
        btns.addWidget(btn_del)
        btns.addWidget(btn_close)

        def do_delete():
            ans = QMessageBox.question(
                self, "Удаление", "Удалить эту операцию?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return
            self.storage.delete_operation_from_shift(self.shift.id, self.op.id)
            self.accept()

        btn_del.clicked.connect(do_delete)
        btn_close.clicked.connect(self.reject)

        root.addLayout(btns)


class ShiftDetailsDialog(QDialog):
    def __init__(self, parent: QWidget, shift: Shift):
        super().__init__(parent)
        self.shift = shift

        self.setWindowTitle("Смена — детали")
        self.setModal(True)
        self.resize(820, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        start = iso_to_dt(shift.start_ts)
        end = iso_to_dt(shift.end_ts) if shift.end_ts else None

        title = QLabel(f"Смена • {pretty_date(dt_to_ymd(start))}")
        title.setObjectName("Title")
        root.addWidget(title)

        meta = QLabel(f"Начало: {dt_to_pretty(start)}   •   Окончание: {dt_to_pretty(end) if end else '— (активна)'}")
        meta.setObjectName("Muted")
        root.addWidget(meta)

        total = sum(op.amount for op in shift.operations)
        total_lbl = QLabel(format_money(total))
        total_lbl.setObjectName("Kpi")
        total_lbl.setStyleSheet(f"color: {amount_color(total)};")
        root.addWidget(total_lbl)

        table = QTableWidget(self)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Дата/время", "Сумма", "Комментарий"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)

        ops = list(shift.operations)
        table.setRowCount(len(ops))
        for r, op in enumerate(ops):
            dt = iso_to_dt(op.ts)
            table.setItem(r, 0, QTableWidgetItem(dt_to_pretty(dt)))

            amt_item = QTableWidgetItem(format_money(op.amount))
            amt_item.setForeground(Qt.green if op.amount >= 0 else Qt.red)
            table.setItem(r, 1, amt_item)

            table.setItem(r, 2, QTableWidgetItem(op.comment))

        root.addWidget(table)

        btn = ShimmerButton("Закрыть", kind="neutral")
        btn.clicked.connect(self.accept)
        root.addWidget(btn, alignment=Qt.AlignRight)


class DayDetailsDialog(QDialog):
    def __init__(self, parent: QWidget, storage: "Storage", ymd: str):
        super().__init__(parent)
        self.storage = storage
        self.ymd = ymd

        self.setWindowTitle("День — детали")
        self.setModal(True)
        self.resize(860, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(f"День • {pretty_date(ymd)}")
        title.setObjectName("Title")
        root.addWidget(title)

        shifts = [s for s in self.storage.shifts() if dt_to_ymd(iso_to_dt(s.start_ts)) == ymd]
        shifts = sorted(shifts, key=lambda s: s.start_ts)

        day_total = sum(sum(op.amount for op in s.operations) for s in shifts)
        kpi = QLabel(format_money(day_total))
        kpi.setObjectName("Kpi")
        kpi.setStyleSheet(f"color: {amount_color(day_total)};")
        root.addWidget(kpi)

        table = QTableWidget(self)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Начало", "Оконч.", "Опер.", "Итог", "ID"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setColumnHidden(4, True)

        table.setRowCount(len(shifts))
        for r, s in enumerate(shifts):
            st = iso_to_dt(s.start_ts)
            en = iso_to_dt(s.end_ts) if s.end_ts else None
            total = sum(op.amount for op in s.operations)

            table.setItem(r, 0, QTableWidgetItem(dt_to_pretty(st)))
            table.setItem(r, 1, QTableWidgetItem(dt_to_pretty(en) if en else "—"))
            table.setItem(r, 2, QTableWidgetItem(str(len(s.operations))))

            ti = QTableWidgetItem(format_money(total))
            ti.setForeground(Qt.green if total >= 0 else Qt.red)
            table.setItem(r, 3, ti)

            table.setItem(r, 4, QTableWidgetItem(s.id))

        def open_shift():
            rr = table.currentRow()
            if rr < 0:
                return
            sid = table.item(rr, 4).text()
            for s in self.storage.shifts():
                if s.id == sid:
                    ShiftDetailsDialog(self, s).exec()
                    return

        table.doubleClicked.connect(open_shift)
        root.addWidget(table)

        btn = ShimmerButton("Закрыть", kind="neutral")
        btn.clicked.connect(self.accept)
        root.addWidget(btn, alignment=Qt.AlignRight)


# ---------------------------
# Pages
# ---------------------------

class ShiftPage(QWidget):
    def __init__(self, storage: Storage, open_history_cb, open_settings_cb):
        super().__init__()
        self.storage = storage
        self.open_history_cb = open_history_cb
        self.open_settings_cb = open_settings_cb

        self._build_ui()
        self._load_active_shift()
        self._refresh_comments_based_on_amount()
        self._refresh_all_time_bar()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # Top bar
        top = QHBoxLayout()
        top.setSpacing(10)

        brand = QLabel("🚕  Калькулятор таксиста")
        brand.setObjectName("Title")
        top.addWidget(brand)

        chip = QLabel("Overlay")
        chip.setObjectName("Chip")
        top.addWidget(chip)

        top.addStretch(1)

        self.btn_back = ShimmerButton("Свернуть", kind="neutral")
        self.btn_back.clicked.connect(self._go_back)
        top.addWidget(self.btn_back)

        self.btn_new_shift = ShimmerButton("Новая смена", kind="primary")
        self.btn_new_shift.clicked.connect(self._new_shift)
        top.addWidget(self.btn_new_shift)

        self.btn_reset = ShimmerButton("Сбросить смену", kind="danger")
        self.btn_reset.clicked.connect(self._reset_shift)
        top.addWidget(self.btn_reset)

        self.btn_history = ShimmerButton("История", kind="neutral")
        self.btn_history.clicked.connect(self.open_history_cb)
        top.addWidget(self.btn_history)

        self.btn_settings = ShimmerButton("Настройки", kind="neutral")
        self.btn_settings.clicked.connect(self.open_settings_cb)
        top.addWidget(self.btn_settings)

        root.addLayout(top)

        # Content
        content = QHBoxLayout()
        content.setSpacing(14)

        # Left column
        left_col = QVBoxLayout()
        left_col.setSpacing(14)

        add_card = Card()
        add_l = QVBoxLayout(add_card)
        add_l.setContentsMargins(16, 16, 16, 16)
        add_l.setSpacing(12)

        h = QLabel("Добавить операцию")
        h.setObjectName("Section")
        add_l.addWidget(h)

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("Сумма (например: 12 000 или -5 000)")
        self.amount_edit.textChanged.connect(self._refresh_comments_based_on_amount)
        add_l.addWidget(self.amount_edit)

        self.comment_combo = QComboBox()
        self.comment_combo.setEnabled(False)
        add_l.addWidget(self.comment_combo)

        self.btn_save = ShimmerButton("Сохранить", kind="primary")
        self.btn_save.clicked.connect(self._save_operation)
        add_l.addWidget(self.btn_save)

        left_col.addWidget(add_card)

        # KPI card
        kpi_card = Card(soft=True)
        kpi_l = QVBoxLayout(kpi_card)
        kpi_l.setContentsMargins(16, 16, 16, 16)
        kpi_l.setSpacing(8)

        t = QLabel("Итог текущей смены")
        t.setObjectName("Muted")
        kpi_l.addWidget(t)

        self.total_label_value = QLabel("0")
        self.total_label_value.setObjectName("Kpi")
        kpi_l.addWidget(self.total_label_value)

        self.shift_info = QLabel("")
        self.shift_info.setObjectName("Muted")
        kpi_l.addWidget(self.shift_info)

        left_col.addWidget(kpi_card)
        left_col.addStretch(1)

        content.addLayout(left_col, 1)

        # Right operations
        right_card = Card()
        right_l = QVBoxLayout(right_card)
        right_l.setContentsMargins(16, 16, 16, 16)
        right_l.setSpacing(12)

        ttl = QLabel("Операции смены")
        ttl.setObjectName("Section")
        right_l.addWidget(ttl)

        self.empty_hint = QLabel("Нет операций")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setObjectName("Muted")
        self.empty_hint.setStyleSheet("padding: 26px; font-weight: 900;")
        right_l.addWidget(self.empty_hint)

        self.ops_list = QListWidget()
        self.ops_list.setSpacing(10)
        self.ops_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ops_list.customContextMenuRequested.connect(self._ops_context_menu)
        self.ops_list.itemClicked.connect(self._open_operation_from_item)
        right_l.addWidget(self.ops_list)

        content.addWidget(right_card, 2)

        root.addLayout(content)

        # Bottom all-time summary bar
        bottom = Card(soft=True)
        b = QHBoxLayout(bottom)
        b.setContentsMargins(16, 12, 16, 12)
        b.setSpacing(16)

        tag = QLabel("За всё время:")
        tag.setObjectName("Muted")
        tag.setStyleSheet("font-weight: 950;")
        b.addWidget(tag)

        self.all_income = QLabel("Доход: 0")
        self.all_income.setObjectName("KpiSmall")
        self.all_income.setStyleSheet("color: #2EE6A6;")
        b.addWidget(self.all_income)

        self.all_expense = QLabel("Расход: 0")
        self.all_expense.setObjectName("KpiSmall")
        self.all_expense.setStyleSheet("color: #FF5B77;")
        b.addWidget(self.all_expense)

        b.addStretch(1)

        self.all_net = QLabel("Чистая прибыль: 0")
        self.all_net.setObjectName("KpiSmall")
        b.addWidget(self.all_net)

        root.addWidget(bottom)

    def _go_back(self):
        w = self.window()
        if isinstance(w, QMainWindow):
            w.showMinimized()

    def _load_active_shift(self):
        self.active_shift = self.storage.get_active_shift()
        self._render_shift()

    def _render_shift(self):
        s = self.active_shift
        start_dt = iso_to_dt(s.start_ts)
        end_dt = iso_to_dt(s.end_ts) if s.end_ts else None

        info = f"{pretty_date(dt_to_ymd(start_dt))} • {dt_to_pretty(start_dt)}"
        info += f" — {dt_to_pretty(end_dt)}" if end_dt else " — активна"
        self.shift_info.setText(info)

        total = sum(op.amount for op in s.operations)
        self.total_label_value.setText(format_money(total))
        self.total_label_value.setStyleSheet(f"color: {amount_color(total)};")

        self.ops_list.clear()
        if not s.operations:
            self.empty_hint.show()
            self.ops_list.hide()
            return

        self.empty_hint.hide()
        self.ops_list.show()

        for op in reversed(s.operations):
            dt = iso_to_dt(op.ts)
            widget = OperationCard(dt_to_short(dt), op.comment, op.amount)

            item = QListWidgetItem()
            item.setData(Qt.UserRole, op.id)
            item.setSizeHint(QSize(10, 78))
            self.ops_list.addItem(item)
            self.ops_list.setItemWidget(item, widget)

    def _refresh_comments_based_on_amount(self):
        amt = parse_amount(self.amount_edit.text())
        self.comment_combo.clear()
        self.comment_combo.setEnabled(False)

        if amt is None or amt == 0:
            self.comment_combo.addItem("Введите сумму")
            return

        comments = self.storage.get_comments()
        if amt > 0:
            choices = comments.get("income", [])
            self.comment_combo.addItem(HEADER_INCOME)
        else:
            choices = comments.get("expense", [])
            self.comment_combo.addItem(HEADER_EXPENSE)

        for c in choices:
            self.comment_combo.addItem(c)

        # Всегда добавляем "Другое" (ввод вручную)
        self.comment_combo.addItem(OTHER_COMMENT_TEXT)

        self.comment_combo.setEnabled(True)
        self.comment_combo.setCurrentIndex(0)

    def _save_operation(self):
        amt = parse_amount(self.amount_edit.text())
        if amt is None or amt == 0:
            QMessageBox.warning(self, "Ошибка", "Введите корректную сумму (не 0).")
            return
        if not self.comment_combo.isEnabled() or self.comment_combo.currentIndex() <= 0:
            QMessageBox.warning(self, "Ошибка", "Выберите комментарий.")
            return

        chosen = self.comment_combo.currentText().strip()
        if chosen in (HEADER_INCOME, HEADER_EXPENSE) or not chosen:
            QMessageBox.warning(self, "Ошибка", "Выберите комментарий.")
            return

        if chosen == OTHER_COMMENT_TEXT:
            text, ok = QInputDialog.getText(self, "Комментарий", "Введите комментарий:")
            if not ok:
                return
            manual = (text or "").strip()
            if not manual:
                QMessageBox.warning(self, "Ошибка", "Комментарий не может быть пустым.")
                return
            comment = manual
        else:
            comment = chosen

        self.storage.add_operation_to_active(amt, comment)
        self.active_shift = self.storage.get_active_shift()
        self._render_shift()
        self._refresh_all_time_bar()

        self.amount_edit.clear()
        self.comment_combo.setCurrentIndex(0)
        self.comment_combo.setEnabled(False)

    def _new_shift(self):
        self.storage.end_shift_and_create_new()
        self._load_active_shift()
        self.amount_edit.clear()
        self._refresh_comments_based_on_amount()
        self._refresh_all_time_bar()

    def _reset_shift(self):
        ans = QMessageBox.question(
            self,
            "Сбросить смену",
            "Удалить все операции в текущей активной смене?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        self.storage.reset_current_shift_operations()
        self._load_active_shift()
        self.amount_edit.clear()
        self._refresh_comments_based_on_amount()
        self._refresh_all_time_bar()

    def _ops_context_menu(self, pos):
        item = self.ops_list.itemAt(pos)
        if not item:
            return
        op_id = item.data(Qt.UserRole)

        menu = QMenu(self)
        act_open = QAction("Открыть детали", self)
        act_del = QAction("Удалить", self)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_del)

        act_open.triggered.connect(lambda: self._open_operation_by_id(op_id))

        def do_del():
            ans = QMessageBox.question(
                self, "Удаление", "Удалить выбранную операцию?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return
            self.storage.delete_operation_from_active(op_id)
            self.active_shift = self.storage.get_active_shift()
            self._render_shift()
            self._refresh_all_time_bar()

        act_del.triggered.connect(do_del)
        menu.exec(QCursor.pos())

    def _open_operation_from_item(self, item: QListWidgetItem):
        op_id = item.data(Qt.UserRole)
        self._open_operation_by_id(op_id)

    def _open_operation_by_id(self, op_id: str):
        found = self.storage.find_operation(op_id)
        if not found:
            QMessageBox.warning(self, "Не найдено", "Операция не найдена.")
            self._load_active_shift()
            return
        shift, op = found
        OperationDetailsDialog(self, self.storage, shift, op).exec()

        # после закрытия — обновим (вдруг удалили)
        self.active_shift = self.storage.get_active_shift()
        self._render_shift()
        self._refresh_all_time_bar()

    def _refresh_all_time_bar(self):
        inc, exp, net = self.storage.totals_all_time()
        self.all_income.setText(f"Доход: {format_money(inc)}")
        self.all_expense.setText(f"Расход: {format_money(exp)}")
        self.all_net.setText(f"Чистая прибыль: {format_money(net)}")
        self.all_net.setStyleSheet(f"color: {amount_color(net)}; font-size: 14px; font-weight: 950;")


class HistoryPage(QWidget):
    def __init__(self, storage: Storage, back_cb):
        super().__init__()
        self.storage = storage
        self.back_cb = back_cb
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        top = QHBoxLayout()
        btn_back = ShimmerButton("Назад", kind="neutral")
        btn_back.clicked.connect(self.back_cb)
        top.addWidget(btn_back)

        title = QLabel("История")
        title.setObjectName("Title")
        top.addWidget(title)
        top.addStretch(1)

        btn_refresh = ShimmerButton("Обновить", kind="neutral")
        btn_refresh.clicked.connect(self.refresh)
        top.addWidget(btn_refresh)

        root.addLayout(top)

        card = Card()
        c_l = QVBoxLayout(card)
        c_l.setContentsMargins(16, 16, 16, 16)
        c_l.setSpacing(12)

        self.tabs = QTabWidget()
        c_l.addWidget(self.tabs)

        # --- Shifts tab ---
        self.tab_shifts = QWidget()
        t1 = QHBoxLayout(self.tab_shifts)
        t1.setContentsMargins(0, 0, 0, 0)
        t1.setSpacing(12)

        sp1 = QSplitter(Qt.Horizontal)

        left_box = QWidget()
        l = QVBoxLayout(left_box)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        self.shifts_table = QTableWidget()
        self.shifts_table.setColumnCount(6)
        self.shifts_table.setHorizontalHeaderLabels(["Дата", "Начало", "Оконч.", "Опер.", "Итог", "ID"])
        self.shifts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.shifts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.shifts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.shifts_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.shifts_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.shifts_table.setColumnHidden(5, True)
        self.shifts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.shifts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.shifts_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.shifts_table.itemSelectionChanged.connect(self._render_shift_preview)
        self.shifts_table.doubleClicked.connect(self._open_selected_shift)
        l.addWidget(self.shifts_table)

        right_box = Card(soft=True)
        rr = QVBoxLayout(right_box)
        rr.setContentsMargins(14, 14, 14, 14)
        rr.setSpacing(10)

        prev_title = QLabel("Смена — детали")
        prev_title.setObjectName("Section")
        rr.addWidget(prev_title)

        self.shift_preview = QTextEdit()
        self.shift_preview.setReadOnly(True)
        self.shift_preview.setMinimumWidth(340)
        rr.addWidget(self.shift_preview)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_open_shift = ShimmerButton("Открыть", kind="primary")
        self.btn_open_shift.clicked.connect(self._open_selected_shift)
        btns.addWidget(self.btn_open_shift)
        rr.addLayout(btns)

        sp1.addWidget(left_box)
        sp1.addWidget(right_box)
        sp1.setStretchFactor(0, 3)
        sp1.setStretchFactor(1, 2)

        t1.addWidget(sp1)
        self.tabs.addTab(self.tab_shifts, "Смены")

        # --- Days tab ---
        self.tab_days = QWidget()
        t2 = QHBoxLayout(self.tab_days)
        t2.setContentsMargins(0, 0, 0, 0)
        t2.setSpacing(12)

        sp2 = QSplitter(Qt.Horizontal)

        left2 = QWidget()
        l2 = QVBoxLayout(left2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(10)

        self.days_table = QTableWidget()
        self.days_table.setColumnCount(4)
        self.days_table.setHorizontalHeaderLabels(["Дата", "Смен", "Итог дня", "YMD"])
        self.days_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.days_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.days_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.days_table.setColumnHidden(3, True)
        self.days_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.days_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.days_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.days_table.itemSelectionChanged.connect(self._render_day_preview)
        self.days_table.doubleClicked.connect(self._open_selected_day)
        l2.addWidget(self.days_table)

        right2 = Card(soft=True)
        r2 = QVBoxLayout(right2)
        r2.setContentsMargins(14, 14, 14, 14)
        r2.setSpacing(10)

        prev2 = QLabel("День — детали")
        prev2.setObjectName("Section")
        r2.addWidget(prev2)

        self.day_preview = QTextEdit()
        self.day_preview.setReadOnly(True)
        self.day_preview.setMinimumWidth(340)
        r2.addWidget(self.day_preview)

        btns2 = QHBoxLayout()
        btns2.addStretch(1)
        self.btn_open_day = ShimmerButton("Открыть", kind="primary")
        self.btn_open_day.clicked.connect(self._open_selected_day)
        btns2.addWidget(self.btn_open_day)
        r2.addLayout(btns2)

        sp2.addWidget(left2)
        sp2.addWidget(right2)
        sp2.setStretchFactor(0, 3)
        sp2.setStretchFactor(1, 2)

        t2.addWidget(sp2)
        self.tabs.addTab(self.tab_days, "Дни")

        root.addWidget(card)

    def refresh(self):
        shifts = sorted(self.storage.shifts(), key=lambda s: s.start_ts, reverse=True)

        self.shifts_table.setRowCount(len(shifts))
        for r, s in enumerate(shifts):
            start_dt = iso_to_dt(s.start_ts)
            end_dt = iso_to_dt(s.end_ts) if s.end_ts else None
            total = sum(op.amount for op in s.operations)

            self.shifts_table.setItem(r, 0, QTableWidgetItem(pretty_date(dt_to_ymd(start_dt))))
            self.shifts_table.setItem(r, 1, QTableWidgetItem(dt_to_pretty(start_dt)))
            self.shifts_table.setItem(r, 2, QTableWidgetItem(dt_to_pretty(end_dt) if end_dt else "—"))
            self.shifts_table.setItem(r, 3, QTableWidgetItem(str(len(s.operations))))

            total_item = QTableWidgetItem(format_money(total))
            total_item.setForeground(Qt.green if total >= 0 else Qt.red)
            self.shifts_table.setItem(r, 4, total_item)

            it_id = QTableWidgetItem(s.id)
            self.shifts_table.setItem(r, 5, it_id)

        if self.shifts_table.rowCount() > 0:
            self.shifts_table.selectRow(0)
        else:
            self.shift_preview.setPlainText("Нет смен.")

        # days aggregation
        day_map: Dict[str, Dict[str, int]] = {}
        for s in shifts:
            ymd = dt_to_ymd(iso_to_dt(s.start_ts))
            day_map.setdefault(ymd, {"shifts": 0, "total": 0, "ops": 0})
            day_map[ymd]["shifts"] += 1
            day_map[ymd]["total"] += sum(op.amount for op in s.operations)
            day_map[ymd]["ops"] += len(s.operations)

        days_sorted = sorted(day_map.items(), key=lambda kv: kv[0], reverse=True)
        self.days_table.setRowCount(len(days_sorted))
        for r, (ymd, info) in enumerate(days_sorted):
            self.days_table.setItem(r, 0, QTableWidgetItem(pretty_date(ymd)))
            self.days_table.setItem(r, 1, QTableWidgetItem(str(info["shifts"])))

            tot = info["total"]
            tot_item = QTableWidgetItem(format_money(tot))
            tot_item.setForeground(Qt.green if tot >= 0 else Qt.red)
            self.days_table.setItem(r, 2, tot_item)

            self.days_table.setItem(r, 3, QTableWidgetItem(ymd))

        if self.days_table.rowCount() > 0:
            self.days_table.selectRow(0)
        else:
            self.day_preview.setPlainText("Нет данных по дням.")

    def _selected_shift_id(self) -> Optional[str]:
        r = self.shifts_table.currentRow()
        if r < 0:
            return None
        it = self.shifts_table.item(r, 5)
        return it.text() if it else None

    def _selected_day_ymd(self) -> Optional[str]:
        r = self.days_table.currentRow()
        if r < 0:
            return None
        it = self.days_table.item(r, 3)
        return it.text() if it else None

    def _render_shift_preview(self):
        sid = self._selected_shift_id()
        if not sid:
            self.shift_preview.setPlainText("Выберите смену.")
            return

        for s in self.storage.shifts():
            if s.id == sid:
                start = iso_to_dt(s.start_ts)
                end = iso_to_dt(s.end_ts) if s.end_ts else None
                total = sum(op.amount for op in s.operations)

                # 6 последних операций
                ops = list(reversed(s.operations))[:6]
                lines = []
                for op in ops:
                    dt = iso_to_dt(op.ts)
                    sign = "+" if op.amount >= 0 else ""
                    lines.append(f"• {dt_to_pretty(dt)}   {sign}{format_money(op.amount)}   — {op.comment}")
                if not lines:
                    lines = ["— операций нет"]

                txt = (
                    f"Дата: {pretty_date(dt_to_ymd(start))}\n"
                    f"Начало: {dt_to_pretty(start)}\n"
                    f"Окончание: {dt_to_pretty(end) if end else '— (активна)'}\n"
                    f"Операций: {len(s.operations)}\n"
                    f"Итог: {format_money(total)}\n\n"
                    "Последние операции:\n" + "\n".join(lines)
                )
                self.shift_preview.setPlainText(txt)
                return

        self.shift_preview.setPlainText("Смена не найдена.")

    def _render_day_preview(self):
        ymd = self._selected_day_ymd()
        if not ymd:
            self.day_preview.setPlainText("Выберите день.")
            return

        shifts = [s for s in self.storage.shifts() if dt_to_ymd(iso_to_dt(s.start_ts)) == ymd]
        shifts = sorted(shifts, key=lambda s: s.start_ts)

        day_total = sum(sum(op.amount for op in s.operations) for s in shifts)
        ops_total = sum(len(s.operations) for s in shifts)

        # 8 смен в превью
        lines = []
        for s in shifts[:8]:
            st = iso_to_dt(s.start_ts)
            en = iso_to_dt(s.end_ts) if s.end_ts else None
            tot = sum(op.amount for op in s.operations)
            lines.append(f"• {dt_to_pretty(st)} — {dt_to_pretty(en) if en else '—'}   |   опер.: {len(s.operations)}   |   итог: {format_money(tot)}")
        if not lines:
            lines = ["— смен нет"]
        if len(shifts) > 8:
            lines.append(f"… и ещё {len(shifts)-8} смен(ы).")

        txt = (
            f"День: {pretty_date(ymd)}\n"
            f"Смен: {len(shifts)}\n"
            f"Операций: {ops_total}\n"
            f"Итог дня: {format_money(day_total)}\n\n"
            "Смены:\n" + "\n".join(lines)
        )
        self.day_preview.setPlainText(txt)

    def _open_selected_shift(self):
        sid = self._selected_shift_id()
        if not sid:
            return
        for s in self.storage.shifts():
            if s.id == sid:
                ShiftDetailsDialog(self, s).exec()
                return

    def _open_selected_day(self):
        ymd = self._selected_day_ymd()
        if not ymd:
            return
        DayDetailsDialog(self, self.storage, ymd).exec()


class SettingsPage(QWidget):
    def __init__(self, storage: Storage, back_cb, apply_overlay_cb, after_reset_cb):
        super().__init__()
        self.storage = storage
        self.back_cb = back_cb
        self.apply_overlay_cb = apply_overlay_cb
        self.after_reset_cb = after_reset_cb
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        top = QHBoxLayout()
        btn_back = ShimmerButton("Назад", kind="neutral")
        btn_back.clicked.connect(self.back_cb)
        top.addWidget(btn_back)

        title = QLabel("Настройки")
        title.setObjectName("Title")
        top.addWidget(title)
        top.addStretch(1)

        btn_save = ShimmerButton("Сохранить", kind="primary")
        btn_save.clicked.connect(self.save_settings)
        top.addWidget(btn_save)

        root.addLayout(top)

        card = Card()
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 16, 16, 16)
        c.setSpacing(14)

        # Comments
        comm_title = QLabel("Шаблоны комментариев")
        comm_title.setObjectName("Section")
        c.addWidget(comm_title)

        split = QHBoxLayout()
        split.setSpacing(14)

        income_box = Card(soft=True)
        il = QVBoxLayout(income_box)
        il.setContentsMargins(14, 14, 14, 14)
        il.setSpacing(10)

        il.addWidget(self._section_header("Доходы"))
        self.income_list = QListWidget()
        il.addWidget(self.income_list)

        ibtns = QHBoxLayout()
        self.btn_income_add = ShimmerButton("Добавить", kind="neutral")
        self.btn_income_rename = ShimmerButton("Переименовать", kind="neutral")
        self.btn_income_del = ShimmerButton("Удалить", kind="danger")
        ibtns.addWidget(self.btn_income_add)
        ibtns.addWidget(self.btn_income_rename)
        ibtns.addWidget(self.btn_income_del)
        il.addLayout(ibtns)

        self.btn_income_add.clicked.connect(lambda: self._add_comment(True))
        self.btn_income_rename.clicked.connect(lambda: self._rename_comment(True))
        self.btn_income_del.clicked.connect(lambda: self._delete_comment(True))

        expense_box = Card(soft=True)
        el = QVBoxLayout(expense_box)
        el.setContentsMargins(14, 14, 14, 14)
        el.setSpacing(10)

        el.addWidget(self._section_header("Расходы"))
        self.expense_list = QListWidget()
        el.addWidget(self.expense_list)

        ebtns = QHBoxLayout()
        self.btn_exp_add = ShimmerButton("Добавить", kind="neutral")
        self.btn_exp_rename = ShimmerButton("Переименовать", kind="neutral")
        self.btn_exp_del = ShimmerButton("Удалить", kind="danger")
        ebtns.addWidget(self.btn_exp_add)
        ebtns.addWidget(self.btn_exp_rename)
        ebtns.addWidget(self.btn_exp_del)
        el.addLayout(ebtns)

        self.btn_exp_add.clicked.connect(lambda: self._add_comment(False))
        self.btn_exp_rename.clicked.connect(lambda: self._rename_comment(False))
        self.btn_exp_del.clicked.connect(lambda: self._delete_comment(False))

        split.addWidget(income_box, 1)
        split.addWidget(expense_box, 1)
        c.addLayout(split)

        # Note about OTHER
        note = QLabel(f"Примечание: пункт «{OTHER_COMMENT_TEXT}» всегда доступен и не удаляется.")
        note.setObjectName("Muted")
        c.addWidget(note)

        # Overlay settings
        overlay_title = QLabel("Оверлей")
        overlay_title.setObjectName("Section")
        c.addWidget(overlay_title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft)

        self.chk_on_top = QCheckBox("Всегда поверх окон (always-on-top)")
        self.chk_frameless = QCheckBox("Без рамки окна (frameless)")
        self.spn_opacity = QSpinBox()
        self.spn_opacity.setRange(30, 100)
        self.spn_opacity.setSuffix(" %")

        form.addRow(self.chk_on_top)
        form.addRow(self.chk_frameless)
        form.addRow("Прозрачность:", self.spn_opacity)
        c.addLayout(form)

        # Full reset
        danger_card = Card(soft=True)
        dl = QVBoxLayout(danger_card)
        dl.setContentsMargins(14, 14, 14, 14)
        dl.setSpacing(10)

        dtitle = QLabel("Сброс данных")
        dtitle.setObjectName("Section")
        dl.addWidget(dtitle)

        self.btn_reset_all = ShimmerButton("Удалить всю историю (за все периоды)", kind="danger")
        self.btn_reset_all.clicked.connect(self._reset_all)
        dl.addWidget(self.btn_reset_all)

        c.addWidget(danger_card)

        root.addWidget(card)

    def _section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Section")
        return lbl

    def refresh(self):
        comm = self.storage.get_comments()
        self.income_list.clear()
        self.expense_list.clear()
        for x in comm.get("income", []):
            self.income_list.addItem(x)
        for x in comm.get("expense", []):
            self.expense_list.addItem(x)

        o = self.storage.get_overlay_settings()
        self.chk_on_top.setChecked(o["always_on_top"])
        self.chk_frameless.setChecked(o["frameless"])
        self.spn_opacity.setValue(o["opacity"])

    def save_settings(self):
        income = [self.income_list.item(i).text().strip() for i in range(self.income_list.count())]
        expense = [self.expense_list.item(i).text().strip() for i in range(self.expense_list.count())]
        income = [x for x in income if x and x != OTHER_COMMENT_TEXT]
        expense = [x for x in expense if x and x != OTHER_COMMENT_TEXT]

        if not income:
            income = default_comments()["income"][:]
        if not expense:
            expense = default_comments()["expense"][:]

        self.storage.set_comments(income, expense)
        self.storage.set_overlay_settings(
            always_on_top=self.chk_on_top.isChecked(),
            opacity=self.spn_opacity.value(),
            frameless=self.chk_frameless.isChecked(),
        )
        self.apply_overlay_cb()
        QMessageBox.information(self, "Сохранено", "Настройки сохранены.")

    def _add_comment(self, is_income: bool):
        title = "Добавить (доход)" if is_income else "Добавить (расход)"
        text, ok = QInputDialog.getText(self, title, "Комментарий:")
        if not ok:
            return
        t = (text or "").strip()
        if not t:
            return
        if t == OTHER_COMMENT_TEXT:
            QMessageBox.warning(self, "Нельзя", f"«{OTHER_COMMENT_TEXT}» добавлять/удалять не нужно — он встроенный.")
            return

        lst = self.income_list if is_income else self.expense_list
        for i in range(lst.count()):
            if lst.item(i).text().strip().lower() == t.lower():
                QMessageBox.warning(self, "Дубликат", "Такой комментарий уже существует.")
                return
        lst.addItem(t)

    def _rename_comment(self, is_income: bool):
        lst = self.income_list if is_income else self.expense_list
        item = lst.currentItem()
        if not item:
            QMessageBox.warning(self, "Выбор", "Выберите комментарий.")
            return
        old = item.text()
        if old == OTHER_COMMENT_TEXT:
            QMessageBox.warning(self, "Нельзя", f"«{OTHER_COMMENT_TEXT}» нельзя переименовать.")
            return

        title = "Переименовать (доход)" if is_income else "Переименовать (расход)"
        text, ok = QInputDialog.getText(self, title, "Новое название:", text=old)
        if not ok:
            return
        t = (text or "").strip()
        if not t:
            return
        if t == OTHER_COMMENT_TEXT:
            QMessageBox.warning(self, "Нельзя", f"«{OTHER_COMMENT_TEXT}» — встроенный пункт.")
            return
        item.setText(t)

    def _delete_comment(self, is_income: bool):
        lst = self.income_list if is_income else self.expense_list
        item = lst.currentItem()
        if not item:
            QMessageBox.warning(self, "Выбор", "Выберите комментарий.")
            return
        if item.text() == OTHER_COMMENT_TEXT:
            QMessageBox.warning(self, "Нельзя", f"«{OTHER_COMMENT_TEXT}» нельзя удалить.")
            return

        ans = QMessageBox.question(
            self, "Удаление", f"Удалить комментарий:\n\n{item.text()}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ans != QMessageBox.Yes:
            return
        lst.takeItem(lst.row(item))

    def _reset_all(self):
        ans = QMessageBox.question(
            self,
            "Полный сброс",
            "Удалить ВСЮ историю смен и операций?\nЭто действие нельзя отменить.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        text, ok = QInputDialog.getText(self, "Подтверждение", "Введите слово: СБРОС")
        if not ok:
            return
        if (text or "").strip().upper() != "СБРОС":
            QMessageBox.warning(self, "Отменено", "Неверное подтверждение.")
            return

        self.storage.reset_all_history()
        QMessageBox.information(self, "Готово", "История удалена.")
        self.after_reset_cb()


# ---------------------------
# Main window
# ---------------------------

class MainWindow(QMainWindow):
    def __init__(self, storage: Storage):
        super().__init__()
        self.storage = storage

        self.setWindowTitle("Калькулятор таксиста")
        self.resize(1120, 720)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.shift_page = ShiftPage(storage, open_history_cb=self.open_history, open_settings_cb=self.open_settings)
        self.history_page = HistoryPage(storage, back_cb=self.open_shift)
        self.settings_page = SettingsPage(
            storage,
            back_cb=self.open_shift,
            apply_overlay_cb=self.apply_overlay_settings,
            after_reset_cb=self._after_full_reset,
        )

        self.stack.addWidget(self.shift_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.settings_page)

        self.open_shift()
        self.apply_overlay_settings()

    def open_shift(self):
        self.stack.setCurrentWidget(self.shift_page)
        self.shift_page._load_active_shift()
        self.shift_page._refresh_comments_based_on_amount()
        self.shift_page._refresh_all_time_bar()

    def open_history(self):
        self.history_page.refresh()
        self.stack.setCurrentWidget(self.history_page)

    def open_settings(self):
        self.settings_page.refresh()
        self.stack.setCurrentWidget(self.settings_page)

    def apply_overlay_settings(self):
        o = self.storage.get_overlay_settings()

        flags = Qt.Window
        if o["always_on_top"]:
            flags |= Qt.WindowStaysOnTopHint
        if o["frameless"]:
            flags |= Qt.FramelessWindowHint

        self.setWindowFlags(flags)
        self.setWindowOpacity(max(0.30, min(1.0, o["opacity"] / 100.0)))
        self.show()

    def _after_full_reset(self):
        self.open_shift()


# ---------------------------
# Entry
# ---------------------------

def main():
    app = QApplication([])
    app.setStyleSheet(modern_stylesheet())

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    storage = Storage()
    storage.load()

    w = MainWindow(storage)
    w.show()

    app.exec()


if __name__ == "__main__":
    main()
