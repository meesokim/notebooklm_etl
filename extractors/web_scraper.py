"""
NotebookLM ETL Pipeline - 웹 스크래핑 모듈
네이버 카페, 뉴스, 일반 웹페이지 등에서 콘텐츠를 추출합니다.
Playwright를 사용하여 동적 페이지 렌더링 및 로그인 세션을 지원합니다.
"""

import re
import json
import time
import html
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("web_scraper")


@dataclass
class WebContent:
    """스크래핑된 웹 콘텐츠 데이터 구조"""
    url: str
    title: str
    content: str
    author: str = ""
    published_date: str = ""
    platform: str = "web"
    tags: List[str] = field(default_factory=list)
    source: str = "web_scraper"


class ArticleScraper:
    """
    일반 웹 아티클 및 뉴스 페이지에서 본문 콘텐츠를 추출하는 클래스.
    requests + BeautifulSoup을 사용하는 경량 스크래퍼입니다.
    """

    def __init__(self):
        self._session = None
        logger.info("ArticleScraper 초기화")

    def _get_session(self):
        """requests 세션 초기화 (지연 로딩)."""
        if self._session is None:
            try:
                import requests
                self._session = requests.Session()
                self._session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                })
            except ImportError:
                logger.error("requests 라이브러리가 설치되지 않았습니다.")
        return self._session

    def scrape_url(self, url: str, timeout: int = 15) -> Optional[WebContent]:
        """
        단일 URL에서 아티클 콘텐츠를 추출합니다.

        Args:
            url: 스크래핑할 URL
            timeout: 요청 타임아웃 (초)

        Returns:
            추출된 WebContent 또는 None
        """
        try:
            import requests
            from bs4 import BeautifulSoup

            session = self._get_session()
            response = session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()

            # 인코딩 처리
            if response.encoding and response.encoding.lower() in ['iso-8859-1', 'windows-1252']:
                response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, 'html.parser')

            # 제목 추출
            title = self._extract_title(soup)

            # 본문 추출
            content = self._extract_content(soup)

            # 발행일 추출
            published_date = self._extract_date(soup)

            # 저자 추출
            author = self._extract_author(soup)

            if not content or len(content) < 100:
                logger.debug(f"콘텐츠 부족: {url}")
                return None

            return WebContent(
                url=url,
                title=title,
                content=content,
                author=author,
                published_date=published_date,
                platform=urlparse(url).netloc
            )

        except Exception as e:
            logger.warning(f"URL 스크래핑 실패 ({url}): {e}")
            return None

    def scrape_urls(
        self,
        urls: List[str],
        delay: float = 1.0,
        max_items: int = 30
    ) -> List[WebContent]:
        """
        여러 URL을 순차적으로 스크래핑합니다.

        Args:
            urls: 스크래핑할 URL 목록
            delay: 요청 간 지연 시간 (초, 서버 부하 방지)
            max_items: 최대 수집 항목 수

        Returns:
            추출된 WebContent 목록
        """
        results = []
        for i, url in enumerate(urls[:max_items]):
            logger.info(f"스크래핑 중 ({i+1}/{min(len(urls), max_items)}): {url[:80]}")
            content = self.scrape_url(url)
            if content:
                results.append(content)
            if i < len(urls) - 1:
                time.sleep(delay)

        logger.info(f"총 {len(results)}개 아티클 스크래핑 완료")
        return results

    def _extract_title(self, soup) -> str:
        """페이지 제목 추출."""
        # Open Graph 제목 우선
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content'].strip()

        # 일반 title 태그
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text().strip()

        # h1 태그
        h1 = soup.find('h1')
        if h1:
            return h1.get_text().strip()

        return "제목 없음"

    def _extract_content(self, soup) -> str:
        """페이지 본문 추출 (노이즈 제거)."""
        # 불필요한 태그 제거
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer',
                                   'aside', 'advertisement', 'iframe', 'noscript']):
            tag.decompose()

        # 아티클 본문 탐색 (우선순위 순)
        content_selectors = [
            'article',
            '[role="main"]',
            '.article-content',
            '.post-content',
            '.entry-content',
            '#article-body',
            '.content-body',
            'main',
        ]

        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator='\n', strip=True)
                if len(text) > 200:
                    return self._clean_text(text)

        # 폴백: 전체 body에서 텍스트 추출
        body = soup.find('body')
        if body:
            text = body.get_text(separator='\n', strip=True)
            return self._clean_text(text)

        return ""

    def _extract_date(self, soup) -> str:
        """발행일 추출."""
        # Open Graph 날짜
        og_date = soup.find('meta', property='article:published_time')
        if og_date and og_date.get('content'):
            return og_date['content'][:10]

        # time 태그
        time_tag = soup.find('time')
        if time_tag:
            return time_tag.get('datetime', time_tag.get_text())[:10]

        return datetime.now().strftime('%Y-%m-%d')

    def _extract_author(self, soup) -> str:
        """저자 추출."""
        og_author = soup.find('meta', property='article:author')
        if og_author and og_author.get('content'):
            return og_author['content']

        author_tag = soup.find(class_=re.compile(r'author|byline', re.I))
        if author_tag:
            return author_tag.get_text().strip()[:50]

        return ""

    def _clean_text(self, text: str) -> str:
        """텍스트 정제."""
        # 연속 빈 줄 제거
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 연속 공백 제거
        text = re.sub(r'[ \t]+', ' ', text)
        # 앞뒤 공백 제거
        return text.strip()


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
        logger.info(f"NaverCafeScraper 초기화 (Playwright: {use_playwright})")

    def setup_playwright(self) -> bool:
        """Playwright 브라우저 초기화."""
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=False,  # 로그인을 위해 헤드풀 모드 사용
                args=['--disable-blink-features=AutomationControlled']
            )
            context = self._browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                viewport={'width': 1280, 'height': 720}
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

    def scrape_cafe_posts(
        self,
        cafe_url: str,
        keywords: List[str] = None,
        max_posts: int = 20
    ) -> List[WebContent]:
        """
        네이버 카페에서 게시물을 스크래핑합니다.

        Args:
            cafe_url: 카페 URL (예: https://cafe.naver.com/mycafe)
            keywords: 필터링 키워드 목록
            max_posts: 최대 수집 게시물 수

        Returns:
            추출된 WebContent 목록
        """
        if not self._page:
            if not self.setup_playwright():
                return []

        results = []
        keywords = keywords or []

        try:
            logger.info(f"네이버 카페 스크래핑: {cafe_url}")
            self._page.goto(cafe_url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # 게시물 목록 추출 (카페 구조에 따라 셀렉터 조정 필요)
            post_links = self._extract_cafe_post_links(max_posts)

            for link in post_links[:max_posts]:
                try:
                    content = self._scrape_cafe_post(link)
                    if content:
                        # 키워드 필터링
                        if keywords:
                            search_text = f"{content.title} {content.content}".lower()
                            if not any(kw.lower() in search_text for kw in keywords):
                                continue
                        results.append(content)
                        time.sleep(1)
                except Exception as e:
                    logger.warning(f"게시물 스크래핑 실패 ({link}): {e}")

        except Exception as e:
            logger.error(f"카페 스크래핑 오류: {e}")

        logger.info(f"네이버 카페 스크래핑 완료: {len(results)}개 게시물")
        return results

    def _extract_cafe_post_links(self, max_count: int) -> List[str]:
        """카페 메인 페이지에서 게시물 링크 추출."""
        links = []
        try:
            # 네이버 카페 게시물 링크 패턴
            elements = self._page.query_selector_all('a[href*="ArticleRead"]')
            for elem in elements[:max_count]:
                href = elem.get_attribute('href')
                if href:
                    if href.startswith('http'):
                        links.append(href)
                    else:
                        links.append(f"https://cafe.naver.com{href}")
        except Exception as e:
            logger.warning(f"게시물 링크 추출 실패: {e}")
        return links

    def _scrape_cafe_post(self, url: str) -> Optional[WebContent]:
        """네이버 카페 개별 게시물 스크래핑."""
        try:
            self._page.goto(url, wait_until='networkidle', timeout=20000)
            time.sleep(1)

            # iframe 내부 콘텐츠 접근 (네이버 카페는 iframe 구조 사용)
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
        """Playwright 브라우저 종료."""
        if self._browser:
            self._browser.close()
        if hasattr(self, '_playwright'):
            self._playwright.stop()


class GoogleSearchScraper:
    """
    Google 검색 결과에서 관련 아티클 URL을 수집하는 클래스.
    """

    def __init__(self):
        self._session = None

    def search_and_collect(
        self,
        queries: List[str],
        max_results_per_query: int = 5,
        scrape_content: bool = True
    ) -> List[WebContent]:
        """
        Google 검색을 통해 관련 아티클을 수집합니다.

        Args:
            queries: 검색 쿼리 목록
            max_results_per_query: 쿼리당 최대 결과 수
            scrape_content: True이면 각 URL의 콘텐츠도 스크래핑

        Returns:
            수집된 WebContent 목록
        """
        all_urls = []

        for query in queries:
            logger.info(f"Google 검색: '{query}'")
            urls = self._google_search(query, max_results_per_query)
            all_urls.extend(urls)
            time.sleep(2)  # 검색 간 지연

        # 중복 URL 제거
        unique_urls = list(dict.fromkeys(all_urls))

        if not scrape_content:
            return [WebContent(url=url, title=url, content="") for url in unique_urls]

        # 콘텐츠 스크래핑
        scraper = ArticleScraper()
        return scraper.scrape_urls(unique_urls)

    def _google_search(self, query: str, max_results: int) -> List[str]:
        """Google 검색 결과 URL 추출."""
        urls = []
        try:
            import requests
            from bs4 import BeautifulSoup

            search_url = f"https://www.google.com/search?q={query}&num={max_results}&hl=ko"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                              '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            response = requests.get(search_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 검색 결과 링크 추출
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith('/url?q='):
                    url = href.split('/url?q=')[1].split('&')[0]
                    if url.startswith('http') and 'google.com' not in url:
                        urls.append(url)

        except Exception as e:
            logger.warning(f"Google 검색 실패 ({query}): {e}")

        return urls[:max_results]


def web_contents_to_markdown(
    contents: List[WebContent],
    title: str = "웹 콘텐츠 수집 데이터"
) -> str:
    """
    스크래핑된 웹 콘텐츠를 NotebookLM 업로드용 마크다운 형식으로 변환.
    """
    lines = [
        f"# {title}",
        f"",
        f"**수집 일시:** {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}",
        f"**수집된 아티클 수:** {len(contents)}개",
        f"",
        "---",
        ""
    ]

    for i, content in enumerate(contents, 1):
        lines.extend([
            f"## [{i}] {content.title}",
            f"",
            f"| 항목 | 내용 |",
            f"|------|------|",
            f"| 출처 | [{content.platform}]({content.url}) |",
            f"| 저자 | {content.author or '알 수 없음'} |",
            f"| 발행일 | {content.published_date} |",
            f"",
            f"### 본문",
            f"",
            content.content[:4000] + ("..." if len(content.content) > 4000 else ""),
            f"",
            "---",
            ""
        ])

    return "\n".join(lines)


# 테스트 실행
if __name__ == "__main__":
    print("=== 웹 스크래핑 모듈 테스트 ===")
    scraper = ArticleScraper()
    test_url = "https://www.python.org/about/"
    content = scraper.scrape_url(test_url)
    if content:
        print(f"제목: {content.title}")
        print(f"본문 길이: {len(content.content)}자")
        print(f"본문 미리보기: {content.content[:200]}")
