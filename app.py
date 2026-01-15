import streamlit as st
import json

st.title("🕵️ Màn hình kiểm tra lỗi")

# 1. Kiểm tra thư viện
try:
    import gspread
    st.success("✅ Bước 1: Thư viện gspread đã cài OK!")
except ImportError:
    st.error("❌ Bước 1 LỖI: Chưa cài gspread (Kiểm tra file requirements.txt)")
    st.stop()

# 2. Kiểm tra Secrets
try:
    st.info("Đang thử đọc Secrets...")
    # Kiểm tra xem mục [service_account] có tồn tại không
    if "service_account" not in st.secrets:
        st.error("❌ Lỗi TOML: Không tìm thấy mục [service_account]. Hãy kiểm tra dòng đầu tiên trong Secrets.")
        st.stop()
    
    # Kiểm tra xem key 'info' có tồn tại không
    if "info" not in st.secrets["service_account"]:
        st.error("❌ Lỗi TOML: Không tìm thấy key 'info'. Hãy kiểm tra chữ 'info =' trong Secrets.")
        st.stop()

    # Thử giải mã JSON
    json_str = st.secrets["service_account"]["info"]
    creds = json.loads(json_str)
    st.success(f"✅ Bước 2: Đọc Secrets thành công! Email robot là: {creds.get('client_email', 'Không thấy email')}")

except Exception as e:
    st.error(f"❌ Bước 2 LỖI: File Secrets bị sai định dạng!\nChi tiết lỗi: {e}")
