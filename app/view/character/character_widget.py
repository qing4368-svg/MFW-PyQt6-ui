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
桌面小人控件

CharacterWidget 是一个可点击的 QLabel 子类，用于在主窗口或桌面上显示交互式角色。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFont, QPixmap, QMouseEvent
from PySide6.QtWidgets import QLabel, QGraphicsOpacityEffect

from app.view.character.character_config import CharacterConfig

logger = logging.getLogger(__name__)

# --- 延迟加载 QSoundEffect（Qt Multimedia 可能未安装） ---
_QSoundEffect = None


def _get_qsound_effect():
    """尝试导入 QSoundEffect，失败则返回 None。"""
    global _QSoundEffect
    if _QSoundEffect is None:
        try:
            from PySide6.QtMultimedia import QSoundEffect as QSE

            _QSoundEffect = QSE
        except ImportError:
            logger.debug("PySide6.QtMultimedia 不可用，音效功能已禁用")
            _QSoundEffect = False  # type: ignore[assignment]
    return _QSoundEffect if _QSoundEffect is not False else None  # type: ignore[return-value]


class CharacterWidget(QLabel):
    """可交互的桌面角色控件。

    提供以下核心能力：
    - 显示角色图片 / emoji 占位
    - 鼠标点击 → 上下弹跳动画 + 音效
    - set_mood() 切换表情/心情
    - add_action() 注册自定义动作
    - set_on_click_callback() 注入额外点击回调

    Usage::

        char = CharacterWidget(config)
        char.set_on_click_callback(lambda: print("clicked!"))
        char.set_mood("happy")
    """

    # --- 信号 ---
    clicked = Signal()  # 点击时发射（动画/音效之后）
    mood_changed = Signal(str)  # 心情切换时发射，参数为新的 mood 名称

    def __init__(
        self,
        config: CharacterConfig | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config or CharacterConfig()

        # --- 内部状态 ---
        self._mood: str = self._config.default_mood
        self._bounce_animation: QPropertyAnimation | None = None
        self._on_click_callback: Callable[[], None] | None = None
        self._custom_actions: dict[str, Callable[[], None]] = {}
        self._sound_effect = None
        self._base_position: QPoint = QPoint(0, 0)

        # --- 外观初始化 ---
        self._setup_appearance()
        self._init_sound()

        # --- 交互 ---
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ============================================================
    #  外观
    # ============================================================

    def _setup_appearance(self) -> None:
        """根据配置初始化控件外观。"""
        size = self._config.widget_size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 尝试加载图片
        pixmap = None
        image_path = self._config.resolve_image_path()
        if image_path is not None:
            pixmap = QPixmap(str(image_path))
            if pixmap.isNull():
                logger.warning("无法加载角色图片: %s", image_path)

        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)
        else:
            # 使用 emoji 占位
            self._set_emoji_text(self._config.emoji_text)

    def _set_emoji_text(self, text: str) -> None:
        """使用文字 emoji 作为占位显示。"""
        font = QFont()
        font.setPointSize(int(self._config.widget_size * 0.6))
        # QFont.StyleHint.Emoji 在 Qt 6.7+ / PySide6 6.6+ 才可用
        # 旧版本回退到 SansSerif，emoji 渲染依赖系统字体
        try:
            hint = QFont.StyleHint.Emoji
        except AttributeError:
            hint = QFont.StyleHint.SansSerif
        font.setStyleHint(hint)
        self.setFont(font)
        self.setText(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_emoji(self, emoji_text: str) -> None:
        """动态切换 emoji 占位文字（仅在无图片模式生效）。"""
        self._config.emoji_text = emoji_text
        image_path = self._config.resolve_image_path()
        if image_path is None:
            self._set_emoji_text(emoji_text)

    def set_image(self, image_path: str) -> None:
        """动态切换角色图片。

        Args:
            image_path: 图片文件路径（相对路径以 CWD 为基准）。
        """
        self._config.image_path = image_path
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            logger.warning("无法加载角色图片，回退到 emoji: %s", image_path)
            self._set_emoji_text(self._config.emoji_text)
            return
        size = self._config.widget_size
        scaled = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    # ============================================================
    #  音效
    # ============================================================

    def _init_sound(self) -> None:
        """初始化音效播放器（如果可用）。"""
        qse = _get_qsound_effect()
        if qse is None:
            return
        sound_path = self._config.resolve_sound_path()
        if sound_path is None:
            return
        try:
            from PySide6.QtCore import QUrl

            self._sound_effect = qse(self)
            self._sound_effect.setSource(QUrl.fromLocalFile(str(sound_path)))
            self._sound_effect.setVolume(self._config.sound_volume)
        except Exception as exc:
            logger.warning("初始化音效失败: %s", exc)
            self._sound_effect = None

    def set_sound(self, sound_path: str) -> None:
        """更换点击音效。

        Args:
            sound_path: 音效文件路径（为空则禁用音效）。
        """
        self._config.sound_path = sound_path
        self._init_sound()

    def set_sound_volume(self, volume: float) -> None:
        """设置音效音量。

        Args:
            volume: 音量值（0.0 ~ 1.0）。
        """
        self._config.sound_volume = max(0.0, min(1.0, volume))
        if self._sound_effect is not None:
            try:
                self._sound_effect.setVolume(self._config.sound_volume)
            except Exception:
                pass

    def _play_sound(self) -> None:
        """播放音效（如果可用）。"""
        if self._sound_effect is None:
            return
        try:
            self._sound_effect.stop()
            self._sound_effect.play()
        except Exception as exc:
            logger.debug("播放音效失败: %s", exc)

    # ============================================================
    #  弹跳动画
    # ============================================================

    def _save_base_position(self) -> None:
        """保存当前窗口坐标作为动画基准位置。"""
        self._base_position = self.pos()

    def _animate_bounce(self) -> None:
        """执行上下弹跳动画。"""
        self._save_base_position()

        if self._bounce_animation is not None:
            self._bounce_animation.stop()

        distance = self._config.bounce_distance
        start_y = self._base_position.y()

        animation = QPropertyAnimation(self, b"pos", self)
        animation.setDuration(self._config.bounce_duration)
        animation.setEasingCurve(QEasingCurve.Type.OutBounce)
        animation.setStartValue(QPoint(self._base_position.x(), start_y))
        animation.setKeyValueAt(0.3, QPoint(self._base_position.x(), start_y - distance))
        animation.setKeyValueAt(0.6, QPoint(self._base_position.x(), start_y - int(distance * 0.4)))
        animation.setEndValue(self._base_position)

        self._bounce_animation = animation
        animation.start()

    # ============================================================
    #  鼠标事件
    # ============================================================

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标点击：触发弹跳动画 + 音效 + 自定义回调。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._animate_bounce()
            self._play_sound()
            self.clicked.emit()

            if self._on_click_callback is not None:
                try:
                    self._on_click_callback()
                except Exception as exc:
                    logger.warning("点击回调执行失败: %s", exc)

            event.accept()
        else:
            super().mousePressEvent(event)

    # ============================================================
    #  扩展接口
    # ============================================================

    def set_mood(self, mood: str) -> None:
        """切换表情/心情。

        当前实现为切换 emoji 文字作为简单示意。可通过覆写此方法实现更复杂的表情切换（如加载不同图片）。

        预置映射:
            normal → 🐱
            happy  → 😸
            sad    → 😿
            angry  → 😾

        Args:
            mood: 心情标识符。
        """
        self._mood = mood

        # 预置表情映射（仅当没有自定义图片时生效）
        MOOD_EMOJI_MAP = {
            "normal": "🐱",
            "happy": "😸",
            "sad": "😿",
            "angry": "😾",
            "love": "😻",
            "surprised": "😹",
        }
        emoji = MOOD_EMOJI_MAP.get(mood, mood)
        self._config.emoji_text = emoji

        if self._config.resolve_image_path() is None:
            self._set_emoji_text(emoji)

        self.mood_changed.emit(mood)

    def get_mood(self) -> str:
        """获取当前心情标识符。"""
        return self._mood

    def add_action(self, name: str, callback: Callable[[], None]) -> None:
        """注册一个自定义动作。

        注册后的动作可通过名称查找和管理。当前版本动作不会自动绑定到 UI，
        主要供外部通过名称查找并手动调用，或供未来扩展（如右键菜单）。

        Args:
            name: 动作名称（唯一标识）。
            callback: 动作回调函数。
        """
        self._custom_actions[name] = callback

    def remove_action(self, name: str) -> bool:
        """移除已注册的自定义动作。

        Args:
            name: 动作名称。

        Returns:
            是否成功移除。
        """
        if name in self._custom_actions:
            del self._custom_actions[name]
            return True
        return False

    def get_action(self, name: str) -> Callable[[], None] | None:
        """获取已注册的自定义动作。

        Args:
            name: 动作名称。

        Returns:
            回调函数，未找到返回 None。
        """
        return self._custom_actions.get(name)

    def invoke_action(self, name: str) -> bool:
        """按名称执行已注册的自定义动作。

        Args:
            name: 动作名称。

        Returns:
            是否存在并成功调用。
        """
        callback = self._custom_actions.get(name)
        if callback is not None:
            try:
                callback()
                return True
            except Exception as exc:
                logger.warning("执行动作 '%s' 失败: %s", name, exc)
                return False
        return False

    def set_on_click_callback(self, callback: Callable[[], None] | None) -> None:
        """设置点击时额外执行的回调（在弹跳动画和音效之后调用）。

        不覆盖已有的内部点击处理，仅追加一个可选的用户回调。

        Args:
            callback: 回调函数，传 None 可清除。
        """
        self._on_click_callback = callback

    # ============================================================
    #  配置访问
    # ============================================================

    @property
    def config(self) -> CharacterConfig:
        """获取当前配置的只读副本。"""
        return self._config

    def update_config(self, config: CharacterConfig) -> None:
        """整体更新配置并重新应用外观/音效设置。

        Args:
            config: 新的配置对象。
        """
        self._config = config
        self._setup_appearance()
        self._init_sound()
        self._mood = config.default_mood
