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
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = f"""
        당신은 대한민국 대법원 판례 전문 분석가입니다. 아래 판례 내용을 분석하여 **반드시 JSON 형식**으로만 응답하세요.
        
        1. 분류 가이드:
           - 1단계(cat1): 민사법, 형사법, 행정법, 헌법, 지식재산권법, 기타 중 선택
           - 2단계(cat2): 중분류 (예: 채권법, 형법각칙 등)
           - 3단계(cat3): 소분류 (예: 손해배상, 사기죄 등)
        2. 다중 분류: 만약 판례가 여러 분야에 걸쳐 있다면, 각 카테고리를 '|'로 구분하여 작성하세요.
           예: "민사법>채권법>불법행위 | 민사법>민사소송법>상계항변"
        
        [JSON 구조]
        {{
            "categories": "1단계>2단계>3단계 | 1단계>2단계>3단계",
            "title": "사건명",
            "date": "선고일자(YYYY-MM-DD)",
            "summary": "판례 요지 3줄 요약",
            "insight": "실무적 유의사항 및 의의"
        }}
        
        판례 내용: {case_text}
        """
        response = model.generate_content(prompt)
        # JSON 부분만 추출 (마크다운 태그 제거)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI 분석 중 오류 발생: {e}")
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
                    st.session_state['temp_res'] = res
        else:
            st.warning("내용을 입력해주세요.")

    # 분석 결과가 세션에 있을 때 표시
    if 'temp_res' in st.session_state:
        res = st.session_state['temp_res']
        st.markdown("---")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader(f"🔍 분석 결과: {res['title']}")
            final_cats = st.text_input("분류 (수정 가능, '|'로 다중 분류)", value=res['categories'])
            final_summary = st.text_area("AI 요약 요지", value=res['summary'], height=150)
            final_insight = st.text_area("실무적 의의", value=res['insight'], height=100)
        
        with col2:
            st.date_input("선고 일자", datetime.strptime(res['date'], "%Y-%m-%d"))
            user_memo = st.text_area("📝 나의 추가 메모", placeholder="나중에 기억할 포인트 작성...")
            case_url = st.text_input("🔗 판결문 원문 URL")

        if st.button("💾 데이터베이스에 저장"):
            try:
                # 시트 저장 데이터 순서: ID(일자+제목), 선고일자, 사건명, 분류, 요약, 의의, 메모, URL
                row = [res['date'] + "_" + res['title'], res['date'], res['title'], final_cats, final_summary, final_insight, user_memo, case_url]
                sheet.append_row(row)
                st.success("성공적으로 저장되었습니다!")
                del st.session_state['temp_res']
                st.rerun()
            except:
                st.error("저장 중 오류가 발생했습니다.")

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
