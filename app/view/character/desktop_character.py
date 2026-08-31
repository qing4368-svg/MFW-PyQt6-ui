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
桌面悬浮小人（独立设计）

独立于主窗口内小人的桌面悬浮角色，具备：
- 角色图片 + 聊天气泡（气泡显示任务名 / 触发词）
- 点击播放音效
- 连续点击 5 次返回应用
- 上方设置按钮：气泡开关 / 音量 / 透明度 / 可拖动开关
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRect, Qt, QTimer, Signal, QPropertyAnimation
from PySide6.QtGui import QPixmap, QMouseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.common.config import cfg

logger = logging.getLogger(__name__)

# --- 资源路径 ---
CHARACTER_IMAGE = "./app/assets/Desktop_png/character_1.png"
BUBBLE_IMAGE = "./app/assets/Desktop_png/Bubble.png"
CLICK_SOUND = "./app/assets/sounds/character_click_Desktop.mp3"

# --- 尺寸 ---
CHARACTER_SIZE = 150
BUBBLE_SIZE = 240          # 气泡显示尺寸（正方形）
BUBBLE_OVERLAP = 50        # 气泡与人物重叠像素
BUBBLE_Y_OFFSET = 80       # 气泡向下偏移，使气泡与人物重叠更多

# --- 气泡白色文字框在 Bubble.png 内的相对位置（0~1，基于 1000x1000 原图） ---
# 白框区域：x 66~556，y 117~532
BUBBLE_WHITE_BOX = (0.066, 0.117, 0.556, 0.532)  # (x0, y0, x1, y1)

# --- 人物实际视觉中心在 character_1.png 内的相对位置（0~1，基于 1000x1000 原图） ---
# 内容区域：x 338~1000，y 72~1000 → 中心约 (66.9%, 53.6%)
CHAR_VISUAL_CENTER = (0.669, 0.536)

# --- 点击计数超时（毫秒），防止误触 ---
CLICK_RESET_TIMEOUT_MS = 2000

# --- 连续点击次数阈值（达到后返回应用） ---
RETURN_CLICK_COUNT = 5


def _resolve(path: str) -> Path | None:
    """解析资源路径，返回存在的文件路径或 None。"""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p if p.is_file() else None


class DesktopCharacter(QWidget):
    """桌面悬浮小人控件。

    包含角色图片、聊天气泡、设置面板，以及点击计数逻辑。

    Args:
        get_task_name: 可选回调，返回当前执行的任务名（无任务返回 None 或空串）。
    """

    # --- 信号 ---
    go_home_requested = Signal()  # 连续点击 5 次后请求返回应用

    def __init__(self, get_task_name: Callable[[], str | None] | None = None):
        super().__init__(None)
        self._get_task_name = get_task_name

        # --- 窗口标志：无边框、置顶、透明 ---
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
        self.setObjectName("DesktopCharacter")

        # --- 状态 ---
        self._click_count = 0
        self._dragging = False
        self._mouse_pressed = False
        self._drag_start_pos = QPoint()
        self._settings_visible = False

        # --- 缩放动画 ---
        self._scale_animation = None

        # --- 音效播放器池（mp3 需要 QMediaPlayer；多实例避免互相打断） ---
        self._players: list = []
        self._player_index = 0
        self._init_sound()

        # --- 透明度 ---
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)

        # --- 构建 UI ---
        self._build_ui()

        # --- 点击计数重置定时器 ---
        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.setInterval(CLICK_RESET_TIMEOUT_MS)
        self._reset_timer.timeout.connect(self._reset_click_count)

        # --- 返回应用定时器 ---
        self._return_timer = QTimer(self)
        self._return_timer.setSingleShot(True)
        self._return_timer.setInterval(1000)
        self._return_timer.timeout.connect(self._do_return_home)

        # --- 应用初始配置 ---
        self._apply_config()

    # ============================================================
    #  UI 构建
    # ============================================================

    def _build_ui(self) -> None:
        """构建悬浮小人界面（气泡叠加在小人上，文本在白色框内）。"""
        # --- 窗口尺寸 ---
        win_w = BUBBLE_SIZE
        win_h = BUBBLE_SIZE + CHARACTER_SIZE - BUBBLE_OVERLAP
        self.setFixedSize(win_w, win_h)

        # --- 角色图片（底层） ---
        self._char_label = QLabel(self)
        self._char_label.resize(CHARACTER_SIZE, CHARACTER_SIZE)  # 用 resize 允许缩放动画改变尺寸
        self._char_label.setScaledContents(True)  # 图片随控件缩放
        self._char_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._char_label.setCursor(Qt.CursorShape.PointingHandCursor)
        # 鼠标事件穿透，让点击直接落到 DesktopCharacter 本体
        self._char_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        char_pixmap = self._load_pixmap(CHARACTER_IMAGE)
        if char_pixmap is not None:
            self._char_label.setPixmap(
                char_pixmap.scaled(
                    CHARACTER_SIZE, CHARACTER_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        # 人物定位在底部，与气泡尾部重叠
        char_x = (win_w - CHARACTER_SIZE) // 2
        char_y = BUBBLE_SIZE - BUBBLE_OVERLAP
        self._char_label.move(char_x, char_y)
        # 记录人物原始几何（缩放动画的基准，避免连点时基准漂移）
        self._char_base_geo = self._char_label.geometry()

        # --- 聊天气泡（叠加在人物上方） ---
        self._bubble = QLabel(self)
        self._bubble.setFixedSize(BUBBLE_SIZE, BUBBLE_SIZE)
        self._bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bubble.setStyleSheet("background: transparent;")
        # 鼠标事件穿透，让点击直接落到 DesktopCharacter 本体
        self._bubble.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bubble_pixmap = self._load_pixmap(BUBBLE_IMAGE)
        if bubble_pixmap is not None:
            self._bubble.setPixmap(
                bubble_pixmap.scaled(
                    BUBBLE_SIZE, BUBBLE_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._bubble.setScaledContents(False)
        self._bubble.move(0, BUBBLE_Y_OFFSET)
        self._bubble.hide()

        # --- 气泡文字（位于白色框内） ---
        wx0, wy0, wx1, wy1 = BUBBLE_WHITE_BOX
        text_x = int(wx0 * BUBBLE_SIZE) + 6
        text_y = int(wy0 * BUBBLE_SIZE) + 4
        text_w = int((wx1 - wx0) * BUBBLE_SIZE) - 12
        text_h = int((wy1 - wy0) * BUBBLE_SIZE) - 8
        self._bubble_text = QLabel(self._bubble)
        self._bubble_text.setGeometry(text_x, text_y, text_w, text_h)
        self._bubble_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bubble_text.setWordWrap(True)
        self._bubble_text.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: 600;"
        )
        self._bubble_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # --- 设置按钮（右上角） ---
        self._settings_btn = QPushButton("⚙", self)
        self._settings_btn.setFixedSize(32, 32)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.8); border: 1px solid #bbb;"
            " border-radius: 16px; font-size: 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,1); }"
        )
        self._settings_btn.clicked.connect(self._toggle_settings)
        self._settings_btn.move(win_w - 40, BUBBLE_Y_OFFSET + 4)

        # --- 设置面板 ---
        self._settings_panel = self._build_settings_panel()
        self._settings_panel.hide()

        # 气泡置于人物上层
        self._bubble.raise_()
        self._settings_btn.raise_()

    def _build_settings_panel(self) -> QFrame:
        """构建设置面板。"""
        panel = QFrame(self)
        panel.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.96); border: 1px solid #ccc;"
            " border-radius: 8px; }"
            "QLabel { background: transparent; color: #333; font-size: 13px; }"
            "QCheckBox { background: transparent; color: #333; font-size: 13px; }"
            "QSlider::groove:horizontal { height: 4px; background: #ddd; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0;"
            " background: #4a90d9; border-radius: 7px; }"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 气泡开关
        self._bubble_check = QCheckBox("弹出文字框", panel)
        self._bubble_check.toggled.connect(self._on_bubble_toggled)
        layout.addWidget(self._bubble_check)

        # 音量
        vol_row = QHBoxLayout()
        vol_label = QLabel("音量", panel)
        self._volume_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(vol_label)
        vol_row.addWidget(self._volume_slider, 1)
        layout.addLayout(vol_row)

        # 透明度
        opa_row = QHBoxLayout()
        opa_label = QLabel("透明度", panel)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self._opacity_slider.setRange(30, 100)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opa_row.addWidget(opa_label)
        opa_row.addWidget(self._opacity_slider, 1)
        layout.addLayout(opa_row)

        # 可拖动
        self._drag_check = QCheckBox("允许拖动", panel)
        self._drag_check.toggled.connect(self._on_draggable_toggled)
        layout.addWidget(self._drag_check)

        panel.setFixedSize(200, 150)
        return panel

    # ============================================================
    #  资源配置
    # ============================================================

    @staticmethod
    def _load_pixmap(path: str) -> QPixmap | None:
        """加载图片资源。"""
        resolved = _resolve(path)
        if resolved is None:
            logger.warning("资源不存在: %s", path)
            return None
        pixmap = QPixmap(str(resolved))
        if pixmap.isNull():
            logger.warning("无法加载图片: %s", path)
            return None
        return pixmap

    def _init_sound(self) -> None:
        """初始化音效播放器池（mp3 需 QMediaPlayer；多实例避免互相打断）。"""
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl

            sound_path = _resolve(CLICK_SOUND)
            url = QUrl.fromLocalFile(str(sound_path)) if sound_path is not None else None

            # 创建 4 个播放器，轮询播放，互不打断
            for _ in range(4):
                player = QMediaPlayer(self)
                audio_output = QAudioOutput(self)
                player.setAudioOutput(audio_output)
                if url is not None:
                    player.setSource(url)
                self._players.append((player, audio_output))
        except Exception as exc:
            logger.warning("初始化音效失败: %s", exc)
            self._players = []

    def _play_sound(self) -> None:
        """播放点击音效（轮询播放器，不打断上一次声音）。"""
        if not self._players:
            return
        try:
            player, audio_output = self._players[self._player_index]
            self._player_index = (self._player_index + 1) % len(self._players)
            # 应用当前音量
            volume = int(cfg.get(cfg.desktop_character_volume))
            audio_output.setVolume(volume / 100.0)
            player.setPosition(0)
            player.play()
        except Exception as exc:
            logger.debug("播放音效失败: %s", exc)

    # ============================================================
    #  配置应用
    # ============================================================

    def _apply_config(self) -> None:
        """从全局配置读取并应用设置。"""
        # 气泡开关
        bubble_enabled = bool(cfg.get(cfg.desktop_character_bubble))
        self._bubble_check.setChecked(bubble_enabled)
        # 音量
        volume = int(cfg.get(cfg.desktop_character_volume))
        self._volume_slider.setValue(volume)
        self._apply_volume(volume)
        # 透明度
        opacity = int(cfg.get(cfg.desktop_character_opacity))
        self._opacity_slider.setValue(opacity)
        self._apply_opacity(opacity)
        # 可拖动
        draggable = bool(cfg.get(cfg.desktop_character_draggable))
        self._drag_check.setChecked(draggable)

    def _apply_volume(self, value: int) -> None:
        """应用音量设置到所有播放器。"""
        for _, audio_output in self._players:
            try:
                audio_output.setVolume(value / 100.0)
            except Exception:
                pass

    def _apply_opacity(self, value: int) -> None:
        """应用透明度设置。"""
        self._opacity_effect.setOpacity(value / 100.0)

    # ============================================================
    #  设置面板事件
    # ============================================================

    def _toggle_settings(self) -> None:
        """显示/隐藏设置面板。"""
        self._settings_visible = not self._settings_visible
        self._settings_panel.setVisible(self._settings_visible)
        if self._settings_visible:
            # 面板放在设置按钮下方
            x = max(0, self.width() - self._settings_panel.width())
            self._settings_panel.move(x, self._settings_btn.y() + 40)
            self._settings_panel.raise_()

    def _on_bubble_toggled(self, checked: bool) -> None:
        cfg.set(cfg.desktop_character_bubble, bool(checked))
        if not checked:
            self._bubble.hide()

    def _on_volume_changed(self, value: int) -> None:
        cfg.set(cfg.desktop_character_volume, int(value))
        self._apply_volume(value)

    def _on_opacity_changed(self, value: int) -> None:
        cfg.set(cfg.desktop_character_opacity, int(value))
        self._apply_opacity(value)

    def _on_draggable_toggled(self, checked: bool) -> None:
        cfg.set(cfg.desktop_character_draggable, bool(checked))

    # ============================================================
    #  气泡显示
    # ============================================================

    def _show_bubble(self, text: str) -> None:
        """显示气泡文字。"""
        if not bool(cfg.get(cfg.desktop_character_bubble)):
            return
        self._bubble_text.setText(text)
        self._bubble.show()

    def _hide_bubble(self) -> None:
        """隐藏气泡。"""
        self._bubble.hide()

    # ============================================================
    #  缩放动画
    # ============================================================

    def _animate_scale(self) -> None:
        """点击后整体放大 1.25 倍再弹回（以人物视觉中心为锚点）。"""
        if not hasattr(self, "_char_label") or self._char_label is None:
            return

        # 始终使用记录的原始几何作为基准，避免连点时基准漂移
        base_geo = getattr(self, "_char_base_geo", self._char_label.geometry())
        scale = 1.25
        scaled_w = int(base_geo.width() * scale)
        scaled_h = int(base_geo.height() * scale)
        # 以人物视觉中心为锚点缩放：锚点位置保持不动
        anchor_x, anchor_y = CHAR_VISUAL_CENTER
        dx = int((scaled_w - base_geo.width()) * anchor_x)
        dy = int((scaled_h - base_geo.height()) * anchor_y)
        scaled_geo = QRect(
            base_geo.x() - dx, base_geo.y() - dy, scaled_w, scaled_h
        )

        if self._scale_animation is not None:
            self._scale_animation.stop()

        # 先复位到基准几何，再启动动画，避免残留放大状态
        self._char_label.setGeometry(base_geo)

        self._scale_animation = QPropertyAnimation(self._char_label, b"geometry", self)
        self._scale_animation.setDuration(280)
        self._scale_animation.setStartValue(base_geo)
        self._scale_animation.setKeyValueAt(0.35, scaled_geo)
        self._scale_animation.setEndValue(base_geo)
        self._scale_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._scale_animation.start()

    # ============================================================
    #  点击计数逻辑
    # ============================================================

    def _on_character_clicked(self) -> None:
        """角色被点击（非拖拽）。"""
        self._play_sound()
        self._animate_scale()
        self._click_count += 1
        # 重置计数超时定时器
        self._reset_timer.start()

        if self._click_count == 1:
            task_name = None
            if self._get_task_name is not None:
                try:
                    task_name = self._get_task_name()
                except Exception:
                    task_name = None
            if task_name:
                self._show_bubble(f"当前执行：{task_name}")
            else:
                self._show_bubble("当前无执行任务")
        elif self._click_count == 2:
            self._show_bubble("凑杂鱼")
        elif self._click_count >= RETURN_CLICK_COUNT:
            # 达到阈值：弹出"杂鱼杂鱼杂鱼"，1 秒后返回应用
            self._show_bubble("杂鱼杂鱼杂鱼")
            self._reset_timer.stop()
            self._return_timer.start()
            self._click_count = 0
        else:
            # 3、4 次点击：保持"凑杂鱼"
            self._show_bubble("凑杂鱼")

    def _reset_click_count(self) -> None:
        """超时后清理点击计数，防止误触。"""
        self._click_count = 0
        self._hide_bubble()

    def _do_return_home(self) -> None:
        """返回应用（1 秒延迟后触发）。"""
        self._hide_bubble()
        self.go_home_requested.emit()

    # ============================================================
    #  拖拽逻辑
    # ============================================================

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """记录按下位置，不立即判定拖拽。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_pressed = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """按下且移动超过阈值才拖拽窗口（仅在可拖动时）。"""
        if not self._mouse_pressed:
            return
        if not bool(cfg.get(cfg.desktop_character_draggable)):
            return
        if not self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            if delta.manhattanLength() >= 6:
                self._dragging = True
                self._drag_start_pos = event.globalPosition().toPoint() - self.window().pos()
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.window().move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """释放：未拖拽视为点击；已拖拽结束拖拽。"""
        if event.button() == Qt.MouseButton.LeftButton and self._mouse_pressed:
            self._mouse_pressed = False
            if not self._dragging:
                self._on_character_clicked()
            else:
                self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ============================================================
    #  定位
    # ============================================================

    def move_to_bottom_right(self) -> None:
        """移动到主屏幕右下角。"""
        screens = QApplication.screens()
        if not screens:
            return
        geo = screens[0].availableGeometry()
        self.move(geo.right() - self.width() - 30, geo.bottom() - self.height() - 30)

    # ============================================================
    #  清理
    # ============================================================

    def dispose(self) -> None:
        """释放资源。"""
        try:
            self._reset_timer.stop()
            self._return_timer.stop()
        except Exception:
            pass
        try:
            self._scale_animation = None
        except Exception:
            pass
        for player, _ in self._players:
            try:
                player.stop()
            except Exception:
                pass
        self._players = []
