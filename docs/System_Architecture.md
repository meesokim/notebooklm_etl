# NotebookLM ETL 파이프라인 시스템 아키텍처 및 기술 스택 설계

## 1. 개요
본 문서는 Windows 환경에서 동작하는 NotebookLM 전용 데이터 소스 자동화 관리 도구(ETL 파이프라인)의 시스템 아키텍처와 기술 스택을 정의합니다. 이 시스템은 이메일, 웹 브라우저 히스토리, 메신저(카카오톡), 소셜 미디어 등 다양한 소스에서 데이터를 추출(Extract)하고, 사용자의 관심사에 맞게 필터링 및 변환(Transform)한 후, NotebookLM에 자동으로 업로드 및 관리(Load)하는 역할을 수행합니다.

## 2. 시스템 아키텍처

시스템은 크게 4개의 계층(Layer)으로 구성됩니다.

### 2.1. 데이터 수집 계층 (Extraction Layer)
다양한 원본 소스로부터 데이터를 주기적으로 가져오는 모듈들의 집합입니다.
*   **Email Extractor:** IMAP 프로토콜을 사용하여 네이버 메일 및 Gmail 서버에 접속, 특정 라벨이나 키워드가 포함된 메일 본문과 첨부파일 텍스트를 추출합니다.
*   **Browser History Extractor:** Windows 로컬에 저장된 Chrome, Edge, Firefox의 SQLite 데이터베이스 파일(`History`, `places.sqlite` 등)에 접근하여 방문 기록(URL, 페이지 제목, 방문 시간)을 추출합니다.
*   **Messenger Extractor (KakaoTalk):** Windows API(`ctypes`, `pywinauto`) 또는 UI 자동화 도구(`pyautogui`)를 활용하여 활성화된 카카오톡 PC 버전의 특정 채팅방(예: '나에게 쓰기') 텍스트를 주기적으로 스크래핑합니다.
*   **SNS/Web Scraper:** Selenium 또는 Playwright를 사용하여 네이버 카페, Facebook, X(Twitter) 등의 특정 피드나 게시물을 스크래핑합니다. (API가 제공되는 경우 공식 API 우선 사용)

### 2.2. 데이터 처리 계층 (Transformation Layer)
수집된 원시 데이터를 NotebookLM이 이해하기 쉬운 형태로 정제하고 필터링합니다.
*   **Data Cleanser:** HTML 태그 제거, 불필요한 공백 및 특수문자 제거, 메일 서명 및 광고 문구 필터링 등을 수행합니다.
*   **Keyword Filter:** 사용자가 사전에 정의한 '관심 키워드' 목록과 정규표현식을 기반으로, 수집된 데이터 중 가치 있는 정보만을 선별합니다.
*   **Format Converter:** 정제된 데이터를 NotebookLM에 업로드하기 최적화된 마크다운(.md) 또는 일반 텍스트(.txt) 파일로 변환합니다. 메타데이터(출처, 수집 시간, 원본 URL 등)를 문서 상단에 헤더 형태로 추가합니다.

### 2.3. NotebookLM 연동 계층 (Load Layer)
정제된 데이터를 실제 NotebookLM 노트북에 업로드하고, 소스 제한(최대 50개)을 관리합니다.
*   **NotebookLM API Client:** 비공식 Python API 라이브러리(`notebooklm-py`) 또는 Playwright 기반의 브라우저 자동화를 통해 NotebookLM 웹 인터페이스와 상호작용합니다.
*   **Source Manager:** 현재 노트북에 업로드된 소스 목록을 조회하고, 최대 개수(50개)에 도달했을 경우 가장 오래되거나 중요도가 낮은 소스를 자동으로 삭제(Delete)한 후 새로운 소스를 업로드(Add)하는 로직(Source Rotation)을 수행합니다.

### 2.4. 사용자 인터페이스 계층 (Presentation Layer)
Windows 데스크톱 환경에서 사용자가 시스템을 쉽게 제어할 수 있도록 GUI를 제공합니다.
*   **Dashboard:** 현재 수집된 데이터 통계, NotebookLM 업로드 현황, 최근 동기화 시간 등을 시각적으로 보여줍니다.
*   **Configuration Panel:** 이메일 계정 정보(IMAP 설정), 브라우저 경로, 관심 키워드 목록, 동기화 주기(예: 1시간마다, 하루 1번) 등을 설정하고 저장합니다.

## 3. 기술 스택 (Technology Stack)

본 시스템은 Windows 환경에서의 호환성과 개발 생산성을 고려하여 Python을 주력 언어로 사용합니다.

### 3.1. 백엔드 및 코어 로직
*   **프로그래밍 언어:** Python 3.11+
*   **데이터베이스 (로컬 설정 저장용):** SQLite3 (기본 내장)
*   **스케줄링:** `schedule` 또는 `APScheduler` 라이브러리 (주기적인 ETL 작업 실행)

### 3.2. 데이터 수집 (Extraction)
*   **이메일:** `imaplib`, `email` (Python 표준 라이브러리)
*   **브라우저 히스토리:** `sqlite3` (로컬 DB 접근), `browserhistory` 또는 커스텀 스크립트
*   **카카오톡/Windows UI 제어:** `pywinauto`, `pyautogui`, `ctypes`
*   **웹 스크래핑 (SNS/카페):** `playwright` (동적 페이지 렌더링 및 로그인 세션 유지에 유리), `beautifulsoup4` (HTML 파싱)

### 3.3. 데이터 처리 (Transformation)
*   **텍스트 정제:** `re` (정규표현식), `lxml` 또는 `beautifulsoup4` (HTML 태그 제거)
*   **데이터 조작:** `pandas` (수집된 데이터의 임시 저장 및 필터링 연산)

### 3.4. NotebookLM 연동 (Load)
*   **API 클라이언트:** `notebooklm-py` (비공식 Python API 래퍼) 또는 `playwright`를 활용한 직접적인 DOM 제어 자동화 스크립트. (Google의 공식 API는 Enterprise 전용이므로, 개인/일반 사용자를 위해 비공식 API 또는 브라우저 자동화 방식을 채택합니다.)

### 3.5. 데스크톱 GUI (Presentation)
*   **GUI 프레임워크:** `PyQt6` 또는 `CustomTkinter` (Windows 네이티브 룩앤필 및 모던 UI 구현)
*   **패키징:** `PyInstaller` (Python 스크립트를 Windows 실행 파일(.exe)로 변환하여 배포)

## 4. 데이터 흐름도 (Data Flow)

1.  **[Scheduler]** 설정된 주기에 따라 ETL 파이프라인 트리거
2.  **[Extractors]** 메일(IMAP), 브라우저(SQLite), 카카오톡(WinAPI)에서 원시 데이터 수집
3.  **[Cleanser & Filter]** 수집된 텍스트 정제 및 관심 키워드 기반 필터링
4.  **[Converter]** 필터링 통과 데이터를 마크다운(.md) 파일로 로컬 임시 저장
5.  **[Source Manager]** NotebookLM 접속 -> 현재 소스 개수 확인 -> 필요시 오래된 소스 삭제
6.  **[API Client]** 생성된 마크다운 파일을 NotebookLM 특정 노트북에 업로드
7.  **[Dashboard]** 작업 결과(성공/실패, 업로드된 소스 수)를 GUI에 업데이트 및 로그 기록

---
**References**
[1] Python imaplib Documentation. https://docs.python.org/3/library/imaplib.html
[2] Playwright for Python. https://playwright.dev/python/
[3] notebooklm-py GitHub Repository. https://github.com/teng-lin/notebooklm-py
