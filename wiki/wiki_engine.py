"""
LLM Wiki Engine - 지식 베이스 관리 모듈
docs/LLM-wiki.md에 정의된 스키마(Ingest, Query, Lint)를 구현합니다.
추출된 데이터(FilteredContent)를 가져와 로컬 마크다운 기반의 위키 구조로 변환합니다.
"""

import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import dataclasses

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from transformers.filter_engine import FilteredContent
from utils.logger import setup_logger

logger = setup_logger("wiki_engine")

class WikiEngine:
    """
    LLM Wiki 관리를 수행하는 클래스 (Knowledge Engineer 역할).
    /raw, /wiki, index.md, log.md 구조를 유지하고 관리합니다.
    """
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            # 기본 경로는 프로젝트 루트 아래 data/wiki_base
            self.base_dir = Path(__file__).parent.parent / "data" / "wiki_base"
        else:
            self.base_dir = Path(base_dir)

        self.raw_dir = self.base_dir / "raw"
        self.wiki_dir = self.base_dir / "wiki"
        self.index_file = self.base_dir / "index.md"
        self.log_file = self.base_dir / "log.md"

        self._init_directories()

    def _init_directories(self):
        """위키 디렉토리 및 기본 파일을 초기화합니다."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.index_file.exists():
            with open(self.index_file, "w", encoding="utf-8") as f:
                f.write("# LLM Wiki Index\n\n이 문서는 위키 페이지의 목차 및 엔티티 목록입니다.\n\n## Pages\n\n")
        
        if not self.log_file.exists():
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write("# LLM Wiki Operations Log\n\n모든 작업(Ingest, Query, Lint)의 시계열 기록입니다.\n\n")

    def log_operation(self, operation: str, details: str):
        """log.md 파일에 작업을 기록합니다."""
        timestamp = datetime.now().isoformat()
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"- **[{timestamp[:19].replace('T', ' ')}] {operation}**: {details}\n")

    def ingest(self, contents: List[FilteredContent]):
        """
        새로운 소스 데이터 목록을 위키에 흡수합니다.
        1. /raw에 원본 저장
        2. /wiki에 마크다운 변환 및 생성 (YAML Frontmatter 포함)
        3. index.md 업데이트
        4. log.md 업데이트
        """
        if not contents:
            return

        ingested_count = 0
        for content in contents:
            try:
                # 1. Save raw (읽기 전용 목적의 원본 백업)
                raw_filename = f"{content.content_id}.json"
                raw_path = self.raw_dir / raw_filename
                with open(raw_path, "w", encoding="utf-8") as f:
                    json.dump(dataclasses.asdict(content), f, ensure_ascii=False, indent=2)

                # 2. Create/Update Wiki Page
                # 파일명 생성: 특수문자 제거 후 공백은 언더스코어로 변경
                safe_title = re.sub(r'[^\w\s가-힣-]', '', content.title).strip().replace(' ', '_')
                if not safe_title:
                    safe_title = f"Entity_{content.content_id}"
                
                # 최대 길이 제한 (OS 파일명 제한 고려)
                safe_title = safe_title[:50]
                wiki_filename = f"{safe_title}.md"
                wiki_path = self.wiki_dir / wiki_filename

                # YAML Frontmatter
                frontmatter = f"---\n"
                frontmatter += f"title: \"{content.title}\"\n"
                frontmatter += f"date: {datetime.now().isoformat()}\n"
                frontmatter += f"source: {content.source_type}\n"
                frontmatter += f"tags: {json.dumps(content.keywords_matched, ensure_ascii=False)}\n"
                frontmatter += f"---\n\n"

                # 본문
                wiki_body = f"# {content.title}\n\n"
                wiki_body += f"> **출처**: {content.source_url}\n"
                if content.metadata:
                    wiki_body += f"> **메타데이터**: {json.dumps(content.metadata, ensure_ascii=False)}\n"
                wiki_body += f"\n## 내용 요약\n\n{content.content}\n\n"
                wiki_body += f"---\n## 연결된 문서\n\n- [[index]]\n"

                with open(wiki_path, "w", encoding="utf-8") as f:
                    f.write(frontmatter + wiki_body)

                # 3. Update Index.md
                # 줄바꿈 제거하여 한 줄 요약 만들기
                oneline_summary = content.content[:80].replace('\\n', ' ').strip() + "..."
                self._update_index(wiki_filename, content.title, oneline_summary)
                
                ingested_count += 1
            except Exception as e:
                logger.error(f"Wiki Ingest 오류 ({content.title}): {e}")
                self.log_operation("Error", f"Failed to ingest {content.title}: {e}")

        self.log_operation("Ingest", f"Successfully ingested {ingested_count} new sources into wiki.")
        logger.info(f"Wiki Engine: {ingested_count}개 문서 흡수 완료")

    def _update_index(self, filename: str, title: str, summary: str):
        """index.md 파일에 새로운 문서를 목차에 추가합니다."""
        with open(self.index_file, "r", encoding="utf-8") as f:
            index_content = f.read()

        page_name = filename.replace('.md', '')
        entry = f"- [[{page_name}]] - **{title}**: {summary}"
        
        # 이미 목차에 있는지 확인 (단순 문자열 매칭)
        if f"[[{page_name}]]" not in index_content:
            with open(self.index_file, "a", encoding="utf-8") as f:
                f.write(f"{entry}\n")

    def query(self, query_text: str) -> List[str]:
        """
        사용자 질의응답 처리 (단순 텍스트 검색 시뮬레이션).
        실제 LLM 연동 시 index.md를 참조하여 관련 문서를 찾아 분석합니다.
        """
        self.log_operation("Query", f"Searched for '{query_text}'")
        results = []
        for file_path in self.wiki_dir.glob("*.md"):
            with open(file_path, "r", encoding="utf-8") as f:
                if query_text.lower() in f.read().lower():
                    results.append(file_path.name)
        
        self.log_operation("Query Result", f"Found {len(results)} pages matching '{query_text}'")
        return results

    def lint(self) -> Dict[str, List[str]]:
        """
        위키 무결성 점검 (유지보수).
        고립된 페이지(Orphan pages)와 깨진 링크를 찾습니다.
        """
        self.log_operation("Lint", "Started wiki integrity check")
        issues = {"orphans": [], "broken_links": []}
        
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                index_content = f.read()

            all_pages = [p.stem for p in self.wiki_dir.glob("*.md")]
            
            for page_name in all_pages:
                # 1. Orphan check: index.md에 없는 경우
                if f"[[{page_name}]]" not in index_content:
                    issues["orphans"].append(page_name)
                
                # 2. Broken links check (단순 구현: 파일 내의 [[링크]]가 실제 파일로 존재하는지 확인)
                file_path = self.wiki_dir / f"{page_name}.md"
                with open(file_path, "r", encoding="utf-8") as file_f:
                    content = file_f.read()
                    # 정규식으로 [[링크]] 추출
                    links = re.findall(r'\[\[(.*?)\]\]', content)
                    for link in links:
                        link_target = link.split('|')[0] # [[Target|Display]] 처리
                        if link_target != "index" and link_target not in all_pages:
                            issues["broken_links"].append(f"{page_name} -> {link_target}")

            self.log_operation("Lint Result", f"Found {len(issues['orphans'])} orphans, {len(issues['broken_links'])} broken links")
        except Exception as e:
            logger.error(f"Lint 오류: {e}")
            self.log_operation("Lint Error", str(e))
            
        return issues
