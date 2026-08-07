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
桌面小人配置数据类

可修改此文件中的默认值来定制小人的外观和行为。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# --- 默认角色图片路径（相对于项目根目录） ---
DEFAULT_IMAGE_PATH = "./app/assets/char.png"

# --- 默认角色 Emoji（当未指定图片时使用） ---
DEFAULT_CHARACTER_EMOJI = "🐱"

# --- 默认音效路径（相对于项目根目录） ---
DEFAULT_SOUND_PATH = "./app/assets/sounds/character_click.wav"

# --- 默认尺寸 ---
DEFAULT_CHARACTER_SIZE = 80  # 像素


@dataclass
class CharacterConfig:
    """桌面小人配置。

    所有字段均可通过构造参数覆盖，未提供的字段使用类级别默认值。

    Attributes:
        image_path:     角色图片路径（为空时使用 emoji 占位）。
        emoji_text:     当 image_path 无效时显示的 emoji 文字。
        sound_path:     点击时播放的音效文件路径（为空则不播放）。
        sound_volume:   音效音量（0.0 ~ 1.0）。
        widget_size:    小人控件尺寸（宽高相同）。
        default_mood:   初始表情/心情标识（供 set_mood() 使用）。
        position_offset:主窗口模式下距右下角的偏移 (x_offset, y_offset)。
        float_position: 桌面悬浮模式下的初始位置 (x, y)，为 None 时使用默认位置。
        bounce_distance:点击弹跳动画的位移（像素）。
        bounce_duration:弹跳动画持续时间（毫秒）。
        enabled:        是否启用桌面小人功能。
        float_on_minimize:主窗口最小化时是否自动切换到桌面悬浮模式。
    """

    # --- 外观 ---
    image_path: str = DEFAULT_IMAGE_PATH
    emoji_text: str = DEFAULT_CHARACTER_EMOJI
    widget_size: int = DEFAULT_CHARACTER_SIZE

    # --- 音效 ---
    sound_path: str = DEFAULT_SOUND_PATH
    sound_volume: float = 0.5

    # --- 行为 ---
    default_mood: str = "normal"
    bounce_distance: int = 12
    bounce_duration: int = 250  # 毫秒

    # --- 位置 ---
    position_offset: tuple[int, int] = field(default_factory=lambda: (20, 20))
    float_position: tuple[int, int] | None = None

    # --- 开关 ---
    enabled: bool = True
    float_on_minimize: bool = True

    # ============================================================
    #  便捷方法
    # ============================================================

    def resolve_image_path(self) -> Path | None:
        """解析图片路径，返回存在的文件路径或 None。"""
        if not self.image_path:
            return None
        candidate = Path(self.image_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate if candidate.is_file() else None

    def resolve_sound_path(self) -> Path | None:
        """解析音效路径，返回存在的文件路径或 None。"""
        if not self.sound_path:
            return None
        candidate = Path(self.sound_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate if candidate.is_file() else None

    def to_dict(self) -> dict:
        """序列化为字典，用于持久化存储。"""
        return {
            "image_path": self.image_path,
            "emoji_text": self.emoji_text,
            "sound_path": self.sound_path,
            "sound_volume": self.sound_volume,
            "widget_size": self.widget_size,
            "default_mood": self.default_mood,
            "bounce_distance": self.bounce_distance,
            "bounce_duration": self.bounce_duration,
            "position_offset": list(self.position_offset),
            "float_position": (
                list(self.float_position)
                if self.float_position is not None
                else None
            ),
            "enabled": self.enabled,
            "float_on_minimize": self.float_on_minimize,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CharacterConfig:
        """从字典反序列化，用于从持久化存储恢复。"""
        if not isinstance(data, dict):
            return cls()

        def _tuple_from_key(key: str) -> tuple[int, int] | None:
            val = data.get(key)
            if isinstance(val, list) and len(val) == 2:
                return (int(val[0]), int(val[1]))
            if isinstance(val, tuple) and len(val) == 2:
                return (int(val[0]), int(val[1]))
            return None

        return cls(
            image_path=str(data.get("image_path", "")),
            emoji_text=str(data.get("emoji_text", DEFAULT_CHARACTER_EMOJI)),
            sound_path=str(data.get("sound_path", DEFAULT_SOUND_PATH)),
            sound_volume=float(data.get("sound_volume", 0.5)),
            widget_size=int(data.get("widget_size", DEFAULT_CHARACTER_SIZE)),
            default_mood=str(data.get("default_mood", "normal")),
            bounce_distance=int(data.get("bounce_distance", 12)),
            bounce_duration=int(data.get("bounce_duration", 250)),
            position_offset=_tuple_from_key("position_offset") or (20, 20),
            float_position=_tuple_from_key("float_position"),
            enabled=bool(data.get("enabled", True)),
            float_on_minimize=bool(data.get("float_on_minimize", True)),
        )
