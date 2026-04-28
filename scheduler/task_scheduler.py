"""
NotebookLM ETL Pipeline - 스케줄러 모듈
Windows 환경에서 주기적인 ETL 파이프라인 실행을 자동화합니다.
schedule 라이브러리를 사용하여 유연한 스케줄링을 지원합니다.
"""

import asyncio
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Dict, Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("scheduler")


class ETLScheduler:
    """
    ETL 파이프라인의 주기적 실행을 관리하는 스케줄러 클래스.
    """

    def __init__(self, settings=None):
        self.settings = settings
        self._jobs = []
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._last_run: Optional[datetime] = None
        self._run_count = 0

    def add_job(
        self,
        func: Callable,
        interval_hours: float = 6.0,
        job_name: str = "etl_job"
    ):
        """
        스케줄 작업을 추가합니다.

        Args:
            func: 실행할 함수 (async 함수 지원)
            interval_hours: 실행 주기 (시간)
            job_name: 작업 이름
        """
        self._jobs.append({
            "func": func,
            "interval_seconds": interval_hours * 3600,
            "name": job_name,
            "last_run": None,
            "next_run": datetime.now()
        })
        logger.info(f"스케줄 작업 등록: {job_name} (주기: {interval_hours}시간)")

    def start(self, run_immediately: bool = True):
        """스케줄러를 시작합니다."""
        if self._is_running:
            logger.warning("스케줄러가 이미 실행 중입니다.")
            return

        self._is_running = True
        logger.info("스케줄러 시작")

        if run_immediately:
            self._run_all_jobs()

        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """스케줄러를 중지합니다."""
        self._is_running = False
        logger.info("스케줄러 중지")

    def _scheduler_loop(self):
        """스케줄러 메인 루프."""
        while self._is_running:
            now = datetime.now()
            for job in self._jobs:
                if now >= job["next_run"]:
                    logger.info(f"스케줄 작업 실행: {job['name']}")
                    try:
                        if asyncio.iscoroutinefunction(job["func"]):
                            asyncio.run(job["func"]())
                        else:
                            job["func"]()
                        job["last_run"] = now
                        job["next_run"] = datetime.fromtimestamp(
                            now.timestamp() + job["interval_seconds"]
                        )
                        self._run_count += 1
                        logger.info(f"작업 완료: {job['name']} (다음 실행: {job['next_run'].strftime('%H:%M')})")
                    except Exception as e:
                        logger.error(f"작업 실행 오류 ({job['name']}): {e}")

            time.sleep(60)  # 1분마다 확인

    def _run_all_jobs(self):
        """모든 작업을 즉시 실행합니다."""
        for job in self._jobs:
            try:
                if asyncio.iscoroutinefunction(job["func"]):
                    asyncio.run(job["func"]())
                else:
                    job["func"]()
                job["last_run"] = datetime.now()
            except Exception as e:
                logger.error(f"즉시 실행 오류 ({job['name']}): {e}")

    def get_status(self) -> Dict[str, Any]:
        """스케줄러 상태를 반환합니다."""
        return {
            "is_running": self._is_running,
            "total_runs": self._run_count,
            "jobs": [
                {
                    "name": job["name"],
                    "last_run": job["last_run"].isoformat() if job["last_run"] else None,
                    "next_run": job["next_run"].isoformat() if job["next_run"] else None,
                    "interval_hours": job["interval_seconds"] / 3600
                }
                for job in self._jobs
            ]
        }


class SystemTrayApp:
    """
    Windows 시스템 트레이 아이콘 앱.
    백그라운드에서 실행되며 트레이 아이콘을 통해 제어합니다.
    pystray 라이브러리를 사용합니다.
    """

    def __init__(self, etl_scheduler: ETLScheduler, gui_launcher: Callable = None):
        self.scheduler = etl_scheduler
        self.gui_launcher = gui_launcher
        self._tray_icon = None

    def setup(self) -> bool:
        """시스템 트레이 아이콘을 설정합니다."""
        try:
            import pystray
            from PIL import Image, ImageDraw

            # 트레이 아이콘 이미지 생성 (간단한 파란 원)
            icon_image = self._create_icon_image()

            # 메뉴 항목 정의
            menu = pystray.Menu(
                pystray.MenuItem("NotebookLM ETL Manager", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("대시보드 열기", self._open_dashboard),
                pystray.MenuItem("지금 동기화", self._run_sync_now),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "자동 실행",
                    self._toggle_scheduler,
                    checked=lambda item: self.scheduler._is_running
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("종료", self._quit)
            )

            self._tray_icon = pystray.Icon(
                "notebooklm_etl",
                icon_image,
                "NotebookLM ETL Manager",
                menu
            )
            return True

        except ImportError:
            logger.warning("pystray가 설치되지 않았습니다. 시스템 트레이 기능을 사용할 수 없습니다.")
            return False

    def run(self):
        """시스템 트레이 아이콘을 실행합니다."""
        if self._tray_icon:
            self._tray_icon.run()

    def _create_icon_image(self):
        """트레이 아이콘 이미지를 생성합니다."""
        from PIL import Image, ImageDraw
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 파란색 원 배경
        draw.ellipse([2, 2, size-2, size-2], fill=(26, 115, 232, 255))

        # 흰색 "N" 텍스트
        draw.text((20, 15), "N", fill=(255, 255, 255, 255))

        return image

    def _open_dashboard(self, icon, item):
        """대시보드 GUI를 엽니다."""
        if self.gui_launcher:
            threading.Thread(target=self.gui_launcher, daemon=True).start()

    def _run_sync_now(self, icon, item):
        """즉시 동기화를 실행합니다."""
        logger.info("트레이에서 즉시 동기화 요청")
        self.scheduler._run_all_jobs()

    def _toggle_scheduler(self, icon, item):
        """스케줄러를 켜거나 끕니다."""
        if self.scheduler._is_running:
            self.scheduler.stop()
        else:
            self.scheduler.start(run_immediately=False)

    def _quit(self, icon, item):
        """애플리케이션을 종료합니다."""
        self.scheduler.stop()
        if self._tray_icon:
            self._tray_icon.stop()
        logger.info("애플리케이션 종료")


# 테스트 실행
if __name__ == "__main__":
    print("=== 스케줄러 모듈 테스트 ===")

    def test_job():
        print(f"테스트 작업 실행: {datetime.now().strftime('%H:%M:%S')}")

    scheduler = ETLScheduler()
    scheduler.add_job(test_job, interval_hours=0.001, job_name="test_job")  # 약 3.6초 간격

    print("스케줄러 상태:", json.dumps(scheduler.get_status(), ensure_ascii=False, indent=2))
