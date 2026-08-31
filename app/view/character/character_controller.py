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

管理两类小人的显示：
  a) 主窗口内小人（CharacterWidget）— 固定在主窗口右下角
  b) 桌面悬浮小人（DesktopCharacter）— 主窗口最小化/隐藏时显示在桌面

自动检测主窗口状态并切换；悬浮小人支持聊天气泡、点击计数返回应用、设置面板。
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMainWindow

from app.view.character.character_config import CharacterConfig
from app.view.character.character_widget import CharacterWidget
from app.view.character.desktop_character import DesktopCharacter

logger = logging.getLogger(__name__)


class CharacterController(QObject):
    """桌面小人显示模式管理器。

    - 主窗口模式：CharacterWidget 嵌在主窗口右下角
    - 桌面悬浮模式：DesktopCharacter 独立悬浮窗（气泡 + 设置 + 连点返回）
    - 通过 get_task_name 回调获取当前任务名，供悬浮小人气泡显示
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

        # --- 回调 ---
        self._on_go_home_callback: Callable[[], None] | None = None
        self._get_task_name: Callable[[], str | None] | None = None

        # --- 主窗口内小人 ---
        self._characters: list[CharacterWidget] = []
        self._create_window_character()

        # --- 桌面悬浮小人（懒创建） ---
        self._desktop_character: DesktopCharacter | None = None

        # --- 模式 ---
        self._current_mode: str = "none"

        # --- 防抖 ---
        self._mode_timer = QTimer(self)
        self._mode_timer.setSingleShot(True)
        self._mode_timer.setInterval(300)
        self._mode_timer.timeout.connect(self._apply_mode)
        self._pending_mode: str | None = None

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
        """主窗口内小人。"""
        return self._characters[0] if self._characters else None

    @property
    def characters(self) -> list[CharacterWidget]:
        return list(self._characters)

    @property
    def desktop_character(self) -> DesktopCharacter | None:
        """桌面悬浮小人。"""
        return self._desktop_character

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def config(self) -> CharacterConfig:
        return self._config

    # ============================================================
    #  回调设置
    # ============================================================

    def set_on_go_home(self, callback: Callable[[], None] | None) -> None:
        """设置"返回首页"回调（悬浮小人连点 5 次触发）。"""
        self._on_go_home_callback = callback

    def set_get_task_name(self, callback: Callable[[], str | None] | None) -> None:
        """设置"获取当前任务名"回调（供气泡显示）。"""
        self._get_task_name = callback
        if self._desktop_character is not None:
            self._desktop_character._get_task_name = callback

    # ============================================================
    #  模式切换
    # ============================================================

    def switch_to_window_mode(self) -> None:
        """切换到主窗口模式：隐藏桌面小人，显示主窗口内小人。"""
        if not self._config.enabled:
            return
        try:
            if self._desktop_character is not None:
                self._desktop_character.hide()

            for char in self._characters:
                if char.parent() is not self._main_window:
                    char.setParent(self._main_window)
                char.show()

            self._layout_window_chars()
            self._current_mode = "window"
        except Exception as exc:
            logger.warning("切换窗口模式失败: %s", exc)

    def switch_to_float_mode(self) -> None:
        """切换到桌面悬浮模式：隐藏主窗口内小人，显示桌面小人。"""
        if not self._config.enabled:
            return
        try:
            for char in self._characters:
                char.hide()

            if self._desktop_character is None:
                self._desktop_character = DesktopCharacter(
                    get_task_name=self._get_task_name
                )
                self._desktop_character.go_home_requested.connect(
                    self._on_go_home_requested
                )

            self._desktop_character.move_to_bottom_right()
            self._desktop_character.show()
            self._current_mode = "float"
        except Exception as exc:
            logger.warning("切换悬浮模式失败: %s", exc)

    def hide_character(self) -> None:
        """完全隐藏小人。"""
        for char in self._characters:
            char.hide()
        if self._desktop_character is not None:
            self._desktop_character.hide()
        self._current_mode = "none"

    def show_character(self) -> None:
        """显示小人（自动判断模式）。"""
        if not self._config.enabled:
            return
        if self._main_window.isMinimized() or not self._main_window.isVisible():
            self.switch_to_float_mode()
        else:
            self.switch_to_window_mode()

    # ============================================================
    #  悬浮小人返回应用
    # ============================================================

    def _on_go_home_requested(self) -> None:
        """桌面小人连续点击 5 次 → 恢复主窗口 + 返回首页。"""
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
            self._request_mode("float")
        elif not should_float and self._current_mode != "window":
            self._request_mode("window")

    # ============================================================
    #  内部
    # ============================================================

    def _create_window_character(self) -> None:
        """创建主窗口内小人。"""
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
        if self._desktop_character is not None:
            try:
                self._desktop_character.dispose()
                self._desktop_character.close()
            except Exception:
                pass
            self._desktop_character = None
        for char in self._characters:
            try:
                char.deleteLater()
            except Exception:
                pass
        self._characters.clear()
