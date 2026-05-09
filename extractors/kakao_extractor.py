"""
NotebookLM ETL Pipeline - 카카오톡 PC 데이터 추출 모듈
Windows 환경에서 카카오톡 PC 버전의 채팅 내용을 추출합니다.
pywinauto 또는 pyautogui를 사용하여 UI 자동화를 수행합니다.

주의: 이 모듈은 Windows 전용이며, 카카오톡 PC 버전이 설치되어 있어야 합니다.
"""

import os
import re
import subprocess
import time
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Union
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
        self._is_wsl = self._check_is_wsl()
        logger.info(f"KakaoTalkExtractor 초기화 (Windows: {self._is_windows}, WSL: {self._is_wsl})")
        self._config = self._load_kakao_config()

    def _load_kakao_config(self) -> Dict:
        """user_config.json에서 kakao 설정을 로드."""
        default_path = Path(__file__).parent.parent / "config" / "user_config.json"
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            kakao_cfg = data.get("kakao", {})
            if not isinstance(kakao_cfg, dict):
                return {}
            return kakao_cfg
        except FileNotFoundError:
            logger.debug(f"카카오톡 설정 파일 없음: {default_path}")
            return {}
        except Exception as e:
            logger.error(f"카카오톡 설정 로드 실패: {default_path} ({e})")
            return {}

    def _check_is_wsl(self) -> bool:
        """Check if running inside Windows Subsystem for Linux."""
        if sys.platform != 'linux':
            return False
        try:
            # A common way to check for WSL is to check for 'Microsoft' in /proc/version
            with open('/proc/version', 'r') as f:
                if 'microsoft' in f.read().lower():
                    logger.info("WSL 환경 감지됨.")
                    return True
        except FileNotFoundError:
            pass
        # Another check for WSL2
        if 'WSL_DISTRO_NAME' in os.environ:
            logger.info("WSL 환경 감지됨 (WSL_DISTRO_NAME).")
            return True
        return False

    def _find_windows_python(self) -> Optional[str]:
        """
        WSL에서 Windows 호스트의 python.exe 인터프리터를 찾습니다.
        1. 설정 파일(user_config.json)의 'kakao.windows_python_path'를 확인합니다.
        2. 설정이 없으면 일반적인 경로에서 자동으로 탐색합니다.
        """
        # 1. 설정 파일에서 경로 확인
        config_path = self._config.get("windows_python_path")
        if config_path:
            # Windows 경로(C:\...)를 WSL 경로(/mnt/c/...)로 변환
            try:
                if ':/' in config_path or ':\\' in config_path:
                    p = Path(config_path.replace('\\', '/'))
                    drive = p.drive.lower().replace(':', '')
                    wsl_path = Path(f"/mnt/{drive}") / p.relative_to(p.anchor)
                else: # 이미 WSL 경로 형식이라고 가정
                    wsl_path = Path(config_path)

                if wsl_path.exists() and wsl_path.is_file():
                    logger.info(f"설정 파일에서 Windows Python 경로를 사용합니다: {wsl_path}")
                    return str(wsl_path)
                else:
                    logger.warning(f"설정에 지정된 Windows Python 경로를 찾을 수 없습니다: {wsl_path}")
            except Exception as e:
                logger.warning(f"설정된 Python 경로 처리 중 오류 발생 ('{config_path}'): {e}")

        # 2. 자동 탐색 (기존 로직)
        logger.info("user_config.json에 경로가 지정되지 않아 Windows Python 자동 탐색을 시작합니다.")
        try:
            users_dir = Path("/mnt/c/Users")
            if not users_dir.exists():
                return None

            for user_dir in users_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                
                appdata_local = user_dir / "AppData" / "Local" / "Programs" / "Python"
                if not appdata_local.exists():
                    continue

                # Find the latest Python version directory
                py_versions = sorted([d for d in appdata_local.iterdir() if d.is_dir() and d.name.startswith("Python")], reverse=True)
                if not py_versions:
                    continue

                for py_dir in py_versions:
                    py_exe = py_dir / "python.exe"
                    if py_exe.exists():
                        logger.info(f"Found Windows Python at: {py_exe}")
                        return str(py_exe)
        except Exception as e:
            logger.warning(f"Could not automatically find Windows Python: {e}")
        
        return None

    def _run_wsl_helper(self, args: List[str]) -> Optional[Union[Dict, List]]:
        """Generic helper to run this script on Windows via WSL."""
        logger.info(f"WSL 환경에서 Windows Helper 실행: {args}")
        
        win_python = self._find_windows_python()
        if not win_python:
            logger.error("WSL에서 Windows의 Python 인터프리터를 찾을 수 없습니다. 자동 추출이 불가능합니다.")
            return None
            
        try:
            helper_script_path = Path(__file__).resolve()
            proc = subprocess.run(['wslpath', '-w', str(helper_script_path)], capture_output=True, text=True, check=True)
            win_script_path = proc.stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logger.error(f"'wslpath' 명령어 실행 실패. WSL 경로를 Windows 경로로 변환할 수 없습니다: {e}")
            logger.error("대안: 프로젝트를 Windows 파일 시스템(예: /mnt/c/...)에 위치시키세요.")
            return None

        cmd = [win_python, win_script_path] + args
        
        logger.info(f"Helper 실행 명령어: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', timeout=300)
            output = result.stdout
            if not output:
                logger.warning("Windows helper에서 출력이 없습니다.")
                if result.stderr:
                    logger.error(f"Helper 오류 출력: {result.stderr}")
                return None

            # Extract JSON between delimiters to avoid pollution from other libraries
            start_marker = "---JSON-START---"
            end_marker = "---JSON-END---"
            
            start_index = output.find(start_marker)
            end_index = output.find(end_marker)
            
            if start_index != -1 and end_index > start_index:
                json_str = output[start_index + len(start_marker):end_index].strip()
            else:
                logger.warning("WSL helper 출력에서 JSON 구분자를 찾을 수 없습니다. 전체 출력을 파싱합니다.")
                json_str = output.strip()

            if not json_str:
                logger.warning("Windows helper에서 파싱할 JSON 출력이 없습니다.")
                return None

            data = json.loads(json_str)

            if isinstance(data, dict) and "error" in data:
                logger.error(f"Windows helper 실행 오류: {data['error']}")
                return None
            
            return data

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
            logger.error(f"WSL helper 실행 중 예외 발생: {e}")
            return None
            
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
        WSL 환경에서는 Windows의 Python을 호출하여 실행을 시도합니다.

        Args:
            target_rooms: 수집할 채팅방 이름 목록
            max_messages: 최대 추출 메시지 수

        Returns:
            추출된 KakaoMessage 목록
        """
        if not self._is_windows and not self._is_wsl:
            logger.warning("UI 자동화는 Windows 또는 WSL 환경에서만 지원됩니다.")
            return []

        if self._is_wsl:
            target_rooms = target_rooms or ["나에게 쓰기"]
            rooms_str = ",".join(target_rooms)
            args = [
                "--as-wsl-helper",
                "--rooms", rooms_str,
                "--max-messages", str(max_messages)
            ]
            data = self._run_wsl_helper(args)
            
            if isinstance(data, list):
                messages = [KakaoMessage(**item) for item in data]
                logger.info(f"WSL Helper를 통해 {len(messages)}개의 메시지를 성공적으로 추출했습니다.")
                return messages
            return []

        # --- 기존 Windows 전용 로직 ---
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

    def get_room_list(self, max_rooms: int = 300) -> List[str]:
        """
        카카오톡 PC 버전의 채팅 목록을 가져옵니다.
        채팅 목록을 활성화하고 키보드 네비게이션(아래 화살표 + Enter)으로
        순차적으로 채팅방을 열고 닫으면서 제목을 추출합니다. (가장 확실한 방법)
        WSL 환경에서는 Windows Helper를 통해 목록을 가져옵니다.
        """
        if not self._is_windows and not self._is_wsl:
            logger.warning("채팅방 목록 가져오기는 Windows 또는 WSL 환경에서만 지원됩니다.")
            return []
 
        if self._is_wsl:
            args = ["--list-rooms-helper"]
            data = self._run_wsl_helper(args)
            if isinstance(data, list):
                logger.info(f"WSL Helper를 통해 {len(data)}개의 채팅방 목록을 가져왔습니다.")
                return data
            return []
 
        import win32gui
        import win32api
        import win32con
        import time

        rooms = []
        try:
            hwndkakao = win32gui.FindWindow(None, "카카오톡")
            if not hwndkakao:
                logger.warning("카카오톡 프로세스를 찾을 수 없습니다. 카카오톡이 실행 중인지 확인하세요.")
                return []

            # 헬퍼 함수
            def _send_hotkey(hwnd, mod_vk, key_vk, pre_delay=0.05, gap=0.03):
                if hwnd and win32gui.IsWindow(hwnd):
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                        win32gui.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                time.sleep(pre_delay)
                ku = win32con.KEYEVENTF_KEYUP
                if mod_vk:
                    win32api.keybd_event(mod_vk, 0, 0, 0)
                    time.sleep(gap)
                win32api.keybd_event(key_vk, 0, 0, 0)
                time.sleep(gap)
                win32api.keybd_event(key_vk, 0, ku, 0)
                time.sleep(gap)
                if mod_vk:
                    win32api.keybd_event(mod_vk, 0, ku, 0)

            # 카카오톡을 맨 앞으로
            try:
                win32gui.SetForegroundWindow(hwndkakao)
                win32gui.BringWindowToTop(hwndkakao)
            except Exception:
                pass
            time.sleep(0.5)

            # Ctrl+2 로 채팅 탭으로 이동
            _send_hotkey(hwndkakao, win32con.VK_CONTROL, ord('2'))
            time.sleep(0.5)

            # 채팅 목록 부분을 클릭해서 포커스
            rect = win32gui.GetWindowRect(hwndkakao)
            x = rect[0] + (rect[2] - rect[0]) // 2
            y = rect[1] + 150 # 대략 첫번째 채팅방 위치
            win32api.SetCursorPos((x, y))
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.5)

            # Home 키를 눌러 최상단으로 이동
            _send_hotkey(hwndkakao, None, win32con.VK_HOME)
            time.sleep(0.5)

            seen_titles = set()
            consecutive_duplicates = 0

            logger.info("키보드 네비게이션으로 채팅방 목록 추출을 시작합니다...")
            for i in range(max_rooms):
                # Enter 를 눌러 채팅방 열기
                _send_hotkey(hwndkakao, None, win32con.VK_RETURN)
                time.sleep(0.8) # 창이 열리는데 필요한 대기 시간
                
                fg = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(fg)
                
                # 열린 창이 카카오톡 메인 창이 아니고, 이름이 유효한 경우
                if fg != hwndkakao and title and title != "카카오톡":
                    if title not in seen_titles:
                        rooms.append(title)
                        seen_titles.add(title)
                        consecutive_duplicates = 0
                        logger.debug(f"채팅방 발견: {title}")
                    else:
                        consecutive_duplicates += 1
                        
                    # 채팅방 창 닫기 (Esc 또는 Alt+F4)
                    win32gui.PostMessage(fg, win32con.WM_CLOSE, 0, 0)
                    time.sleep(0.3)
                    
                # 메인 창으로 돌아와서 아래 화살표(Down) 누르기
                try:
                    win32gui.SetForegroundWindow(hwndkakao)
                except Exception:
                    pass
                _send_hotkey(hwndkakao, None, win32con.VK_DOWN)
                time.sleep(0.3)

                # 만약 같은 방이 연속으로 3번 나오면 더 이상 방이 없는 것으로 간주
                if consecutive_duplicates >= 3:
                    break

        except Exception as e:
            logger.error(f"채팅방 목록 추출 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

        # 만약 목록을 아예 못 가져왔다면 기본값 세팅
        if not rooms:
            logger.warning("채팅방을 가져오지 못했습니다. '나에게 쓰기'를 기본으로 추가합니다.")
            rooms.append("나에게 쓰기")

        logger.info(f"추출된 채팅방 목록 ({len(rooms)}개): {rooms[:5]}...")
        return rooms

    def _extract_from_room(self, room_name: str, max_messages: int) -> List[KakaoMessage]:
        """특정 채팅방에서 메시지를 추출합니다."""
        messages = []
        try:
            from kakaotalk import open_chatroom, PostKeyEx, _get_clipboard_text, close_chatroom_window
            import win32gui
            import win32con as w
            import re
            from datetime import datetime

            hwnd_chatroom = open_chatroom(room_name)
            if not hwnd_chatroom:
                logger.warning(f"채팅방 '{room_name}'을 열 수 없습니다.")
                return messages

            time.sleep(1)
            hwndListControl = win32gui.FindWindowEx(hwnd_chatroom, None, "EVA_VH_ListControl_Dblclk", None)
            if not hwndListControl:
                logger.warning("채팅방 리스트 컨트롤을 찾을 수 없습니다.")
                close_chatroom_window(hwnd_chatroom)
                return messages

            PostKeyEx(hwndListControl, ord('A'), [w.VK_CONTROL], False)
            time.sleep(1)
            PostKeyEx(hwndListControl, ord('C'), [w.VK_CONTROL], False)
            time.sleep(1)

            clipboard_text = _get_clipboard_text()
            
            close_chatroom_window(hwnd_chatroom)

            # 텍스트 파싱
            if clipboard_text:
                current_sender = "알 수 없음"
                for line in clipboard_text.split('\n'):
                    line = line.strip()
                    if not line: continue
                    
                    match = re.match(r'^\[(.+?)\] \[(오전|오후) \d{1,2}:\d{2}\] (.+)$', line)
                    if match:
                        current_sender = match.group(1)
                        message_text = match.group(3)
                    else:
                        message_text = line

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
    import argparse
    import json
    from dataclasses import asdict

    parser = argparse.ArgumentParser(description="KakaoTalk Extractor Module & Helper")
    parser.add_argument("--as-wsl-helper", action="store_true", help="Run as a message extraction helper for WSL.")
    parser.add_argument("--list-rooms-helper", action="store_true", help="Run as a room list helper for WSL.")
    parser.add_argument("--rooms", type=str, help="Comma-separated list of target room names for helper.")
    parser.add_argument("--max-messages", type=int, default=100, help="Max messages to extract for helper.")
    parser.add_argument("--test-list-rooms", action="store_true", help="Interactively test listing chat rooms.")

    args = parser.parse_args()

    # This part only runs on Windows when called as a helper
    if sys.platform == "win32":
        if args.as_wsl_helper:
            if not args.rooms:
                print(json.dumps({"error": "No rooms specified for helper."}))
                sys.exit(1)
            
            target_rooms = [room.strip() for room in args.rooms.split(',')]
            extractor = KakaoTalkExtractor()
            messages = extractor.extract_via_ui_automation(
                target_rooms=target_rooms,
                max_messages=args.max_messages
            )
            output = [asdict(msg) for msg in messages]
            print("---JSON-START---")
            print(json.dumps(output, ensure_ascii=False))
            print("---JSON-END---")
            sys.exit(0)

        if args.list_rooms_helper:
            extractor = KakaoTalkExtractor()
            rooms = extractor.get_room_list()
            print("---JSON-START---")
            print(json.dumps(rooms, ensure_ascii=False))
            print("---JSON-END---")
            sys.exit(0)

    # Interactive test mode (can run on any OS for file parsing, but UI parts are Windows/WSL)
    if args.test_list_rooms:
        print("=== 카카오톡 추출 모듈 테스트: 채팅방 목록 ===")
        extractor = KakaoTalkExtractor()
        print("채팅방 목록을 가져옵니다 (카카오톡 채팅 탭이 열려있어야 합니다)...")
        rooms = extractor.get_room_list()
        if not rooms:
            print("채팅방 목록을 찾을 수 없거나 카카오톡이 실행 중이 아닙니다.")
        else:
            for i, room in enumerate(rooms, 1):
                print(f"{i}. {room}")
        sys.exit(0)

    # Default message if no specific arguments are given
    if len(sys.argv) == 1:
        print("=== 카카오톡 추출 모듈 ===")
        print("이 스크립트는 다른 모듈에서 가져와서 사용하거나, 헬퍼로 실행됩니다.")
        print("\nCLI 테스트 옵션:")
        print("  --test-list-rooms : (Windows/WSL) UI 자동화로 채팅방 목록 가져오기")
        print("\nWSL 헬퍼 모드 (내부용):")
        print("  --as-wsl-helper --rooms \"...\" : 메시지 추출")
        print("  --list-rooms-helper : 채팅방 목록 추출")
