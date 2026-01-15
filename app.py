import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import unicodedata
from fpdf import FPDF
import time

# ==============================================================================
# CẤU HÌNH TRANG & GIAO DIỆN (THEME)
# ==============================================================================
st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường học (GSheets V2 Fixed)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stApp { background-color: #fcfcfc; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 5px; border: none; }
    .stButton>button:hover { background-color: #e07b00; color: white; }
    h1, h2, h3 { color: #E65100; }
    .status-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
        text-align: center;
        min-width: 80px;
    }
    .badge-green { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .badge-red { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .badge-yellow { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
    .badge-grey { background-color: #e2e3e5; color: #383d41; border: 1px solid #d6d8db; }
    .big-score { font-size: 24px; font-weight: bold; color: #E65100; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# XỬ LÝ KẾT NỐI GOOGLE SHEETS
# ==============================================================================
SHEET_ID = "14E2JfVyOhGMa7T1VA44F31IaPMWIVIPRApo4B-ipDLk"

@st.cache_resource
def init_connection():
    """Khởi tạo kết nối đến Google Sheets"""
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(st.secrets["service_account"]["info"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Lỗi kết nối Google Sheets: {e}")
        return None

def get_worksheet(sheet_name):
    """Lấy worksheet, nếu chưa có thì tạo mới"""
    client = init_connection()
    if not client: return None
    
    sh = client.open_by_key(SHEET_ID)
    try:
        return sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
        # Header cập nhật: Bỏ ClassID/ID, dùng TenLop
        if sheet_name == "Users":
            ws.append_row(["Email", "Password", "HoTen", "VaiTro", "TenLop"])
            ws.append_row(["admin@school.com", "123", "Quản Trị Viên", "Admin", ""])
        elif sheet_name == "Classes":
            ws.append_row(["TenLop", "EmailGVCN", "SiSo"]) 
        elif sheet_name == "Periods":
            ws.append_row(["ID", "TenDot", "TrangThai"])
        elif sheet_name == "Relationships":
            ws.append_row(["Email_HocSinh", "Email_PhuHuynh"])
        elif sheet_name == "OKRs":
            ws.append_row(["ID", "Email_HocSinh", "ID_Dot", "MucTieu", "KetQuaThenChot", "TienDo", "TrangThai", "NhanXet_GV", "NhanXet_PH", "MinhChung", "TargetValue", "ActualValue", "Unit", "DeleteRequest"])
        elif sheet_name == "FinalReviews":
            ws.append_row(["Email_HocSinh", "ID_Dot", "NhanXet_GV", "NhanXet_PH", "DaGui_PH"])
        return ws

# --- CÁC HÀM CRUD ---

@st.cache_data(ttl=10)
def load_data(sheet_name):
    """Đọc dữ liệu và xử lý an toàn (Fix lỗi KeyError)"""
    ws = get_worksheet(sheet_name)
    if not ws: return pd.DataFrame()
    
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    # --- FIX LỖI TƯƠNG THÍCH CỘT ---
    # 1. Bảng Users
    if sheet_name == "Users":
        # Map ClassID -> TenLop nếu cột cũ tồn tại
        if 'ClassID' in df.columns and 'TenLop' not in df.columns:
            df = df.rename(columns={'ClassID': 'TenLop'})
        # Đảm bảo cột TenLop luôn tồn tại
        if 'TenLop' not in df.columns:
            df['TenLop'] = ""

    # 2. Bảng Classes
    if sheet_name == "Classes":
        if 'TenLop' not in df.columns and 'ID' in df.columns:
             df['TenLop'] = df['ID']

    # --- XỬ LÝ KIỂU DỮ LIỆU AN TOÀN (Check if col exists) ---
    if sheet_name == "OKRs" and not df.empty:
        if 'ID' in df.columns: df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
        if 'ID_Dot' in df.columns: df['ID_Dot'] = pd.to_numeric(df['ID_Dot'], errors='coerce')
        if 'TargetValue' in df.columns: df['TargetValue'] = pd.to_numeric(df['TargetValue'], errors='coerce').fillna(0)
        if 'ActualValue' in df.columns: df['ActualValue'] = pd.to_numeric(df['ActualValue'], errors='coerce').fillna(0)
        if 'DeleteRequest' in df.columns: df['DeleteRequest'] = pd.to_numeric(df['DeleteRequest'], errors='coerce').fillna(0)

    if sheet_name == "Periods" and not df.empty:
        # FIX LỖI CHÍNH Ở ĐÂY: Kiểm tra xem cột ID có tồn tại không
        if 'ID' in df.columns:
            df['ID'] = pd.to_numeric(df['ID'], errors='coerce')
        else:
            # Nếu thiếu cột ID, tự tạo index làm ID tạm thời để không crash
            df['ID'] = df.index + 1
            
    if sheet_name == "Classes" and not df.empty:
        if 'SiSo' in df.columns: df['SiSo'] = pd.to_numeric(df['SiSo'], errors='coerce').fillna(0)

    if sheet_name == "FinalReviews" and not df.empty:
        if 'ID_Dot' in df.columns: df['ID_Dot'] = pd.to_numeric(df['ID_Dot'], errors='coerce')
        if 'DaGui_PH' in df.columns: df['DaGui_PH'] = pd.to_numeric(df['DaGui_PH'], errors='coerce').fillna(0)
        
    return df

def add_record(sheet_name, row_data):
    ws = get_worksheet(sheet_name)
    if ws:
        ws.append_row(row_data)
        st.cache_data.clear()

def update_record(sheet_name, match_col, match_val, update_col, update_val, match_col_2=None, match_val_2=None):
    ws = get_worksheet(sheet_name)
    if not ws: return
    try:
        # Logic map tên cột cũ sang mới khi UPDATE
        real_match_col = match_col
        if sheet_name == "Users" and match_col == "TenLop":
            headers = ws.row_values(1)
            if "ClassID" in headers and "TenLop" not in headers:
                real_match_col = "ClassID"

        if match_col_2:
            records = ws.get_all_records()
            for i, r in enumerate(records):
                val1 = str(r.get(real_match_col, r.get(match_col, '')))
                val2 = str(r.get(match_col_2, ''))
                
                if val1 == str(match_val) and val2 == str(match_val_2):
                    row_idx = i + 2
                    col_idx = ws.find(update_col).col
                    ws.update_cell(row_idx, col_idx, update_val)
                    break
        else:
            find_col = ws.find(real_match_col)
            if not find_col: return
                
            cell = ws.find(str(match_val), in_column=find_col.col)
            if cell:
                col_idx = ws.find(update_col).col
                ws.update_cell(cell.row, col_idx, update_val)
        st.cache_data.clear()
    except Exception as e:
        print(f"Error update: {e}")

def delete_record(sheet_name, match_col, match_val):
    ws = get_worksheet(sheet_name)
    if not ws: return
    try:
        cell = ws.find(str(match_val), in_column=ws.find(match_col).col)
        if cell:
            ws.delete_rows(cell.row)
            st.cache_data.clear()
    except:
        pass

def get_next_id(sheet_name):
    df = load_data(sheet_name)
    if df.empty: return 1
    if 'ID' in df.columns:
        return int(df['ID'].max()) + 1
    return 1

def upsert_final_review(email, id_dot, col_name, value):
    df = load_data("FinalReviews")
    exists = False
    if not df.empty:
        mask = (df['Email_HocSinh'] == email) & (df['ID_Dot'] == id_dot)
        if not df[mask].empty:
            exists = True
    
    if exists:
        update_record("FinalReviews", "Email_HocSinh", email, col_name, value, "ID_Dot", id_dot)
    else:
        row = [email, id_dot, "", "", 0]
        if col_name == "NhanXet_GV": row[2] = value
        elif col_name == "NhanXet_PH": row[3] = value
        elif col_name == "DaGui_PH": row[4] = value
        add_record("FinalReviews", row)

# ==============================================================================
# TIỆN ÍCH
# ==============================================================================

def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', str(input_str))
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def calculate_percent(actual, target):
    try:
        acc = float(actual)
        tar = float(target)
        if tar == 0: return 0
        return round((acc / tar) * 100, 1)
    except: return 0

def get_rank(percent):
    if percent >= 80: return "Tốt", "green"
    elif percent >= 65: return "Khá", "blue"
    elif percent >= 50: return "Đạt", "orange"
    return "Chưa đạt", "red"

def change_password_ui(email):
    with st.expander("🔐 Đổi mật khẩu"):
        with st.form("change_pass_form"):
            new_pass = st.text_input("Mật khẩu mới", type="password")
            confirm_pass = st.text_input("Xác nhận mật khẩu mới", type="password")
            if st.form_submit_button("Cập nhật"):
                if new_pass and new_pass == confirm_pass:
                    update_record("Users", "Email", email, "Password", new_pass)
                    st.success("Đổi mật khẩu thành công!")
                else:
                    st.error("Mật khẩu không khớp.")

def get_periods_map(role):
    df = load_data("Periods")
    if df.empty: return {}
    # Fix: Kiểm tra xem cột TrangThai có tồn tại không
    if 'TrangThai' not in df.columns: return {}
    
    if role != 'Admin':
        df = df[df['TrangThai'] == 'Mo']
        
    if 'TenDot' in df.columns and 'ID' in df.columns:
        return dict(zip(df['TenDot'], df['ID']))
    return {}

# ==============================================================================
# DASHBOARD LOGIC
# ==============================================================================

def login_page():
    st.markdown("<h2 style='text-align: center;'>🔐 Đăng Nhập Hệ Thống OKR</h2>", unsafe_allow_html=True)
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Mật khẩu", type="password")
        submitted = st.form_submit_button("Đăng nhập")
        if submitted:
            df_users = load_data("Users")
            if df_users.empty:
                st.error("Không kết nối được dữ liệu User.")
                return

            # Convert to string to ensure matching
            df_users['Password'] = df_users['Password'].astype(str)
            
            user = df_users[(df_users['Email'] == email) & (df_users['Password'] == str(password))]
            
            if not user.empty:
                u = user.iloc[0]
                ten_lop_val = u.get('TenLop', '')
                st.session_state['user'] = {
                    'email': u['Email'], 
                    'name': u['HoTen'], 
                    'role': u['VaiTro'], 
                    'ten_lop': ten_lop_val
                }
                st.rerun()
            else:
                st.error("Sai Email hoặc mật khẩu.")

# --- 1. ADMIN DASHBOARD ---
def admin_dashboard(period_id):
    st.header("🛠️ Dashboard Quản Trị Viên")
    change_password_ui(st.session_state['user']['email'])

    tab1, tab2, tab3 = st.tabs(["Quản lý Lớp & Thống kê", "Quản lý User", "Quản lý Đợt"])

    # TAB 1: DANH SÁCH LỚP
    with tab1:
        st.subheader(f"📊 Thống kê Lớp học - Đợt ID: {period_id}")
        
        classes = load_data("Classes")
        
        if classes.empty:
            st.info("Chưa có lớp học nào.")
        else:
            stats_data = []
            reviews = load_data("FinalReviews")
            all_users = load_data("Users")
            
            for _, cl in classes.iterrows():
                siso = float(cl['SiSo']) if 'SiSo' in cl else 0
                ten_lop = cl.get('TenLop', 'N/A')
                gvcn = cl.get('EmailGVCN', 'N/A')
                
                # Lọc HS theo Tên Lớp
                class_users = []
                if not all_users.empty and 'TenLop' in all_users.columns:
                    class_users = all_users[all_users['TenLop'] == ten_lop]['Email'].tolist()
                
                if not reviews.empty and class_users:
                    approved_count = reviews[
                        (reviews['ID_Dot'] == period_id) & 
                        (reviews['Email_HocSinh'].isin(class_users)) & 
                        (reviews['NhanXet_GV'] != "")
                    ].shape[0]
                else:
                    approved_count = 0

                pct_approved = round((approved_count / siso * 100), 1) if siso > 0 else 0
                
                stats_data.append({
                    "Tên Lớp": ten_lop,
                    "GVCN": gvcn,
                    "Sĩ Số": int(siso),
                    "Đã Duyệt Tổng Kết (%)": f"{pct_approved}%",
                    "Chưa Duyệt (%)": f"{100 - pct_approved}%"
                })
            st.dataframe(pd.DataFrame(stats_data))

        st.divider()
        st.markdown("### 🏫 Tạo Lớp & Cấp Tài khoản")
        col_a, col_b = st.columns([1, 2])
        with col_a:
            with st.form("add_class_admin"):
                c_name = st.text_input("Tên Lớp (VD: 12A1)")
                c_gv = st.text_input("Email GVCN")
                c_siso = st.number_input("Sĩ số", min_value=1, value=40)
                if st.form_submit_button("Tạo Lớp"):
                    if c_name and c_gv:
                        try:
                            if not classes.empty and 'TenLop' in classes.columns and c_name in classes['TenLop'].values:
                                st.error("Tên lớp đã tồn tại!")
                            else:
                                add_record("Classes", [c_name, c_gv, c_siso])
                                users = load_data("Users")
                                if users.empty or users[users['Email'] == c_gv].empty:
                                    add_record("Users", [c_gv, "123", f"GV ({c_name})", "GiaoVien", ""])
                                st.success(f"Đã tạo lớp {c_name}!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi: {e}")

        with col_b:
            st.write("###### Danh sách kích hoạt")
            for _, cl in classes.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    t_lop = cl.get('TenLop', 'N/A')
                    e_gv = cl.get('EmailGVCN', 'N/A')
                    c1.write(f"**{t_lop}** - GV: {e_gv}")
                    if c2.button("🚀 Cấp TK", key=f"grant_{t_lop}"):
                        update_record("Users", "Email", e_gv, "Password", "123")
                        st.toast(f"Đã kích hoạt tài khoản cho GV: {e_gv} (Pass: 123)")

    with tab2:
        st.subheader("Quản lý User")
        search = st.text_input("Tìm Email:")
        if search:
            users = load_data("Users")
            if not users.empty:
                u = users[users['Email'] == search]
                st.write(u)
                if not u.empty and st.button("Reset Pass"):
                    update_record("Users", "Email", search, "Password", "123")
                    st.success("Đã reset về 123")

    with tab3:
        st.subheader("Quản lý Đợt")
        periods = load_data("Periods")
        for i, row in periods.iterrows():
            c_tog, c_del = st.columns([4, 1])
            with c_tog:
                is_open = row.get('TrangThai') == 'Mo'
                p_id = row.get('ID')
                p_name = row.get('TenDot', 'Unknown')
                
                toggle = st.toggle(f"{p_name} (ID: {p_id})", value=is_open, key=f"p_{p_id}")
                new_st = 'Mo' if toggle else 'Khoa'
                if new_st != row.get('TrangThai'):
                    update_record("Periods", "ID", p_id, "TrangThai", new_st)
                    st.rerun()
            with c_del:
                if st.button("🗑️", key=f"del_p_{p_id}"):
                    delete_record("Periods", "ID", p_id)
                    st.warning(f"Đã xóa đợt: {p_name}")
                    st.rerun()
        
        with st.form("new_period"):
            p_name = st.text_input("Tên đợt mới")
            if st.form_submit_button("Thêm"):
                next_id = get_next_id("Periods")
                add_record("Periods", [next_id, p_name, 'Mo'])
                st.rerun()

# --- 2. TEACHER DASHBOARD ---
def teacher_dashboard(period_id):
    user_email = st.session_state['user']['email']
    st.header(f"🍎 Giáo Viên: {st.session_state['user']['name']}")
    change_password_ui(user_email)
    
    classes = load_data("Classes")
    if classes.empty:
        st.warning("Dữ liệu lớp học trống.")
        return

    my_class = classes[classes['EmailGVCN'] == user_email]
    
    if my_class.empty:
        st.warning("Bạn chưa được phân công lớp.")
        return

    class_name = my_class.iloc[0]['TenLop']
    st.info(f"Lớp: {class_name} - Đợt làm việc ID: {period_id}")

    tab1, tab2 = st.tabs(["Danh sách Học sinh (List View)", "Import Excel"])

    with tab1:
        st.subheader("📋 Trạng thái OKR Học sinh")
        
        users = load_data("Users")
        students = pd.DataFrame()
        if 'TenLop' in users.columns:
            students = users[users['TenLop'] == class_name]
        
        if students.empty:
            st.write("Lớp chưa có học sinh.")
        else:
            cols = st.columns([0.5, 2, 1.5, 1.5, 1])
            cols[0].markdown("**STT**")
            cols[1].markdown("**Họ Tên**")
            cols[2].markdown("**Duyệt Lần 1 (Mục Tiêu)**")
            cols[3].markdown("**Duyệt Lần 2 (Tổng Kết)**")
            cols[4].markdown("**Hành động**")
            
            all_okrs = load_data("OKRs")
            all_reviews = load_data("FinalReviews")

            for idx, hs in students.iterrows():
                if not all_okrs.empty:
                    hs_okrs = all_okrs[(all_okrs['Email_HocSinh'] == hs['Email']) & (all_okrs['ID_Dot'] == period_id)]
                else:
                    hs_okrs = pd.DataFrame()

                # Status L1
                l1_status = ""
                l1_badge = ""
                
                if hs_okrs.empty:
                    l1_status = "Chưa tạo"
                    l1_badge = "badge-red"
                else:
                    pending = hs_okrs[hs_okrs['TrangThai'] == 'ChoDuyet']
                    if not pending.empty:
                        l1_status = "Chờ duyệt"
                        l1_badge = "badge-yellow"
                    else:
                        l1_status = "Đã duyệt"
                        l1_badge = "badge-green"

                # Status L2
                has_final = False
                if not all_reviews.empty:
                    rev = all_reviews[(all_reviews['Email_HocSinh'] == hs['Email']) & (all_reviews['ID_Dot'] == period_id)]
                    if not rev.empty and rev.iloc[0]['NhanXet_GV'] != "":
                        has_final = True
                
                l2_status = "Đã xong" if has_final else "Chưa xong"
                l2_badge = "badge-green" if has_final else "badge-grey"
                
                has_del_req = False
                if not hs_okrs.empty:
                    if not hs_okrs[hs_okrs['DeleteRequest'] == 1].empty:
                        has_del_req = True
                
                with st.container():
                    c = st.columns([0.5, 2, 1.5, 1.5, 1])
                    c[0].write(f"{idx+1}")
                    
                    name_display = hs['HoTen']
                    if has_del_req:
                        name_display += " ⚠️ (Có yêu cầu xóa)"
                    c[1].write(name_display)
                    
                    c[2].markdown(f'<span class="status-badge {l1_badge}">{l1_status}</span>', unsafe_allow_html=True)
                    c[3].markdown(f'<span class="status-badge {l2_badge}">{l2_status}</span>', unsafe_allow_html=True)
                    
                    if c[4].button("Chi tiết", key=f"view_{hs['Email']}"):
                        st.session_state['selected_hs'] = hs.to_dict()
                        st.rerun()

            st.divider()
            
            if 'selected_hs' in st.session_state:
                hs_curr = st.session_state['selected_hs']
                st.markdown(f"### 📝 Chi tiết: {hs_curr['HoTen']}")
                
                if not all_okrs.empty:
                    df_okr = all_okrs[(all_okrs['Email_HocSinh'] == hs_curr['Email']) & (all_okrs['ID_Dot'] == period_id)]
                else:
                    df_okr = pd.DataFrame()
                
                if df_okr.empty:
                    st.warning("Học sinh này chưa nhập OKR nào.")
                else:
                    for i, row in df_okr.iterrows():
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([4, 2, 2])
                            
                            if row['DeleteRequest'] == 1:
                                st.error(f"⚠️ Học sinh yêu cầu xóa mục tiêu: {row['MucTieu']} - {row['KetQuaThenChot']}")
                            
                            c1.markdown(f"**O:** {row['MucTieu']}")
                            c1.text(f"KR: {row['KetQuaThenChot']}")
                            c2.metric("Mục tiêu/Đạt", f"{row['TargetValue']} / {row['ActualValue']} {row['Unit']}")
                            pct = calculate_percent(row['ActualValue'], row['TargetValue'])
                            c2.progress(min(pct/100, 1.0))
                            
                            with c3:
                                st.write(f"TT: {row['TrangThai']}")
                                if row['TrangThai'] == 'ChoDuyet':
                                    if st.button("✅ Duyệt Mục Tiêu", key=f"app_{row['ID']}"):
                                        update_record("OKRs", "ID", row['ID'], "TrangThai", "DaDuyetMucTieu")
                                        st.rerun()
                                if row['DeleteRequest'] == 1:
                                    if st.button("🗑️ Chấp thuận xóa", key=f"del_{row['ID']}"):
                                        delete_record("OKRs", "ID", row['ID'])
                                        st.rerun()

                    st.write("---")
                    old_cmt_gv = ""
                    cmt_ph = None
                    if not all_reviews.empty:
                        rev = all_reviews[(all_reviews['Email_HocSinh'] == hs_curr['Email']) & (all_reviews['ID_Dot'] == period_id)]
                        if not rev.empty:
                            old_cmt_gv = rev.iloc[0]['NhanXet_GV']
                            if rev.iloc[0]['NhanXet_PH']:
                                cmt_ph = rev.iloc[0]['NhanXet_PH']
                    
                    if cmt_ph:
                        st.info(f"🏠 **Ý kiến gia đình:** {cmt_ph}")
                    else:
                        st.caption("🏠 Gia đình chưa gửi ý kiến.")

                    st.write("**Đánh giá cuối kỳ (Final Review):**")
                    with st.form("teacher_review"):
                        cmt = st.text_area("Nhận xét giáo viên:", value=old_cmt_gv)
                        if st.form_submit_button("Lưu & Hoàn tất Duyệt Lần 2"):
                            upsert_final_review(hs_curr['Email'], period_id, "NhanXet_GV", cmt)
                            st.success("Đã lưu nhận xét!")

    with tab2:
        st.subheader("Import Excel")
        st.caption("Cột bắt buộc: Email, HoTen, EmailPH")
        upl = st.file_uploader("Upload Excel", type=['xlsx'])
        if upl:
            try:
                df = pd.read_excel(upl)
                count = 0
                all_users = load_data("Users")
                all_rels = load_data("Relationships")
                
                for _, r in df.iterrows():
                    # Thêm HS
                    if all_users.empty or r['Email'] not in all_users['Email'].values:
                         add_record("Users", [r['Email'], '123', r['HoTen'], 'HocSinh', class_name])

                    if pd.notna(r['EmailPH']):
                        ph_email = str(r['EmailPH'])
                        if all_users.empty or ph_email not in all_users['Email'].values:
                            add_record("Users", [ph_email, '123', 'Phụ Huynh', 'PhuHuynh', ''])
                        
                        rel_exists = False
                        if not all_rels.empty:
                            mask = (all_rels['Email_HocSinh'] == r['Email']) & (all_rels['Email_PhuHuynh'] == ph_email)
                            if not all_rels[mask].empty:
                                rel_exists = True
                        
                        if not rel_exists:
                            add_record("Relationships", [r['Email'], ph_email])

                    count += 1
                st.success(f"Đã import {count} dòng.")
            except Exception as e:
                st.error(str(e))

# --- 3. STUDENT DASHBOARD ---
def student_dashboard(period_id):
    user_email = st.session_state['user']['email']
    st.header(f"🎒 Góc Học Tập: {st.session_state['user']['name']}")
    change_password_ui(user_email)
    
    with st.expander("➕ Thêm Mục tiêu & Kết quả (OKR)", expanded=True):
        with st.form("student_add"):
            st.caption("Nhập nhiều KR cho cùng 1 Mục tiêu bằng cách gõ lại tên Mục tiêu.")
            mt = st.text_input("Mục tiêu (Objective) - VD: Học sinh giỏi", placeholder="Nhập tên mục tiêu lớn...")
            kr = st.text_input("Kết quả then chốt (KR) - VD: Toán > 8.0")
            c1, c2 = st.columns(2)
            target = c1.number_input("Con số mục tiêu (Target)", min_value=0.1)
            unit = c2.text_input("Đơn vị (VD: Điểm, Bài...)", value="Điểm")
            
            if st.form_submit_button("Lưu OKR"):
                if mt and kr:
                    next_id = get_next_id("OKRs")
                    add_record("OKRs", [next_id, user_email, period_id, mt, kr, 0, 'ChoDuyet', '', '', '', target, 0, unit, 0])
                    st.success("Đã thêm!")
                    st.rerun()

    st.divider()
    st.subheader("📋 OKR của tôi")
    
    all_okrs = load_data("OKRs")
    if not all_okrs.empty:
        df_okrs = all_okrs[(all_okrs['Email_HocSinh'] == user_email) & (all_okrs['ID_Dot'] == period_id)]
    else:
        df_okrs = pd.DataFrame()
    
    if df_okrs.empty:
        st.info("Chưa có dữ liệu.")
    else:
        unique_objs = df_okrs['MucTieu'].unique()
        total_pct = 0
        count_kr = 0
        
        for obj in unique_objs:
            st.markdown(f"#### 🎯 O: {obj}")
            krs = df_okrs[df_okrs['MucTieu'] == obj]
            
            for _, row in krs.iterrows():
                pct = calculate_percent(row['ActualValue'], row['TargetValue'])
                total_pct += pct
                count_kr += 1
                
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                    c1.markdown(f"**KR:** {row['KetQuaThenChot']}")
                    status_text = row['TrangThai']
                    if row['DeleteRequest'] == 1:
                        status_text += " (Đang chờ xóa)"
                    c1.caption(f"Trạng thái: {status_text}")
                    c2.metric("Tiến độ", f"{row['ActualValue']} / {row['TargetValue']} {row['Unit']}")
                    c2.progress(min(pct/100, 1.0))
                    
                    with c3:
                        with st.popover("Báo cáo KQ"):
                            with st.form(f"upd_{row['ID']}"):
                                new_val = st.number_input("Đạt được:", value=float(row['ActualValue']))
                                if st.form_submit_button("Lưu"):
                                    update_record("OKRs", "ID", row['ID'], "ActualValue", new_val)
                                    st.rerun()
                    
                    with c4:
                        if row['TrangThai'] == 'ChoDuyet':
                            if st.button("🗑️", key=f"del_{row['ID']}"):
                                delete_record("OKRs", "ID", row['ID'])
                                st.rerun()
                        else:
                            if row['DeleteRequest'] == 0:
                                if st.button("Xin xóa", key=f"req_{row['ID']}"):
                                    update_record("OKRs", "ID", row['ID'], "DeleteRequest", 1)
                                    st.rerun()
                            else:
                                st.caption("Đang chờ xóa")

        st.divider()
        final_score = round(total_pct / count_kr, 1) if count_kr > 0 else 0
        rank, color = get_rank(final_score)
        st.markdown(f"### 🏁 Tổng kết: <span style='color:{color}'>{final_score}% - {rank}</span>", unsafe_allow_html=True)
        
        all_reviews = load_data("FinalReviews")
        fr = pd.DataFrame()
        if not all_reviews.empty:
            fr = all_reviews[(all_reviews['Email_HocSinh'] == user_email) & (all_reviews['ID_Dot'] == period_id)]
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 👨‍🏫 Giáo viên nhận xét:")
            if not fr.empty and fr.iloc[0]['NhanXet_GV']:
                st.info(fr.iloc[0]['NhanXet_GV'])
            else:
                st.caption("Chưa có nhận xét.")

        with col2:
            st.markdown("##### 🏠 Gia đình nhận xét:")
            if not fr.empty and fr.iloc[0]['NhanXet_PH']:
                st.success(fr.iloc[0]['NhanXet_PH'])
            else:
                st.caption("Gia đình chưa có ý kiến.")

# --- 4. PARENT DASHBOARD ---
def parent_dashboard(period_id):
    user_email = st.session_state['user']['email']
    st.header("👨‍👩‍👧‍👦 Phụ Huynh")
    change_password_ui(user_email)
    
    rels = load_data("Relationships")
    if rels.empty:
        st.warning("Chưa liên kết học sinh.")
        return
        
    my_child = rels[rels['Email_PhuHuynh'] == user_email]
    if my_child.empty:
        st.warning("Chưa liên kết học sinh.")
        return
        
    child_email = my_child.iloc[0]['Email_HocSinh']
    
    users = load_data("Users")
    child_info = users[users['Email'] == child_email].iloc[0]
    st.info(f"Con: {child_info['HoTen']} - Lớp: {child_info.get('TenLop', '')}")
    
    all_okrs = load_data("OKRs")
    df_okr = pd.DataFrame()
    if not all_okrs.empty:
        df_okr = all_okrs[(all_okrs['Email_HocSinh'] == child_email) & (all_okrs['ID_Dot'] == period_id)]
    
    if df_okr.empty:
        st.info("Con chưa có dữ liệu đợt này.")
    else:
        total = 0
        cnt = 0
        st.subheader("Kết quả chi tiết")
        for _, row in df_okr.iterrows():
            pct = calculate_percent(row['ActualValue'], row['TargetValue'])
            total += pct
            cnt += 1
            st.write(f"- **{row['MucTieu']}** ({row['KetQuaThenChot']}): {row['ActualValue']}/{row['TargetValue']} ({pct}%)")
        
        avg = round(total/cnt, 1) if cnt > 0 else 0
        r, c = get_rank(avg)
        st.markdown(f"#### Tổng kết: <span style='color:{c}'>{avg}% ({r})</span>", unsafe_allow_html=True)
        
        st.divider()
        col1, col2 = st.columns(2)
        all_reviews = load_data("FinalReviews")
        fr = pd.DataFrame()
        if not all_reviews.empty:
            fr = all_reviews[(all_reviews['Email_HocSinh'] == child_email) & (all_reviews['ID_Dot'] == period_id)]
        
        with col1:
            st.write("**Giáo viên:**")
            if not fr.empty and fr.iloc[0]['NhanXet_GV']:
                st.info(fr.iloc[0]['NhanXet_GV'])
            else:
                st.text("Chưa có nhận xét.")
                
        with col2:
            st.write("**Gia đình:**")
            cmt_ph = fr.iloc[0]['NhanXet_PH'] if not fr.empty else ""
            sent = fr.iloc[0]['DaGui_PH'] if not fr.empty else 0
            
            if sent == 1:
                st.success(f"Đã gửi: {cmt_ph}")
            else:
                with st.form("ph_cmt"):
                    txt = st.text_area("Ý kiến:", value=cmt_ph)
                    if st.form_submit_button("Gửi"):
                        upsert_final_review(child_email, period_id, "NhanXet_PH", txt)
                        upsert_final_review(child_email, period_id, "DaGui_PH", 1)
                        st.rerun()

# ==============================================================================
# MAIN ROUTING
# ==============================================================================
def main():
    if 'user' not in st.session_state:
        login_page()
    else:
        role = st.session_state['user']['role']
        
        with st.sidebar:
            st.markdown(f"### 👤 {st.session_state['user']['name']}")
            st.caption(f"Vai trò: {role}")
            
            st.divider()
            st.write("📅 **Chọn Đợt (Học kỳ):**")
            
            periods_map = get_periods_map(role)
            
            if periods_map:
                selected_period_name = st.selectbox("Danh sách đợt:", list(periods_map.keys()))
                selected_period_id = periods_map[selected_period_name]
            else:
                st.warning("Chưa có Đợt nào khả dụng.")
                selected_period_id = None
            
            st.divider()
            if st.button("Đăng xuất"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        if selected_period_id:
            if role == 'Admin': admin_dashboard(selected_period_id)
            elif role == 'GiaoVien': teacher_dashboard(selected_period_id)
            elif role == 'HocSinh': student_dashboard(selected_period_id)
            elif role == 'PhuHuynh': parent_dashboard(selected_period_id)
        else:
            if role == 'Admin':
                admin_dashboard(0)
            else:
                st.info("Hiện không có đợt nhập liệu nào đang mở.")

if __name__ == "__main__":
    main()
