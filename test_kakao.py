# -*- coding: utf-8 -*-
"""
카카오톡 추출 기능 독립 테스트 스크립트
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from extractors.kakao_extractor import KakaoTalkExtractor, kakao_messages_to_markdown

def test_kakao_extraction():
    extractor = KakaoTalkExtractor()
    
    print("="*50)
    print(" 카카오톡 추출 기능 테스트 모드")
    print("="*50)
    print("1. UI 자동화 테스트 (카카오톡 PC 버전이 켜져 있어야 함)")
    print("2. 내보내기 파일(.txt) 파싱 테스트")
    print("q. 종료")
    if len(sys.argv) < 2:
        choice = input("\n테스트할 번호를 선택하세요: ")
    else:
        choice = '1'
    if choice == '1':
        if len(sys.argv) > 1:
            room_name = sys.argv[1]
        else:
            room_name = input("가져올 채팅방 이름 (기본: 나에게 쓰기): ") or "나에게 쓰기"
        print(f"\n[실시간 추출] '{room_name}' 채팅방에서 메시지를 가져오는 중...")
        
        # UI 자동화 실행
        messages = extractor.extract_via_ui_automation(target_rooms=[room_name], max_messages=20)
        
        if messages:
            print(f"✅ 성공: {len(messages)}개의 메시지를 발견했습니다.")
            for msg in messages[:5]:
                print(f"  - [{msg.timestamp}] {msg.sender}: {msg.message[:30]}...")
            
            # 마크다운 변환 테스트
            md = kakao_messages_to_markdown(messages)
            print("\n--- 마크다운 변환 미리보기 ---")
            print(md[:300] + "...")
        else:
            print("❌ 실패: 메시지를 가져오지 못했습니다. 카카오톡이 켜져 있고 채팅방이 목록에 있는지 확인하세요.")

    elif choice == '2':
        file_path = input("카카오톡 내보내기 파일 경로 (.txt): ")
        if not os.path.exists(file_path):
            print(f"❌ 오류: 파일을 찾을 수 없습니다: {file_path}")
            return
            
        print(f"\n[파일 파싱] '{file_path}' 분석 중...")
        messages = extractor.extract_from_export_file(file_path, max_messages=50)
        
        if messages:
            print(f"✅ 성공: {len(messages)}개의 메시지를 파싱했습니다.")
            for msg in messages[:5]:
                print(f"  - [{msg.timestamp}] {msg.sender}: {msg.message[:30]}...")
        else:
            print("❌ 실패: 파일에서 메시지를 찾지 못했습니다. 올바른 카카오톡 내보내기 형식인지 확인하세요.")

    elif choice == 'q':
        print("테스트를 종료합니다.")
    else:
        print("잘못된 선택입니다.")

if __name__ == "__main__":
    try:
        test_kakao_extraction()
    except KeyboardInterrupt:
        print("\n중단되었습니다.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n실행 중 오류 발생: {e}")
  