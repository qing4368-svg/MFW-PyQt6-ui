#   This file is part of MFW-ChainFlow Assistant.
#
#   MFW-ChainFlow Assistant is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.
#
#   MFW-ChainFlow Assistant is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with MFW-ChainFlow Assistant. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: err.overflow@gmail.com
#   Copyright (C) 2024-2025  MFW-ChainFlow Assistant. All rights reserved.

"""
MFW-ChainFlow Assistant
桌面小人控制器

两种显示模式：
  a) 主窗口模式：CharacterWidget 固定在主窗口右下角
  b) 桌面悬浮模式：一个可拖拽的圆形浮动按钮（即桌面小人本身），
     点击后恢复主窗口并导航到首页。

扩展接口：
  - set_float_image(pixmap) 切换悬浮小人外观
  - 用户可在设置中选择不同角色图片
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPixmap,
    QBrush,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.view.character.character_config import CharacterConfig
from app.view.character.character_widget import CharacterWidget

logger = logging.getLogger(__name__)

# --- 悬浮小人按钮样式 ---
_FLOAT_CHAR_STYLE = """
    QPushButton {
        background: rgba(255, 255, 255, 0.85);
        border: 3px solid #aaa;
        border-radius: 44px;
        font-size: 36px;
        min-width: 88px;
        min-height: 88px;
        max-width: 88px;
        max-height: 88px;
    }
    QPushButton:hover {
        background: rgba(255, 255, 255, 1);
        border-color: #666;
    }
"""


class _FloatCharacterButton(QPushButton):
    """桌面悬浮小人按钮。

    无边框置顶透明窗口中的可拖拽圆形按钮，是桌面小人在悬浮模式下的载体。
    预留通过 setIcon() / setText() 切换外观的接口。
    """

    def __init__(self, emoji: str = "🏠", parent=None):
        super().__init__(emoji, parent)
        self.setStyleSheet(_FLOAT_CHAR_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to return home")

        # 拖拽相关
        self._dragging = False
        self._mouse_pressed = False
        self._drag_start_pos = QPoint()

    def set_float_icon(self, pixmap: QPixmap | None) -> None:
        """设置悬浮小人的图片图标。

        传入 None 则恢复 emoji 文字模式。
        """
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                60, 60,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setIcon(QIcon(scaled))
            self.setIconSize(scaled.size())
            self.setText("")
        else:
            self.setIcon(QIcon())
            self.setText("🏠")

    def set_float_emoji(self, text: str) -> None:
        """设置悬浮小人的 emoji 文字。"""
        self.setIcon(QIcon())
        self.setText(text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """记录按下的起始位置，不立即判定拖拽。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_pressed = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._dragging = False
        # 始终调用父类，确保 QPushButton 的 clicked 信号能正常触发
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标按下且移动超过 5px 才开始拖拽窗口。"""
        if not self._mouse_pressed:
            return
        if not self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            if delta.manhattanLength() >= 5:
                self._dragging = True
                self._drag_start_pos = event.globalPosition().toPoint() - self.window().pos()
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.window().move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """释放鼠标：未拖拽 → 点击回首页；已拖拽 → 结束拖拽。"""
        self._mouse_pressed = False
        if not self._dragging:
            super().mouseReleaseEvent(event)
        else:
            self._dragging = False
            event.accept()


class _FloatWindow(QWidget):
    """悬浮小人容器窗口：透明背景、无边框、置顶。"""

    def __init__(self, char_button: _FloatCharacterButton):
        super().__init__(None)
        self.setObjectName("CharacterFloatWindow")

        _flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        try:
            _flags |= Qt.WindowType.NoDropShadowWindowHint
        except AttributeError:
            pass
        self.setWindowFlags(_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        except AttributeError:
            pass

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(char_button)
        self.setLayout(layout)
        self.setFixedSize(88, 88)

    def move_to_screen_bottom_right(self) -> None:
        """移动到主屏幕右下角。"""
        screens = QApplication.screens()
        if not screens:
            return
        geo = screens[0].availableGeometry()
        self.move(geo.right() - self.width() - 30, geo.bottom() - self.height() - 30)


class CharacterController(QObject):
    """桌面小人显示模式管理器。

    - 主窗口模式：CharacterWidget 嵌在主窗口右下角
    - 桌面悬浮模式：独立浮动圆形按钮，点击恢复主窗口并返回首页
    - 可通过 set_float_image() / set_float_emoji() 切换悬浮外观
    - 预留多角色扩展（characters 列表）
    """

    go_home_requested = Signal()

    def __init__(
        self,
        main_window: QMainWindow,
        config: CharacterConfig | None = None,
    ):
        super().__init__(main_window)
        self._main_window = main_window
        self._config = config or CharacterConfig()

        # --- 角色列表 ---
        self._characters: list[CharacterWidget] = []

        # --- 回调 ---
        self._on_go_home_callback: Callable[[], None] | None = None

        # --- 悬浮窗口 ---
        self._float_window: _FloatWindow | None = None
        self._float_button: _FloatCharacterButton | None = None

        # --- 模式 ---
        self._current_mode: str = "none"

        # --- 防抖 ---
        self._mode_timer = QTimer(self)
        self._mode_timer.setSingleShot(True)
        self._mode_timer.setInterval(300)
        self._mode_timer.timeout.connect(self._apply_mode)

        self._pending_mode: str | None = None

        # --- 创建默认小人 ---
        self._create_default_character()

        # --- 事件过滤 ---
        self._main_window.installEventFilter(self)

        if not self._config.enabled:
            for c in self._characters:
                c.hide()

    # ============================================================
    #  属性
    # ============================================================

    @property
    def character(self) -> CharacterWidget | None:
        return self._characters[0] if self._characters else None

    @property
    def characters(self) -> list[CharacterWidget]:
        return list(self._characters)

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def config(self) -> CharacterConfig:
        return self._config

    # ============================================================
    #  浮动小人外观（用户可在设置中切换）
    # ============================================================

    def set_float_image(self, image_path: str) -> None:
        """设置悬浮小人的图片。"""
        if self._float_button is None:
            return
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self._float_button.set_float_icon(pixmap)
        else:
            logger.warning("无法加载悬浮小人图片: %s", image_path)

    def set_float_emoji(self, emoji: str) -> None:
        """设置悬浮小人的 emoji 文字。"""
        if self._float_button is not None:
            self._float_button.set_float_emoji(emoji)

    # ============================================================
    #  回调
    # ============================================================

    def set_on_go_home(self, callback: Callable[[], None] | None) -> None:
        self._on_go_home_callback = callback

    # ============================================================
    #  模式切换
    # ============================================================

    def switch_to_window_mode(self) -> None:
        if not self._config.enabled:
            return
        try:
            # 隐藏悬浮窗
            if self._float_window is not None:
                self._float_window.hide()

            # 挂回主窗口
            for char in self._characters:
                if char.parent() is not self._main_window:
                    char.setParent(self._main_window)
                char.show()

            self._layout_window_chars()
            self._current_mode = "window"
            logger.debug("Character → window mode")
        except Exception as exc:
            logger.warning("切换窗口模式失败: %s", exc)

    def switch_to_float_mode(self) -> None:
        if not self._config.enabled:
            return
        try:
            # 隐藏主窗口中的小人
            for char in self._characters:
                char.hide()

            # 创建悬浮窗（懒加载）
            if self._float_window is None:
                self._float_button = _FloatCharacterButton()
                # 尝试加载角色图片
                img_path = self._config.resolve_image_path()
                if img_path is not None:
                    pixmap = QPixmap(str(img_path))
                    if not pixmap.isNull():
                        self._float_button.set_float_icon(pixmap)
                self._float_button.clicked.connect(self._on_float_clicked)
                self._float_window = _FloatWindow(self._float_button)

            # 定位并显示
            float_pos = self._config.float_position
            if float_pos is not None:
                self._float_window.move(float_pos[0], float_pos[1])
            else:
                self._float_window.move_to_screen_bottom_right()

            self._float_window.show()
            self._current_mode = "float"
            logger.debug("Character → float mode")
        except Exception as exc:
            logger.warning("切换悬浮模式失败: %s", exc)

    def hide_character(self) -> None:
        for char in self._characters:
            char.hide()
        if self._float_window is not None:
            self._float_window.hide()
        self._current_mode = "none"

    def show_character(self) -> None:
        if not self._config.enabled:
            return
        if self._main_window.isMinimized() or not self._main_window.isVisible():
            self.switch_to_float_mode()
        else:
            self.switch_to_window_mode()

    # ============================================================
    #  防抖
    # ============================================================

    def _request_mode(self, mode: str) -> None:
        self._pending_mode = mode
        if not self._mode_timer.isActive():
            self._mode_timer.start()

    def _apply_mode(self) -> None:
        target = self._pending_mode
        self._pending_mode = None
        if target is None or target == self._current_mode:
            return
        if target == "float":
            self.switch_to_float_mode()
        elif target == "window":
            self.switch_to_window_mode()

    # ============================================================
    #  悬浮按钮点击
    # ============================================================

    def _on_float_clicked(self) -> None:
        """悬浮小人被点击 → 恢复主窗口 + 返回首页。"""
        self._main_window.showNormal()
        self._main_window.raise_()
        self._main_window.activateWindow()

        if self._on_go_home_callback is not None:
            try:
                self._on_go_home_callback()
            except Exception as exc:
                logger.warning("go_home 回调失败: %s", exc)

        self.go_home_requested.emit()

    # ============================================================
    #  配置
    # ============================================================

    def update_config(self, config: CharacterConfig) -> None:
        old_enabled = self._config.enabled
        self._config = config
        for char in self._characters:
            char.update_config(config)
        if config.enabled and not old_enabled:
            self.show_character()
        elif not config.enabled and old_enabled:
            self.hide_character()
        if self._current_mode == "window":
            self._layout_window_chars()

    def set_enabled(self, enabled: bool) -> None:
        self._config.enabled = enabled
        if enabled:
            self.show_character()
        else:
            self.hide_character()

    # ============================================================
    #  事件过滤
    # ============================================================

    def eventFilter(self, watched, event) -> bool:
        if watched is not self._main_window:
            return False
        if not self._config.enabled or not self._config.float_on_minimize:
            return False

        if event.type() in (QEvent.Type.WindowStateChange, QEvent.Type.Hide):
            QTimer.singleShot(200, self._check_state_and_switch)
        elif event.type() == QEvent.Type.Show:
            QTimer.singleShot(200, self._check_state_and_switch)
        elif event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            if self._current_mode == "window":
                self._layout_window_chars()

        return False

    def _check_state_and_switch(self) -> None:
        """根据主窗口当前实际状态决定模式。"""
        if not self._config.enabled or not self._config.float_on_minimize:
            return

        is_visible = self._main_window.isVisible()
        is_minimized = self._main_window.isMinimized()

        should_float = (not is_visible) or is_minimized

        if should_float and self._current_mode != "float":
            logger.debug("检测到主窗口隐藏/最小化，切换悬浮模式")
            self._request_mode("float")
        elif not should_float and self._current_mode != "window":
            logger.debug("检测到主窗口恢复，切换窗口模式")
            self._request_mode("window")

    # ============================================================
    #  内部
    # ============================================================

    def _create_default_character(self) -> None:
        char = CharacterWidget(self._config)
        self._characters.append(char)

    def _layout_window_chars(self) -> None:
        count = len(self._characters)
        if count == 0:
            return
        offset_x, offset_y = self._config.position_offset
        main_rect = self._main_window.rect()
        char_size = self._config.widget_size
        spacing = 6

        total_h = count * char_size + (count - 1) * spacing
        base_x = max(0, main_rect.right() - char_size - offset_x)
        base_y = max(0, main_rect.bottom() - total_h - offset_y)

        for i, char in enumerate(reversed(self._characters)):
            y = base_y + i * (char_size + spacing)
            char.move(base_x, y)
            char.raise_()

    # ============================================================
    #  清理
    # ============================================================

    def dispose(self) -> None:
        try:
            self._main_window.removeEventFilter(self)
        except Exception:
            pass
        try:
            self._mode_timer.stop()
        except Exception:
            pass
        if self._float_window is not None:
            try:
                self._float_window.close()
            except Exception:
                pass
            self._float_window = None
        for char in self._characters:
            try:
                char.deleteLater()
            except Exception:
                pass
        self._characters.clear()
