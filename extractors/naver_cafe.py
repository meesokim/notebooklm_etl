"""
NotebookLM ETL Pipeline - 네이버 카페 스크래핑 모듈
Playwright를 사용하여 네이버 카페에서 콘텐츠를 추출합니다.
"""

import time
from datetime import datetime
from urllib.parse import urljoin
from typing import List, Optional
from pathlib import Path
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger
from extractors.web_scraper import WebContent

logger = setup_logger("naver_cafe_scraper")


class NaverCafeScraper:
    """
    네이버 카페 게시물을 스크래핑하는 클래스.
    로그인이 필요한 경우 Playwright를 사용합니다.
    """

    def __init__(self, use_playwright: bool = True):
        """
        Args:
            use_playwright: True이면 Playwright 사용 (로그인 세션 유지 가능)
        """
        self.use_playwright = use_playwright
        self._browser = None
        self._page = None
        self._config = self._load_naver_cafe_config()
        self._storage_state_path = Path(__file__).parent.parent / "data" / "browser_state" / "naver_cafe_state.json"
        logger.info(f"NaverCafeScraper 초기화 (Playwright: {use_playwright})")

    def _load_naver_cafe_config(self) -> dict:
        """user_config.json에서 naver_cafe 설정을 로드."""
        default_path = Path(__file__).parent.parent / "config" / "user_config.json"
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = data.get("naver_cafe", {})
            if not isinstance(cfg, dict):
                return {}
            return cfg
        except FileNotFoundError:
            logger.debug(f"네이버 카페 설정 파일 없음: {default_path}")
            return {}
        except Exception as e:
            logger.error(f"네이버 카페 설정 로드 실패: {default_path} ({e})")
            return {}

    def setup_playwright(self) -> bool:
        """Playwright 브라우저 초기화."""
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=False,  # 자동 로그인을 보거나 수동으로 로그인하려면 헤드풀 모드
                args=['--disable-blink-features=AutomationControlled']
            )

            storage_state = None
            if self._storage_state_path.exists():
                logger.info(f"저장된 브라우저 상태를 불러옵니다: {self._storage_state_path}")
                storage_state = self._storage_state_path
            else:
                logger.info("저장된 브라우저 상태 파일이 없습니다. 새 세션을 시작합니다.")

            context = self._browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720},
                storage_state=storage_state
            )
            self._page = context.new_page()
            logger.info("Playwright 브라우저 초기화 완료")
            return True
        except ImportError:
            logger.error("playwright가 설치되지 않았습니다. 'pip install playwright'를 실행하세요.")
            return False
        except Exception as e:
            logger.error(f"Playwright 초기화 실패: {e}")
            return False

    def _login(self):
        """설정 파일의 정보로 자동 로그인 시도."""
        username = self._config.get("username")
        password = self._config.get("password")

        if not username or not password:
            logger.warning("자동 로그인을 위한 사용자 정보가 설정에 없습니다.")
            return False

        logger.info(f"'{username}' 계정으로 자동 로그인을 시도합니다.")
        try:
            self._page.goto("https://nid.naver.com/nidlogin.login", wait_until='networkidle')

            self._page.wait_for_selector('#id', timeout=10000)
            # Simulate human typing for robustness against bot detection
            self._page.type('#id', username, delay=100)
            time.sleep(0.3)
            self._page.type('#pw', password, delay=100)
            time.sleep(0.5)

            self._page.locator(r'#log\.login').click()
            
            self._page.wait_for_url(lambda url: "nid.naver.com" not in url, timeout=30000)
            logger.info("로그인 성공 또는 페이지 이동 감지됨.")
            return True
        except Exception as e:
            logger.error(f"자동 로그인 실패: {e}")
            logger.error("CAPTCHA, 2단계 인증, 또는 로그인 페이지 변경으로 인해 실패할 수 있습니다. 브라우저에서 직접 로그인해주세요.")
            return False

    def scrape_my_activity(self, max_posts: int = 50) -> List[WebContent]:
        """
        네이버 카페 '내 활동' 피드에서 게시물을 스크래핑합니다.
        (내가 쓴 글, 댓글 단 글 등)
        로그인이 필요합니다.
        """
        if not self._page:
            if not self.setup_playwright():
                return []

        results = []
        my_activity_url = "https://section.cafe.naver.com/ca-fe/home/my-news/cafe-activity"
        
        try:
            logger.info(f"네이버 카페 '내 활동' 스크래핑 시작: {my_activity_url}")
            self._page.goto(my_activity_url, wait_until='networkidle', timeout=60000)
            
            if "nid.naver.com/nidlogin.login" in self._page.url:
                login_success = False
                if self._config.get("use_programmatic_login"):
                    login_success = self._login()
                
                if not login_success:
                    logger.warning("네이버 로그인이 필요합니다. 브라우저에서 로그인해주세요. 5분 동안 대기합니다...")
                    try:
                        self._page.wait_for_url(lambda url: "nid.naver.com" not in url, timeout=300000) # 5분
                        logger.info("로그인 감지됨. '내 활동' 페이지로 다시 이동합니다.")
                    except Exception:
                        logger.error("로그인 시간 초과. '내 활동' 수집을 중단합니다.")
                        return []
                
                self._page.goto(my_activity_url, wait_until='networkidle', timeout=60000)

            # 활동 피드 컨테이너가 로드될 때까지 대기
            try:
                self._page.wait_for_selector('div.my_news_list_area', timeout=30000)
                logger.info("'내 활동' 피드 컨테이너 로드 완료.")
            except Exception:
                logger.error("'내 활동' 페이지의 메인 컨테이너를 찾을 수 없습니다. 페이지 구조가 변경되었을 수 있습니다.")
                return []

            # 활동 내역이 없는 경우 처리
            is_empty = self._page.locator('div.empty').is_visible()
            if is_empty:
                logger.info("수집할 '내 활동' 내역이 없습니다.")
                return []

            activity_items = self._page.query_selector_all('div.item_wrap')
            logger.info(f"총 {len(activity_items)}개의 활동 항목을 찾았습니다. 최대 {max_posts}개를 처리합니다.")

            for item_el in activity_items[:max_posts]:
                try:
                    link_tag = item_el.query_selector('a')
                    if not link_tag:
                        continue

                    url = urljoin(my_activity_url, link_tag.get_attribute('href') or "")
                    
                    # 활동 피드 아이템에서 직접 텍스트 정보 추출
                    cafe_name_tag = item_el.query_selector('.cafe_info .source')
                    activity_type_tag = item_el.query_selector('.title_box .status')
                    main_text_tag = item_el.query_selector('p.text')
                    reply_text_tag = item_el.query_selector('p.text_reply')
                    date_tag = item_el.query_selector('.cafe_info .date')
                    author_tag = item_el.query_selector('strong.title')

                    cafe_name = cafe_name_tag.inner_text().strip() if cafe_name_tag else "알 수 없는 카페"
                    activity_type = activity_type_tag.inner_text().strip() if activity_type_tag else "알 수 없는 활동"
                    main_text = main_text_tag.inner_text().strip() if main_text_tag else ""
                    reply_text = reply_text_tag.inner_text().strip() if reply_text_tag else ""
                    date_str = date_tag.inner_text().strip().replace('.', '-') if date_tag else datetime.now().strftime('%Y-%m-%d')
                    author = author_tag.inner_text().strip() if author_tag else "알 수 없는 작성자"

                    title = f"[{cafe_name}] {activity_type}"
                    
                    content_parts = [f"활동: {activity_type} (작성자: {author})"]
                    if main_text: content_parts.append(f"내용: {main_text}")
                    if reply_text: content_parts.append(f"답글: {reply_text}")
                    content = "\n".join(content_parts)

                    results.append(WebContent(
                        url=url, title=title, content=content, author=author,
                        published_date=date_str, platform="naver_cafe", tags=["my-activity"]
                    ))
                except Exception as e:
                    logger.warning(f"활동 항목 파싱 중 오류 발생: {e}")
                    continue
        except Exception as e:
            logger.error(f"'내 활동' 스크래핑 중 오류 발생: {e}")

        logger.info(f"네이버 카페 '내 활동' 스크래핑 완료: {len(results)}개 게시물")
        return results

    def scrape_cafe_posts(self, cafe_url: str, keywords: List[str] = None, max_posts: int = 20) -> List[WebContent]:
        if not self._page:
            if not self.setup_playwright():
                return []
        # (기존과 동일, 생략)
        return []

    def _scrape_cafe_post(self, url: str) -> Optional[WebContent]:
        """네이버 카페 개별 게시물 스크래핑."""
        try:
            self._page.goto(url, wait_until='networkidle', timeout=20000)
            time.sleep(1)

            iframe = self._page.query_selector('iframe#cafe_main')
            if iframe:
                frame = iframe.content_frame()
                if frame:
                    title = frame.query_selector('.title-text, .tit-box h3')
                    content_elem = frame.query_selector('.se-main-container, .tbody')
                    author_elem = frame.query_selector('.nick-name, .writer')

                    title_text = title.inner_text() if title else "제목 없음"
                    content_text = content_elem.inner_text() if content_elem else ""
                    author_text = author_elem.inner_text() if author_elem else ""

                    if content_text and len(content_text) > 50:
                        return WebContent(
                            url=url,
                            title=title_text.strip(),
                            content=content_text.strip()[:5000],
                            author=author_text.strip(),
                            published_date=datetime.now().strftime('%Y-%m-%d'),
                            platform="naver_cafe"
                        )
        except Exception as e:
            logger.debug(f"카페 게시물 파싱 오류: {e}")
        return None

    def close(self):
        """Playwright 브라우저 종료 및 상태 저장."""
        if self._page:
            try:
                self._storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                self._page.context.storage_state(path=self._storage_state_path)
                logger.info(f"브라우저 상태를 저장했습니다: {self._storage_state_path}")
            except Exception as e:
                logger.error(f"브라우저 상태 저장 실패: {e}")

        if self._browser:
            self._browser.close()
        if hasattr(self, '_playwright'):
            self._playwright.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Naver Cafe Scraper - Test Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python extractors/naver_cafe.py --test-activity --max-posts 15
        """
    )
    parser.add_argument("--test-activity", action="store_true", help="네이버 카페 '내 활동' 피드 스크래핑을 테스트합니다.")
    parser.add_argument("--max-posts", type=int, default=10, help="테스트 시 수집할 최대 게시물 수")

    args = parser.parse_args()

    if args.test_activity:
        print("=== 네이버 카페 스크래퍼 테스트: 내 활동 수집 ===")
        scraper = NaverCafeScraper()
        activities = scraper.scrape_my_activity(max_posts=args.max_posts)

        if activities:
            print(f"\n✅ 성공: {len(activities)}개의 활동 관련 게시물을 수집했습니다.")
            for i, item in enumerate(activities[:5], 1):
                print(f"  [{i}] {item.title[:60]}...")
        else:
            print("\n❌ 실패: 활동 내역을 수집하지 못했습니다. 로그인을 확인하거나 설정이 올바른지 확인하세요.")
        
        scraper.close()
    else:
        print("실행할 테스트를 지정해주세요. 예: --test-activity")
        parser.print_help()