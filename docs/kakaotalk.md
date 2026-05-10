# 카카오톡 기능

1. 카카오톡 방목록
WSL 환경에서 windows 앱인 카카오톡 대화방 목록을 얻는 것임
windows 환경에서도 동작시키는 기능이 extractors/bakao_extractor.py에 구현되어 있어. 
pywin32 패키지는 windows에서만 동작하기 때문에 python.exe를 실행시켜야 함
인터넷 검색을 통해서도 카카오톡 대화방 목록을 얻는 방법이 정확하게 설명되어있지 않음
최대한 다양한 방식으로 대화방 목록을 얻는 방법을 찾아야 함

2. 카카오톡 특정 대화방 내용 추출
config/user_config.json에 저정한 대화방 목록에 해당하는 대화방의 내용을 txt 파일로 저장한다.
저장된 파일을 LLM-wiki를 위해서 md 파일로 변경한다.