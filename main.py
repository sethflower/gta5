#!/usr/bin/env python3
"""
Калькулятор таксиста — Premium Edition
Профессиональное корпоративное приложение

Требуется: PySide6
pip install PySide6
python taxi_calculator.py
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from PySide6.QtCore import Qt, QTimer, QStandardPaths, QSize, QRectF, Signal, QEvent
from PySide6.QtGui import QFont, QAction, QCursor, QPainter, QLinearGradient, QColor, QPen, QKeyEvent
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
    QMessageBox,
    QStackedWidget,
    QFrame,
    QDialog,
    QCheckBox,
    QSpinBox,
    QInputDialog,
    QMenu,
    QScrollArea,
)


APP_NAME = "TaxiCalculatorPremium"
DATA_FILE = "taxi_calculator_data.json"

OTHER_COMMENT_TEXT = "Другое (ввести вручную)"


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


def dt_to_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


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


# ---------------------------
# Colors
# ---------------------------

class Colors:
    BG_DARK = "#0A0E1A"
    BG_CARD = "rgba(255,255,255,0.03)"
    BG_CARD_HOVER = "rgba(255,255,255,0.05)"
    BORDER = "rgba(255,255,255,0.08)"
    BORDER_ACCENT = "rgba(124,58,237,0.5)"
    
    TEXT_PRIMARY = "#F7FAFF"
    TEXT_SECONDARY = "rgba(232,236,246,0.7)"
    TEXT_MUTED = "rgba(232,236,246,0.5)"
    
    ACCENT_VIOLET = "#7C3AED"
    ACCENT_CYAN = "#22D3EE"
    
    SUCCESS = "#2EE6A6"
    SUCCESS_BG = "rgba(46,230,166,0.12)"
    SUCCESS_BORDER = "rgba(46,230,166,0.4)"
    
    DANGER = "#FF5B77"
    DANGER_BG = "rgba(255,91,119,0.12)"
    DANGER_BORDER = "rgba(255,91,119,0.4)"
    
    INFO = "#60A5FA"
    INFO_BG = "rgba(96,165,250,0.12)"
    INFO_BORDER = "rgba(96,165,250,0.4)"

    @staticmethod
    def amount_color(amount: int) -> str:
        return Colors.SUCCESS if amount >= 0 else Colors.DANGER

    @staticmethod
    def amount_bg(amount: int) -> str:
        return Colors.SUCCESS_BG if amount >= 0 else Colors.DANGER_BG

    @staticmethod
    def amount_border(amount: int) -> str:
        return Colors.SUCCESS_BORDER if amount >= 0 else Colors.DANGER_BORDER


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
    
    def income(self) -> int:
        return sum(op.amount for op in self.operations if op.amount > 0)
    
    def expense(self) -> int:
        return sum(-op.amount for op in self.operations if op.amount < 0)
    
    def total(self) -> int:
        return sum(op.amount for op in self.operations)


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
            "overlay_opacity": 95,
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
            self.save()
            return self.data

        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = default_data()
            self.save()

        self.data.setdefault("settings", default_data()["settings"])
        self.data["settings"].setdefault("comments", default_comments())
        self.data.setdefault("shifts", [])
        self.data.setdefault("active_shift_id", None)

        s = self.data["settings"]
        s.setdefault("overlay_always_on_top", True)
        s.setdefault("overlay_opacity", 95)
        s.setdefault("overlay_frameless", False)

        self.save()
        return self.data

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
            "opacity": int(self.data["settings"].get("overlay_opacity", 95)),
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

def get_stylesheet() -> str:
    return f"""
    * {{
        font-family: "Segoe UI", "Inter", system-ui, sans-serif;
        color: {Colors.TEXT_PRIMARY};
    }}
    
    QMainWindow, QWidget, QDialog {{
        background: {Colors.BG_DARK};
    }}
    
    QLabel {{
        background: transparent;
        border: none;
        padding: 0px;
        margin: 0px;
    }}
    
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    
    QScrollBar:vertical {{
        background: rgba(255,255,255,0.02);
        width: 8px;
        border-radius: 4px;
        margin: 2px;
    }}
    
    QScrollBar::handle:vertical {{
        background: rgba(124,58,237,0.4);
        border-radius: 4px;
        min-height: 30px;
    }}
    
    QScrollBar::handle:vertical:hover {{
        background: rgba(124,58,237,0.6);
    }}
    
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    
    QScrollBar:horizontal {{
        background: rgba(255,255,255,0.02);
        height: 8px;
        border-radius: 4px;
        margin: 2px;
    }}
    
    QScrollBar::handle:horizontal {{
        background: rgba(124,58,237,0.4);
        border-radius: 4px;
        min-width: 30px;
    }}
    
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    
    QLineEdit, QComboBox, QSpinBox {{
        background: rgba(255,255,255,0.04);
        border: 1px solid {Colors.BORDER};
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 14px;
        font-weight: 500;
        min-height: 20px;
    }}
    
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {Colors.BORDER_ACCENT};
        background: rgba(255,255,255,0.05);
    }}
    
    QComboBox::drop-down {{
        border: none;
        width: 30px;
    }}
    
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {Colors.TEXT_SECONDARY};
        margin-right: 10px;
    }}
    
    QComboBox QAbstractItemView {{
        background: #12162B;
        border: 1px solid {Colors.BORDER};
        border-radius: 12px;
        padding: 6px;
        selection-background-color: rgba(124,58,237,0.3);
        outline: none;
    }}
    
    QListWidget {{
        background: transparent;
        border: none;
        outline: none;
    }}
    
    QListWidget::item {{
        background: transparent;
        border: none;
        padding: 4px 0px;
    }}
    
    QListWidget::item:selected {{
        background: transparent;
    }}
    
    QCheckBox {{
        spacing: 10px;
        font-weight: 600;
        background: transparent;
    }}
    
    QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 6px;
        border: 2px solid {Colors.BORDER};
        background: rgba(0,0,0,0.2);
    }}
    
    QCheckBox::indicator:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {Colors.ACCENT_VIOLET}, stop:1 {Colors.ACCENT_CYAN});
        border: none;
    }}
    
    QMessageBox {{
        background: {Colors.BG_DARK};
    }}
    
    QMessageBox QLabel {{
        color: {Colors.TEXT_PRIMARY};
        font-size: 14px;
        background: transparent;
    }}
    
    QMessageBox QPushButton {{
        min-width: 80px;
        padding: 8px 16px;
    }}
    
    QFrame {{
        background: transparent;
        border: none;
    }}
    """


# ---------------------------
# Custom Widgets
# ---------------------------

class GlassCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_style()
        
    def _setup_style(self):
        self.setStyleSheet(f"""
            GlassCard {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 16px;
            }}
        """)


class AccentCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_style()
        
    def _setup_style(self):
        self.setStyleSheet(f"""
            AccentCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(124,58,237,0.15), stop:1 rgba(34,211,238,0.08));
                border: 1px solid {Colors.BORDER_ACCENT};
                border-radius: 20px;
            }}
        """)


class ShimmerButton(QPushButton):
    def __init__(self, text: str, kind: str = "primary", parent=None):
        super().__init__(text, parent)
        self.kind = kind
        self._phase = 0.0
        self._hover = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setFont(QFont("Segoe UI", 10, QFont.Bold))

    def enterEvent(self, event):
        self._hover = True
        self._timer.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._timer.stop()
        self.update()
        super().leaveEvent(event)

    def _tick(self):
        self._phase += 0.018
        if self._phase > 1.0:
            self._phase -= 1.0
        self.update()

    def _get_colors(self):
        if self.kind == "danger":
            c1 = QColor("#F43F5E")
            c2 = QColor("#DC2626")
            border = QColor(255, 100, 130, 180)
        elif self.kind == "neutral":
            c1 = QColor(70, 85, 120)
            c2 = QColor(90, 110, 150)
            border = QColor(140, 160, 200, 100)
        else:
            c1 = QColor("#7C3AED")
            c2 = QColor("#22D3EE")
            border = QColor(140, 120, 255, 180)

        if not self.isEnabled():
            c1 = QColor(60, 60, 80)
            c2 = QColor(50, 50, 70)
            border = QColor(100, 100, 120, 60)

        return c1, c2, border

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 12.0

        c1, c2, border = self._get_colors()

        g = QLinearGradient(r.left(), r.top(), r.right(), r.bottom())
        
        if self._hover and self.isEnabled():
            p = self._phase
            g.setColorAt(0.0, c1)
            g.setColorAt(max(0.0, p - 0.25), c1)
            g.setColorAt(p, QColor(min(255, c2.red() + 40), min(255, c2.green() + 40), min(255, c2.blue() + 40)))
            g.setColorAt(min(1.0, p + 0.25), c2)
            g.setColorAt(1.0, c2)
        else:
            g.setColorAt(0.0, c1)
            g.setColorAt(1.0, c2)

        painter.setPen(Qt.NoPen)
        painter.setBrush(g)
        painter.drawRoundedRect(r, radius, radius)

        pen = QPen(border)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(r, radius, radius)

        painter.setPen(QColor("#FFFFFF") if self.isEnabled() else QColor(180, 180, 200))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())


class MetricCard(QWidget):
    def __init__(self, icon: str, label: str, value: str, color: str = None, parent=None):
        super().__init__(parent)
        self._color = color
        self._setup_ui(icon, label, value, color)
        
    def _setup_ui(self, icon: str, label: str, value: str, color: str):
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            MetricCard {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 14px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        
        header = QHBoxLayout()
        header.setSpacing(8)
        
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 18px; background: transparent;")
        header.addWidget(icon_label)
        
        title = QLabel(label)
        title.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px; font-weight: 600; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        
        layout.addLayout(header)
        
        self.value_label = QLabel(value)
        value_color = color or Colors.TEXT_PRIMARY
        self.value_label.setStyleSheet(f"color: {value_color}; font-size: 22px; font-weight: 800; background: transparent;")
        layout.addWidget(self.value_label)
        
    def set_value(self, value: str, color: str = None):
        self.value_label.setText(value)
        if color:
            self._color = color
            self.value_label.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 800; background: transparent;")


class OperationItem(QWidget):
    clicked = Signal(str)
    
    def __init__(self, op_id: str, time_str: str, comment: str, amount: int, parent=None):
        super().__init__(parent)
        self.op_id = op_id
        self._setup_ui(time_str, comment, amount)
        
    def _setup_ui(self, time_str: str, comment: str, amount: int):
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        color = Colors.amount_color(amount)
        bg = Colors.amount_bg(amount)
        border_color = Colors.amount_border(amount)
        
        self.setStyleSheet(f"""
            OperationItem {{
                background: {bg};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
            OperationItem:hover {{
                background: {Colors.BG_CARD_HOVER};
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        
        type_indicator = QLabel("+" if amount >= 0 else "−")
        type_indicator.setFixedSize(32, 32)
        type_indicator.setAlignment(Qt.AlignCenter)
        type_indicator.setStyleSheet(f"""
            QLabel {{
                background: {color};
                color: {Colors.BG_DARK};
                border-radius: 8px;
                font-size: 18px;
                font-weight: 900;
            }}
        """)
        layout.addWidget(type_indicator)
        
        info = QVBoxLayout()
        info.setSpacing(2)
        
        comment_label = QLabel(comment)
        comment_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent;")
        info.addWidget(comment_label)
        
        time_label = QLabel(time_str)
        time_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 500; background: transparent;")
        info.addWidget(time_label)
        
        layout.addLayout(info, 1)
        
        sign = "+" if amount >= 0 else ""
        amount_label = QLabel(f"{sign}{format_money(amount)}")
        amount_label.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: 800; background: transparent;")
        layout.addWidget(amount_label)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.op_id)
        super().mousePressEvent(event)


class ShiftCard(QWidget):
    clicked = Signal(str)
    
    def __init__(self, shift: Shift, parent=None):
        super().__init__(parent)
        self.shift_id = shift.id
        self._setup_ui(shift)
        
    def _setup_ui(self, shift: Shift):
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        total = shift.total()
        color = Colors.amount_color(total)
        
        self.setStyleSheet(f"""
            ShiftCard {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 16px;
            }}
            ShiftCard:hover {{
                background: {Colors.BG_CARD_HOVER};
                border: 1px solid {Colors.BORDER_ACCENT};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        
        header = QHBoxLayout()
        
        start_dt = iso_to_dt(shift.start_ts)
        end_dt = iso_to_dt(shift.end_ts) if shift.end_ts else None
        
        date_label = QLabel(f"📅  {pretty_date(dt_to_ymd(start_dt))}")
        date_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 15px; font-weight: 700; background: transparent;")
        header.addWidget(date_label)
        
        header.addStretch()
        
        if end_dt is None:
            status = QLabel("● Активна")
            status.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 12px; font-weight: 700; background: transparent;")
        else:
            status = QLabel(f"{dt_to_time(start_dt)} — {dt_to_time(end_dt)}")
            status.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; font-weight: 600; background: transparent;")
        header.addWidget(status)
        
        layout.addLayout(header)
        
        metrics = QHBoxLayout()
        metrics.setSpacing(20)
        
        inc_box = QVBoxLayout()
        inc_box.setSpacing(2)
        inc_title = QLabel("Доход")
        inc_title.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
        inc_box.addWidget(inc_title)
        inc_value = QLabel(f"+{format_money(shift.income())}")
        inc_value.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 16px; font-weight: 800; background: transparent;")
        inc_box.addWidget(inc_value)
        metrics.addLayout(inc_box)
        
        exp_box = QVBoxLayout()
        exp_box.setSpacing(2)
        exp_title = QLabel("Расход")
        exp_title.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
        exp_box.addWidget(exp_title)
        exp_value = QLabel(f"−{format_money(shift.expense())}")
        exp_value.setStyleSheet(f"color: {Colors.DANGER}; font-size: 16px; font-weight: 800; background: transparent;")
        exp_box.addWidget(exp_value)
        metrics.addLayout(exp_box)
        
        metrics.addStretch()
        
        total_box = QVBoxLayout()
        total_box.setSpacing(2)
        total_title = QLabel("Итог")
        total_title.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
        total_box.addWidget(total_title, alignment=Qt.AlignRight)
        sign = "+" if total >= 0 else ""
        total_value = QLabel(f"{sign}{format_money(total)}")
        total_value.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 900; background: transparent;")
        total_box.addWidget(total_value, alignment=Qt.AlignRight)
        metrics.addLayout(total_box)
        
        layout.addLayout(metrics)
        
        info = QLabel(f"Операций: {len(shift.operations)}")
        info.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; font-weight: 500; background: transparent;")
        layout.addWidget(info)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.shift_id)
        super().mousePressEvent(event)


class DayCard(QWidget):
    clicked = Signal(str)
    
    def __init__(self, ymd: str, shifts_count: int, ops_count: int, income: int, expense: int, parent=None):
        super().__init__(parent)
        self.ymd = ymd
        self._setup_ui(ymd, shifts_count, ops_count, income, expense)
        
    def _setup_ui(self, ymd: str, shifts_count: int, ops_count: int, income: int, expense: int):
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        total = income - expense
        color = Colors.amount_color(total)
        
        self.setStyleSheet(f"""
            DayCard {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 16px;
            }}
            DayCard:hover {{
                background: {Colors.BG_CARD_HOVER};
                border: 1px solid {Colors.BORDER_ACCENT};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        
        header = QHBoxLayout()
        
        date_label = QLabel(f"📆  {pretty_date(ymd)}")
        date_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        header.addWidget(date_label)
        
        header.addStretch()
        
        stats = QLabel(f"{shifts_count} смен • {ops_count} опер.")
        stats.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; font-weight: 600; background: transparent;")
        header.addWidget(stats)
        
        layout.addLayout(header)
        
        metrics = QHBoxLayout()
        metrics.setSpacing(24)
        
        inc_box = QVBoxLayout()
        inc_box.setSpacing(2)
        inc_title = QLabel("Доход")
        inc_title.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
        inc_box.addWidget(inc_title)
        inc_value = QLabel(f"+{format_money(income)}")
        inc_value.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 18px; font-weight: 800; background: transparent;")
        inc_box.addWidget(inc_value)
        metrics.addLayout(inc_box)
        
        exp_box = QVBoxLayout()
        exp_box.setSpacing(2)
        exp_title = QLabel("Расход")
        exp_title.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
        exp_box.addWidget(exp_title)
        exp_value = QLabel(f"−{format_money(expense)}")
        exp_value.setStyleSheet(f"color: {Colors.DANGER}; font-size: 18px; font-weight: 800; background: transparent;")
        exp_box.addWidget(exp_value)
        metrics.addLayout(exp_box)
        
        metrics.addStretch()
        
        total_box = QVBoxLayout()
        total_box.setSpacing(2)
        total_title = QLabel("Итог дня")
        total_title.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 600; background: transparent;")
        total_box.addWidget(total_title, alignment=Qt.AlignRight)
        sign = "+" if total >= 0 else ""
        total_value = QLabel(f"{sign}{format_money(total)}")
        total_value.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 900; background: transparent;")
        total_box.addWidget(total_value, alignment=Qt.AlignRight)
        metrics.addLayout(total_box)
        
        layout.addLayout(metrics)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ymd)
        super().mousePressEvent(event)


# ---------------------------
# Dialogs
# ---------------------------

class OperationDetailsDialog(QDialog):
    def __init__(self, parent: QWidget, storage: Storage, shift: Shift, op: Operation):
        super().__init__(parent)
        self.storage = storage
        self.shift = shift
        self.op = op
        
        self.setWindowTitle("Детали операции")
        self.setModal(True)
        self.setMinimumSize(420, 320)
        self.resize(450, 350)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        header = QHBoxLayout()
        
        type_text = "Доход" if self.op.amount >= 0 else "Расход"
        color = Colors.amount_color(self.op.amount)
        
        title = QLabel(f"💰  {type_text}")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 20px; font-weight: 800; background: transparent;")
        header.addWidget(title)
        
        header.addStretch()
        
        sign = "+" if self.op.amount >= 0 else ""
        amount = QLabel(f"{sign}{format_money(self.op.amount)}")
        amount.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: 900; background: transparent;")
        header.addWidget(amount)
        
        layout.addLayout(header)
        
        info_card = GlassCard()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setSpacing(12)
        
        dt = iso_to_dt(self.op.ts)
        
        fields = [
            ("📝", "Комментарий", self.op.comment),
            ("🕐", "Дата и время", dt_to_pretty(dt)),
            ("📋", "Смена", pretty_date(dt_to_ymd(iso_to_dt(self.shift.start_ts)))),
        ]
        
        for icon, label, value in fields:
            row = QHBoxLayout()
            
            left = QLabel(f"{icon}  {label}")
            left.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px; font-weight: 600; background: transparent;")
            row.addWidget(left)
            
            row.addStretch()
            
            right = QLabel(value)
            right.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: 700; background: transparent;")
            row.addWidget(right)
            
            info_layout.addLayout(row)
        
        layout.addWidget(info_card)
        
        layout.addStretch()
        
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        
        btn_delete = ShimmerButton("Удалить", kind="danger")
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(8)
        
        for op in reversed(self.shift.operations):
            dt = iso_to_dt(op.ts)
            card = OperationItem(op.id, dt_to_time(dt), op.comment, op.amount)
            scroll_layout.addWidget(card)
        
        if not self.shift.operations:
            empty = QLabel("Нет операций")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 14px; padding: 30px; background: transparent;")
            scroll_layout.addWidget(empty)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        
        layout.addWidget(scroll)
        
        btn_close = ShimmerButton("Закрыть", kind="neutral")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)


class DayDetailsDialog(QDialog):
    def __init__(self, parent: QWidget, storage: Storage, ymd: str):
        super().__init__(parent)
        self.storage = storage
        self.ymd = ymd
        
        self.setWindowTitle("Детали дня")
        self.setModal(True)
        self.setMinimumSize(650, 550)
        self.resize(750, 650)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        shifts = [s for s in self.storage.shifts() if dt_to_ymd(iso_to_dt(s.start_ts)) == self.ymd]
        shifts = sorted(shifts, key=lambda s: s.start_ts)
        
        day_income = sum(s.income() for s in shifts)
        day_expense = sum(s.expense() for s in shifts)
        day_total = day_income - day_expense
        
        header = QHBoxLayout()
        
        title = QLabel(f"📆  {pretty_date(self.ymd)}")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 22px; font-weight: 800; background: transparent;")
        header.addWidget(title)
        
        header.addStretch()
        
        stats = QLabel(f"{len(shifts)} смен")
        stats.setStyleSheet(f"""
            background: {Colors.INFO_BG};
            border: 1px solid {Colors.INFO_BORDER};
            border-radius: 10px;
            padding: 6px 12px;
            color: {Colors.INFO};
            font-size: 12px;
            font-weight: 700;
        """)
        header.addWidget(stats)
        
        layout.addLayout(header)
        
        metrics = QHBoxLayout()
        metrics.setSpacing(16)
        
        income_card = MetricCard("📈", "Доход за день", f"+{format_money(day_income)}", Colors.SUCCESS)
        metrics.addWidget(income_card)
        
        expense_card = MetricCard("📉", "Расход за день", f"−{format_money(day_expense)}", Colors.DANGER)
        metrics.addWidget(expense_card)
        
        sign = "+" if day_total >= 0 else ""
        total_card = MetricCard("💰", "Итог дня", f"{sign}{format_money(day_total)}", Colors.amount_color(day_total))
        metrics.addWidget(total_card)
        
        layout.addLayout(metrics)
        
        shifts_label = QLabel("Смены")
        shifts_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        layout.addWidget(shifts_label)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(12)
        
        for shift in shifts:
            card = ShiftCard(shift)
            card.clicked.connect(self._open_shift)
            scroll_layout.addWidget(card)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        
        layout.addWidget(scroll)
        
        btn_close = ShimmerButton("Закрыть", kind="neutral")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)
        
    def _open_shift(self, shift_id: str):
        for s in self.storage.shifts():
            if s.id == shift_id:
                ShiftDetailsDialog(self, s).exec()
                return


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
        
    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Hero
        hero = AccentCard()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(16)
        
        header = QHBoxLayout()
        
        title_box = QVBoxLayout()
        title_box.setSpacing(6)
        
        title = QLabel("🚕  Калькулятор таксиста")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 24px; font-weight: 900; background: transparent;")
        title_box.addWidget(title)
        
        subtitle = QLabel("Профессиональный учёт доходов и расходов")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px; font-weight: 600; background: transparent;")
        title_box.addWidget(subtitle)
        
        header.addLayout(title_box)
        header.addStretch()
        
        actions = QHBoxLayout()
        actions.setSpacing(10)
        
        self.btn_new_shift = ShimmerButton("Новая смена")
        self.btn_new_shift.setFixedWidth(130)
        self.btn_new_shift.clicked.connect(self._new_shift)
        actions.addWidget(self.btn_new_shift)
        
        self.btn_history = ShimmerButton("История", kind="neutral")
        self.btn_history.setFixedWidth(100)
        self.btn_history.clicked.connect(self.open_history_cb)
        actions.addWidget(self.btn_history)
        
        self.btn_settings = ShimmerButton("⚙", kind="neutral")
        self.btn_settings.setFixedWidth(44)
        self.btn_settings.clicked.connect(self.open_settings_cb)
        actions.addWidget(self.btn_settings)
        
        header.addLayout(actions)
        hero_layout.addLayout(header)
        
        self.shift_status = QLabel()
        hero_layout.addWidget(self.shift_status, alignment=Qt.AlignLeft)
        
        layout.addWidget(hero)
        
        # Content
        content = QHBoxLayout()
        content.setSpacing(20)
        
        # Left
        left = QVBoxLayout()
        left.setSpacing(16)
        
        form_card = GlassCard()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(14)
        
        form_title = QLabel("Новая операция")
        form_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        form_layout.addWidget(form_title)
        
        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("Сумма (например: 1500 или -300)")
        self.amount_edit.textChanged.connect(self._on_amount_changed)
        self.amount_edit.returnPressed.connect(self._focus_comment)
        form_layout.addWidget(self.amount_edit)
        
        self.comment_combo = QComboBox()
        self.comment_combo.setEnabled(False)
        self.comment_combo.setMinimumHeight(44)
        form_layout.addWidget(self.comment_combo)
        
        self.btn_save = ShimmerButton("Сохранить")
        self.btn_save.clicked.connect(self._save_operation)
        form_layout.addWidget(self.btn_save)
        
        left.addWidget(form_card)
        
        self.income_metric = MetricCard("📈", "Доход", "+0", Colors.SUCCESS)
        left.addWidget(self.income_metric)
        
        self.expense_metric = MetricCard("📉", "Расход", "−0", Colors.DANGER)
        left.addWidget(self.expense_metric)
        
        self.total_metric = MetricCard("💰", "Итог смены", "0", Colors.TEXT_PRIMARY)
        left.addWidget(self.total_metric)
        
        left.addStretch()
        
        content.addLayout(left, 1)
        
        # Right
        right_card = GlassCard()
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)
        
        ops_header = QHBoxLayout()
        ops_title = QLabel("Операции смены")
        ops_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        ops_header.addWidget(ops_title)
        
        ops_header.addStretch()
        
        self.btn_clear = ShimmerButton("Очистить", kind="danger")
        self.btn_clear.setFixedWidth(100)
        self.btn_clear.clicked.connect(self._reset_shift)
        ops_header.addWidget(self.btn_clear)
        
        right_layout.addLayout(ops_header)
        
        ops_scroll = QScrollArea()
        ops_scroll.setWidgetResizable(True)
        ops_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ops_scroll.setMinimumWidth(350)
        
        self.ops_container = QWidget()
        self.ops_layout = QVBoxLayout(self.ops_container)
        self.ops_layout.setContentsMargins(0, 0, 8, 0)
        self.ops_layout.setSpacing(8)
        self.ops_layout.addStretch()
        
        ops_scroll.setWidget(self.ops_container)
        right_layout.addWidget(ops_scroll)
        
        content.addWidget(right_card, 2)
        
        layout.addLayout(content)
        
        # Bottom
        bottom = GlassCard()
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(20, 14, 20, 14)
        bottom_layout.setSpacing(30)
        
        all_time = QLabel("📊  За всё время:")
        all_time.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px; font-weight: 700; background: transparent;")
        bottom_layout.addWidget(all_time)
        
        self.all_income = QLabel()
        self.all_income.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 14px; font-weight: 800; background: transparent;")
        bottom_layout.addWidget(self.all_income)
        
        self.all_expense = QLabel()
        self.all_expense.setStyleSheet(f"color: {Colors.DANGER}; font-size: 14px; font-weight: 800; background: transparent;")
        bottom_layout.addWidget(self.all_expense)
        
        bottom_layout.addStretch()
        
        self.all_total = QLabel()
        bottom_layout.addWidget(self.all_total)
        
        layout.addWidget(bottom)
        
        scroll.setWidget(main_widget)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.comment_combo.hasFocus():
                self._save_operation()
                return
        super().keyPressEvent(event)
        
    def _focus_comment(self):
        if self.comment_combo.isEnabled() and self.comment_combo.count() > 1:
            self.comment_combo.setFocus()
            self.comment_combo.showPopup()
        
    def _load_active_shift(self):
        self.active_shift = self.storage.get_active_shift()
        self._render_shift()
        self._update_all_time()
        
    def _render_shift(self):
        s = self.active_shift
        start_dt = iso_to_dt(s.start_ts)
        end_dt = iso_to_dt(s.end_ts) if s.end_ts else None
        
        if end_dt is None:
            status = f"● Активная смена • {pretty_date(dt_to_ymd(start_dt))} с {dt_to_time(start_dt)}"
            self.shift_status.setStyleSheet(f"""
                background: {Colors.SUCCESS_BG};
                border: 1px solid {Colors.SUCCESS_BORDER};
                border-radius: 10px;
                padding: 8px 14px;
                color: {Colors.SUCCESS};
                font-size: 12px;
                font-weight: 700;
            """)
        else:
            status = f"Смена завершена • {dt_to_time(start_dt)} — {dt_to_time(end_dt)}"
            self.shift_status.setStyleSheet(f"""
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
                padding: 8px 14px;
                color: {Colors.TEXT_MUTED};
                font-size: 12px;
                font-weight: 700;
            """)
        self.shift_status.setText(status)
        
        income = s.income()
        expense = s.expense()
        total = s.total()
        
        self.income_metric.set_value(f"+{format_money(income)}", Colors.SUCCESS)
        self.expense_metric.set_value(f"−{format_money(expense)}", Colors.DANGER)
        
        sign = "+" if total >= 0 else ""
        self.total_metric.set_value(f"{sign}{format_money(total)}", Colors.amount_color(total))
        
        # Очищаем операции
        while self.ops_layout.count() > 1:
            item = self.ops_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not s.operations:
            empty = QLabel("Нет операций")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 14px; padding: 40px; background: transparent;")
            self.ops_layout.insertWidget(0, empty)
        else:
            for op in reversed(s.operations):
                dt = iso_to_dt(op.ts)
                card = OperationItem(op.id, dt_to_time(dt), op.comment, op.amount)
                card.clicked.connect(self._open_operation)
                card.setContextMenuPolicy(Qt.CustomContextMenu)
                card.customContextMenuRequested.connect(lambda pos, oid=op.id: self._ops_context_menu(pos, oid))
                self.ops_layout.insertWidget(self.ops_layout.count() - 1, card)
                
    def _update_all_time(self):
        inc, exp, net = self.storage.totals_all_time()
        self.all_income.setText(f"Доход: +{format_money(inc)}")
        self.all_expense.setText(f"Расход: −{format_money(exp)}")
        
        sign = "+" if net >= 0 else ""
        self.all_total.setText(f"Чистая прибыль: {sign}{format_money(net)}")
        self.all_total.setStyleSheet(f"color: {Colors.amount_color(net)}; font-size: 16px; font-weight: 900; background: transparent;")
        
    def _on_amount_changed(self):
        amt = parse_amount(self.amount_edit.text())
        self.comment_combo.clear()
        
        if amt is None or amt == 0:
            self.comment_combo.addItem("Введите сумму")
            self.comment_combo.setEnabled(False)
            return
            
        comments = self.storage.get_comments()
        
        if amt > 0:
            choices = comments.get("income", [])
            self.comment_combo.addItem("— Выберите комментарий —")
        else:
            choices = comments.get("expense", [])
            self.comment_combo.addItem("— Выберите комментарий —")
            
        for c in choices:
            self.comment_combo.addItem(c)
            
        self.comment_combo.addItem(OTHER_COMMENT_TEXT)
        self.comment_combo.setEnabled(True)
        
    def _save_operation(self):
        amt = parse_amount(self.amount_edit.text())
        if amt is None or amt == 0:
            QMessageBox.warning(self, "Ошибка", "Введите корректную сумму (не 0).")
            self.amount_edit.setFocus()
            return
            
        if not self.comment_combo.isEnabled() or self.comment_combo.currentIndex() <= 0:
            QMessageBox.warning(self, "Ошибка", "Выберите комментарий.")
            return
            
        chosen = self.comment_combo.currentText().strip()
        
        if chosen == OTHER_COMMENT_TEXT:
            text, ok = QInputDialog.getText(self, "Комментарий", "Введите комментарий:")
            if not ok:
                return
            comment = (text or "").strip()
            if not comment:
                QMessageBox.warning(self, "Ошибка", "Комментарий не может быть пустым.")
                return
        else:
            comment = chosen
            
        self.storage.add_operation_to_active(amt, comment)
        self.active_shift = self.storage.get_active_shift()
        self._render_shift()
        self._update_all_time()
        
        self.amount_edit.clear()
        self.amount_edit.setFocus()
        self._on_amount_changed()
        
    def _new_shift(self):
        self.storage.end_shift_and_create_new()
        self._load_active_shift()
        self.amount_edit.clear()
        self._on_amount_changed()
        
    def _reset_shift(self):
        if not self.active_shift.operations:
            return
            
        ans = QMessageBox.question(
            self, "Очистить смену",
            "Удалить все операции текущей смены?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            self.storage.reset_current_shift_operations()
            self._load_active_shift()
            
    def _open_operation(self, op_id: str):
        found = self.storage.find_operation(op_id)
        if not found:
            self._load_active_shift()
            return
            
        shift, op = found
        dlg = OperationDetailsDialog(self, self.storage, shift, op)
        dlg.exec()
        self._load_active_shift()
        
    def _ops_context_menu(self, pos, op_id: str):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: #12162B;
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 20px;
                border-radius: 4px;
                background: transparent;
            }}
            QMenu::item:selected {{
                background: rgba(124,58,237,0.3);
            }}
        """)
        
        act_open = QAction("Открыть", self)
        act_delete = QAction("Удалить", self)
        
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_delete)
        
        act_open.triggered.connect(lambda: self._open_operation(op_id))
        act_delete.triggered.connect(lambda: self._delete_operation(op_id))
        
        menu.exec(QCursor.pos())
        
    def _delete_operation(self, op_id: str):
        ans = QMessageBox.question(
            self, "Удаление",
            "Удалить эту операцию?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            self.storage.delete_operation_from_active(op_id)
            self._load_active_shift()


class HistoryPage(QWidget):
    def __init__(self, storage: Storage, back_cb):
        super().__init__()
        self.storage = storage
        self.back_cb = back_cb
        self.current_view = "shifts"
        
        self._build_ui()
        
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        
        btn_back = ShimmerButton("← Назад", kind="neutral")
        btn_back.setFixedWidth(100)
        btn_back.clicked.connect(self.back_cb)
        header.addWidget(btn_back)
        
        title = QLabel("📊  История")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 24px; font-weight: 900; background: transparent;")
        header.addWidget(title)
        
        header.addStretch()
        
        btn_refresh = ShimmerButton("Обновить", kind="neutral")
        btn_refresh.setFixedWidth(100)
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh)
        
        layout.addLayout(header)
        
        # View switch
        view_switch = QHBoxLayout()
        view_switch.setSpacing(10)
        
        self.btn_shifts = ShimmerButton("Смены")
        self.btn_shifts.setFixedWidth(120)
        self.btn_shifts.clicked.connect(lambda: self._switch_view("shifts"))
        view_switch.addWidget(self.btn_shifts)
        
        self.btn_days = ShimmerButton("Дни", kind="neutral")
        self.btn_days.setFixedWidth(120)
        self.btn_days.clicked.connect(lambda: self._switch_view("days"))
        view_switch.addWidget(self.btn_days)
        
        view_switch.addStretch()
        
        layout.addLayout(view_switch)
        
        # Content
        self.content_stack = QStackedWidget()
        
        # Shifts view
        self.shifts_widget = QWidget()
        shifts_layout = QVBoxLayout(self.shifts_widget)
        shifts_layout.setContentsMargins(0, 0, 0, 0)
        shifts_layout.setSpacing(12)
        
        self.shifts_container = QVBoxLayout()
        self.shifts_container.setSpacing(12)
        shifts_layout.addLayout(self.shifts_container)
        shifts_layout.addStretch()
        
        # Days view
        self.days_widget = QWidget()
        days_layout = QVBoxLayout(self.days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        days_layout.setSpacing(12)
        
        self.days_container = QVBoxLayout()
        self.days_container.setSpacing(12)
        days_layout.addLayout(self.days_container)
        days_layout.addStretch()
        
        self.content_stack.addWidget(self.shifts_widget)
        self.content_stack.addWidget(self.days_widget)
        
        layout.addWidget(self.content_stack)
        
        scroll.setWidget(main_widget)
        main_layout.addWidget(scroll)
        
    def _switch_view(self, view: str):
        self.current_view = view
        
        if view == "shifts":
            self.btn_shifts.kind = "primary"
            self.btn_days.kind = "neutral"
            self.content_stack.setCurrentWidget(self.shifts_widget)
        else:
            self.btn_shifts.kind = "neutral"
            self.btn_days.kind = "primary"
            self.content_stack.setCurrentWidget(self.days_widget)
            
        self.btn_shifts.update()
        self.btn_days.update()
        
    def refresh(self):
        # Clear shifts
        while self.shifts_container.count():
            item = self.shifts_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # Clear days
        while self.days_container.count():
            item = self.days_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        shifts = sorted(self.storage.shifts(), key=lambda s: s.start_ts, reverse=True)
        
        # Fill shifts
        if not shifts:
            empty = QLabel("История пуста")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 16px; padding: 60px; background: transparent;")
            self.shifts_container.addWidget(empty)
        else:
            for shift in shifts[:50]:
                card = ShiftCard(shift)
                card.clicked.connect(self._open_shift)
                self.shifts_container.addWidget(card)
                
        # Aggregate days
        day_map: Dict[str, Dict] = {}
        for s in shifts:
            ymd = dt_to_ymd(iso_to_dt(s.start_ts))
            if ymd not in day_map:
                day_map[ymd] = {"shifts": 0, "ops": 0, "income": 0, "expense": 0}
            day_map[ymd]["shifts"] += 1
            day_map[ymd]["ops"] += len(s.operations)
            day_map[ymd]["income"] += s.income()
            day_map[ymd]["expense"] += s.expense()
            
        days_sorted = sorted(day_map.items(), key=lambda x: x[0], reverse=True)
        
        # Fill days
        if not days_sorted:
            empty = QLabel("История пуста")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 16px; padding: 60px; background: transparent;")
            self.days_container.addWidget(empty)
        else:
            for ymd, info in days_sorted[:30]:
                card = DayCard(ymd, info["shifts"], info["ops"], info["income"], info["expense"])
                card.clicked.connect(self._open_day)
                self.days_container.addWidget(card)
                
    def _open_shift(self, shift_id: str):
        for s in self.storage.shifts():
            if s.id == shift_id:
                ShiftDetailsDialog(self, s).exec()
                return
                
    def _open_day(self, ymd: str):
        DayDetailsDialog(self, self.storage, ymd).exec()


class SettingsPage(QWidget):
    def __init__(self, storage: Storage, back_cb, apply_overlay_cb, after_reset_cb):
        super().__init__()
        self.storage = storage
        self.back_cb = back_cb
        self.apply_overlay_cb = apply_overlay_cb
        self.after_reset_cb = after_reset_cb
        
        self._build_ui()
        
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        
        btn_back = ShimmerButton("← Назад", kind="neutral")
        btn_back.setFixedWidth(100)
        btn_back.clicked.connect(self.back_cb)
        header.addWidget(btn_back)
        
        title = QLabel("⚙  Настройки")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 24px; font-weight: 900; background: transparent;")
        header.addWidget(title)
        
        header.addStretch()
        
        btn_save = ShimmerButton("Сохранить")
        btn_save.setFixedWidth(120)
        btn_save.clicked.connect(self._save)
        header.addWidget(btn_save)
        
        layout.addLayout(header)
        
        # Comments card
        comments_card = GlassCard()
        comments_layout = QVBoxLayout(comments_card)
        comments_layout.setContentsMargins(20, 20, 20, 20)
        comments_layout.setSpacing(16)
        
        comments_title = QLabel("📝  Шаблоны комментариев")
        comments_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        comments_layout.addWidget(comments_title)
        
        comments_grid = QHBoxLayout()
        comments_grid.setSpacing(20)
        
        # Income
        income_box = QVBoxLayout()
        income_box.setSpacing(10)
        
        income_title = QLabel("Доходы")
        income_title.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 14px; font-weight: 700; background: transparent;")
        income_box.addWidget(income_title)
        
        self.income_list = QListWidget()
        self.income_list.setMaximumHeight(150)
        self.income_list.setStyleSheet(f"""
            QListWidget {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
                padding: 8px;
            }}
            QListWidget::item {{
                padding: 6px 10px;
                border-radius: 6px;
                background: transparent;
            }}
            QListWidget::item:selected {{
                background: rgba(124,58,237,0.3);
            }}
        """)
        income_box.addWidget(self.income_list)
        
        income_btns = QHBoxLayout()
        income_btns.setSpacing(8)
        
        btn_inc_add = ShimmerButton("+", kind="neutral")
        btn_inc_add.setFixedSize(36, 36)
        btn_inc_add.clicked.connect(lambda: self._add_comment(True))
        income_btns.addWidget(btn_inc_add)
        
        btn_inc_del = ShimmerButton("−", kind="danger")
        btn_inc_del.setFixedSize(36, 36)
        btn_inc_del.clicked.connect(lambda: self._delete_comment(True))
        income_btns.addWidget(btn_inc_del)
        
        income_btns.addStretch()
        income_box.addLayout(income_btns)
        
        comments_grid.addLayout(income_box)
        
        # Expense
        expense_box = QVBoxLayout()
        expense_box.setSpacing(10)
        
        expense_title = QLabel("Расходы")
        expense_title.setStyleSheet(f"color: {Colors.DANGER}; font-size: 14px; font-weight: 700; background: transparent;")
        expense_box.addWidget(expense_title)
        
        self.expense_list = QListWidget()
        self.expense_list.setMaximumHeight(150)
        self.expense_list.setStyleSheet(f"""
            QListWidget {{
                background: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
                padding: 8px;
            }}
            QListWidget::item {{
                padding: 6px 10px;
                border-radius: 6px;
                background: transparent;
            }}
            QListWidget::item:selected {{
                background: rgba(124,58,237,0.3);
            }}
        """)
        expense_box.addWidget(self.expense_list)
        
        expense_btns = QHBoxLayout()
        expense_btns.setSpacing(8)
        
        btn_exp_add = ShimmerButton("+", kind="neutral")
        btn_exp_add.setFixedSize(36, 36)
        btn_exp_add.clicked.connect(lambda: self._add_comment(False))
        expense_btns.addWidget(btn_exp_add)
        
        btn_exp_del = ShimmerButton("−", kind="danger")
        btn_exp_del.setFixedSize(36, 36)
        btn_exp_del.clicked.connect(lambda: self._delete_comment(False))
        expense_btns.addWidget(btn_exp_del)
        
        expense_btns.addStretch()
        expense_box.addLayout(expense_btns)
        
        comments_grid.addLayout(expense_box)
        
        comments_layout.addLayout(comments_grid)
        
        note = QLabel(f"Пункт «{OTHER_COMMENT_TEXT}» всегда доступен")
        note.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; background: transparent;")
        comments_layout.addWidget(note)
        
        layout.addWidget(comments_card)
        
        # Overlay card
        overlay_card = GlassCard()
        overlay_layout = QVBoxLayout(overlay_card)
        overlay_layout.setContentsMargins(20, 20, 20, 20)
        overlay_layout.setSpacing(16)
        
        overlay_title = QLabel("🖥  Режим окна")
        overlay_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        overlay_layout.addWidget(overlay_title)
        
        self.chk_on_top = QCheckBox("Всегда поверх других окон")
        overlay_layout.addWidget(self.chk_on_top)
        
        self.chk_frameless = QCheckBox("Без рамки окна")
        overlay_layout.addWidget(self.chk_frameless)
        
        opacity_row = QHBoxLayout()
        opacity_label = QLabel("Прозрачность:")
        opacity_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-weight: 600; background: transparent;")
        opacity_row.addWidget(opacity_label)
        
        self.spn_opacity = QSpinBox()
        self.spn_opacity.setRange(30, 100)
        self.spn_opacity.setSuffix(" %")
        self.spn_opacity.setFixedWidth(100)
        opacity_row.addWidget(self.spn_opacity)
        
        opacity_row.addStretch()
        overlay_layout.addLayout(opacity_row)
        
        layout.addWidget(overlay_card)
        
        # Danger zone
        danger_card = GlassCard()
        danger_card.setStyleSheet(f"""
            GlassCard {{
                background: {Colors.DANGER_BG};
                border: 1px solid {Colors.DANGER_BORDER};
                border-radius: 16px;
            }}
        """)
        danger_layout = QVBoxLayout(danger_card)
        danger_layout.setContentsMargins(20, 20, 20, 20)
        danger_layout.setSpacing(12)
        
        danger_title = QLabel("⚠️  Опасная зона")
        danger_title.setStyleSheet(f"color: {Colors.DANGER}; font-size: 16px; font-weight: 700; background: transparent;")
        danger_layout.addWidget(danger_title)
        
        danger_desc = QLabel("Удаление всей истории операций и смен")
        danger_desc.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px; background: transparent;")
        danger_layout.addWidget(danger_desc)
        
        btn_reset = ShimmerButton("Удалить всю историю", kind="danger")
        btn_reset.clicked.connect(self._reset_all)
        danger_layout.addWidget(btn_reset)
        
        layout.addWidget(danger_card)
        
        layout.addStretch()
        
        scroll.setWidget(main_widget)
        main_layout.addWidget(scroll)
        
    def refresh(self):
        comm = self.storage.get_comments()
        
        self.income_list.clear()
        for c in comm.get("income", []):
            self.income_list.addItem(c)
            
        self.expense_list.clear()
        for c in comm.get("expense", []):
            self.expense_list.addItem(c)
            
        o = self.storage.get_overlay_settings()
        self.chk_on_top.setChecked(o["always_on_top"])
        self.chk_frameless.setChecked(o["frameless"])
        self.spn_opacity.setValue(o["opacity"])
        
    def _save(self):
        income = [self.income_list.item(i).text().strip() for i in range(self.income_list.count())]
        expense = [self.expense_list.item(i).text().strip() for i in range(self.expense_list.count())]
        
        income = [x for x in income if x]
        expense = [x for x in expense if x]
        
        if not income:
            income = default_comments()["income"][:]
        if not expense:
            expense = default_comments()["expense"][:]
            
        self.storage.set_comments(income, expense)
        self.storage.set_overlay_settings(
            always_on_top=self.chk_on_top.isChecked(),
            opacity=self.spn_opacity.value(),
            frameless=self.chk_frameless.isChecked()
        )
        
        self.apply_overlay_cb()
        QMessageBox.information(self, "Сохранено", "Настройки успешно сохранены.")
        
    def _add_comment(self, is_income: bool):
        text, ok = QInputDialog.getText(
            self,
            "Добавить комментарий",
            "Название:"
        )
        if not ok or not text.strip():
            return
            
        lst = self.income_list if is_income else self.expense_list
        
        for i in range(lst.count()):
            if lst.item(i).text().lower() == text.strip().lower():
                QMessageBox.warning(self, "Ошибка", "Такой комментарий уже существует.")
                return
                
        lst.addItem(text.strip())
        
    def _delete_comment(self, is_income: bool):
        lst = self.income_list if is_income else self.expense_list
        item = lst.currentItem()
        
        if not item:
            QMessageBox.warning(self, "Ошибка", "Выберите комментарий для удаления.")
            return
            
        ans = QMessageBox.question(
            self, "Удаление",
            f"Удалить комментарий «{item.text()}»?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            lst.takeItem(lst.row(item))
            
    def _reset_all(self):
        ans = QMessageBox.question(
            self, "Подтверждение",
            "Вы уверены, что хотите удалить ВСЮ историю?\n\nЭто действие нельзя отменить!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ans != QMessageBox.Yes:
            return
            
        text, ok = QInputDialog.getText(
            self,
            "Подтверждение",
            "Для подтверждения введите слово УДАЛИТЬ:"
        )
        if not ok or text.strip().upper() != "УДАЛИТЬ":
            QMessageBox.information(self, "Отменено", "Удаление отменено.")
            return
            
        self.storage.reset_all_history()
        QMessageBox.information(self, "Готово", "История успешно удалена.")
        self.after_reset_cb()


# ---------------------------
# Main Window
# ---------------------------

class MainWindow(QMainWindow):
    def __init__(self, storage: Storage):
        super().__init__()
        self.storage = storage
        
        self.setWindowTitle("Калькулятор таксиста")
        self.setMinimumSize(900, 650)
        self.resize(1100, 750)
        
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        self.shift_page = ShiftPage(
            storage,
            open_history_cb=self.open_history,
            open_settings_cb=self.open_settings
        )
        
        self.history_page = HistoryPage(
            storage,
            back_cb=self.open_shift
        )
        
        self.settings_page = SettingsPage(
            storage,
            back_cb=self.open_shift,
            apply_overlay_cb=self.apply_overlay_settings,
            after_reset_cb=self.open_shift
        )
        
        self.stack.addWidget(self.shift_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.settings_page)
        
        self.open_shift()
        self.apply_overlay_settings()
        
    def open_shift(self):
        self.stack.setCurrentWidget(self.shift_page)
        self.shift_page._load_active_shift()
        
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
        self.setWindowOpacity(max(0.3, min(1.0, o["opacity"] / 100.0)))
        self.show()


# ---------------------------
# Entry Point
# ---------------------------

def main():
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(get_stylesheet())
    
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    storage = Storage()
    storage.load()
    
    window = MainWindow(storage)
    window.show()
    
    app.exec()


if __name__ == "__main__":
    main()

