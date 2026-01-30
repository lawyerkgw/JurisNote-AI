import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime

# --- 1. 초기 설정 및 페이지 구성 ---
st.set_page_config(page_title="JurisNote AI - 법률 전문가용 판례 노트", layout="wide")

# Gemini 설정
def get_ai_analysis(case_text):
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # 최신 모델 사용 (fallback 로직 적용 가능)
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = f"""
        당신은 대한민국 대법원 판례 분석 전문가입니다. 판례를 분석하여 반드시 아래 JSON 형식으로만 답하세요.
        쟁점이 여러 개인 경우 각 항목 내에서 '1. ..., 2. ...' 형태로 번호를 매겨 서술하세요.

        [JSON 구조]
        {{
            "categories": "1단계>2단계>3단계 | 1단계>2단계>3단계",
            "title": "사건명",
            "date": "YYYY-MM-DD",
            "facts": "사실관계 요약",
            "issues": "법적 쟁점 (다수일 경우 번호 부여)",
            "laws": "직접 관련된 관련 법률 조문",
            "holdings": "판결 요지",
            "insight": "실무적 의의 및 주의사항"
        }}

        판례 내용: {case_text}
        """
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI 분석 중 오류: {e}")
        return None

# 구글 시트 인증 함수
def init_spreadsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # 시트 이름 'JurisNote_DB'가 미리 생성되어 있어야 합니다.
        sh = client.open("JurisNote_DB").sheet1
        return sh
    except Exception as e:
        st.error(f"시트 연결 오류: {e}")
        return None

sheet = init_spreadsheet()

# --- 2. 사이드바 메뉴 ---
menu = st.sidebar.radio("📌 메뉴 선택", ["판례 분석 및 등록", "나의 공부노트 (조회)"])

# --- 3. [기능 1] 판례 분석 및 등록 ---
if menu == "판례 분석 및 등록":
    st.title("⚖️ 최신 대법원 판례 분석")
    st.info("대법원 판결문 원문 또는 요지를 붙여넣으면 AI가 법리 분석 및 분류를 수행합니다.")
    
    case_content = st.text_area("판례 내용 입력", height=300, placeholder="여기에 판결 내용을 복사해 넣으세요...")
    
    if st.button("🪄 AI 법리 분석 시작"):
        if case_content:
            with st.spinner("AI 전문가가 법리를 검토 중입니다..."):
                res = get_ai_analysis(case_content)
                if res:
                    # 세션에 결과 저장
                    st.session_state['temp_res'] = res
        else:
            st.warning("분석할 내용을 입력해주세요.")

    # AI 분석 결과가 세션에 있을 때만 편집 및 저장 화면 표시
    if 'temp_res' in st.session_state:
        res = st.session_state['temp_res']
        st.markdown("---")
        st.subheader(f"🔍 AI 분석 결과 검토: {res['title']}")
        
        # 편집을 위한 양식(Form) 구성
        with st.form("edit_and_save_form"):
            col1, col2 = st.columns([1, 1])
            
            with col1:
                final_cats = st.text_input("📁 분류 (1단계>2단계>3단계 | 다중분류는 '|' 구분)", value=res['categories'])
                final_facts = st.text_area("📍 사실관계 (사건의 경위)", value=res.get('facts', ''), height=150)
                # 다중 쟁점 대응을 위해 넓은 칸 제공
                final_issues = st.text_area("❓ 법적 쟁점 (쟁점이 여러 개인 경우 번호별 정리)", value=res.get('issues', ''), height=200)
                final_laws = st.text_area("📜 관련법률 (직접 관련된 조문)", value=res.get('laws', ''), height=100)
                
            with col2:
                # 날짜 파싱 안전 처리
                try:
                    target_date = datetime.strptime(res['date'], "%Y-%m-%d")
                except:
                    target_date = datetime.now()
                
                final_date = st.date_input("📅 선고 일자", target_date)
                final_holdings = st.text_area("📢 판결요지 (법원의 판단 핵심)", value=res.get('holdings', ''), height=200)
                final_insight = st.text_area("💡 실무적 의의 (유의사항 및 해설)", value=res.get('insight', ''), height=150)
                case_url = st.text_input("🔗 판결문 원문 URL", placeholder="https://...")
            
            st.divider()
            user_memo = st.text_area("📝 나의 학습 노트 (추가 메모)", placeholder="나만의 공부 내용이나 판례의 특징을 기록하세요.")
            
            # 저장 버튼
            submit_btn = st.form_submit_button("💾 데이터베이스에 최종 저장")

            if submit_btn:
                try:
                    # 시트 저장 데이터 순서 업데이트 (A~K열: 11개 항목)
                    # ID, 선고일자, 사건명, 분류, 사실관계, 쟁점, 관련법률, 판결요지, 실무적의의, 내메모, URL
                    row = [
                        f"{final_date}_{res['title']}", # A: ID
                        str(final_date),               # B: 선고일자
                        res['title'],                   # C: 사건명
                        final_cats,                     # D: 분류
                        final_facts,                    # E: 사실관계
                        final_issues,                   # F: 쟁점
                        final_laws,                     # G: 관련법률
                        final_holdings,                 # H: 판결요지
                        final_insight,                  # I: 실무적의의
                        user_memo,                      # J: 내메모
                        case_url                        # K: URL
                    ]
                    
                    if sheet:
                        sheet.append_row(row)
                        st.success(f"✅ '{res['title']}' 판례가 성공적으로 저장되었습니다!")
                        # 저장 후 세션 초기화 및 페이지 새로고침
                        del st.session_state['temp_res']
                        st.rerun()
                    else:
                        st.error("구글 시트 연결을 확인해주세요.")
                except Exception as e:
                    st.error(f"저장 중 오류가 발생했습니다: {e}")

        # 분석 결과 초기화 버튼 (폼 외부에 배치)
        if st.button("❌ 분석 결과 취소"):
            del st.session_state['temp_res']
            st.rerun()
# --- 4. [기능 2] 나의 공부노트 (조회) ---
elif menu == "나의 공부노트 (조회)":
    st.title("📚 카테고리별 판례 복기")
    
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if not df.empty:
            # 1단계 대분류 필터 구성
            cat1_list = ["전체", "민사법", "형사법", "행정법", "헌법", "지식재산권법", "기타"]
            selected_cat1 = st.sidebar.selectbox("1단계 분류 필터", cat1_list)
            
            # 검색어 필터
            search_q = st.sidebar.text_input("사건명/내용 검색")
            
            # 필터링 로직 (다중 분류 대응)
            if selected_cat1 != "전체":
                df = df[df['분류'].str.contains(selected_cat1)]
            if search_q:
                df = df[df['사건명'].str.contains(search_q) | df['AI요약'].str.contains(search_q)]
            
            # 카드 형태로 판례 표시
            for _, row in df.iterrows():
                with st.container():
                    st.markdown(f"### [{row['선고일자']}] {row['사건명']}")
                    # 태그 표시
                    tags = row['분류'].split('|')
                    tag_html = "".join([f'<span style="background-color:#e1e4e8; color:#0366d6; padding:2px 8px; border-radius:10px; margin-right:5px; font-size:12px;">{t.strip()}</span>' for t in tags])
                    st.markdown(tag_html, unsafe_allow_html=True)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.info(f"**📍 판례 요지**\n\n{row['AI요약']}")
                    with c2:
                        st.warning(f"**💡 실무적 의의**\n\n{row['의의']}")
                    
                    if row['내메모']:
                        st.success(f"**📝 내 메모:** {row['내메모']}")
                    
                    if row['URL']:
                        st.link_button("⚖️ 대법원 판결문 원문 보기", row['URL'])
                    st.divider()
        else:
            st.info("아직 저장된 판례가 없습니다.")
