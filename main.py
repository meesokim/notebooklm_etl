# -*- coding: utf-8 -*-
"""
NotebookLM ETL Pipeline - 메인 진입점
Windows 환경에서 GUI 또는 CLI 모드로 실행합니다.

사용법:
  python main.py              # GUI 모드 (기본)
  python main.py --cli        # CLI 모드
  python main.py --sync       # 즉시 동기화 후 종료
  python main.py --daemon     # 백그라운드 데몬 모드
  python main.py --status     # 현재 상태 출력
"""

import argparse
import asyncio
import json
import sys
import io
import os
import locale
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import SettingsManager
from utils.logger import setup_logger

logger = setup_logger("main")


def run_gui():
    """GUI 모드로 실행합니다."""
    try:
        from gui.main_app import NotebookLMETLApp
        app = NotebookLMETLApp()
        app.run()
    except ImportError as e:
        logger.error(f"GUI 모듈 로드 실패: {e}")
        print("GUI를 시작할 수 없습니다. tkinter가 설치되어 있는지 확인하세요.")
        sys.exit(1)


def init_directories():
    """필요한 데이터 디렉토리를 초기화합니다."""
    dirs = [
        "data/raw",
        "data/processed",
        "data/logs",
        "config"
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
    logger.info("디렉토리 초기화 완료")


async def run_sync(settings_manager: SettingsManager):
    """전체 ETL 파이프라인을 한 번 실행합니다."""
    settings = settings_manager.get()
    all_contents = []

    print(f"\n{'='*60}")
    print(f"  NotebookLM ETL 파이프라인 실행")
    print(f"  시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # 1. 이메일 수집
    emails = []
    if settings.email.enabled and settings.email.username:
        print("📧 이메일 수집 중...")
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
            print(f"   ✓ {len(emails)}개 이메일 수집 완료")
        except Exception as e:
            print(f"   ✗ 이메일 수집 실패: {e}")
    else:
        print("📧 이메일 수집: 비활성화 또는 계정 미설정")

    # 2. 브라우저 히스토리 수집
    history = []
    if settings.browser.enabled:
        print("🌐 브라우저 히스토리 수집 중...")
        try:
            from extractors.browser_extractor import BrowserHistoryExtractor
            extractor = BrowserHistoryExtractor(browsers=settings.browser.browsers)
            history = extractor.extract(
                days_back=settings.browser.days_back,
                min_visit_count=settings.browser.min_visit_count,
                exclude_domains=settings.browser.exclude_domains
            )
            print(f"   ✓ {len(history)}개 히스토리 항목 수집 완료")
        except Exception as e:
            print(f"   ✗ 브라우저 히스토리 수집 실패: {e}")
    else:
        print("🌐 브라우저 히스토리 수집: 비활성화")

    # 3. 카카오톡 메시지 수집
    kakao_msgs = []
    if settings.kakao.enabled:
        print("💬 카카오톡 메시지 수집 중...")
        try:
            from extractors.kakao_extractor import KakaoTalkExtractor
            extractor = KakaoTalkExtractor()
            # UI 자동화 시도
            kakao_msgs = extractor.extract_via_ui_automation(
                target_rooms=settings.kakao.target_rooms,
                max_messages=settings.kakao.max_messages
            )
            print(f"   ✓ {len(kakao_msgs)}개 카카오톡 메시지 수집 완료")
        except Exception as e:
            print(f"   ✗ 카카오톡 수집 실패: {e}")
    else:
        print("💬 카카오톡 수집: 비활성화")

    # 4. 웹 콘텐츠 및 네이버 카페 수집
    web_contents = []
    if settings.naver_cafe.enabled:
        print("☕ 네이버 카페 수집 중...")
        try:
            from extractors.web_scraper import NaverCafeScraper
            scraper = NaverCafeScraper()
            for url in settings.naver_cafe.cafe_urls:
                posts = scraper.scrape_cafe_posts(
                    url, 
                    keywords=settings.naver_cafe.keywords,
                    max_posts=settings.naver_cafe.max_posts
                )
                web_contents.extend(posts)
            scraper.close()
            print(f"   ✓ {len(web_contents)}개 네이버 카페 게시물 수집 완료")
        except Exception as e:
            print(f"   ✗ 네이버 카페 수집 실패: {e}")
    else:
        print("☕ 네이버 카페 수집: 비활성화")

    # 5. 데이터 변환 및 필터링
    print("\n🔄 데이터 변환 및 필터링 중...")
    try:
        from transformers.filter_engine import ETLPipeline
        pipeline = ETLPipeline(settings)

        processed_emails = pipeline.process_emails(emails)
        processed_history = pipeline.process_browser_history(history)
        processed_kakao = pipeline.process_kakao_messages(kakao_msgs)
        processed_web = pipeline.process_web_contents(web_contents)
        
        all_contents = processed_emails + processed_history + processed_kakao + processed_web

        print(f"   ✓ 이메일: {len(processed_emails)}개 처리")
        print(f"   ✓ 브라우저: {len(processed_history)}개 처리")
        print(f"   ✓ 카카오톡: {len(processed_kakao)}개 처리")
        print(f"   ✓ 웹/카페: {len(processed_web)}개 처리")
        print(f"   ✓ 총 {len(all_contents)}개 콘텐츠 준비 완료")
    except Exception as e:
        print(f"   ✗ 데이터 변환 실패: {e}")
        logger.exception("데이터 변환 중 치명적 오류")
        return

    if not all_contents:
        print("\n⚠️  업로드할 콘텐츠가 없습니다.")
        return

    # 6. 마크다운 파일 저장
    print("\n💾 마크다운 파일 저장 중...")
    try:
        saved_files = pipeline.save_all(all_contents, "notebooklm_sync")
        print(f"   ✓ {len(saved_files)}개 파일 저장 완료")
    except Exception as e:
        print(f"   ✗ 파일 저장 실패: {e}")
        return

    # 7. NotebookLM 업로드
    print("\n📤 NotebookLM 업로드 중...")
    try:
        from loaders.notebooklm_manager import ETLOrchestrator
        orchestrator = ETLOrchestrator(settings)

        if not settings.notebooklm.target_notebooks:
            print("   ⚠️ 대상 노트북이 설정되지 않았습니다. 업로드를 건너뜁니다.")
        else:
            for nb_name, nb_id in settings.notebooklm.target_notebooks.items():
                print(f"   노트북: {nb_name} ({nb_id[:8]}...)")
                result = await orchestrator.run_full_pipeline(nb_id, nb_name, saved_files)
                if result.get("status") == "success":
                    upload = result.get("upload_results", {})
                    print(f"   ✓ 업로드 완료: 성공 {upload.get('success', 0)}, "
                          f"건너뜀 {upload.get('skipped', 0)}, "
                          f"실패 {upload.get('failed', 0)}")
                else:
                    print(f"   ✗ 업로드 실패: {result.get('error', '알 수 없는 오류')}")
    except Exception as e:
        print(f"   ✗ NotebookLM 업로드 실패: {e}")

    print(f"\n{'='*60}")
    print(f"  파이프라인 완료: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")


def run_daemon(settings_manager: SettingsManager):
    """백그라운드 데몬 모드로 실행합니다."""
    settings = settings_manager.get()

    print("NotebookLM ETL 데몬 시작...")
    print(f"실행 주기: {settings.schedule_interval_hours}시간")
    print("종료하려면 Ctrl+C를 누르세요.\n")

    from scheduler.task_scheduler import ETLScheduler

    scheduler = ETLScheduler(settings)
    scheduler.add_job(
        lambda: asyncio.run(run_sync(settings_manager)),
        interval_hours=settings.schedule_interval_hours,
        job_name="full_etl_sync"
    )

    try:
        scheduler.start(run_immediately=True)
        # 메인 스레드 유지
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n데몬 종료 중...")
        scheduler.stop()


def show_status(settings_manager: SettingsManager):
    """현재 상태를 출력합니다."""
    settings = settings_manager.get()

    print(f"\n{'='*60}")
    print(f"  NotebookLM ETL Manager - 현재 상태")
    print(f"{'='*60}")

    print(f"\n📧 이메일 수집:")
    print(f"   활성화: {settings.email.enabled}")
    print(f"   제공자: {settings.email.provider}")
    print(f"   계정: {settings.email.username or '(미설정)'}")

    print(f"\n🌐 브라우저 히스토리:")
    print(f"   활성화: {settings.browser.enabled}")
    print(f"   브라우저: {', '.join(settings.browser.browsers)}")

    print(f"\n🔍 필터링:")
    print(f"   관심 키워드: {len(settings.filter.global_keywords)}개")
    print(f"   제외 키워드: {len(settings.filter.global_exclude_keywords)}개")

    print(f"\n📓 NotebookLM:")
    print(f"   Google 계정: {settings.notebooklm.google_account_email or '(미설정)'}")
    print(f"   대상 노트북: {len(settings.notebooklm.target_notebooks)}개")
    for name, nb_id in settings.notebooklm.target_notebooks.items():
        print(f"     - {name}: {nb_id[:20]}...")

    print(f"\n⏰ 스케줄:")
    print(f"   자동 실행: {settings.schedule_enabled}")
    print(f"   실행 주기: {settings.schedule_interval_hours}시간")

    try:
        from loaders.notebooklm_manager import SourceTracker
        tracker = SourceTracker()
        stats = tracker.get_statistics()
        print(f"\n📊 소스 통계:")
        print(f"   활성 소스: {stats.get('active_sources', 0)}개")
        print(f"   삭제된 소스: {stats.get('deleted_sources', 0)}개")
    except Exception:
        pass

    print(f"\n{'='*60}\n")


def setup_wizard(settings_manager: SettingsManager):
    """초기 설정 마법사를 실행합니다."""
    print(f"\n{'='*60}")
    print(f"  NotebookLM ETL Manager - 초기 설정 마법사")
    print(f"{'='*60}\n")

    settings = settings_manager.get()

    print("이메일 설정:")
    provider = input("  이메일 제공자 (naver/gmail) [naver]: ").strip() or "naver"
    username = input("  이메일 주소: ").strip()
    password = input("  앱 비밀번호: ").strip()

    settings.email.provider = provider
    settings.email.username = username
    settings.email.password = password
    settings.email.enabled = bool(username and password)

    print("\nNotebookLM 설정:")
    google_email = input("  Google 계정 이메일: ").strip()
    settings.notebooklm.google_account_email = google_email

    print("\n관심 키워드 (쉼표로 구분):")
    keywords_input = input("  키워드: ").strip()
    if keywords_input:
        settings.filter.global_keywords = [k.strip() for k in keywords_input.split(',')]

    settings_manager.save(settings)
    print("\n✓ 설정이 저장되었습니다.")
    print("  이제 'python main.py --sync'로 동기화를 실행하거나")
    print("  'python main.py'로 GUI를 시작할 수 있습니다.\n")


def main():
    """메인 진입점."""
    # 리눅스/WSL에서 한글 로케일 설정
    if sys.platform != "win32":
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
            os.environ['LANG'] = 'C.UTF-8'
            os.environ['LC_ALL'] = 'C.UTF-8'
        except Exception:
            pass

    # Windows 콘솔에서 한글 깨짐 방지
    if sys.platform == "win32":
        if not hasattr(sys.stdout, 'encoding') or sys.stdout.encoding.lower() != 'utf-8':
            try:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)
            except (AttributeError, io.UnsupportedOperation):
                pass

    parser = argparse.ArgumentParser(
        description="NotebookLM ETL Manager - 데이터 소스 자동화 관리 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python main.py              GUI 모드로 실행 (기본)
  python main.py --sync       즉시 동기화 실행
  python main.py --daemon     백그라운드 데몬 모드
  python main.py --status     현재 상태 확인
  python main.py --setup      초기 설정 마법사
        """
    )

    parser.add_argument("--sync", action="store_true", help="즉시 동기화 실행 후 종료")
    parser.add_argument("--daemon", action="store_true", help="백그라운드 데몬 모드")
    parser.add_argument("--status", action="store_true", help="현재 상태 출력")
    parser.add_argument("--setup", action="store_true", help="초기 설정 마법사")
    parser.add_argument("--cli", action="store_true", help="CLI 모드 (GUI 없이)")
    parser.add_argument("--config", type=str, help="설정 파일 경로")

    args = parser.parse_args()

    # 디렉토리 초기화
    init_directories()

    # 설정 관리자 초기화
    settings_manager = SettingsManager(config_path=args.config)
    settings_manager.load()

    if args.setup:
        setup_wizard(settings_manager)
    elif args.status:
        show_status(settings_manager)
    elif args.sync:
        asyncio.run(run_sync(settings_manager))
    elif args.daemon:
        run_daemon(settings_manager)
    elif args.cli:
        show_status(settings_manager)
    else:
        # 기본: GUI 모드
        run_gui()


if __name__ == "__main__":
    main()
