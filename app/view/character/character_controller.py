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

管理 CharacterWidget 的两种显示模式：
  a) 主窗口模式：固定在主窗口右下角，随窗口移动/缩放
  b) 桌面悬浮模式：独立无边框置顶透明窗口，当主窗口最小化/隐藏时自动切换
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from app.view.character.character_config import CharacterConfig
from app.view.character.character_widget import CharacterWidget

logger = logging.getLogger(__name__)

# --- 悬浮窗口样式 ---
_FLOAT_WINDOW_STYLE = """
    QWidget#CharacterFloatWindow {
        background: transparent;
    }
"""


class _CharacterFloatWindow(QWidget):
    """桌面悬浮小人专用窗口：无边框、置顶、透明背景。"""

    def __init__(self, character_widget: CharacterWidget):
        super().__init__(None)
        self.setObjectName("CharacterFloatWindow")

        # 窗口标志：兼容不同 PySide6 版本的枚举名
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
        self.setStyleSheet(_FLOAT_WINDOW_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(character_widget)
        self.setLayout(layout)

        size = character_widget.config.widget_size
        self.setFixedSize(size, size)

    def move_to_screen_bottom_right(self) -> None:
        """将悬浮窗移动到主屏幕右下角。"""
        screens = QApplication.screens()
        if not screens:
            return
        screen_geometry = screens[0].availableGeometry()
        x = screen_geometry.right() - self.width() - 30
        y = screen_geometry.bottom() - self.height() - 30
        self.move(x, y)


class CharacterController(QObject):
    """桌面小人显示模式管理器。

    职责：
    - 管理 CharacterWidget 实例的生命周期
    - 主窗口模式 ↔ 桌面悬浮模式切换
    - 自动检测主窗口状态并切换显示模式

    Usage::

        controller = CharacterController(main_window, config)
        controller.show_in_window_mode()  # 将小人嵌入主窗口

        # 当主窗口最小化时，自动切换为悬浮模式（如果 float_on_minimize=True）
    """

    def __init__(
        self,
        main_window: QMainWindow,
        config: CharacterConfig | None = None,
    ):
        super().__init__(main_window)  # QObject 需要 parent
        self._main_window = main_window
        self._config = config or CharacterConfig()

        # --- 创建小人控件 ---
        self._character = CharacterWidget(self._config)

        # --- 悬浮窗口（懒创建） ---
        self._float_window: _CharacterFloatWindow | None = None

        # --- 当前模式 ---
        self._current_mode: str = "none"  # "none" | "window" | "float"

        # --- 是否正在切换中（防止递归） ---
        self._switching: bool = False

        # --- 安装主窗口事件过滤器 ---
        self._main_window.installEventFilter(self)

        if not self._config.enabled:
            self._character.hide()

    # ============================================================
    #  属性
    # ============================================================

    @property
    def character(self) -> CharacterWidget:
        """获取小人控件实例，供外部直接操作（如 set_mood 等）。"""
        return self._character

    @property
    def current_mode(self) -> str:
        """获取当前显示模式：'none' / 'window' / 'float'。"""
        return self._current_mode

    @property
    def config(self) -> CharacterConfig:
        """获取当前配置。"""
        return self._config

    # ============================================================
    #  模式切换
    # ============================================================

    def switch_to_window_mode(self) -> None:
        """切换到主窗口模式：将小人嵌入到主窗口右下角。"""
        if self._switching:
            return
        if not self._config.enabled:
            return

        self._switching = True
        try:
            # 隐藏悬浮窗口
            self._hide_float_window()

            # 将小人重新挂载到主窗口
            if self._character.parent() is not self._main_window:
                self._character.setParent(self._main_window)

            self._character.show()
            self._update_window_position()
            self._current_mode = "window"
        finally:
            self._switching = False

    def switch_to_float_mode(self) -> None:
        """切换到桌面悬浮模式：独立无边框置顶窗口。"""
        if self._switching:
            return
        if not self._config.enabled:
            return

        self._switching = True
        try:
            # 从主窗口移除
            self._character.hide()

            # 创建或复用悬浮窗口
            if self._float_window is None:
                self._float_window = _CharacterFloatWindow(self._character)
                self._character.setParent(self._float_window)

                # 恢复布局
                layout = self._float_window.layout()
                if layout is not None:
                    layout.addWidget(self._character)

            # 设置悬浮窗口位置
            float_pos = self._config.float_position
            if float_pos is not None:
                self._float_window.move(float_pos[0], float_pos[1])
            else:
                self._float_window.move_to_screen_bottom_right()

            self._float_window.show()
            self._current_mode = "float"
        finally:
            self._switching = False

    def hide_character(self) -> None:
        """完全隐藏小人（两种模式均隐藏）。"""
        self._character.hide()
        self._hide_float_window()
        self._current_mode = "none"

    def show_character(self) -> None:
        """显示小人（恢复到上次的非 none 模式，默认为窗口模式）。"""
        if not self._config.enabled:
            return

        if self._main_window.isMinimized() and self._config.float_on_minimize:
            self.switch_to_float_mode()
        else:
            self.switch_to_window_mode()

    # ============================================================
    #  配置
    # ============================================================

    def update_config(self, config: CharacterConfig) -> None:
        """更新配置并刷新显示。

        Args:
            config: 新的配置对象。
        """
        old_enabled = self._config.enabled
        self._config = config
        self._character.update_config(config)

        # 启用状态变化
        if config.enabled and not old_enabled:
            self.show_character()
        elif not config.enabled and old_enabled:
            self.hide_character()

        # 如果当前在窗口模式，刷新位置
        if self._current_mode == "window":
            self._update_window_position()

    def set_enabled(self, enabled: bool) -> None:
        """启用或禁用桌面小人。

        Args:
            enabled: True 启用，False 禁用并隐藏。
        """
        self._config.enabled = enabled
        if enabled:
            self.show_character()
        else:
            self.hide_character()

    # ============================================================
    #  事件过滤：自动检测主窗口状态
    # ============================================================

    def eventFilter(self, watched, event) -> bool:
        """监听主窗口状态变化，自动切换显示模式。"""
        if watched is not self._main_window:
            return False

        if not self._config.enabled or not self._config.float_on_minimize:
            return False

        if event.type() == QEvent.Type.WindowStateChange:
            is_minimized = self._main_window.isMinimized()
            if is_minimized and self._current_mode == "window":
                # 主窗口最小化 → 自动切换到悬浮模式
                QTimer.singleShot(100, self.switch_to_float_mode)
            elif not is_minimized and self._current_mode == "float":
                # 主窗口恢复 → 自动切换回窗口模式
                QTimer.singleShot(100, self.switch_to_window_mode)

        elif event.type() == QEvent.Type.Hide:
            if self._current_mode == "window":
                QTimer.singleShot(100, self.switch_to_float_mode)

        elif event.type() == QEvent.Type.Show:
            if self._current_mode == "float" and not self._main_window.isMinimized():
                QTimer.singleShot(100, self.switch_to_window_mode)

        elif event.type() == QEvent.Type.Resize:
            if self._current_mode == "window":
                self._update_window_position()

        elif event.type() == QEvent.Type.Move:
            if self._current_mode == "window":
                self._update_window_position()

        return False  # 不拦截事件，继续传播

    # ============================================================
    #  内部方法
    # ============================================================

    def _hide_float_window(self) -> None:
        """隐藏并清理悬浮窗口。"""
        if self._float_window is not None:
            self._float_window.hide()

    def _update_window_position(self) -> None:
        """将小人定位到主窗口右下角（偏移由配置决定）。"""
        if self._character.parent() is not self._main_window:
            return

        offset_x, offset_y = self._config.position_offset
        main_rect: QRect = self._main_window.rect()
        char_size = self._config.widget_size

        x = main_rect.right() - char_size - offset_x
        y = main_rect.bottom() - char_size - offset_y

        # 确保不超出窗口范围
        x = max(0, x)
        y = max(0, y)

        self._character.move(x, y)
        self._character.raise_()  # 保持在最上层

    # ============================================================
    #  清理
    # ============================================================

    def dispose(self) -> None:
        """清理所有资源：移除事件过滤器、关闭悬浮窗口、删除控件。"""
        try:
            self._main_window.removeEventFilter(self)
        except Exception:
            pass

        if self._float_window is not None:
            try:
                self._float_window.close()
            except Exception:
                pass
            self._float_window = None

        try:
            self._character.deleteLater()
        except Exception:
            pass
