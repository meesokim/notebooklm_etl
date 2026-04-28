"""
NotebookLM ETL Pipeline - 이메일 추출 모듈
네이버 메일 및 Gmail의 IMAP 프로토콜을 사용하여 이메일 데이터를 추출합니다.
"""

import imaplib
import email
import email.header
import email.utils
import email.message
import re
import html
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

# 내부 모듈
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("email_extractor")


# IMAP 서버 설정 프리셋
IMAP_PRESETS = {
    "naver": {
        "server": "imap.naver.com",
        "port": 993,
        "use_ssl": True
    },
    "gmail": {
        "server": "imap.gmail.com",
        "port": 993,
        "use_ssl": True
    },
    "daum": {
        "server": "imap.daum.net",
        "port": 993,
        "use_ssl": True
    },
    "outlook": {
        "server": "outlook.office365.com",
        "port": 993,
        "use_ssl": True
    }
}


@dataclass
class EmailItem:
    """추출된 이메일 데이터 구조"""
    uid: str
    subject: str
    sender: str
    sender_email: str
    date: datetime
    body: str
    body_html: str = ""
    attachments: List[str] = field(default_factory=list)
    folder: str = "INBOX"
    source: str = "email"


class EmailExtractor:
    """
    IMAP 프로토콜을 사용하여 이메일 데이터를 추출하는 클래스.
    네이버 메일, Gmail 등 IMAP을 지원하는 모든 이메일 서비스에 사용 가능합니다.
    """

    def __init__(
        self,
        provider: str = "naver",
        username: str = "",
        password: str = "",
        custom_server: Optional[str] = None,
        custom_port: int = 993
    ):
        """
        Args:
            provider: 이메일 제공자 ("naver", "gmail", "daum", "outlook", "custom")
            username: 이메일 계정 (전체 이메일 주소)
            password: 비밀번호 또는 앱 비밀번호
            custom_server: 커스텀 IMAP 서버 주소 (provider="custom"일 때 사용)
            custom_port: 커스텀 IMAP 포트
        """
        self.username = username
        self.password = password
        self.connection: Optional[imaplib.IMAP4_SSL] = None

        if provider in IMAP_PRESETS:
            preset = IMAP_PRESETS[provider]
            self.server = preset["server"]
            self.port = preset["port"]
        else:
            self.server = custom_server or "imap.gmail.com"
            self.port = custom_port

        logger.info(f"EmailExtractor 초기화: {provider} ({self.server}:{self.port})")

    def connect(self) -> bool:
        """IMAP 서버에 연결 및 로그인."""
        try:
            self.connection = imaplib.IMAP4_SSL(self.server, self.port)
            self.connection.login(self.username, self.password)
            logger.info(f"IMAP 연결 성공: {self.username}")
            return True
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP 로그인 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"IMAP 연결 오류: {e}")
            return False

    def disconnect(self) -> None:
        """IMAP 연결 종료."""
        if self.connection:
            try:
                self.connection.logout()
                logger.info("IMAP 연결 종료")
            except Exception:
                pass
            self.connection = None

    def list_folders(self) -> List[str]:
        """사용 가능한 메일 폴더 목록 반환."""
        if not self.connection:
            return []
        try:
            _, folders = self.connection.list()
            result = []
            for folder in folders:
                if isinstance(folder, bytes):
                    folder_str = folder.decode('utf-8', errors='replace')
                    # 폴더 이름 추출 (마지막 따옴표 안의 내용)
                    match = re.search(r'"([^"]+)"$', folder_str)
                    if match:
                        result.append(match.group(1))
                    else:
                        parts = folder_str.split(' ')
                        if parts:
                            result.append(parts[-1].strip('"'))
            return result
        except Exception as e:
            logger.error(f"폴더 목록 조회 실패: {e}")
            return []

    def extract_emails(
        self,
        folders: List[str] = None,
        days_back: int = 7,
        max_emails: int = 50,
        filter_keywords: List[str] = None,
        exclude_senders: List[str] = None
    ) -> List[EmailItem]:
        """
        이메일 추출 메인 함수.

        Args:
            folders: 수집할 폴더 목록 (None이면 INBOX만)
            days_back: 최근 N일 이내 메일만 수집
            max_emails: 최대 수집 메일 수
            filter_keywords: 포함해야 할 키워드 목록 (제목 또는 본문)
            exclude_senders: 제외할 발신자 도메인/이메일 목록

        Returns:
            추출된 EmailItem 목록
        """
        if not self.connection:
            logger.error("IMAP 연결이 없습니다. connect()를 먼저 호출하세요.")
            return []

        folders = folders or ["INBOX"]
        filter_keywords = filter_keywords or []
        exclude_senders = exclude_senders or []
        all_emails = []

        # 날짜 필터 (IMAP DATE 형식)
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")

        for folder in folders:
            logger.info(f"폴더 '{folder}' 처리 중...")
            try:
                # 폴더 선택
                status, _ = self.connection.select(f'"{folder}"' if ' ' in folder else folder)
                if status != 'OK':
                    logger.warning(f"폴더 '{folder}' 선택 실패")
                    continue

                # 날짜 기반 검색
                _, msg_ids = self.connection.search(None, f'SINCE {since_date}')
                if not msg_ids or not msg_ids[0]:
                    logger.info(f"폴더 '{folder}': 해당 기간 내 메일 없음")
                    continue

                uid_list = msg_ids[0].split()
                logger.info(f"폴더 '{folder}': {len(uid_list)}개 메일 발견")

                # 최신 메일부터 처리 (역순)
                uid_list = uid_list[::-1][:max_emails]

                for uid in uid_list:
                    if len(all_emails) >= max_emails:
                        break

                    email_item = self._fetch_email(uid.decode(), folder)
                    if email_item is None:
                        continue

                    # 발신자 필터링
                    if self._should_exclude_sender(email_item.sender_email, exclude_senders):
                        continue

                    # 키워드 필터링 (키워드가 설정된 경우에만)
                    if filter_keywords:
                        if not self._matches_keywords(email_item, filter_keywords):
                            continue

                    all_emails.append(email_item)

            except Exception as e:
                logger.error(f"폴더 '{folder}' 처리 중 오류: {e}")
                continue

        logger.info(f"총 {len(all_emails)}개 이메일 추출 완료")
        return all_emails

    def _fetch_email(self, uid: str, folder: str) -> Optional[EmailItem]:
        """단일 이메일 메시지를 가져와 파싱."""
        try:
            _, msg_data = self.connection.fetch(uid, '(RFC822)')
            if not msg_data or not msg_data[0]:
                return None

            raw_email = msg_data[0][1]
            if not isinstance(raw_email, bytes):
                return None

            msg = email.message_from_bytes(raw_email)

            # 제목 디코딩
            subject = self._decode_header(msg.get('Subject', '(제목 없음)'))

            # 발신자 파싱
            sender_raw = msg.get('From', '')
            sender_name, sender_email_addr = self._parse_sender(sender_raw)

            # 날짜 파싱
            date_str = msg.get('Date', '')
            date = self._parse_date(date_str)

            # 본문 추출
            body, body_html = self._extract_body(msg)

            return EmailItem(
                uid=uid,
                subject=subject,
                sender=sender_name,
                sender_email=sender_email_addr,
                date=date,
                body=body,
                body_html=body_html,
                folder=folder
            )

        except Exception as e:
            logger.warning(f"이메일 UID {uid} 파싱 실패: {e}")
            return None

    def _decode_header(self, header_value: str) -> str:
        """이메일 헤더의 인코딩을 디코딩."""
        if not header_value:
            return ""
        try:
            decoded_parts = email.header.decode_header(header_value)
            result = []
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    charset = charset or 'utf-8'
                    try:
                        result.append(part.decode(charset, errors='replace'))
                    except (LookupError, UnicodeDecodeError):
                        result.append(part.decode('utf-8', errors='replace'))
                else:
                    result.append(str(part))
            return ''.join(result)
        except Exception:
            return str(header_value)

    def _parse_sender(self, sender_raw: str) -> Tuple[str, str]:
        """발신자 문자열에서 이름과 이메일 주소를 분리."""
        try:
            name, addr = email.utils.parseaddr(sender_raw)
            name = self._decode_header(name) if name else addr
            return name, addr.lower()
        except Exception:
            return sender_raw, sender_raw.lower()

    def _parse_date(self, date_str: str) -> datetime:
        """이메일 날짜 문자열을 datetime 객체로 변환."""
        try:
            parsed = email.utils.parsedate_to_datetime(date_str)
            return parsed.replace(tzinfo=None)
        except Exception:
            return datetime.now()

    def _extract_body(self, msg: email.message.Message) -> Tuple[str, str]:
        """멀티파트 이메일에서 텍스트 본문과 HTML 본문을 추출."""
        body_text = ""
        body_html = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))

                if 'attachment' in content_disposition:
                    continue

                if content_type == 'text/plain':
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        body_text = part.get_payload(decode=True).decode(charset, errors='replace')
                    except Exception:
                        body_text = str(part.get_payload())

                elif content_type == 'text/html':
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        body_html = part.get_payload(decode=True).decode(charset, errors='replace')
                    except Exception:
                        body_html = str(part.get_payload())
        else:
            content_type = msg.get_content_type()
            charset = msg.get_content_charset() or 'utf-8'
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    content = payload.decode(charset, errors='replace')
                    if content_type == 'text/html':
                        body_html = content
                    else:
                        body_text = content
            except Exception:
                body_text = str(msg.get_payload())

        # HTML에서 텍스트 추출 (텍스트 본문이 없는 경우)
        if not body_text and body_html:
            body_text = self._html_to_text(body_html)

        return body_text.strip(), body_html.strip()

    def _html_to_text(self, html_content: str) -> str:
        """HTML 콘텐츠에서 순수 텍스트를 추출."""
        # 스크립트 및 스타일 제거
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', ' ', text)
        # HTML 엔티티 디코딩
        text = html.unescape(text)
        # 연속 공백 제거
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _should_exclude_sender(self, sender_email: str, exclude_patterns: List[str]) -> bool:
        """발신자 이메일이 제외 패턴에 해당하는지 확인."""
        for pattern in exclude_patterns:
            if pattern.lower() in sender_email.lower():
                return True
        return False

    def _matches_keywords(self, email_item: EmailItem, keywords: List[str]) -> bool:
        """이메일이 키워드 중 하나라도 포함하는지 확인."""
        search_text = f"{email_item.subject} {email_item.body}".lower()
        return any(keyword.lower() in search_text for keyword in keywords)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


def emails_to_markdown(emails: List[EmailItem], title: str = "이메일 수집 데이터") -> str:
    """
    추출된 이메일 목록을 NotebookLM 업로드용 마크다운 형식으로 변환.
    """
    lines = [
        f"# {title}",
        f"",
        f"**수집 일시:** {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}",
        f"**수집된 이메일 수:** {len(emails)}개",
        f"",
        "---",
        ""
    ]

    for i, em in enumerate(emails, 1):
        lines.extend([
            f"## [{i}] {em.subject}",
            f"",
            f"| 항목 | 내용 |",
            f"|------|------|",
            f"| 발신자 | {em.sender} ({em.sender_email}) |",
            f"| 수신 일시 | {em.date.strftime('%Y-%m-%d %H:%M')} |",
            f"| 폴더 | {em.folder} |",
            f"",
            f"### 본문",
            f"",
            em.body[:3000] + ("..." if len(em.body) > 3000 else ""),
            f"",
            "---",
            ""
        ])

    return "\n".join(lines)


# 테스트 실행
if __name__ == "__main__":
    print("=== 이메일 추출 모듈 테스트 ===")
    print("실제 테스트를 위해서는 계정 정보를 설정하세요.")
    print("예시:")
    print("  extractor = EmailExtractor(provider='naver', username='your@naver.com', password='앱비밀번호')")
    print("  with extractor:")
    print("      emails = extractor.extract_emails(days_back=7, max_emails=20)")
    print("      md = emails_to_markdown(emails)")
