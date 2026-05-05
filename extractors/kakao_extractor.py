"""
NotebookLM ETL Pipeline - 카카오톡 PC 데이터 추출 모듈
Windows 환경에서 카카오톡 PC 버전의 채팅 내용을 추출합니다.
pywinauto 또는 pyautogui를 사용하여 UI 자동화를 수행합니다.

주의: 이 모듈은 Windows 전용이며, 카카오톡 PC 버전이 설치되어 있어야 합니다.
"""

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass, field

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("kakao_extractor")


@dataclass
class KakaoMessage:
    """카카오톡 메시지 데이터 구조"""
    room_name: str
    sender: str
    message: str
    timestamp: str
    message_type: str = "text"  # "text", "link", "image", "file"
    links: List[str] = field(default_factory=list)
    source: str = "kakao"


class KakaoTalkExtractor:
    """
    카카오톡 PC 버전에서 채팅 내용을 추출하는 클래스.
    Windows UI 자동화를 통해 채팅방 내용을 읽어옵니다.

    지원 방법:
    1. 내보내기 파일 파싱 (가장 안정적): 카카오톡 '대화 내보내기' 기능 활용
    2. UI 자동화 (실시간): pywinauto를 사용한 화면 텍스트 추출
    """

    def __init__(self):
        self._is_windows = sys.platform == "win32"
        logger.info(f"KakaoTalkExtractor 초기화 (Windows: {self._is_windows})")

    def extract_from_export_file(
        self,
        file_path: str,
        keywords: List[str] = None,
        max_messages: int = 200
    ) -> List[KakaoMessage]:
        """
        카카오톡 '대화 내보내기' 기능으로 저장된 텍스트 파일을 파싱합니다.

        카카오톡 PC에서 대화 내보내기:
        채팅방 우측 상단 메뉴 → 대화 내보내기 → 텍스트 파일(.txt) 저장

        Args:
            file_path: 내보내기된 .txt 파일 경로
            keywords: 필터링 키워드 목록
            max_messages: 최대 추출 메시지 수

        Returns:
            추출된 KakaoMessage 목록
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"파일을 찾을 수 없습니다: {file_path}")
            return []

        messages = []
        keywords = keywords or []

        try:
            # 카카오톡 내보내기 파일은 UTF-8 또는 UTF-8 BOM 인코딩
            with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                content = f.read()

            # 채팅방 이름 추출 (첫 번째 줄)
            lines = content.split('\n')
            room_name = lines[0].strip() if lines else "알 수 없는 채팅방"

            # 메시지 파싱
            # 형식: [발신자] [오전/오후 HH:MM] 메시지 내용
            # 또는: YYYY년 MM월 DD일 (날짜 구분선)
            message_pattern = re.compile(
                r'^\[(.+?)\] \[(오전|오후) (\d{1,2}:\d{2})\] (.+)$'
            )
            date_pattern = re.compile(r'^\d{4}년 \d{1,2}월 \d{1,2}일')

            current_date = ""
            current_message = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 날짜 구분선
                if date_pattern.match(line):
                    current_date = line
                    continue

                # 메시지 시작
                match = message_pattern.match(line)
                if match:
                    # 이전 메시지 저장
                    if current_message:
                        if self._should_include_message(current_message, keywords):
                            messages.append(current_message)
                            if len(messages) >= max_messages:
                                break

                    sender = match.group(1)
                    am_pm = match.group(2)
                    time_str = match.group(3)
                    message_text = match.group(4)

                    # 링크 추출
                    links = re.findall(r'https?://[^\s]+', message_text)

                    # 메시지 타입 판단
                    msg_type = "link" if links else "text"
                    if message_text in ['사진', '동영상', '파일']:
                        msg_type = "media"

                    current_message = KakaoMessage(
                        room_name=room_name,
                        sender=sender,
                        message=message_text,
                        timestamp=f"{current_date} {am_pm} {time_str}",
                        message_type=msg_type,
                        links=links
                    )
                elif current_message:
                    # 멀티라인 메시지 처리
                    current_message.message += f"\n{line}"

            # 마지막 메시지 처리
            if current_message and self._should_include_message(current_message, keywords):
                messages.append(current_message)

        except Exception as e:
            logger.error(f"카카오톡 파일 파싱 오류: {e}")

        logger.info(f"카카오톡 메시지 추출 완료: {len(messages)}개")
        return messages

    def extract_via_ui_automation(
        self,
        target_rooms: List[str] = None,
        max_messages: int = 100
    ) -> List[KakaoMessage]:
        """
        Windows UI 자동화를 통해 카카오톡 PC에서 실시간으로 채팅 내용을 추출합니다.
        카카오톡이 실행 중이어야 합니다.

        Args:
            target_rooms: 수집할 채팅방 이름 목록
            max_messages: 최대 추출 메시지 수

        Returns:
            추출된 KakaoMessage 목록
        """
        if not self._is_windows:
            logger.warning("UI 자동화는 Windows 환경에서만 지원됩니다.")
            return []

        target_rooms = target_rooms or ["나에게 쓰기"]
        messages: List[KakaoMessage] = []

        # 1) kakaotalk.py의 안정화된 내보내기 경로 사용
        try:
            import kakaotalk
            logger.info("카카오톡 내보내기 자동화 경로를 사용합니다. (kakaotalk.py)")

            for room_name in target_rooms:
                if len(messages) >= max_messages:
                    break

                remaining = max_messages - len(messages)
                logger.info(f"채팅방 '{room_name}' 내보내기/파싱 시작... (남은 한도: {remaining})")

                try:
                    # kakaotalk.py의 기능을 직접 호출하여 파일로 내보내기
                    exported_file = kakaotalk.extract_messages_from_chatroom(room_name)
                    if not exported_file or not os.path.exists(exported_file):
                        logger.warning(f"채팅방 '{room_name}' 내보내기 실패")
                        continue

                    room_messages = self.extract_from_export_file(
                        exported_file,
                        max_messages=remaining
                    )
                    
                    if room_messages:
                        for m in room_messages:
                            m.room_name = room_name
                        messages.extend(room_messages)
                        logger.info(f"채팅방 '{room_name}' 추출 완료: {len(room_messages)}개")
                except Exception as e:
                    logger.warning(f"채팅방 '{room_name}' 내보내기 기반 추출 실패: {e}")

            if messages:
                logger.info(f"카카오톡 추출 완료(내보내기 경로): 총 {len(messages)}개")
                return messages[:max_messages]

        except ImportError:
            logger.warning("kakaotalk.py 모듈을 찾을 수 없습니다. pywinauto 폴백을 시도합니다.")
        except Exception as e:
            logger.warning(f"kakaotalk.py 경로 사용 중 오류: {e}")

        # 2) 클립보드 폴백 (kakaotalk.py 및 pywinauto 기반)
        try:
            logger.info("클립보드 복사 방식을 시도합니다.")
            import pywinauto
            from pywinauto import Application
            
            try:
                app = Application(backend='uia').connect(title="카카오톡", timeout=5)
            except Exception:
                logger.warning("카카오톡이 실행 중이지 않거나 찾을 수 없습니다.")
                return messages

            for room_name in target_rooms:
                if len(messages) >= max_messages:
                    break
                remaining = max_messages - len(messages)
                room_messages = self._extract_from_room(app, room_name, remaining)
                messages.extend(room_messages)

            return messages[:max_messages]

        except Exception as e:
            logger.error(f"UI 자동화 폴백 오류: {e}")
            return messages[:max_messages]

    def get_room_list(self) -> List[str]:
        """
        카카오톡 프로세스의 모든 창을 뒤져서 채팅방 목록을 찾아냅니다.
        """
        if not self._is_windows:
            return []
            
        import pywinauto
        from pywinauto import Application
        import re

        rooms = set()
        
        try:
            # 1) 프로세스에 연결
            try:
                app = Application(backend='uia').connect(path="KakaoTalk.exe", timeout=3)
            except Exception:
                logger.warning("카카오톡 프로세스를 찾을 수 없습니다.")
                return []

            # 2) 모든 창 순회
            for win in app.windows():
                try:
                    if not win.is_visible():
                        continue
                    
                    # 창 제목이 '카카오톡'이거나 빈 경우(메인 리스트 창일 확률 높음)
                    win_text = win.window_text()
                    
                    # 3) ListItem 검색
                    items = win.descendants(control_type="ListItem")
                    if not items:
                        continue
                        
                    logger.info(f"창 '{win_text or 'Untitled'}'에서 {len(items)}개의 항목 탐색 중...")
                    
                    for item in items:
                        try:
                            # 다양한 속성에서 이름 추출 시도
                            name = ""
                            
                            # (1) 기본 텍스트
                            name = item.window_text().strip()
                            
                            # (2) 속성 딕셔너리에서 시도 (UIA 전용)
                            if not name or len(name) <= 1:
                                try:
                                    props = item.get_properties()
                                    name = props.get("texts", [""])[0].strip() or props.get("name", "").strip()
                                except Exception:
                                    pass
                            
                            # (3) 자식 요소에서 시도
                            if not name or len(name) <= 1:
                                for child in item.children():
                                    c_name = child.window_text().strip()
                                    if c_name and len(c_name) > 1:
                                        if not re.match(r'^\d+:\d+$', c_name) and not re.match(r'^\d+$', c_name):
                                            name = c_name
                                            break
                            
                            # 필터링 및 추가
                            if name and len(name) > 1:
                                if not any(ex in name for ex in ["최소화", "최대화", "닫기", "광고", "MOMENT"]):
                                    if not re.match(r'^\d+:\d+$', name) and not re.match(r'^\d+$', name):
                                        if name not in ["채팅", "친구", "더보기", "검색"]:
                                            rooms.add(name)
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"목록 추출 중 오류: {e}")

        result = sorted(list(rooms))
        logger.info(f"최종 추출된 채팅방 수: {len(result)}")
        return result

    def _extract_from_room(self, app, room_name: str, max_messages: int) -> List[KakaoMessage]:
        """특정 채팅방에서 메시지를 추출합니다."""
        messages = []
        try:
            # 채팅방 찾기 및 클릭
            main_window = app.top_window()

            # 검색창에 채팅방 이름 입력
            search_box = main_window.child_window(control_type="Edit", found_index=0)
            search_box.set_text(room_name)
            time.sleep(0.5)

            # 검색 결과에서 채팅방 선택
            room_item = main_window.child_window(title=room_name, control_type="ListItem")
            room_item.double_click_input()
            time.sleep(1)

            # 채팅창에서 텍스트 추출
            chat_window = app.window(title_re=f".*{room_name}.*")
            if chat_window.exists():
                # 전체 선택 및 복사
                chat_window.set_focus()
                chat_window.type_keys('^a^c')  # ^a(전체선택) 후 ^c(복사)
                time.sleep(1.0)  # 클립보드 복사 대기 시간 증가

                # pywinauto 내장 클립보드 기능 사용 (더 안정적)
                try:
                    import pywinauto.clipboard
                    clipboard_text = pywinauto.clipboard.GetData()
                except Exception as e:
                    logger.warning(f"클립보드 데이터 읽기 실패: {e}")
                    clipboard_text = ""

                # 텍스트 파싱
                if clipboard_text:
                    # 카카오톡 복사 텍스트 형식 파싱 (날짜, 시간, 발신자, 메시지 분리 시도)
                    current_sender = "알 수 없음"
                    for line in clipboard_text.split('\n'):
                        line = line.strip()
                        if not line: continue
                        
                        # [발신자] [오후 12:00] 메시지 형태인 경우
                        match = re.match(r'^\[(.+?)\] \[(오전|오후) \d{1,2}:\d{2}\] (.+)$', line)
                        if match:
                            current_sender = match.group(1)
                            message_text = match.group(3)
                        else:
                            message_text = line

                        # 링크 추출
                        links = re.findall(r'https?://[^\s]+', message_text)

                        messages.append(KakaoMessage(
                            room_name=room_name,
                            sender=current_sender,
                            message=message_text,
                            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M'),
                            links=links,
                            message_type="link" if links else "text"
                        ))
                        
                        if len(messages) >= max_messages:
                            break

        except Exception as e:
            logger.warning(f"채팅방 '{room_name}' 추출 실패: {e}")

        return messages

    def _should_include_message(self, msg: KakaoMessage, keywords: List[str]) -> bool:
        """메시지가 키워드 필터를 통과하는지 확인."""
        if not keywords:
            return True
        return any(kw.lower() in msg.message.lower() for kw in keywords)

    def watch_my_notes_room(
        self,
        output_dir: str = None,
        check_interval: int = 300
    ):
        """
        '나에게 쓰기' 채팅방을 주기적으로 모니터링하여 새 메시지를 수집합니다.
        이 메서드는 백그라운드 스레드로 실행하기 위한 용도입니다.

        Args:
            output_dir: 수집된 메시지 저장 디렉토리
            check_interval: 확인 주기 (초)
        """
        logger.info(f"'나에게 쓰기' 모니터링 시작 (주기: {check_interval}초)")
        # 실제 구현은 UI 자동화 또는 파일 감시 방식으로 구현


def kakao_messages_to_markdown(
    messages: List[KakaoMessage],
    title: str = "카카오톡 메시지 수집 데이터"
) -> str:
    """
    추출된 카카오톡 메시지를 NotebookLM 업로드용 마크다운 형식으로 변환.
    """
    # 링크가 포함된 메시지와 일반 메시지 분리
    link_messages = [m for m in messages if m.links]
    text_messages = [m for m in messages if not m.links and len(m.message) > 20]

    lines = [
        f"# {title}",
        f"",
        f"**수집 일시:** {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}",
        f"**수집된 메시지 수:** {len(messages)}개",
        f"**링크 포함 메시지:** {len(link_messages)}개",
        f"",
        "---",
        ""
    ]

    if link_messages:
        lines.extend([
            "## 공유된 링크 모음",
            ""
        ])
        for msg in link_messages:
            lines.extend([
                f"### {msg.timestamp} - {msg.sender}",
                f"{msg.message}",
                f""
            ])
            for link in msg.links:
                lines.append(f"- {link}")
            lines.append("")

        lines.extend(["---", ""])

    if text_messages:
        lines.extend([
            "## 주요 메시지",
            ""
        ])
        for msg in text_messages:
            lines.extend([
                f"**[{msg.timestamp}] {msg.sender}:** {msg.message}",
                ""
            ])

    return "\n".join(lines)


# 테스트 실행
if __name__ == "__main__":
    print("=== 카카오톡 추출 모듈 테스트 ===")
    extractor = KakaoTalkExtractor()

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        print("채팅방 목록을 가져옵니다 (카카오톡 채팅 탭이 열려있어야 합니다)...")
        rooms = extractor.get_room_list()
        if not rooms:
            print("채팅방 목록을 찾을 수 없거나 카카오톡이 실행 중이 아닙니다.")
        else:
            for i, room in enumerate(rooms, 1):
                print(f"{i}. {room}")
        sys.exit(0)

    # 내보내기 파일 테스트
    print("카카오톡 대화 내보내기 파일 파싱 테스트")
    print("사용법: extractor.extract_from_export_file('KakaoTalk_export.txt')")
