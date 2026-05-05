# -*- coding: utf-8 -*-
"""
NotebookLM ETL Pipeline - Windows 데스크톱 GUI 관리 도구
tkinter를 사용하여 Windows 환경에서 동작하는 직관적인 GUI를 제공합니다.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, font as tkfont
import threading
import asyncio
import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import SettingsManager, AppSettings
from utils.logger import setup_logger
from extractors.email_extractor import EmailItem
from extractors.browser_extractor import BrowserHistoryItem
from extractors.kakao_extractor import KakaoMessage
from extractors.web_scraper import WebContent

logger = setup_logger("gui")


class WindowsStartupManager:
    """Windows 시작 프로그램 등록 관리"""
    
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "NotebookLM_ETL_Manager"

    @staticmethod
    def is_registered() -> bool:
        if sys.platform != "win32": return False
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WindowsStartupManager.REG_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, WindowsStartupManager.APP_NAME)
                return True
        except WindowsError:
            return False

    @staticmethod
    def register():
        if sys.platform != "win32": return
        import winreg
        # pythonw.exe를 사용하여 콘솔 없이 실행되도록 등록
        cmd = f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{Path(__file__).parent.parent / "main.py"}" --daemon'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WindowsStartupManager.REG_PATH, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, WindowsStartupManager.APP_NAME, 0, winreg.REG_SZ, cmd)

    @staticmethod
    def unregister():
        if sys.platform != "win32": return
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WindowsStartupManager.REG_PATH, 0, winreg.KEY_WRITE) as key:
                winreg.DeleteValue(key, WindowsStartupManager.APP_NAME)
        except WindowsError:
            pass

# 색상 테마 (모던 다크/라이트 테마)
COLORS = {
    "primary": "#1a73e8",       # Google Blue
    "primary_dark": "#1557b0",
    "secondary": "#34a853",     # Google Green
    "warning": "#fbbc04",       # Google Yellow
    "danger": "#ea4335",        # Google Red
    "bg_main": "#f8f9fa",
    "bg_card": "#ffffff",
    "bg_sidebar": "#202124",
    "text_primary": "#202124",
    "text_secondary": "#5f6368",
    "text_light": "#ffffff",
    "border": "#dadce0",
    "success": "#34a853",
}


def get_best_font(size=9, bold=False):
    """시스템에서 사용 가능한 최적의 한글 폰트를 반환합니다."""
    families = tkfont.families()
    korean_fonts = [
        "Malgun Gothic", "NanumGothic", "Nanum Gothic", "NanumBarunGothic", 
        "NanumMyeongjo", "Noto Sans CJK KR", "Noto Sans KR", "Apple SD Gothic Neo", 
        "UnDotum", "Baekmuk Gulim", "Dotum", "Gulim", "Ubuntu", "DejaVu Sans"
    ]
    
    selected_family = "sans-serif" # 기본값
    for font in korean_fonts:
        if font in families:
            selected_family = font
            break
            
    style = "bold" if bold else "normal"
    return (selected_family, size, style)


class StatusBar(tk.Frame):
    """하단 상태 표시줄"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["bg_sidebar"], height=28, **kwargs)
        self.pack_propagate(False)

        self._status_label = tk.Label(
            self, text="준비", bg=COLORS["bg_sidebar"],
            fg=COLORS["text_light"], font=get_best_font(9)
        )
        self._status_label.pack(side=tk.LEFT, padx=10)

        self._time_label = tk.Label(
            self, text="", bg=COLORS["bg_sidebar"],
            fg=COLORS["text_secondary"], font=get_best_font(9)
        )
        self._time_label.pack(side=tk.RIGHT, padx=10)

        self._update_time()

    def set_status(self, message: str, color: str = None):
        """상태 메시지를 업데이트합니다."""
        self._status_label.config(
            text=message,
            fg=color or COLORS["text_light"]
        )

    def _update_time(self):
        """현재 시간을 업데이트합니다."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._time_label.config(text=now)
        self.after(1000, self._update_time)


class DashboardTab(tk.Frame):
    """대시보드 탭 - 현재 상태 및 통계 표시"""

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=COLORS["bg_main"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        """UI 구성."""
        # 헤더
        header = tk.Frame(self, bg=COLORS["bg_main"])
        header.pack(fill=tk.X, padx=20, pady=(20, 10))

        tk.Label(
            header, text="📊 대시보드",
            font=get_best_font(18, True),
            bg=COLORS["bg_main"], fg=COLORS["text_primary"]
        ).pack(side=tk.LEFT)

        # 마지막 동기화 시간
        self._last_sync_label = tk.Label(
            header, text="마지막 동기화: 없음",
            font=get_best_font(10),
            bg=COLORS["bg_main"], fg=COLORS["text_secondary"]
        )
        self._last_sync_label.pack(side=tk.RIGHT)

        # 통계 카드 영역
        cards_frame = tk.Frame(self, bg=COLORS["bg_main"])
        cards_frame.pack(fill=tk.X, padx=20, pady=10)

        self._stat_cards = {}
        stats = [
            ("total_collected", "총 수집 항목", "0", COLORS["primary"]),
            ("uploaded_sources", "업로드된 소스", "0", COLORS["secondary"]),
            ("filtered_out", "필터링 제외", "0", COLORS["warning"]),
            ("available_slots", "사용 가능 슬롯", "45", COLORS["danger"]),
        ]

        for i, (key, label, value, color) in enumerate(stats):
            card = self._create_stat_card(cards_frame, label, value, color)
            card.grid(row=0, column=i, padx=8, pady=5, sticky="ew")
            self._stat_cards[key] = card
            cards_frame.columnconfigure(i, weight=1)

        # 빠른 실행 버튼
        action_frame = tk.LabelFrame(
            self, text="빠른 실행",
            font=get_best_font(11, True),
            bg=COLORS["bg_main"], fg=COLORS["text_primary"],
            padx=15, pady=10
        )
        action_frame.pack(fill=tk.X, padx=20, pady=10)

        btn_configs = [
            ("▶ 지금 동기화 실행", COLORS["primary"], self.app.run_sync_now),
            ("📧 이메일만 수집", COLORS["secondary"], lambda: self.app.run_partial_sync("email")),
            ("🌐 브라우저 히스토리", COLORS["warning"], lambda: self.app.run_partial_sync("browser")),
            ("🗑 오래된 소스 정리", COLORS["danger"], self.app.cleanup_old_sources),
        ]

        for i, (text, color, cmd) in enumerate(btn_configs):
            btn = tk.Button(
                action_frame, text=text,
                font=get_best_font(10),
                bg=color, fg="white",
                relief=tk.FLAT, padx=15, pady=8,
                cursor="hand2", command=cmd,
                activebackground=COLORS["primary_dark"],
                activeforeground="white"
            )
            btn.grid(row=0, column=i, padx=5, pady=5)

        # 활동 로그
        log_frame = tk.LabelFrame(
            self, text="최근 활동 로그",
            font=get_best_font(11, True),
            bg=COLORS["bg_main"], fg=COLORS["text_primary"],
            padx=10, pady=10
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4",
            height=12, state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 로그 색상 태그 설정
        self.log_text.tag_config("INFO", foreground="#4fc3f7")
        self.log_text.tag_config("SUCCESS", foreground="#81c784")
        self.log_text.tag_config("WARNING", foreground="#ffb74d")
        self.log_text.tag_config("ERROR", foreground="#e57373")

    def _create_stat_card(self, parent, label: str, value: str, color: str) -> tk.Frame:
        """통계 카드 위젯 생성."""
        card = tk.Frame(
            parent, bg=COLORS["bg_card"],
            relief=tk.FLAT,
            highlightbackground=COLORS["border"],
            highlightthickness=1
        )

        # 색상 바
        color_bar = tk.Frame(card, bg=color, height=4)
        color_bar.pack(fill=tk.X)

        # 값
        value_label = tk.Label(
            card, text=value,
            font=("Malgun Gothic", 24, "bold"),
            bg=COLORS["bg_card"], fg=color
        )
        value_label.pack(pady=(10, 2))
        card._value_label = value_label

        # 라벨
        tk.Label(
            card, text=label,
            font=get_best_font(9),
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"]
        ).pack(pady=(0, 10))

        return card

    def update_stats(self, stats: Dict[str, Any]):
        """통계 카드를 업데이트합니다."""
        if "total_collected" in stats:
            self._stat_cards["total_collected"]._value_label.config(
                text=str(stats["total_collected"])
            )
        if "uploaded_sources" in stats:
            self._stat_cards["uploaded_sources"]._value_label.config(
                text=str(stats["uploaded_sources"])
            )
        if "last_sync" in stats:
            self._last_sync_label.config(text=f"마지막 동기화: {stats['last_sync']}")

    def append_log(self, message: str, level: str = "INFO"):
        """로그 메시지를 추가합니다."""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] ", "INFO")
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)


class SettingsTab(tk.Frame):
    """설정 탭 - 이메일, 브라우저, 키워드 등 설정"""

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=COLORS["bg_main"], **kwargs)
        self.app = app
        self.settings = app.settings_manager.get()
        self._vars = {}
        self._build_ui()

    def _build_ui(self):
        """UI 구성."""
        # 헤더
        header = tk.Frame(self, bg=COLORS["bg_main"])
        header.pack(fill=tk.X, padx=20, pady=(20, 10))

        tk.Label(
            header, text="⚙️ 설정",
            font=get_best_font(18, True),
            bg=COLORS["bg_main"], fg=COLORS["text_primary"]
        ).pack(side=tk.LEFT)

        save_btn = tk.Button(
            header, text="💾 설정 저장",
            font=get_best_font(10),
            bg=COLORS["secondary"], fg="white",
            relief=tk.FLAT, padx=15, pady=6,
            cursor="hand2", command=self.save_settings
        )
        save_btn.pack(side=tk.RIGHT)

        # 스크롤 가능한 설정 영역
        canvas = tk.Canvas(self, bg=COLORS["bg_main"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=COLORS["bg_main"])

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 설정 섹션 생성
        self._build_email_section()
        self._build_browser_section()
        self._build_filter_section()
        self._build_notebooklm_section()
        self._build_schedule_section()

    def _build_email_section(self):
        """이메일 설정 섹션."""
        frame = self._create_section("📧 이메일 설정")

        s = self.settings.email

        # 활성화 체크박스
        self._add_checkbox(frame, "email_enabled", "이메일 수집 활성화", s.enabled, 0)

        # 이메일 제공자
        self._add_combobox(frame, "email_provider", "이메일 제공자",
                           ["naver", "gmail", "daum", "outlook"],
                           s.provider, 1)

        # 계정 정보
        self._add_entry(frame, "email_username", "이메일 주소", s.username, 2)
        self._add_entry(frame, "email_password", "앱 비밀번호", s.password, 3, show="*")

        # 수집 설정
        self._add_entry(frame, "email_days_back", "최근 N일 수집", str(s.days_back), 4)
        self._add_entry(frame, "email_max_emails", "최대 수집 수", str(s.max_emails), 5)

        # 필터 키워드
        self._add_text_area(frame, "email_keywords",
                            "수집 키워드 (줄바꿈으로 구분)",
                            "\n".join(s.filter_keywords), 6)

        tk.Label(
            frame,
            text="💡 네이버 메일: 환경설정 > POP3/IMAP 설정 > IMAP 사용함으로 설정 필요\n"
                 "    Gmail: 앱 비밀번호 생성 필요 (2단계 인증 활성화 후)",
            font=("Malgun Gothic", 8),
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            justify=tk.LEFT
        ).grid(row=7, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    def _build_browser_section(self):
        """브라우저 설정 섹션."""
        frame = self._create_section("🌐 브라우저 히스토리 설정")

        s = self.settings.browser

        self._add_checkbox(frame, "browser_enabled", "브라우저 히스토리 수집 활성화", s.enabled, 0)

        # 브라우저 선택 (체크박스 그룹)
        tk.Label(frame, text="수집할 브라우저:", font=get_best_font(10),
                 bg=COLORS["bg_card"], fg=COLORS["text_primary"]).grid(
            row=1, column=0, padx=10, pady=5, sticky="w"
        )

        browser_frame = tk.Frame(frame, bg=COLORS["bg_card"])
        browser_frame.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        for browser in ["chrome", "edge", "firefox", "whale"]:
            var = tk.BooleanVar(value=browser in s.browsers)
            self._vars[f"browser_{browser}"] = var
            tk.Checkbutton(
                browser_frame, text=browser.capitalize(),
                variable=var, bg=COLORS["bg_card"],
                font=get_best_font(9)
            ).pack(side=tk.LEFT, padx=5)

        self._add_entry(frame, "browser_days_back", "최근 N일 수집", str(s.days_back), 2)
        self._add_entry(frame, "browser_min_visits", "최소 방문 횟수", str(s.min_visit_count), 3)

        self._add_text_area(frame, "browser_exclude_domains",
                            "제외 도메인 (줄바꿈으로 구분)",
                            "\n".join(s.exclude_domains), 4)

    def _build_filter_section(self):
        """필터링 설정 섹션."""
        frame = self._create_section("🔍 필터링 설정")

        s = self.settings.filter

        self._add_text_area(frame, "filter_include_keywords",
                            "관심 키워드 (줄바꿈으로 구분)\n비어있으면 모든 내용 수집",
                            "\n".join(s.global_keywords), 0, height=6)

        self._add_text_area(frame, "filter_exclude_keywords",
                            "제외 키워드 (줄바꿈으로 구분)",
                            "\n".join(s.global_exclude_keywords), 1, height=4)

        self._add_entry(frame, "filter_min_length", "최소 콘텐츠 길이 (문자)", str(s.min_content_length), 2)

    def _build_notebooklm_section(self):
        """NotebookLM 설정 섹션."""
        frame = self._create_section("📓 NotebookLM 설정")

        s = self.settings.notebooklm

        self._add_entry(frame, "nlm_email", "Google 계정 이메일", s.google_account_email, 0)
        self._add_entry(frame, "nlm_max_sources", "노트북당 최대 소스 수", str(s.max_sources_per_notebook), 1)
        self._add_checkbox(frame, "nlm_auto_delete", "오래된 소스 자동 삭제", s.auto_delete_old_sources, 2)
        self._add_entry(frame, "nlm_retention_days", "소스 보관 기간 (일)", str(s.source_retention_days), 3)

        # 노트북 목록 관리
        tk.Label(frame, text="대상 노트북 설정:",
                 font=("Malgun Gothic", 10, "bold"),
                 bg=COLORS["bg_card"], fg=COLORS["text_primary"]).grid(
            row=4, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="w"
        )

        notebook_frame = tk.Frame(frame, bg=COLORS["bg_card"])
        notebook_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        tk.Label(notebook_frame, text="노트북 이름:",
                 font=get_best_font(9), bg=COLORS["bg_card"]).grid(row=0, column=0, padx=5)
        tk.Label(notebook_frame, text="노트북 ID:",
                 font=get_best_font(9), bg=COLORS["bg_card"]).grid(row=0, column=1, padx=5)

        self._notebook_name_var = tk.StringVar()
        self._notebook_id_var = tk.StringVar()

        tk.Entry(notebook_frame, textvariable=self._notebook_name_var,
                 width=20, font=get_best_font(9)).grid(row=1, column=0, padx=5)
        tk.Entry(notebook_frame, textvariable=self._notebook_id_var,
                 width=30, font=get_best_font(9)).grid(row=1, column=1, padx=5)

        tk.Button(
            notebook_frame, text="추가",
            font=get_best_font(9),
            bg=COLORS["primary"], fg="white",
            relief=tk.FLAT, padx=8, pady=3,
            command=self._add_notebook
        ).grid(row=1, column=2, padx=5)

        # 노트북 목록 표시
        self._notebook_listbox = tk.Listbox(
            frame, height=4, font=get_best_font(9),
            bg=COLORS["bg_main"]
        )
        self._notebook_listbox.grid(row=6, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        # 기존 노트북 로드
        for name, nb_id in s.target_notebooks.items():
            self._notebook_listbox.insert(tk.END, f"{name}: {nb_id}")

        tk.Label(
            frame,
            text="💡 NotebookLM 노트북 ID는 URL에서 확인:\n"
                 "    https://notebooklm.google.com/notebook/{노트북ID}",
            font=("Malgun Gothic", 8),
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            justify=tk.LEFT
        ).grid(row=7, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    def _build_schedule_section(self):
        """스케줄 설정 섹션."""
        frame = self._create_section("⏰ 자동 실행 스케줄")

        s = self.settings

        self._add_checkbox(frame, "schedule_enabled", "자동 실행 활성화", s.schedule_enabled, 0)
        self._add_entry(frame, "schedule_interval", "실행 주기 (시간)", str(s.schedule_interval_hours), 1)

        # Windows 자동 시작 등록 버튼
        if sys.platform == "win32":
            btn_text = "✅ 자동 시작 취소" if WindowsStartupManager.is_registered() else "🚀 Windows 시작 시 자동 실행"
            self.startup_btn = tk.Button(
                frame, text=btn_text,
                font=get_best_font(9),
                bg=COLORS["primary"] if not WindowsStartupManager.is_registered() else COLORS["warning"],
                fg="white", relief=tk.FLAT, padx=10, pady=5,
                command=self._toggle_startup
            )
            self.startup_btn.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        tk.Label(
            frame,
            text="💡 Windows 시작 시 자동 실행을 원하면 위 버튼을 누르거나 시작 프로그램에 등록하세요.\n"
                 "    설치 가이드의 'Windows 시작 프로그램 등록' 섹션을 참고하세요.",
            font=("Malgun Gothic", 8),
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            justify=tk.LEFT
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    def _toggle_startup(self):
        """Windows 시작 프로그램 등록 토글"""
        if WindowsStartupManager.is_registered():
            WindowsStartupManager.unregister()
            messagebox.showinfo("해제 완료", "Windows 시작 시 자동 실행이 해제되었습니다.")
            self.startup_btn.config(text="🚀 Windows 시작 시 자동 실행", bg=COLORS["primary"])
        else:
            WindowsStartupManager.register()
            messagebox.showinfo("등록 완료", "Windows 시작 시 자동 실행(백그라운드)이 등록되었습니다.")
            self.startup_btn.config(text="✅ 자동 시작 취소", bg=COLORS["warning"])

    def _create_section(self, title: str) -> tk.Frame:
        """설정 섹션 프레임 생성."""
        section = tk.LabelFrame(
            self.scroll_frame, text=title,
            font=get_best_font(11, True),
            bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            padx=10, pady=10,
            relief=tk.GROOVE
        )
        section.pack(fill=tk.X, padx=5, pady=8)
        section.columnconfigure(1, weight=1)
        return section

    def _add_checkbox(self, parent, key, label, value, row):
        """체크박스 추가."""
        var = tk.BooleanVar(value=value)
        self._vars[key] = var
        tk.Checkbutton(
            parent, text=label, variable=var,
            font=get_best_font(10), bg=COLORS["bg_card"]
        ).grid(row=row, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    def _add_entry(self, parent, key, label, value, row, show=None):
        """입력 필드 추가."""
        tk.Label(
            parent, text=f"{label}:",
            font=get_best_font(10), bg=COLORS["bg_card"],
            fg=COLORS["text_primary"]
        ).grid(row=row, column=0, padx=10, pady=5, sticky="w")

        var = tk.StringVar(value=value)
        self._vars[key] = var
        entry = tk.Entry(
            parent, textvariable=var,
            font=get_best_font(10), width=40,
            show=show
        )
        entry.grid(row=row, column=1, padx=10, pady=5, sticky="ew")

    def _add_combobox(self, parent, key, label, values, current, row):
        """콤보박스 추가."""
        tk.Label(
            parent, text=f"{label}:",
            font=get_best_font(10), bg=COLORS["bg_card"],
            fg=COLORS["text_primary"]
        ).grid(row=row, column=0, padx=10, pady=5, sticky="w")

        var = tk.StringVar(value=current)
        self._vars[key] = var
        combo = ttk.Combobox(
            parent, textvariable=var, values=values,
            font=get_best_font(10), width=20, state="readonly"
        )
        combo.grid(row=row, column=1, padx=10, pady=5, sticky="w")

    def _add_text_area(self, parent, key, label, value, row, height=5):
        """텍스트 영역 추가."""
        tk.Label(
            parent, text=f"{label}:",
            font=get_best_font(10), bg=COLORS["bg_card"],
            fg=COLORS["text_primary"], justify=tk.LEFT
        ).grid(row=row, column=0, padx=10, pady=5, sticky="nw")

        text_widget = tk.Text(
            parent, font=get_best_font(9),
            height=height, width=40
        )
        text_widget.insert(tk.END, value)
        text_widget.grid(row=row, column=1, padx=10, pady=5, sticky="ew")
        self._vars[key] = text_widget

    def _add_notebook(self):
        """노트북을 목록에 추가합니다."""
        name = self._notebook_name_var.get().strip()
        nb_id = self._notebook_id_var.get().strip()
        if name and nb_id:
            self._notebook_listbox.insert(tk.END, f"{name}: {nb_id}")
            self._notebook_name_var.set("")
            self._notebook_id_var.set("")

    def save_settings(self):
        """현재 설정을 저장합니다."""
        try:
            s = self.settings

            # 이메일 설정
            s.email.enabled = self._vars.get("email_enabled", tk.BooleanVar()).get()
            s.email.provider = self._vars.get("email_provider", tk.StringVar(value="naver")).get()
            s.email.username = self._vars.get("email_username", tk.StringVar()).get()
            s.email.password = self._vars.get("email_password", tk.StringVar()).get()
            s.email.days_back = int(self._vars.get("email_days_back", tk.StringVar(value="7")).get() or 7)
            s.email.max_emails = int(self._vars.get("email_max_emails", tk.StringVar(value="50")).get() or 50)

            kw_text = self._vars.get("email_keywords")
            if hasattr(kw_text, 'get'):
                keywords = kw_text.get("1.0", tk.END).strip()
                s.email.filter_keywords = [k.strip() for k in keywords.split('\n') if k.strip()]

            # 브라우저 설정
            s.browser.enabled = self._vars.get("browser_enabled", tk.BooleanVar()).get()
            s.browser.browsers = [
                b for b in ["chrome", "edge", "firefox", "whale"]
                if self._vars.get(f"browser_{b}", tk.BooleanVar()).get()
            ]
            s.browser.days_back = int(self._vars.get("browser_days_back", tk.StringVar(value="3")).get() or 3)
            s.browser.min_visit_count = int(self._vars.get("browser_min_visits", tk.StringVar(value="1")).get() or 1)

            # 필터 설정
            inc_kw = self._vars.get("filter_include_keywords")
            if hasattr(inc_kw, 'get'):
                keywords = inc_kw.get("1.0", tk.END).strip()
                s.filter.global_keywords = [k.strip() for k in keywords.split('\n') if k.strip()]

            exc_kw = self._vars.get("filter_exclude_keywords")
            if hasattr(exc_kw, 'get'):
                keywords = exc_kw.get("1.0", tk.END).strip()
                s.filter.global_exclude_keywords = [k.strip() for k in keywords.split('\n') if k.strip()]

            s.filter.min_content_length = int(
                self._vars.get("filter_min_length", tk.StringVar(value="100")).get() or 100
            )

            # NotebookLM 설정
            s.notebooklm.google_account_email = self._vars.get("nlm_email", tk.StringVar()).get()
            s.notebooklm.max_sources_per_notebook = int(
                self._vars.get("nlm_max_sources", tk.StringVar(value="45")).get() or 45
            )
            s.notebooklm.auto_delete_old_sources = self._vars.get("nlm_auto_delete", tk.BooleanVar(value=True)).get()
            s.notebooklm.source_retention_days = int(
                self._vars.get("nlm_retention_days", tk.StringVar(value="30")).get() or 30
            )

            # 노트북 목록
            s.notebooklm.target_notebooks = {}
            for item in self._notebook_listbox.get(0, tk.END):
                if ": " in item:
                    name, nb_id = item.split(": ", 1)
                    s.notebooklm.target_notebooks[name.strip()] = nb_id.strip()

            # 스케줄 설정
            s.schedule_enabled = self._vars.get("schedule_enabled", tk.BooleanVar(value=True)).get()
            s.schedule_interval_hours = int(
                self._vars.get("schedule_interval", tk.StringVar(value="6")).get() or 6
            )

            # 저장
            self.app.settings_manager.save(s)
            messagebox.showinfo("저장 완료", "설정이 성공적으로 저장되었습니다.")
            logger.info("설정 저장 완료")

        except Exception as e:
            messagebox.showerror("저장 오류", f"설정 저장 중 오류가 발생했습니다:\n{e}")
            logger.error(f"설정 저장 오류: {e}")


class SourceManagerTab(tk.Frame):
    """소스 관리 탭 - 업로드된 소스 목록 및 관리"""

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, bg=COLORS["bg_main"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        """UI 구성."""
        # 헤더
        header = tk.Frame(self, bg=COLORS["bg_main"])
        header.pack(fill=tk.X, padx=20, pady=(20, 10))

        tk.Label(
            header, text="📁 소스 관리",
            font=get_best_font(18, True),
            bg=COLORS["bg_main"], fg=COLORS["text_primary"]
        ).pack(side=tk.LEFT)

        refresh_btn = tk.Button(
            header, text="🔄 새로고침",
            font=get_best_font(10),
            bg=COLORS["primary"], fg="white",
            relief=tk.FLAT, padx=12, pady=6,
            cursor="hand2", command=self.refresh_sources
        )
        refresh_btn.pack(side=tk.RIGHT, padx=5)

        delete_btn = tk.Button(
            header, text="🗑 선택 삭제",
            font=get_best_font(10),
            bg=COLORS["danger"], fg="white",
            relief=tk.FLAT, padx=12, pady=6,
            cursor="hand2", command=self.delete_selected
        )
        delete_btn.pack(side=tk.RIGHT, padx=5)

        # 소스 목록 테이블
        table_frame = tk.Frame(self, bg=COLORS["bg_main"])
        table_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 트리뷰 (테이블)
        columns = ("title", "source_type", "notebook", "uploaded_at", "status")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            selectmode="extended"
        )

        # 컬럼 설정
        col_configs = [
            ("title", "소스 제목", 250),
            ("source_type", "소스 타입", 100),
            ("notebook", "노트북", 150),
            ("uploaded_at", "업로드 시간", 150),
            ("status", "상태", 80),
        ]

        for col_id, col_label, col_width in col_configs:
            self.tree.heading(col_id, text=col_label)
            self.tree.column(col_id, width=col_width, minwidth=50)

        # 스크롤바
        v_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # 초기 데이터 로드
        self.refresh_sources()

    def refresh_sources(self):
        """소스 목록을 새로고침합니다."""
        # 기존 항목 제거
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            from loaders.notebooklm_manager import SourceTracker
            tracker = SourceTracker()
            stats = tracker.get_statistics()

            # 각 노트북의 소스 로드
            settings = self.app.settings_manager.get()
            for nb_name, nb_id in settings.notebooklm.target_notebooks.items():
                sources = tracker.get_active_sources(nb_id)
                for source in sources:
                    self.tree.insert("", tk.END, values=(
                        source.title[:50],
                        source.source_type,
                        nb_name,
                        source.uploaded_at[:16].replace('T', ' '),
                        "활성"
                    ), tags=(source.source_id,))
            tracker.close()

        except Exception as e:
            logger.warning(f"소스 목록 로드 실패: {e}")

    def delete_selected(self):
        """선택된 소스를 삭제합니다."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("선택 없음", "삭제할 소스를 선택하세요.")
            return

        if messagebox.askyesno("삭제 확인", f"{len(selected)}개의 소스를 삭제하시겠습니까?"):
            for item_id in selected:
                self.tree.delete(item_id)
            messagebox.showinfo("삭제 완료", "선택된 소스가 삭제되었습니다.")


class NotebookLMETLApp:
    """NotebookLM ETL 파이프라인 메인 애플리케이션"""

    def __init__(self):
        self.settings_manager = SettingsManager()
        self.settings_manager.load()
        self._sync_thread: Optional[threading.Thread] = None
        self._is_syncing = False

        # 메인 윈도우 생성
        self.root = tk.Tk()
        self.root.title("NotebookLM ETL Manager v1.0")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.configure(bg=COLORS["bg_main"])

        # 아이콘 설정 (선택적)
        try:
            self.root.iconbitmap("icon.ico")
        except Exception:
            pass

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._tray_icon = None

        self._build_ui()
        self._setup_logging_handler()

    def _build_ui(self):
        """메인 UI 구성."""
        # 상단 타이틀 바
        title_bar = tk.Frame(self.root, bg=COLORS["bg_sidebar"], height=50)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        tk.Label(
            title_bar,
            text="📓 NotebookLM ETL Manager",
            font=get_best_font(14, True),
            bg=COLORS["bg_sidebar"], fg=COLORS["text_light"]
        ).pack(side=tk.LEFT, padx=20, pady=10)

        # 버전 정보
        tk.Label(
            title_bar, text="v1.0",
            font=get_best_font(9),
            bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"]
        ).pack(side=tk.RIGHT, padx=20)

        # 탭 노트북
        style = ttk.Style()
        style.configure("TNotebook", background=COLORS["bg_main"])
        style.configure("TNotebook.Tab",
                        font=get_best_font(10),
                        padding=[15, 8])

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 탭 생성
        self.dashboard_tab = DashboardTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self)
        self.source_manager_tab = SourceManagerTab(self.notebook, self)

        self.notebook.add(self.dashboard_tab, text="📊 대시보드")
        self.notebook.add(self.settings_tab, text="⚙️ 설정")
        self.notebook.add(self.source_manager_tab, text="📁 소스 관리")

        # 상태 표시줄
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        # 환경 체크 (지연 실행)
        self.root.after(1000, self.check_environment)

    def check_environment(self):
        """실행 환경 및 필수 라이브러리 체크."""
        warnings = []
        missing_playwright = False
        
        # 1. notebooklm-py 체크
        try:
            import notebooklm
        except ImportError:
            warnings.append("- notebooklm-py 라이브러리가 설치되지 않았습니다.")
            
        # 2. Playwright 체크
        try:
            import playwright
            # 라이브러리는 있지만 브라우저가 없는 경우도 체크 (추후 구현 가능)
        except ImportError:
            missing_playwright = True
            warnings.append("- playwright 라이브러리가 설치되지 않았습니다. (네이버 카페 수집 불가)")
            
        # 3. NotebookLM 인증 체크
        auth_verified = False
        try:
            import notebooklm
            # 두 가지 가능한 인증 파일명 모두 체크
            auth_dir = Path.home() / ".notebooklm"
            possible_files = ["storage.json", "storage_state.json"]
            
            if any((auth_dir / f).exists() for f in possible_files):
                auth_verified = True
        except ImportError:
            pass
            
        if not auth_verified:
            warnings.append("- NotebookLM 인증 정보 파일을 찾을 수 없습니다. (동기화 실패 시 'notebooklm auth' 재실행 권장)")
            
        if warnings:
            warn_msg = "일부 기능이 정상적으로 작동하지 않을 수 있습니다:\n\n" + "\n".join(warnings)
            self.dashboard_tab.append_log(warn_msg, "WARNING")
            
            if missing_playwright:
                if messagebox.askyesno("Playwright 설치", 
                    "웹 수집(네이버 카페 등)에 필요한 Playwright가 설치되어 있지 않습니다.\n지금 자동으로 설치하시겠습니까?\n(수 분이 소요될 수 있습니다)"):
                    self._setup_playwright_auto()
            else:
                messagebox.showwarning("환경 체크 알림", warn_msg)
        else:
            self.dashboard_tab.append_log("✅ 모든 필수 라이브러리 및 인증이 확인되었습니다.", "SUCCESS")

    def _setup_playwright_auto(self):
        """Playwright 및 브라우저 자동 설치 수행."""
        import subprocess
        
        self.dashboard_tab.append_log("⏳ Playwright 자동 설치 시작...", "INFO")
        self.status_bar.set_status("Playwright 설치 중...")
        
        def run_install():
            try:
                # 1. pip install
                self.dashboard_tab.append_log("  - 라이브러리(pip) 설치 중...", "INFO")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
                
                # 2. playwright install chromium
                self.dashboard_tab.append_log("  - 브라우저(Chromium) 설치 중...", "INFO")
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
                
                self.dashboard_tab.append_log("✅ Playwright 설치가 완료되었습니다. 프로그램을 재시작해 주세요.", "SUCCESS")
                messagebox.showinfo("설치 완료", "Playwright 설치가 완료되었습니다.\n정상적인 동작을 위해 프로그램을 재시작해 주세요.")
            except Exception as e:
                err_msg = f"❌ Playwright 설치 중 오류 발생: {e}"
                self.dashboard_tab.append_log(err_msg, "ERROR")
                messagebox.showerror("설치 오류", f"자동 설치에 실패했습니다.\n터미널에서 직접 'playwright install chromium'을 실행해 보세요.\n\n오류: {e}")
            finally:
                self.root.after(0, lambda: self.status_bar.set_status("준비"))

        threading.Thread(target=run_install, daemon=True).start()


    def _setup_logging_handler(self):
        """GUI 로그 핸들러 설정."""
        import logging

        class GUILogHandler(logging.Handler):
            def __init__(self, app):
                super().__init__()
                self.app = app

            def emit(self, record):
                try:
                    msg = self.format(record)
                    level = record.levelname
                    self.app.root.after(0, lambda: self.app.dashboard_tab.append_log(msg, level))
                except Exception:
                    pass

        handler = GUILogHandler(self)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger("notebooklm_etl").addHandler(handler)

    def run_sync_now(self):
        """전체 동기화를 즉시 실행합니다."""
        if self._is_syncing:
            messagebox.showwarning("실행 중", "동기화가 이미 진행 중입니다.")
            return

        self._is_syncing = True
        self.status_bar.set_status("동기화 실행 중...", COLORS["warning"])
        self.dashboard_tab.append_log("전체 동기화 시작", "INFO")

        def sync_worker():
            try:
                asyncio.run(self._run_full_sync())
            except Exception as e:
                logger.error(f"동기화 오류: {e}")
            finally:
                self._is_syncing = False
                self.root.after(0, lambda: self.status_bar.set_status("동기화 완료"))

        self._sync_thread = threading.Thread(target=sync_worker, daemon=True)
        self._sync_thread.start()

    async def _run_full_sync(self):
        """전체 동기화 파이프라인 실행."""
        settings = self.settings_manager.get()
        all_contents = []

        # 1. 이메일 수집
        if settings.email.enabled and settings.email.username:
            logger.info("📧 이메일 수집 시작...")
            try:
                from extractors.email_extractor import EmailExtractor
                with EmailExtractor(
                    provider=settings.email.provider,
                    username=settings.email.username,
                    password=settings.email.password
                ) as extractor:
                    emails = extractor.extract_emails(
                        days_back=settings.email.days_back,
                        max_emails=settings.email.max_emails,
                        filter_keywords=settings.email.filter_keywords
                    )
                logger.info(f"   ✓ 이메일 {len(emails)}개 수집 완료")
                all_contents.extend(emails)
            except Exception as e:
                logger.error(f"   ✗ 이메일 수집 실패: {e}")

        # 2. 브라우저 히스토리 수집
        if settings.browser.enabled:
            logger.info("🌐 브라우저 히스토리 수집 시작...")
            try:
                from extractors.browser_extractor import BrowserHistoryExtractor
                extractor = BrowserHistoryExtractor(browsers=settings.browser.browsers)
                history = extractor.extract(
                    days_back=settings.browser.days_back,
                    min_visit_count=settings.browser.min_visit_count,
                    exclude_domains=settings.browser.exclude_domains
                )
                logger.info(f"   ✓ 브라우저 히스토리 {len(history)}개 수집 완료")
                all_contents.extend(history)
            except Exception as e:
                logger.error(f"   ✗ 브라우저 히스토리 수집 실패: {e}")

        # 3. 카카오톡 수집
        if settings.kakao.enabled:
            logger.info("💬 카카오톡 메시지 수집 시작...")
            try:
                from extractors.kakao_extractor import KakaoTalkExtractor
                extractor = KakaoTalkExtractor()
                kakao_msgs = extractor.extract_via_ui_automation(
                    target_rooms=settings.kakao.target_rooms,
                    max_messages=settings.kakao.max_messages
                )
                logger.info(f"   ✓ 카카오톡 메시지 {len(kakao_msgs)}개 수집 완료")
                all_contents.extend(kakao_msgs)
            except Exception as e:
                logger.error(f"   ✗ 카카오톡 수집 실패: {e}")

        # 4. 네이버 카페 수집
        if settings.naver_cafe.enabled:
            logger.info("☕ 네이버 카페 수집 시작...")
            try:
                from extractors.web_scraper import NaverCafeScraper
                scraper = NaverCafeScraper()
                cafe_contents = []
                for url in settings.naver_cafe.cafe_urls:
                    posts = scraper.scrape_cafe_posts(
                        url,
                        keywords=settings.naver_cafe.keywords,
                        max_posts=settings.naver_cafe.max_posts
                    )
                    cafe_contents.extend(posts)
                scraper.close()
                logger.info(f"   ✓ 네이버 카페 {len(cafe_contents)}개 게시물 수집 완료")
                all_contents.extend(cafe_contents)
            except Exception as e:
                logger.error(f"   ✗ 네이버 카페 수집 실패: {e}")

        if not all_contents:
            logger.warning("⚠️ 업로드할 콘텐츠가 없습니다.")
            return

        # 5. 데이터 처리 및 변환
        logger.info("🔄 데이터 변환 및 필터링 중...")
        try:
            from transformers.filter_engine import ETLPipeline
            pipeline = ETLPipeline(settings)
            
            # 타입별로 분리하여 처리
            emails = [c for c in all_contents if isinstance(c, EmailItem)]
            history = [c for c in all_contents if isinstance(c, BrowserHistoryItem)]
            kakao = [c for c in all_contents if isinstance(c, KakaoMessage)]
            web = [c for c in all_contents if isinstance(c, WebContent)]
            
            processed_emails = pipeline.process_emails(emails)
            processed_history = pipeline.process_browser_history(history)
            processed_kakao = pipeline.process_kakao_messages(kakao)
            processed_web = pipeline.process_web_contents(web)
            
            processed_all = processed_emails + processed_history + processed_kakao + processed_web
            logger.info(f"   ✓ 총 {len(processed_all)}개 콘텐츠 정제 완료")
            
            # 마크다운 저장
            saved_files = pipeline.save_all(processed_all, "gui_sync")
            logger.info(f"   ✓ {len(saved_files)}개 마크다운 파일 생성 완료")
            
            # 6. NotebookLM 업로드
            if settings.notebooklm.target_notebooks:
                logger.info("📤 NotebookLM 업로드 중...")
                from loaders.notebooklm_manager import ETLOrchestrator
                orchestrator = ETLOrchestrator(settings)
                
                for nb_name, nb_id in settings.notebooklm.target_notebooks.items():
                    logger.info(f"   노트북: {nb_name} 업로드 시작...")
                    result = await orchestrator.run_full_pipeline(nb_id, nb_name, saved_files)
                    
                    if result.get("status") == "success":
                        stats = result.get("upload_results", {})
                        logger.info(f"   ✓ {nb_name}: 성공 {stats.get('success')}, 건너뜀 {stats.get('skipped')}")
                    else:
                        logger.error(f"   ✗ {nb_name} 업로드 실패: {result.get('error')}")
            else:
                logger.warning("⚠️ 대상 노트북이 설정되지 않았습니다. 업로드를 건너뜁니다.")
                
            logger.info("✨ 모든 동기화 작업이 완료되었습니다!")
            
            self.root.after(0, lambda: self.dashboard_tab.update_stats({
                "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "total_collected": len(all_contents),
                "uploaded_sources": len(processed_all)
            }))
            
        except Exception as e:
            logger.error(f"❌ 데이터 처리 중 오류 발생: {e}")
            logger.exception(e)


    def run_partial_sync(self, source_type: str):
        """특정 소스 타입만 동기화합니다."""
        if self._is_syncing:
            messagebox.showwarning("작업 중", "이미 동기화가 진행 중입니다.")
            return

        logger.info(f"{source_type} 부분 동기화 시작...")
        self.status_bar.set_status(f"{source_type} 동기화 중...")
        
        # 백그라운드 스레드에서 실행
        thread = threading.Thread(
            target=lambda: asyncio.run(self._run_partial_sync_async(source_type)),
            daemon=True
        )
        thread.start()

    async def _run_partial_sync_async(self, source_type: str):
        """부분 동기화 비동기 작업 코어"""
        self._is_syncing = True
        try:
            settings = self.settings_manager.get()
            contents = []

            if source_type == "email":
                from extractors.email_extractor import EmailExtractor
                with EmailExtractor.from_user_config() as extractor:
                    contents = extractor.extract_emails(
                        days_back=settings.email.days_back,
                        max_emails=settings.email.max_emails,
                        filter_keywords=settings.email.filter_keywords
                    )
            elif source_type == "browser":
                from extractors.browser_extractor import BrowserHistoryExtractor
                extractor = BrowserHistoryExtractor(browsers=settings.browser.browsers)
                contents = extractor.extract(
                    days_back=settings.browser.days_back,
                    min_visit_count=settings.browser.min_visit_count
                )
            # ... 다른 타입들도 유사하게 추가 가능

            if not contents:
                logger.info(f"ℹ️ {source_type}: 수집된 새로운 데이터가 없습니다.")
                return

            # 데이터 처리 및 업로드 (공통 로직 활용)
            from transformers.filter_engine import ETLPipeline
            pipeline = ETLPipeline(settings)
            
            if source_type == "email":
                processed = pipeline.process_emails(contents)
            elif source_type == "browser":
                processed = pipeline.process_browser_history(contents)
            else:
                processed = []

            if processed:
                saved_files = pipeline.save_all(processed, f"partial_{source_type}")
                
                # NotebookLM 업로드
                if settings.notebooklm.target_notebooks:
                    from loaders.notebooklm_manager import ETLOrchestrator
                    orchestrator = ETLOrchestrator(settings)
                    for nb_name, nb_id in settings.notebooklm.target_notebooks.items():
                        await orchestrator.run_full_pipeline(nb_id, nb_name, saved_files)
                
                logger.info(f"✨ {source_type} 동기화 완료!")
            
        except Exception as e:
            logger.error(f"❌ {source_type} 동기화 중 오류: {e}")
        finally:
            self._is_syncing = False
            self.root.after(0, lambda: self.status_bar.set_status("준비"))

    def cleanup_old_sources(self):
        """오래된 소스를 정리합니다."""
        if messagebox.askyesno("소스 정리", "오래된 소스를 삭제하시겠습니까?"):
            logger.info("오래된 소스 정리 시작...")
            self.status_bar.set_status("소스 정리 중...")

    def _on_closing(self):
        """창을 닫을 때 트레이로 숨김 (Windows만)"""
        if sys.platform == "win32":
            self.root.withdraw()
            if not self._tray_icon:
                self._setup_tray()
        else:
            self._exit_app()

    def _show_window(self):
        """트레이에서 창 복구"""
        self.root.after(0, self.root.deiconify)

    def _exit_app(self, icon=None):
        """완전 종료"""
        if icon:
            icon.stop()
        self.root.quit()
        sys.exit(0)

    def _setup_tray(self):
        """시스템 트레이 아이콘 설정"""
        import pystray
        from PIL import Image

        # 아이콘 이미지 생성 (또는 파일 로드)
        try:
            image = Image.open("icon.ico")
        except Exception:
            # 기본 색상 사각형 아이콘 생성
            image = Image.new('RGB', (64, 64), COLORS["primary"])

        menu = (
            pystray.MenuItem('열기', self._show_window),
            pystray.MenuItem('종료', self._exit_app)
        )
        self._tray_icon = pystray.Icon("notebooklm_etl", image, "NotebookLM ETL", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def run(self):
        """애플리케이션을 실행합니다."""
        logger.info("NotebookLM ETL Manager 시작")
        self.dashboard_tab.append_log("애플리케이션이 시작되었습니다.", "SUCCESS")
        self.root.mainloop()


def main():
    """메인 진입점."""
    app = NotebookLMETLApp()
    app.run()


if __name__ == "__main__":
    main()
