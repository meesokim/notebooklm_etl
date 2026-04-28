"""
NotebookLM ETL Pipeline - 브라우저 히스토리 추출 모듈
Windows 환경에서 Chrome, Edge, Firefox의 로컬 SQLite DB에서 방문 기록을 추출합니다.
"""

import sqlite3
import shutil
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("browser_extractor")


@dataclass
class BrowserHistoryItem:
    """브라우저 방문 기록 데이터 구조"""
    url: str
    title: str
    visit_time: datetime
    visit_count: int
    browser: str
    domain: str = ""
    source: str = "browser_history"

    def __post_init__(self):
        if not self.domain:
            try:
                parsed = urlparse(self.url)
                self.domain = parsed.netloc
            except Exception:
                self.domain = ""


class BrowserHistoryExtractor:
    """
    Windows 환경에서 주요 브라우저의 방문 기록을 추출하는 클래스.
    Chrome, Microsoft Edge, Firefox를 지원합니다.
    """

    # Windows 환경에서의 브라우저 히스토리 파일 경로
    BROWSER_PATHS = {
        "chrome": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "History",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Profile 1" / "History",
        ],
        "edge": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default" / "History",
        ],
        "firefox": [
            # Firefox는 프로파일 폴더가 동적으로 생성됨
        ],
        "whale": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Naver" / "Naver Whale" / "User Data" / "Default" / "History",
        ]
    }

    def __init__(self, browsers: List[str] = None):
        """
        Args:
            browsers: 수집할 브라우저 목록 ["chrome", "edge", "firefox", "whale"]
        """
        self.browsers = browsers or ["chrome", "edge"]
        logger.info(f"BrowserHistoryExtractor 초기화: {self.browsers}")

    def _get_firefox_history_path(self) -> List[Path]:
        """Firefox 프로파일 폴더에서 히스토리 파일 경로를 동적으로 탐색."""
        paths = []
        firefox_profiles_dir = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles"

        if firefox_profiles_dir.exists():
            for profile_dir in firefox_profiles_dir.iterdir():
                if profile_dir.is_dir():
                    places_file = profile_dir / "places.sqlite"
                    if places_file.exists():
                        paths.append(places_file)
        return paths

    def extract(
        self,
        days_back: int = 3,
        min_visit_count: int = 1,
        exclude_domains: List[str] = None,
        include_domains: List[str] = None,
        max_results: int = 500
    ) -> List[BrowserHistoryItem]:
        """
        브라우저 방문 기록 추출 메인 함수.

        Args:
            days_back: 최근 N일 이내 방문 기록만 수집
            min_visit_count: 최소 방문 횟수 (노이즈 제거)
            exclude_domains: 제외할 도메인 목록
            include_domains: 포함할 도메인 목록 (비어있으면 모든 도메인)
            max_results: 최대 결과 수

        Returns:
            추출된 BrowserHistoryItem 목록
        """
        exclude_domains = exclude_domains or []
        include_domains = include_domains or []
        all_history = []

        for browser in self.browsers:
            logger.info(f"브라우저 '{browser}' 히스토리 추출 시작...")

            if browser == "firefox":
                paths = self._get_firefox_history_path()
            else:
                paths = self.BROWSER_PATHS.get(browser, [])

            for history_path in paths:
                if not history_path.exists():
                    logger.debug(f"히스토리 파일 없음: {history_path}")
                    continue

                try:
                    items = self._extract_chromium_history(history_path, browser, days_back) \
                        if browser != "firefox" \
                        else self._extract_firefox_history(history_path, days_back)

                    all_history.extend(items)
                    logger.info(f"'{browser}' ({history_path.name}): {len(items)}개 항목 추출")

                except Exception as e:
                    logger.error(f"'{browser}' 히스토리 추출 오류: {e}")

        # 필터링
        filtered = self._filter_history(
            all_history, min_visit_count, exclude_domains, include_domains
        )

        # 중복 제거 (URL 기준)
        seen_urls = set()
        unique_history = []
        for item in filtered:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                unique_history.append(item)

        # 방문 횟수 및 최신 방문 기준으로 정렬
        unique_history.sort(key=lambda x: (x.visit_count, x.visit_time), reverse=True)

        result = unique_history[:max_results]
        logger.info(f"총 {len(result)}개 고유 방문 기록 추출 완료")
        return result

    def _extract_chromium_history(
        self, db_path: Path, browser: str, days_back: int
    ) -> List[BrowserHistoryItem]:
        """Chrome/Edge/Whale (Chromium 기반) 브라우저의 히스토리 추출."""
        items = []

        # 브라우저가 실행 중일 때 DB 파일이 잠겨있을 수 있으므로 임시 복사본 사용
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            shutil.copy2(str(db_path), tmp_path)
            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()

            # Chrome의 타임스탬프는 1601-01-01 기준 마이크로초
            # Python datetime의 1970-01-01 기준으로 변환 필요
            # 차이: 11644473600초
            since_timestamp = int(
                (datetime.now() - timedelta(days=days_back) - datetime(1601, 1, 1)).total_seconds() * 1_000_000
            )

            query = """
                SELECT
                    urls.url,
                    urls.title,
                    urls.last_visit_time,
                    urls.visit_count
                FROM urls
                WHERE urls.last_visit_time > ?
                    AND urls.url NOT LIKE 'chrome://%'
                    AND urls.url NOT LIKE 'edge://%'
                    AND urls.url NOT LIKE 'about:%'
                    AND urls.url NOT LIKE 'file://%'
                ORDER BY urls.last_visit_time DESC
                LIMIT 1000
            """

            cursor.execute(query, (since_timestamp,))
            rows = cursor.fetchall()
            conn.close()

            for url, title, last_visit_time, visit_count in rows:
                try:
                    # Chrome 타임스탬프 변환
                    visit_dt = datetime(1601, 1, 1) + timedelta(microseconds=last_visit_time)
                    items.append(BrowserHistoryItem(
                        url=url,
                        title=title or url,
                        visit_time=visit_dt,
                        visit_count=visit_count or 1,
                        browser=browser
                    ))
                except Exception as e:
                    logger.debug(f"항목 변환 오류: {e}")

        except sqlite3.OperationalError as e:
            logger.warning(f"DB 접근 오류 ({db_path.name}): {e}. 브라우저가 실행 중인지 확인하세요.")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        return items

    def _extract_firefox_history(
        self, db_path: Path, days_back: int
    ) -> List[BrowserHistoryItem]:
        """Firefox 브라우저의 히스토리 추출."""
        items = []

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            shutil.copy2(str(db_path), tmp_path)
            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()

            # Firefox는 Unix 타임스탬프 (마이크로초)
            since_timestamp = int(
                (datetime.now() - timedelta(days=days_back)).timestamp() * 1_000_000
            )

            query = """
                SELECT
                    moz_places.url,
                    moz_places.title,
                    moz_historyvisits.visit_date,
                    moz_places.visit_count
                FROM moz_historyvisits
                JOIN moz_places ON moz_historyvisits.place_id = moz_places.id
                WHERE moz_historyvisits.visit_date > ?
                    AND moz_places.url NOT LIKE 'about:%'
                    AND moz_places.url NOT LIKE 'file://%'
                ORDER BY moz_historyvisits.visit_date DESC
                LIMIT 1000
            """

            cursor.execute(query, (since_timestamp,))
            rows = cursor.fetchall()
            conn.close()

            for url, title, visit_date, visit_count in rows:
                try:
                    visit_dt = datetime.fromtimestamp(visit_date / 1_000_000)
                    items.append(BrowserHistoryItem(
                        url=url,
                        title=title or url,
                        visit_time=visit_dt,
                        visit_count=visit_count or 1,
                        browser="firefox"
                    ))
                except Exception as e:
                    logger.debug(f"Firefox 항목 변환 오류: {e}")

        except sqlite3.OperationalError as e:
            logger.warning(f"Firefox DB 접근 오류: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        return items

    def _filter_history(
        self,
        history: List[BrowserHistoryItem],
        min_visit_count: int,
        exclude_domains: List[str],
        include_domains: List[str]
    ) -> List[BrowserHistoryItem]:
        """히스토리 필터링."""
        filtered = []

        for item in history:
            # 최소 방문 횟수 필터
            if item.visit_count < min_visit_count:
                continue

            # 제외 도메인 필터
            if any(excl.lower() in item.domain.lower() for excl in exclude_domains):
                continue

            # 포함 도메인 필터 (설정된 경우에만)
            if include_domains:
                if not any(incl.lower() in item.domain.lower() for incl in include_domains):
                    continue

            # URL 유효성 검사
            if not item.url.startswith(('http://', 'https://')):
                continue

            filtered.append(item)

        return filtered

    def get_domain_statistics(self, history: List[BrowserHistoryItem]) -> Dict[str, int]:
        """도메인별 방문 통계 반환."""
        stats = {}
        for item in history:
            stats[item.domain] = stats.get(item.domain, 0) + item.visit_count
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))


def browser_history_to_markdown(
    history: List[BrowserHistoryItem],
    title: str = "웹 브라우저 활동 기록"
) -> str:
    """
    추출된 브라우저 히스토리를 NotebookLM 업로드용 마크다운 형식으로 변환.
    """
    # 도메인별 그룹화
    domain_groups: Dict[str, List[BrowserHistoryItem]] = {}
    for item in history:
        domain = item.domain or "기타"
        if domain not in domain_groups:
            domain_groups[domain] = []
        domain_groups[domain].append(item)

    lines = [
        f"# {title}",
        f"",
        f"**수집 일시:** {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}",
        f"**수집된 URL 수:** {len(history)}개",
        f"**방문한 도메인 수:** {len(domain_groups)}개",
        f"",
        "---",
        ""
    ]

    # 도메인별 섹션 생성
    for domain, items in sorted(domain_groups.items(), key=lambda x: len(x[1]), reverse=True):
        lines.extend([
            f"## {domain} ({len(items)}개 페이지)",
            f""
        ])

        for item in sorted(items, key=lambda x: x.visit_count, reverse=True):
            lines.extend([
                f"### {item.title}",
                f"- **URL:** {item.url}",
                f"- **마지막 방문:** {item.visit_time.strftime('%Y-%m-%d %H:%M')}",
                f"- **방문 횟수:** {item.visit_count}회",
                f"- **브라우저:** {item.browser}",
                f""
            ])

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# 테스트 실행
if __name__ == "__main__":
    print("=== 브라우저 히스토리 추출 모듈 테스트 ===")
    extractor = BrowserHistoryExtractor(browsers=["chrome", "edge"])
    history = extractor.extract(days_back=3, min_visit_count=1)
    print(f"추출된 히스토리: {len(history)}개")
    if history:
        print("\n상위 5개 방문 기록:")
        for item in history[:5]:
            print(f"  [{item.visit_count}회] {item.title[:50]} - {item.domain}")
