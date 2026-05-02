"""
NotebookLM ETL Pipeline - NotebookLM 연동 및 소스 관리 모듈
notebooklm-py 비공식 API 라이브러리를 사용하여 NotebookLM과 연동합니다.
소스 추가, 삭제, 노트북 관리 등의 기능을 제공합니다.

참고: notebooklm-py (https://github.com/teng-lin/notebooklm-py)
     Google 계정 인증이 필요합니다.
"""

import asyncio
import json
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

import sys
from contextlib import contextmanager
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("notebooklm_manager")

# 로컬 소스 추적 DB 경로 (JSON으로 변경)
SOURCE_TRACKING_DB = Path(__file__).parent.parent / "data" / "source_tracking.json"


@dataclass
class SourceRecord:
    """업로드된 소스 추적 레코드"""
    source_id: str           # NotebookLM에서 부여한 소스 ID
    notebook_id: str         # 노트북 ID
    notebook_name: str       # 노트북 이름
    title: str               # 소스 제목
    source_type: str         # 소스 타입
    local_file: str          # 로컬 파일 경로
    uploaded_at: str         # 업로드 시간
    content_hash: str        # 콘텐츠 해시 (중복 방지)
    is_active: bool = True   # 현재 활성 상태


class SourceTracker:
    """
    업로드된 소스의 메타데이터를 로컬 JSON 파일에서 추적하는 클래스.
    NotebookLM의 소스 제한(50개)을 관리하고 중복 업로드를 방지합니다.
    """

    def __init__(self, db_path: Path = SOURCE_TRACKING_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """데이터베이스 초기화."""
        if not self.db_path.exists():
            self._save_data({"sources": []})

    @contextmanager
    def _lock_file(self, mode='r'):
        """OS 파일 생성을 이용한 크로스 플랫폼 잠금. JSON 파일 동시성 문제 방지."""
        lock_path = self.db_path.with_suffix('.lock')
        start_time = time.time()
        
        while True:
            try:
                # O_CREAT | O_EXCL는 파일이 없을 때만 생성, 있으면 에러
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.close(fd)
                break
            except (FileExistsError, OSError):
                if time.time() - start_time > 10:
                    raise RuntimeError("Timeout waiting for file lock")
                time.sleep(0.1)

        file_obj = None
        try:
            file_mode = 'r+' if mode == 'w' else 'r'
            if not self.db_path.exists() and mode == 'w':
                file_mode = 'w+'
                
            if self.db_path.exists() or mode == 'w':
                file_obj = open(self.db_path, file_mode, encoding='utf-8')
            
            yield file_obj
            
        finally:
            if file_obj:
                try:
                    file_obj.close()
                except Exception:
                    pass
            try:
                if lock_path.exists():
                    os.unlink(str(lock_path))
            except OSError:
                pass

    def _load_data(self) -> Dict:
        try:
            with self._lock_file('r') as f:
                content = f.read().strip()
                if not content:
                    return {"sources": []}
                return json.loads(content)
        except Exception as e:
            logger.error(f"JSON 데이터 로드 실패: {e}")
            return {"sources": []}

    def _save_data(self, data: Dict):
        try:
            with self._lock_file('w') as f:
                f.seek(0)
                f.truncate()
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"JSON 데이터 저장 실패: {e}")

    def close(self):
        """이전 SQLite 인터페이스 호환성을 위해 유지"""
        pass

    def add_source(self, record: SourceRecord) -> bool:
        """소스 레코드를 추가합니다."""
        try:
            data = self._load_data()
            # 기존 레코드 업데이트 또는 새 레코드 추가
            updated = False
            for i, src in enumerate(data["sources"]):
                if src["source_id"] == record.source_id:
                    data["sources"][i] = asdict(record)
                    updated = True
                    break
            
            if not updated:
                data["sources"].append(asdict(record))
                
            self._save_data(data)
            return True
        except Exception as e:
            logger.error(f"소스 레코드 추가 실패: {e}")
            return False

    def mark_deleted(self, source_id: str) -> bool:
        """소스를 삭제 상태로 표시합니다."""
        try:
            data = self._load_data()
            for src in data["sources"]:
                if src["source_id"] == source_id:
                    src["is_active"] = False
                    self._save_data(data)
                    return True
            return False
        except Exception as e:
            logger.error(f"소스 상태 업데이트 실패: {e}")
            return False

    def get_active_sources(self, notebook_id: str) -> List[SourceRecord]:
        """특정 노트북의 활성 소스 목록을 반환합니다."""
        try:
            data = self._load_data()
            active_sources = [
                SourceRecord(**src) 
                for src in data["sources"] 
                if src["notebook_id"] == notebook_id and src.get("is_active", True)
            ]
            # uploaded_at 기준으로 오름차순 정렬
            active_sources.sort(key=lambda x: x.uploaded_at)
            return active_sources
        except Exception as e:
            logger.error(f"소스 목록 조회 실패: {e}")
            return []

    def is_already_uploaded(self, content_hash: str, notebook_id: str) -> bool:
        """동일한 콘텐츠가 이미 업로드되었는지 확인합니다."""
        try:
            data = self._load_data()
            for src in data["sources"]:
                if (src["content_hash"] == content_hash and 
                    src["notebook_id"] == notebook_id and 
                    src.get("is_active", True)):
                    return True
            return False
        except Exception:
            return False

    def get_oldest_sources(self, notebook_id: str, count: int) -> List[SourceRecord]:
        """가장 오래된 소스 N개를 반환합니다 (삭제 대상 선정용)."""
        active_sources = self.get_active_sources(notebook_id)
        return active_sources[:count]

    def get_statistics(self) -> Dict[str, Any]:
        """전체 소스 통계를 반환합니다."""
        try:
            data = self._load_data()
            active_count = 0
            deleted_count = 0
            per_notebook = {}
            
            for src in data["sources"]:
                is_active = src.get("is_active", True)
                if is_active:
                    active_count += 1
                    nb_id = src["notebook_id"]
                    per_notebook[nb_id] = per_notebook.get(nb_id, 0) + 1
                else:
                    deleted_count += 1
                    
            return {
                "active_sources": active_count,
                "deleted_sources": deleted_count,
                "per_notebook": per_notebook
            }
        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")
            return {}


class NotebookLMManager:
    """
    NotebookLM과의 연동을 관리하는 메인 클래스.
    notebooklm-py 라이브러리를 사용하여 소스 추가/삭제/관리를 수행합니다.
    """

    def __init__(
        self,
        max_sources_per_notebook: int = 45,
        auto_delete_old: bool = True
    ):
        """
        Args:
            max_sources_per_notebook: 노트북당 최대 소스 수 (안전 마진 포함)
            auto_delete_old: 한도 초과 시 오래된 소스 자동 삭제 여부
        """
        self.max_sources = max_sources_per_notebook
        self.auto_delete_old = auto_delete_old
        self.tracker = SourceTracker()
        self._client = None
        self._is_available = False

        # notebooklm-py 라이브러리 가용성 확인
        self._check_library_availability()

    def _check_library_availability(self):
        """notebooklm-py 라이브러리 가용성 확인."""
        try:
            import notebooklm
            self._is_available = True
            logger.info("notebooklm-py 라이브러리 사용 가능")
        except ImportError:
            self._is_available = False
            logger.warning(
                "notebooklm-py 라이브러리를 찾을 수 없습니다. "
                "시뮬레이션 모드로 실행됩니다. "
                "설치: pip install notebooklm-py"
            )

    async def initialize(self) -> bool:
        """NotebookLM 클라이언트를 초기화합니다."""
        if not self._is_available:
            logger.warning("notebooklm-py가 없어 시뮬레이션 모드로 실행됩니다.")
            return False

        try:
            from notebooklm import NotebookLMClient
            client = await NotebookLMClient.from_storage()
            if hasattr(client, "__aenter__"):
                self._client = await client.__aenter__()
            else:
                self._client = client
            logger.info("NotebookLM 클라이언트 초기화 성공")
            return True
        except Exception as e:
            logger.error(f"NotebookLM 클라이언트 초기화 실패: {e}")
            logger.info("Google 계정으로 먼저 인증이 필요합니다. 'notebooklm auth' 명령을 실행하세요.")
            return False

    async def list_notebooks(self) -> List[Dict[str, str]]:
        """사용 가능한 노트북 목록을 반환합니다."""
        if not self._client:
            logger.warning("[시뮬레이션] 노트북 목록 조회")
            return [{"id": "demo_nb_001", "title": "데모 노트북"}]

        try:
            notebooks = await self._client.notebooks.list()
            return [{"id": nb.id, "title": nb.title} for nb in notebooks]
        except Exception as e:
            logger.error(f"노트북 목록 조회 실패: {e}")
            return []

    async def upload_source(
        self,
        notebook_id: str,
        notebook_name: str,
        file_path: Path,
        source_type: str = "text",
        content_hash: str = ""
    ) -> Optional[str]:
        """
        NotebookLM 노트북에 소스를 업로드합니다.

        Args:
            notebook_id: 대상 노트북 ID
            notebook_name: 노트북 이름
            file_path: 업로드할 파일 경로
            source_type: 소스 타입
            content_hash: 콘텐츠 해시 (중복 방지용)

        Returns:
            업로드된 소스 ID 또는 None
        """
        # 중복 확인
        if content_hash and self.tracker.is_already_uploaded(content_hash, notebook_id):
            logger.info(f"이미 업로드된 콘텐츠 건너뜀: {file_path.name}")
            return None

        # 소스 개수 확인 및 정리
        active_sources = self.tracker.get_active_sources(notebook_id)
        if len(active_sources) >= self.max_sources:
            if self.auto_delete_old:
                await self._cleanup_old_sources(notebook_id, 5)
            else:
                logger.warning(f"소스 한도 초과 ({len(active_sources)}/{self.max_sources}). 업로드 건너뜀.")
                return None

        # 실제 업로드
        source_id = await self._do_upload(notebook_id, file_path)

        if source_id:
            # 추적 DB에 기록
            record = SourceRecord(
                source_id=source_id,
                notebook_id=notebook_id,
                notebook_name=notebook_name,
                title=file_path.stem,
                source_type=source_type,
                local_file=str(file_path),
                uploaded_at=datetime.now().isoformat(),
                content_hash=content_hash,
                is_active=True
            )
            self.tracker.add_source(record)
            logger.info(f"소스 업로드 성공: {file_path.name} -> {source_id}")

        return source_id

    async def _do_upload(self, notebook_id: str, file_path: Path) -> Optional[str]:
        """실제 파일 업로드를 수행합니다."""
        if not self._client:
            # 시뮬레이션 모드
            import hashlib
            fake_id = f"sim_{hashlib.md5(str(file_path).encode()).hexdigest()[:8]}"
            logger.info(f"[시뮬레이션] 파일 업로드: {file_path.name} -> {fake_id}")
            return fake_id

        try:
            source = await self._client.sources.add_file(notebook_id, file_path)
            return source.id
        except Exception as e:
            logger.error(f"파일 업로드 실패 ({file_path.name}): {e}")
            return None

    async def upload_url(
        self,
        notebook_id: str,
        notebook_name: str,
        url: str,
        content_hash: str = ""
    ) -> Optional[str]:
        """URL을 소스로 추가합니다."""
        # 중복 확인
        if content_hash and self.tracker.is_already_uploaded(content_hash, notebook_id):
            logger.info(f"이미 업로드된 URL 건너뜀: {url[:60]}")
            return None

        if not self._client:
            fake_id = f"sim_url_{hash(url) % 10000:04d}"
            logger.info(f"[시뮬레이션] URL 추가: {url[:60]} -> {fake_id}")
            return fake_id

        try:
            source = await self._client.sources.add_url(notebook_id, url)
            if source:
                record = SourceRecord(
                    source_id=source.id,
                    notebook_id=notebook_id,
                    notebook_name=notebook_name,
                    title=url[:100],
                    source_type="url",
                    local_file="",
                    uploaded_at=datetime.now().isoformat(),
                    content_hash=content_hash,
                    is_active=True
                )
                self.tracker.add_source(record)
                logger.info(f"URL 소스 추가 성공: {url[:60]} -> {source.id}")
                return source.id
        except Exception as e:
            logger.error(f"URL 소스 추가 실패 ({url[:60]}): {e}")
        return None

    async def delete_source(self, notebook_id: str, source_id: str) -> bool:
        """소스를 삭제합니다."""
        if not self._client:
            logger.info(f"[시뮬레이션] 소스 삭제: {source_id}")
            self.tracker.mark_deleted(source_id)
            return True

        try:
            success = await self._client.sources.delete(notebook_id, source_id)
            if success:
                self.tracker.mark_deleted(source_id)
                logger.info(f"소스 삭제 성공: {source_id}")
            return success
        except Exception as e:
            logger.error(f"소스 삭제 실패 ({source_id}): {e}")
            return False

    async def _cleanup_old_sources(self, notebook_id: str, count: int = 5):
        """오래된 소스를 삭제하여 공간을 확보합니다."""
        old_sources = self.tracker.get_oldest_sources(notebook_id, count)
        logger.info(f"오래된 소스 {len(old_sources)}개 삭제 시작...")

        for source in old_sources:
            success = await self.delete_source(notebook_id, source.source_id)
            if success:
                logger.info(f"삭제됨: {source.title} (업로드: {source.uploaded_at[:10]})")
            await asyncio.sleep(1)  # API 호출 간 지연

    async def bulk_upload_files(
        self,
        notebook_id: str,
        notebook_name: str,
        file_paths: List[Path],
        delay: float = 2.0
    ) -> Dict[str, Any]:
        """
        여러 파일을 일괄 업로드합니다.

        Args:
            notebook_id: 대상 노트북 ID
            notebook_name: 노트북 이름
            file_paths: 업로드할 파일 경로 목록
            delay: 업로드 간 지연 시간 (초)

        Returns:
            업로드 결과 통계
        """
        results = {
            "total": len(file_paths),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "source_ids": []
        }

        for i, file_path in enumerate(file_paths):
            logger.info(f"업로드 중 ({i+1}/{len(file_paths)}): {file_path.name}")

            # 파일 해시 계산
            import hashlib
            with open(file_path, 'rb') as f:
                content_hash = hashlib.md5(f.read()).hexdigest()

            source_id = await self.upload_source(
                notebook_id, notebook_name, file_path,
                content_hash=content_hash
            )

            if source_id is None:
                if self.tracker.is_already_uploaded(content_hash, notebook_id):
                    results["skipped"] += 1
                else:
                    results["failed"] += 1
            else:
                results["success"] += 1
                results["source_ids"].append(source_id)

            if i < len(file_paths) - 1:
                await asyncio.sleep(delay)

        logger.info(
            f"일괄 업로드 완료: 성공 {results['success']}, "
            f"실패 {results['failed']}, 건너뜀 {results['skipped']}"
        )
        return results

    def get_status(self, notebook_id: str = None) -> Dict[str, Any]:
        """현재 소스 관리 상태를 반환합니다."""
        stats = self.tracker.get_statistics()

        if notebook_id:
            active_sources = self.tracker.get_active_sources(notebook_id)
            stats["current_notebook"] = {
                "notebook_id": notebook_id,
                "active_sources": len(active_sources),
                "max_sources": self.max_sources,
                "available_slots": max(0, self.max_sources - len(active_sources))
            }

        return stats

    async def close(self):
        """클라이언트 연결을 종료합니다."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
        self.tracker.close()


class ETLOrchestrator:
    """
    전체 ETL 파이프라인의 실행을 조율하는 오케스트레이터 클래스.
    스케줄러와 연동하여 주기적인 데이터 수집 및 업로드를 자동화합니다.
    """

    def __init__(self, settings=None):
        self.settings = settings
        self.manager = NotebookLMManager(
            max_sources_per_notebook=getattr(
                getattr(settings, 'notebooklm', None), 'max_sources_per_notebook', 45
            ) if settings else 45
        )
        self._last_run = None
        self._is_running = False

    async def run_full_pipeline(
        self,
        notebook_id: str,
        notebook_name: str,
        processed_files: List[Path]
    ) -> Dict[str, Any]:
        """
        전체 ETL 파이프라인을 실행합니다.

        Args:
            notebook_id: 대상 NotebookLM 노트북 ID
            notebook_name: 노트북 이름
            processed_files: 업로드할 처리된 파일 목록

        Returns:
            실행 결과 통계
        """
        if self._is_running:
            logger.warning("파이프라인이 이미 실행 중입니다.")
            return {"status": "already_running"}

        self._is_running = True
        start_time = datetime.now()
        logger.info(f"ETL 파이프라인 시작: {notebook_name}")

        try:
            # NotebookLM 클라이언트 초기화
            await self.manager.initialize()

            # 파일 업로드
            upload_results = await self.manager.bulk_upload_files(
                notebook_id, notebook_name, processed_files
            )

            # 결과 기록
            self._last_run = datetime.now()
            elapsed = (datetime.now() - start_time).total_seconds()

            result = {
                "status": "success",
                "started_at": start_time.isoformat(),
                "completed_at": self._last_run.isoformat(),
                "elapsed_seconds": elapsed,
                "upload_results": upload_results,
                "source_status": self.manager.get_status(notebook_id)
            }

            logger.info(f"ETL 파이프라인 완료: {elapsed:.1f}초 소요")
            return result

        except Exception as e:
            logger.error(f"ETL 파이프라인 오류: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            self._is_running = False
            await self.manager.close()


# 테스트 실행
if __name__ == "__main__":
    async def test():
        print("=== NotebookLM 관리 모듈 테스트 ===")
        manager = NotebookLMManager()

        # 상태 확인
        status = manager.get_status()
        print(f"현재 상태: {json.dumps(status, ensure_ascii=False, indent=2)}")

        # 노트북 목록 조회
        notebooks = await manager.list_notebooks()
        print(f"노트북 목록: {notebooks}")

    asyncio.run(test())
