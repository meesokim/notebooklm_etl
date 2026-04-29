# -*- coding: utf-8 -*-
"""
NotebookLM ETL Pipeline - 로깅 유틸리티
"""

import logging
import sys
import io
from pathlib import Path
from datetime import datetime


LOG_DIR = Path(__file__).parent.parent / "data" / "logs"


def setup_logger(name: str = "notebooklm_etl", level: str = "INFO") -> logging.Logger:
    """로거 설정 및 반환."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Windows 콘솔에서 한글 깨짐 방지
    if sys.platform == "win32":
        # 이미 UTF-8로 설정되어 있는지 확인하고, 아닐 경우에만 안전하게 래핑
        if not hasattr(sys.stdout, 'encoding') or sys.stdout.encoding.lower() != 'utf-8':
            try:
                # 스트림이 닫히지 않도록 조심스럽게 재정의
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)
            except (AttributeError, io.UnsupportedOperation):
                pass

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)

    # 파일 핸들러 (날짜별 로그 파일)
    log_file = LOG_DIR / f"etl_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(name)s (%(filename)s:%(lineno)d): %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# 기본 로거
logger = setup_logger()
