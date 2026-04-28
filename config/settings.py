"""
NotebookLM ETL Pipeline - 설정 관리 모듈
사용자 설정을 JSON 파일로 저장하고 불러오는 기능을 제공합니다.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Union


# 기본 경로 설정
BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config" / "user_config.json"
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_DIR = DATA_DIR / "logs"


@dataclass
class EmailConfig:
    """이메일 수집 설정"""
    enabled: bool = False
    provider: str = "naver"  # "naver" or "gmail"
    imap_server: str = "imap.naver.com"
    imap_port: int = 993
    username: str = ""
    password: str = ""  # 앱 비밀번호 사용 권장
    folders: List[str] = field(default_factory=lambda: ["INBOX"])
    max_emails: int = 50
    days_back: int = 7  # 최근 N일 이내 메일만 수집
    filter_keywords: List[str] = field(default_factory=list)
    exclude_senders: List[str] = field(default_factory=lambda: ["noreply", "no-reply", "newsletter"])


@dataclass
class BrowserConfig:
    """브라우저 히스토리 수집 설정"""
    enabled: bool = True
    browsers: List[str] = field(default_factory=lambda: ["chrome", "edge"])
    days_back: int = 3
    min_visit_count: int = 2  # 최소 방문 횟수 (노이즈 제거)
    exclude_domains: List[str] = field(default_factory=lambda: [
        "google.com/search", "bing.com/search",
        "localhost", "127.0.0.1",
        "chrome://", "edge://",
        "youtube.com",  # 유튜브는 별도 처리
        "facebook.com", "instagram.com"  # SNS는 별도 처리
    ])
    include_domains: List[str] = field(default_factory=list)  # 비어있으면 모든 도메인


@dataclass
class KakaoTalkConfig:
    """카카오톡 PC 데이터 수집 설정"""
    enabled: bool = False
    target_rooms: List[str] = field(default_factory=lambda: ["나에게 쓰기"])
    max_messages: int = 100


@dataclass
class NaverCafeConfig:
    """네이버 카페 수집 설정"""
    enabled: bool = False
    cafe_urls: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    max_posts: int = 20


@dataclass
class SNSConfig:
    """소셜 미디어 수집 설정"""
    enabled: bool = False
    platforms: List[str] = field(default_factory=list)  # "twitter", "facebook", etc.
    keywords: List[str] = field(default_factory=list)
    max_posts: int = 30


@dataclass
class FilterConfig:
    """전역 필터링 설정"""
    global_keywords: List[str] = field(default_factory=list)
    global_exclude_keywords: List[str] = field(default_factory=lambda: [
        "광고", "스팸", "이벤트 당첨", "무료 쿠폰"
    ])
    min_content_length: int = 100  # 최소 콘텐츠 길이 (문자 수)
    max_content_length: int = 50000  # 최대 콘텐츠 길이 (문자 수)
    language: str = "ko"  # 주요 언어


@dataclass
class NotebookLMConfig:
    """NotebookLM 연동 설정"""
    google_account_email: str = ""
    target_notebooks: Dict[str, str] = field(default_factory=dict)  # {"노트북명": "notebook_id"}
    default_notebook: str = ""
    max_sources_per_notebook: int = 45  # 50개 제한의 안전 마진
    auto_delete_old_sources: bool = True
    source_retention_days: int = 30  # 소스 보관 기간
    upload_interval_hours: int = 6  # 업로드 주기 (시간)


@dataclass
class AppSettings:
    """전체 애플리케이션 설정"""
    version: str = "1.0.0"
    email: EmailConfig = field(default_factory=EmailConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    kakao: KakaoTalkConfig = field(default_factory=KakaoTalkConfig)
    naver_cafe: NaverCafeConfig = field(default_factory=NaverCafeConfig)
    sns: SNSConfig = field(default_factory=SNSConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    notebooklm: NotebookLMConfig = field(default_factory=NotebookLMConfig)
    schedule_enabled: bool = True
    schedule_interval_hours: int = 6
    log_level: str = "INFO"


class SettingsManager:
    """설정 파일 관리 클래스"""

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = CONFIG_FILE
        self._settings: Optional[AppSettings] = None

    def load(self) -> AppSettings:
        """설정 파일 로드. 파일이 없으면 기본값으로 생성."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._settings = self._dict_to_settings(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[WARNING] 설정 파일 로드 실패: {e}. 기본값을 사용합니다.")
                self._settings = AppSettings()
        else:
            self._settings = AppSettings()
            self.save(self._settings)
        return self._settings

    def save(self, settings: AppSettings) -> None:
        """설정을 JSON 파일로 저장."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
        self._settings = settings

    def get(self) -> AppSettings:
        """현재 설정 반환. 로드되지 않았으면 자동으로 로드."""
        if self._settings is None:
            return self.load()
        return self._settings

    def _dict_to_settings(self, data: dict) -> AppSettings:
        """딕셔너리를 AppSettings 객체로 변환."""
        return AppSettings(
            version=data.get('version', '1.0.0'),
            email=EmailConfig(**(data.get('email') or {})),
            browser=BrowserConfig(**(data.get('browser') or {})),
            kakao=KakaoTalkConfig(**(data.get('kakao') or {})),
            naver_cafe=NaverCafeConfig(**(data.get('naver_cafe') or {})),
            sns=SNSConfig(**(data.get('sns') or {})),
            filter=FilterConfig(**(data.get('filter') or {})),
            notebooklm=NotebookLMConfig(**(data.get('notebooklm') or {})),
            schedule_enabled=data.get('schedule_enabled', True),
            schedule_interval_hours=data.get('schedule_interval_hours', 6),
            log_level=data.get('log_level', 'INFO'),
        )


# 전역 설정 인스턴스
settings_manager = SettingsManager()
