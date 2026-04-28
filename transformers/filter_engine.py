"""
NotebookLM ETL Pipeline - 필터링 및 변환 엔진
수집된 원시 데이터를 정제하고, 관심 키워드 기반으로 필터링하며,
NotebookLM 업로드에 최적화된 마크다운 형식으로 변환합니다.
"""

import re
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass, field, asdict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("filter_engine")


@dataclass
class FilteredContent:
    """필터링 및 변환된 최종 콘텐츠 데이터 구조"""
    content_id: str          # 고유 ID (URL 또는 내용의 해시값)
    title: str               # 콘텐츠 제목
    content: str             # 정제된 본문
    source_type: str         # "email", "browser", "kakao", "web"
    source_url: str          # 원본 URL 또는 식별자
    collected_at: str        # 수집 시간
    keywords_matched: List[str] = field(default_factory=list)  # 매칭된 키워드
    relevance_score: float = 0.0  # 관련성 점수 (0~1)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContentFilter:
    """
    수집된 데이터를 필터링하고 관련성 점수를 계산하는 클래스.
    """

    def __init__(
        self,
        include_keywords: List[str] = None,
        exclude_keywords: List[str] = None,
        min_content_length: int = 100,
        max_content_length: int = 50000,
    ):
        """
        Args:
            include_keywords: 포함해야 할 키워드 목록 (하나라도 포함되면 통과)
            exclude_keywords: 제외할 키워드 목록 (하나라도 포함되면 제외)
            min_content_length: 최소 콘텐츠 길이
            max_content_length: 최대 콘텐츠 길이
        """
        self.include_keywords = [kw.lower() for kw in (include_keywords or [])]
        self.exclude_keywords = [kw.lower() for kw in (exclude_keywords or [])]
        self.min_content_length = min_content_length
        self.max_content_length = max_content_length

        logger.info(
            f"ContentFilter 초기화: 포함 키워드 {len(self.include_keywords)}개, "
            f"제외 키워드 {len(self.exclude_keywords)}개"
        )

    def filter(self, items: List[Any]) -> List[Any]:
        """
        아이템 목록에 필터를 적용합니다.

        Args:
            items: 필터링할 아이템 목록 (EmailItem, BrowserHistoryItem, WebContent 등)

        Returns:
            필터를 통과한 아이템 목록
        """
        filtered = []
        for item in items:
            text = self._get_text(item)
            if self._passes_filter(text):
                filtered.append(item)

        logger.info(f"필터링 결과: {len(items)}개 중 {len(filtered)}개 통과")
        return filtered

    def _get_text(self, item: Any) -> str:
        """아이템에서 텍스트를 추출합니다."""
        if hasattr(item, 'body'):
            return f"{getattr(item, 'subject', '')} {item.body}"
        elif hasattr(item, 'content'):
            return f"{getattr(item, 'title', '')} {item.content}"
        elif hasattr(item, 'message'):
            return item.message
        elif hasattr(item, 'title'):
            return item.title
        return str(item)

    def _passes_filter(self, text: str) -> bool:
        """텍스트가 필터 조건을 통과하는지 확인합니다."""
        text_lower = text.lower()

        # 길이 필터 (min_content_length가 0이면 길이 필터 비활성화)
        if self.min_content_length > 0 and len(text) < self.min_content_length:
            return False

        # 제외 키워드 필터
        if any(kw in text_lower for kw in self.exclude_keywords):
            return False

        # 포함 키워드 필터 (설정된 경우에만)
        if self.include_keywords:
            if not any(kw in text_lower for kw in self.include_keywords):
                return False

        return True

    def calculate_relevance_score(self, text: str) -> float:
        """
        텍스트의 관련성 점수를 계산합니다 (0~1).
        키워드 매칭 빈도를 기반으로 점수를 산출합니다.
        """
        if not self.include_keywords:
            return 0.5  # 키워드 없으면 중간 점수

        text_lower = text.lower()
        matched_count = sum(1 for kw in self.include_keywords if kw in text_lower)
        frequency_score = sum(
            text_lower.count(kw) for kw in self.include_keywords if kw in text_lower
        )

        # 매칭 비율 + 빈도 기반 점수
        match_ratio = matched_count / len(self.include_keywords) if self.include_keywords else 0
        freq_score = min(frequency_score / 10, 1.0)  # 최대 1.0으로 정규화

        return round((match_ratio * 0.7 + freq_score * 0.3), 3)

    def get_matched_keywords(self, text: str) -> List[str]:
        """텍스트에서 매칭된 키워드 목록을 반환합니다."""
        text_lower = text.lower()
        return [kw for kw in self.include_keywords if kw in text_lower]





class ContentCleaner:
    """
    수집된 텍스트 데이터를 정제하는 클래스.
    HTML 태그 제거, 광고 문구 제거, 불필요한 공백 정리 등을 수행합니다.
    """

    # 광고 및 스팸성 문구 패턴
    SPAM_PATTERNS = [
        r'광고\s*[\|｜]',
        r'\[광고\]',
        r'수신거부',
        r'무단전재.*금지',
        r'Copyright\s*©',
        r'All rights reserved',
        r'구독\s*취소',
        r'이 메일은.*발송',
        r'본 메일은.*자동',
    ]

    def clean(self, text: str) -> str:
        """텍스트를 정제합니다."""
        if not text:
            return ""

        # HTML 태그 제거
        text = self._remove_html_tags(text)

        # HTML 엔티티 디코딩
        text = self._decode_html_entities(text)

        # 광고/스팸 문구 제거
        text = self._remove_spam_patterns(text)

        # URL 정리 (너무 긴 URL 단축)
        text = self._clean_urls(text)

        # 연속 공백 및 줄바꿈 정리
        text = self._normalize_whitespace(text)

        return text.strip()

    def _remove_html_tags(self, text: str) -> str:
        """HTML 태그를 제거합니다."""
        # 스크립트 및 스타일 블록 제거
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # 나머지 HTML 태그 제거
        text = re.sub(r'<[^>]+>', ' ', text)
        return text

    def _decode_html_entities(self, text: str) -> str:
        """HTML 엔티티를 디코딩합니다."""
        import html
        return html.unescape(text)

    def _remove_spam_patterns(self, text: str) -> str:
        """광고 및 스팸 패턴을 제거합니다."""
        for pattern in self.SPAM_PATTERNS:
            # 패턴이 포함된 줄 전체를 제거
            text = re.sub(f'.*{pattern}.*\n?', '', text, flags=re.IGNORECASE)
        return text

    def _clean_urls(self, text: str) -> str:
        """너무 긴 URL을 정리합니다."""
        def shorten_url(match):
            url = match.group(0)
            if len(url) > 100:
                return url[:80] + "..."
            return url

        return re.sub(r'https?://[^\s]+', shorten_url, text)

    def _normalize_whitespace(self, text: str) -> str:
        """연속 공백 및 줄바꿈을 정리합니다."""
        # 연속 빈 줄을 최대 2줄로 제한
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 각 줄의 앞뒤 공백 제거
        lines = [line.strip() for line in text.split('\n')]
        # 연속 공백 제거
        text = '\n'.join(lines)
        text = re.sub(r'[ \t]+', ' ', text)
        return text


class ContentConverter:
    """
    정제된 데이터를 NotebookLM 업로드용 마크다운 파일로 변환하는 클래스.
    """

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "processed"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cleaner = ContentCleaner()

    def convert_to_filtered_content(
        self,
        item: Any,
        source_type: str,
        filter_engine: ContentFilter = None
    ) -> Optional[FilteredContent]:
        """
        수집된 아이템을 FilteredContent로 변환합니다.

        Args:
            item: 수집된 데이터 아이템
            source_type: 소스 타입 ("email", "browser", "kakao", "web")
            filter_engine: 필터링 엔진 (None이면 필터링 생략)

        Returns:
            변환된 FilteredContent 또는 None
        """
        try:
            # 아이템 타입에 따른 필드 추출
            title, content, url, metadata = self._extract_fields(item, source_type)

            # 텍스트 정제
            clean_content = self.cleaner.clean(content)
            clean_title = self.cleaner.clean(title)

            if not clean_content:
                return None

            # 고유 ID 생성 (URL 또는 내용 해시)
            content_id = hashlib.md5(f"{url}{clean_content[:100]}".encode()).hexdigest()[:12]

            # 관련성 점수 및 매칭 키워드 계산
            relevance_score = 0.5
            matched_keywords = []
            if filter_engine:
                full_text = f"{clean_title} {clean_content}"
                relevance_score = filter_engine.calculate_relevance_score(full_text)
                matched_keywords = filter_engine.get_matched_keywords(full_text)

            return FilteredContent(
                content_id=content_id,
                title=clean_title or "제목 없음",
                content=clean_content,
                source_type=source_type,
                source_url=url,
                collected_at=datetime.now().isoformat(),
                keywords_matched=matched_keywords,
                relevance_score=relevance_score,
                metadata=metadata
            )

        except Exception as e:
            logger.warning(f"콘텐츠 변환 실패: {e}")
            return None

    def _extract_fields(self, item: Any, source_type: str) -> tuple:
        """아이템에서 공통 필드를 추출합니다."""
        if source_type == "email":
            return (
                getattr(item, 'subject', ''),
                getattr(item, 'body', ''),
                f"email://{getattr(item, 'sender_email', '')}",
                {
                    "sender": getattr(item, 'sender', ''),
                    "date": str(getattr(item, 'date', '')),
                    "folder": getattr(item, 'folder', '')
                }
            )
        elif source_type == "browser":
            return (
                getattr(item, 'title', ''),
                f"URL: {getattr(item, 'url', '')}\n방문 횟수: {getattr(item, 'visit_count', 0)}",
                getattr(item, 'url', ''),
                {
                    "browser": getattr(item, 'browser', ''),
                    "visit_count": getattr(item, 'visit_count', 0),
                    "visit_time": str(getattr(item, 'visit_time', ''))
                }
            )
        elif source_type == "kakao":
            return (
                f"카카오톡 - {getattr(item, 'room_name', '')}",
                getattr(item, 'message', ''),
                f"kakao://{getattr(item, 'room_name', '')}",
                {
                    "sender": getattr(item, 'sender', ''),
                    "timestamp": getattr(item, 'timestamp', ''),
                    "links": getattr(item, 'links', [])
                }
            )
        elif source_type == "web":
            return (
                getattr(item, 'title', ''),
                getattr(item, 'content', ''),
                getattr(item, 'url', ''),
                {
                    "platform": getattr(item, 'platform', ''),
                    "author": getattr(item, 'author', ''),
                    "published_date": getattr(item, 'published_date', '')
                }
            )
        else:
            return (str(item)[:100], str(item), "", {})

    def save_as_markdown(
        self,
        contents: List[FilteredContent],
        notebook_name: str = "default",
        batch_size: int = 20
    ) -> List[Path]:
        """
        FilteredContent 목록을 마크다운 파일로 저장합니다.
        NotebookLM의 소스 크기 제한을 고려하여 배치로 분할 저장합니다.

        Args:
            contents: 저장할 콘텐츠 목록
            notebook_name: 노트북 이름 (파일명 접두사로 사용)
            batch_size: 파일당 최대 콘텐츠 수

        Returns:
            생성된 마크다운 파일 경로 목록
        """
        saved_files = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 관련성 점수 기준으로 정렬
        sorted_contents = sorted(contents, key=lambda x: x.relevance_score, reverse=True)

        # 배치 분할
        batches = [sorted_contents[i:i+batch_size] for i in range(0, len(sorted_contents), batch_size)]

        for batch_idx, batch in enumerate(batches):
            filename = f"{notebook_name}_{timestamp}_batch{batch_idx+1:02d}.md"
            file_path = self.output_dir / filename

            md_content = self._generate_markdown(batch, notebook_name, batch_idx+1, len(batches))

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            saved_files.append(file_path)
            logger.info(f"마크다운 파일 저장: {filename} ({len(batch)}개 항목)")

        return saved_files

    def _generate_markdown(
        self,
        contents: List[FilteredContent],
        notebook_name: str,
        batch_num: int,
        total_batches: int
    ) -> str:
        """마크다운 콘텐츠를 생성합니다."""
        lines = [
            f"# {notebook_name} - 데이터 수집 보고서",
            f"",
            f"**생성 일시:** {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}",
            f"**배치:** {batch_num}/{total_batches}",
            f"**포함된 항목 수:** {len(contents)}개",
            f"",
        ]

        # 소스 타입별 통계
        source_stats = {}
        for c in contents:
            source_stats[c.source_type] = source_stats.get(c.source_type, 0) + 1

        lines.extend([
            "## 데이터 소스 현황",
            "",
            "| 소스 타입 | 항목 수 |",
            "|---------|--------|",
        ])
        for src_type, count in source_stats.items():
            lines.append(f"| {src_type} | {count}개 |")

        lines.extend(["", "---", ""])

        # 소스 타입별 섹션
        source_type_labels = {
            "email": "이메일",
            "browser": "웹 브라우저 활동",
            "kakao": "카카오톡 메시지",
            "web": "웹 아티클"
        }

        for source_type in ["email", "web", "browser", "kakao"]:
            type_contents = [c for c in contents if c.source_type == source_type]
            if not type_contents:
                continue

            label = source_type_labels.get(source_type, source_type)
            lines.extend([
                f"## {label} ({len(type_contents)}개)",
                ""
            ])

            for i, content in enumerate(type_contents, 1):
                # 콘텐츠 크기 제한 (각 항목당 최대 3000자)
                truncated_content = content.content[:3000]
                if len(content.content) > 3000:
                    truncated_content += "\n\n*[내용이 길어 일부 생략됨]*"

                lines.extend([
                    f"### {i}. {content.title}",
                    f"",
                    f"- **출처:** {content.source_url}",
                    f"- **수집 시간:** {content.collected_at[:16].replace('T', ' ')}",
                    f"- **관련성 점수:** {content.relevance_score:.2f}",
                ])

                if content.keywords_matched:
                    lines.append(f"- **매칭 키워드:** {', '.join(content.keywords_matched)}")

                if content.metadata:
                    for key, value in content.metadata.items():
                        if value:
                            lines.append(f"- **{key}:** {value}")

                lines.extend([
                    f"",
                    truncated_content,
                    f"",
                    "---",
                    ""
                ])

        return "\n".join(lines)


class ETLPipeline:
    """
    전체 ETL 파이프라인을 조율하는 메인 클래스.
    Extract → Transform → Load 과정을 통합 관리합니다.
    """

    def __init__(self, settings=None):
        self.settings = settings
        self.cleaner = ContentCleaner()
        self.converter = ContentConverter()
        self._filter_engine = None

        if settings and hasattr(settings, 'filter'):
            self._filter_engine = ContentFilter(
                include_keywords=settings.filter.global_keywords,
                exclude_keywords=settings.filter.global_exclude_keywords,
                min_content_length=settings.filter.min_content_length,
                max_content_length=settings.filter.max_content_length,
            )

        logger.info("ETLPipeline 초기화 완료")

    def process_emails(self, emails: list) -> List[FilteredContent]:
        """이메일 데이터를 처리합니다."""
        results = []
        for email_item in emails:
            content = self.converter.convert_to_filtered_content(
                email_item, "email", self._filter_engine
            )
            if content and len(content.content) >= 100:
                results.append(content)
        logger.info(f"이메일 처리 완료: {len(results)}개")
        return results

    def process_browser_history(self, history: list) -> List[FilteredContent]:
        """브라우저 히스토리를 처리합니다."""
        results = []
        for item in history:
            content = self.converter.convert_to_filtered_content(
                item, "browser", self._filter_engine
            )
            if content:
                results.append(content)
        logger.info(f"브라우저 히스토리 처리 완료: {len(results)}개")
        return results

    def process_web_contents(self, web_contents: list) -> List[FilteredContent]:
        """웹 콘텐츠를 처리합니다."""
        results = []
        for item in web_contents:
            content = self.converter.convert_to_filtered_content(
                item, "web", self._filter_engine
            )
            if content and len(content.content) >= 200:
                results.append(content)
        logger.info(f"웹 콘텐츠 처리 완료: {len(results)}개")
        return results

    def process_kakao_messages(self, messages: list) -> List[FilteredContent]:
        """카카오톡 메시지를 처리합니다."""
        results = []
        for item in messages:
            content = self.converter.convert_to_filtered_content(
                item, "kakao", self._filter_engine
            )
            if content:
                results.append(content)
        logger.info(f"카카오톡 메시지 처리 완료: {len(results)}개")
        return results

    def save_all(
        self,
        all_contents: List[FilteredContent],
        notebook_name: str = "notebooklm_data"
    ) -> List[Path]:
        """모든 처리된 콘텐츠를 마크다운 파일로 저장합니다."""
        if not all_contents:
            logger.warning("저장할 콘텐츠가 없습니다.")
            return []

        return self.converter.save_as_markdown(all_contents, notebook_name)


# 테스트 실행
if __name__ == "__main__":
    print("=== 필터링 및 변환 엔진 테스트 ===")

    # 필터 테스트
    filter_engine = ContentFilter(
        include_keywords=["Python", "AI", "머신러닝"],
        exclude_keywords=["광고", "스팸"]
    )

    test_text = "Python을 활용한 AI 머신러닝 프로젝트 소개"
    score = filter_engine.calculate_relevance_score(test_text)
    keywords = filter_engine.get_matched_keywords(test_text)
    print(f"관련성 점수: {score}")
    print(f"매칭 키워드: {keywords}")

    # 클리너 테스트
    cleaner = ContentCleaner()
    dirty_text = "<p>안녕하세요! <b>Python</b> 튜토리얼입니다.</p>\n\n\n광고 | 수신거부"
    clean_text = cleaner.clean(dirty_text)
    print(f"\n정제 전: {dirty_text}")
    print(f"정제 후: {clean_text}")
