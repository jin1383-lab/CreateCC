import streamlit as st
import re
from googleapiclient.discovery import build

# 페이지 기본 설정
st.set_page_config(
    page_title="유튜브 CCL 영상 검색기",
    page_icon="🔍",
    layout="centered"
)

st.title("유튜브 채널 CCL 영상 검색기 🔍")
st.write("유튜브 채널 주소를 입력하면 크리에이티브 커먼즈 라이선스(CCL)가 적용된 영상들을 찾아줍니다.")

# 1. Streamlit Secrets에서 API 키 불러오기
try:
    API_KEY = st.secrets["YOUTUBE_API_KEY"]
    youtube = build('youtube', 'v3', developerKey=API_KEY)
except Exception:
    st.error("⚠️ Streamlit Secrets에 'YOUTUBE_API_KEY'가 설정되지 않았습니다.")
    st.stop()

# 2. 다양한 형태의 유튜브 링크/핸들에서 채널 ID 또는 핸들 추출하는 함수
def extract_channel_info(url_or_handle):
    url_or_handle = url_or_handle.strip()
    
    # 정규식을 이용해 UC... 형식의 채널 ID 직접 추출
    channel_id_match = re.search(r"channel/(UC[a-zA-Z0-9_-]{22})", url_or_handle)
    if channel_id_match:
        return {"type": "id", "value": channel_id_match.group(1)}
    
    # @handle 형태 추출 (@가 없어도 주소창의 @handle 추출)
    handle_match = re.search(r"@(A-Za-z0-9_\-\.]+)", url_or_handle)
    if handle_match:
        return {"type": "handle", "value": f"@{handle_match.group(1)}"}
    
    if url_or_handle.startswith("@"):
        return {"type": "handle", "value": url_or_handle}
        
    return {"type": "unknown", "value": url_or_handle}

# 3. 핸들네임(@)을 기반으로 실제 채널 ID를 조회하는 함수
def get_channel_id_by_handle(handle):
    # 핸들로 채널 검색 시, @를 포함하여 'forHandle' 파라미터 사용
    response = youtube.channels().list(
        part="id",
        forHandle=handle
    ).execute()
    
    if "items" in response and len(response["items"]) > 0:
        return response["items"][0]["id"]
    return None

# --- UI 및 메인 로직 시작 ---

# 사용자 입력창
user_input = st.text_input(
    "유튜브 채널 주소 또는 핸들을 입력하세요", 
    placeholder="예: https://www.youtube.com/@정부24 또는 UC_x5XG1OV2P6uZZ5FSM9Ttw"
)

# 최대 검색 영상 개수 조절 슬라이더
max_results = st.slider("검색할 최신 영상 개수", min_value=10, max_value=50, value=20, step=10)

if st.button("CCL 영상 조회하기", type="primary"):
    if user_input:
        with st.spinner("채널 정보를 분석하고 영상을 탐색 중입니다..."):
            try:
                info = extract_channel_info(user_input)
                channel_id = None
                
                # 입력된 값의 타입에 따라 채널 ID 확보
                if info["type"] == "id":
                    channel_id = info["value"]
                elif info["type"] == "handle":
                    channel_id = get_channel_id_by_handle(info["value"])
                    if not channel_id:
                        st.error(f"❌ '{info['value']}' 핸들에 해당하는 채널을 찾을 수 없습니다.")
                        st.stop()
                else:
                    # 입력이 불명확할 경우 직접 ID로 가정하고 시도
                    channel_id = info["value"]
                
                # 1단계: 채널의 '업로드 목록' 재생목록 ID 가져오기
                channel_response = youtube.channels().list(
                    part='contentDetails,snippet',
                    id=channel_id
                ).execute()
                
                if not channel_response.get('items'):
                    st.error("❌ 올바른 채널 ID를 찾지 못했거나 존재하지 않는 채널입니다.")
                    st.stop()
                    
                channel_title = channel_response['items'][0]['snippet']['title']
                st.subheader(f"📺 '{channel_title}' 채널의 결과")
                
                uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
                
                # 2단계: 최근 업로드 동영상 목록 가져오기
                playlist_response = youtube.playlistItems().list(
                    part='snippet',
                    playlistId=uploads_playlist_id,
                    maxResults=max_results
                ).execute()
                
                if not playlist_response.get('items'):
                    st.warning("채널에 업로드된 영상이 없습니다.")
                    st.stop()
                    
                video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_response['items']]
                
                # 3단계: 각 동영상의 라이선스 상태 상세 조회
                videos_response = youtube.videos().list(
                    part='status,snippet',
                    id=','.join(video_ids)
                ).execute()
                
                ccl_videos = []
                for video in videos_response.get('items', []):
                    license_type = video['status']['license']
                    # 라이선스가 'creativeCommon'인 것만 필터링
                    if license_type == 'creativeCommon':
                        ccl_videos.append({
                            'title': video['snippet']['title'],
                            'id': video['id'],
                            'publishedAt': video['snippet']['publishedAt'][:10] # 날짜만 추출
                        })
                
                # 4단계: 결과 화면 출력
                if ccl_videos:
                    st.success(f"✅ 최근 {max_results}개의 영상 중 {len(ccl_videos)}개의 CCL 영상을 찾았습니다!")
                    for vid in ccl_videos:
                        with st.container():
                            st.markdown(f"### {vid['title']}")
                            st.caption(f"업로드 날짜: {vid['publishedAt']} | 라이선스: Creative Commons (저작자 표시)")
                            st.video(f"https://www.youtube.com/watch?v={vid['id']}")
                            st.write("---")
                else:
                    st.warning(f"ℹ️ 최근 {max_results}개의 영상 중 CCL 라이선스가 적용된 영상이 없습니다. (모두 표준 유튜브 라이선스)")
                    
            except Exception as e:
                st.error(f"💥 에러가 발생했습니다: {e}")
    else:
        st.info("💡 채널 링크나 핸들명을 입력창에 넣어주세요.")
