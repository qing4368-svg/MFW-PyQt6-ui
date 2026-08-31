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
桌面小人模块 (Desktop Character / Mascot)

提供:
- CharacterConfig:     小人配置数据类
- CharacterWidget:     小人控件（QLabel 子类，带弹跳动画 & 音效）
- CharacterController: 小人显示模式管理器（主窗口模式 / 桌面悬浮模式）
"""

from app.view.character.character_config import CharacterConfig
from app.view.character.character_widget import CharacterWidget
from app.view.character.character_controller import CharacterController
from app.view.character.desktop_character import DesktopCharacter

__all__ = [
    "CharacterConfig",
    "CharacterWidget",
    "CharacterController",
    "DesktopCharacter",
]
