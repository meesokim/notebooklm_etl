# NotebookLM ETL Manager

NotebookLM ETL Manager는 다양한 소스(이메일, 브라우저 히스토리, 카카오톡, 웹사이트 등)에서 데이터를 추출하여 Google NotebookLM에 자동으로 업로드하고 관리해주는 도구입니다.

## 🚀 주요 기능

- **다중 소스 추출:**
  - **이메일:** 네이버, Gmail 등 IMAP 지원 메일 수집
  - **브라우저 히스토리:** Chrome, Edge, Firefox, Whale 방문 기록 수집
  - **카카오톡:** PC 버전 채팅 내용 및 공유 링크 수집
  - **웹 스크래핑:** 일반 뉴스/아티클 및 네이버 카페 게시물 수집
- **스마트 필터링:** 키워드 기반 필터링, 관련성 점수 계산, 광고 제거
- **NotebookLM 연동:** 소스 자동 업로드 및 50개 제한 관리 (오래된 소스 자동 로테이션)
- **사용자 인터페이스:** 직관적인 Windows GUI 및 CLI 모드 지원
- **자동화:** 백그라운드 데몬 모드 및 스케줄링 지원

## 🛠 설치 방법

1. **Python 설치:** Python 3.11 이상의 버전이 필요합니다.
2. **의존성 설치:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Playwright 설치 (웹 수집 필수):**
   본 프로그램은 네이버 카페 스크래핑 등을 위해 Playwright를 사용합니다. 
   처음 사용 시 아래 명령어로 브라우저를 설치해야 합니다:
   ```bash
   # 브라우저 바이너리 설치
   playwright install chromium
   
   # (Linux/WSL 전용) 시스템 의존성 설치
   sudo playwright install-deps
   ```
   *참고: 프로그램 실행 시 Playwright가 설치되어 있지 않으면 자동으로 설치를 시도합니다.*

4. **NotebookLM 인증 (필수):**
   이 도구는 비공식 NotebookLM API를 사용합니다. 최초 1회 브라우저를 통한 인증이 필요합니다.
   ```bash
   notebooklm auth
   ```
   *위 명령 실행 후 브라우저가 열리면 Google 계정으로 로그인하세요.*

## 🐧 WSL (Linux) 사용 시 주의 사항

WSL 환경에서 GUI의 한글이 깨지거나 네모로 표시될 경우, 다음 명령어를 통해 한글 폰트를 설치해야 합니다:

```bash
# 한글 폰트 설치 (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y fonts-nanum

# 폰트 캐시 갱신
fc-cache -fv
```

설치 후 프로그램을 재시작하면 한글이 정상적으로 표시됩니다.

## 📖 사용 방법

### GUI 모드 (권장)
```bash
python main.py
```
- '설정' 탭에서 이메일 계정, 관심 키워드, 대상 노트북 ID를 입력하세요.
- '대시보드'에서 '지금 동기화 실행' 버튼을 클릭하여 시작합니다.

### CLI / 자동화 모드
- **즉시 동기화:** `python main.py --sync`
- **백그라운드 실행:** `python main.py --daemon`
- **설정 마법사:** `python main.py --setup`
- **상태 확인:** `python main.py --status`

## ⚙️ 주요 설정 가이드

### NotebookLM 노트북 ID 확인
NotebookLM에 접속한 후, 해당 노트북의 URL 끝부분이 ID입니다.
`https://notebooklm.google.com/notebook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
여기서 `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` 부분이 노트북 ID입니다.

### 이메일 앱 비밀번호
- **네이버:** 내정보 > 보안설정 > 2단계 인증 > [관리] > 애플리케이션 비밀번호 생성
- **Gmail:** Google 계정 관리 > 보안 > 2단계 인증 > 앱 비밀번호

## ⚠️ 주의 사항
- 이 도구는 비공식 API를 사용하므로, Google의 서비스 정책 변경에 따라 동작이 멈출 수 있습니다.
- 카카오톡 UI 자동화 기능을 사용할 때는 카카오톡 PC 버전이 실행 중이어야 합니다.
- 브라우저 히스토리 수집 시 브라우저가 실행 중이면 데이터베이스 잠금으로 인해 수집이 제한될 수 있습니다.

## 📄 라이선스
MIT License
