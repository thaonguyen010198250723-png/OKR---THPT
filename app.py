import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import unicodedata
from fpdf import FPDF
import time
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io
import matplotlib.pyplot as plt

# ==============================================================================
# CẤU HÌNH TRANG & GIAO DIỆN
# ==============================================================================
st.set_page_config(
    page_title="Hệ thống Quản lý OKR (V7 - Optimized)",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #fcfcfc; }
    .stButton>button { background-color: #FF8C00; color: white; border-radius: 5px; border: none; }
    .stButton>button:hover { background-color: #e07b00; color: white; }
    h1, h2, h3 { color: #E65100; }
    .status-badge {
        display: inline-block; padding: 5px 10px; border-radius: 15px;
        font-size: 0.8rem; font-weight: bold; text-align: center; min-width: 80px;
    }
    .badge-green { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .badge-red { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .badge-yellow { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
    .badge-grey { background-color: #e2e3e5; color: #383d41; border: 1px solid #d6d8db; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# KẾT NỐI GOOGLE SHEETS
# ==============================================================================
SHEET_ID = "14E2JfVyOhGMa7T1VA44F31IaPMWIVIPRApo4B-ipDLk"

@st.cache_resource
def init_connection():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(st.secrets["service_account"]["info"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Lỗi kết nối API: {e}")
        return None

def get_worksheet(sheet_name):
    client = init_connection()
    if not client: return None
    try:
        sh = client.open_by_key(SHEET_ID)
        return sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        # Tự động tạo tab nếu thiếu
        sh = client.open_by_key(SHEET_ID)
        ws = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
        # Headers mặc định
        headers = {
            "Users": ["Email", "Password", "HoTen", "VaiTro", "TenLop"],
            "Classes": ["TenLop", "EmailGVCN", "SiSo"],
            "Periods": ["ID", "TenDot", "TrangThai"],
            "Relationships": ["Email_HocSinh", "Email_PhuHuynh"],
            "OKRs": ["ID", "Email_HocSinh", "ID_Dot", "MucTieu", "KetQuaThenChot", "TienDo", "TrangThai", "NhanXet_GV", "NhanXet_PH", "MinhChung", "TargetValue", "ActualValue", "Unit", "DeleteRequest"],
            "FinalReviews": ["Email_HocSinh", "ID_Dot", "NhanXet_GV", "NhanXet_PH", "DaGui_PH"]
        }
        if sheet_name in headers:
            ws.append_row(headers[sheet_name])
            if sheet_name == "Users":
                ws.append_row(["admin@school.com", "123", "Quản Trị Viên", "Admin", ""])
        return ws
    except Exception as e:
        st.error(f"Lỗi truy cập dữ liệu: {e}")
        return None

# ==============================================================================
# XỬ LÝ DỮ LIỆU (OPTIMIZED)
# ==============================================================================

@st.cache_data(ttl=10)
def load_data(sheet_name):
    """Đọc dữ liệu với caching để giảm tải API"""
    ws = get_worksheet(sheet_name)
    if not ws: return pd.DataFrame()
    try:
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Xử lý kiểu dữ liệu số
        numeric_cols = {
            "OKRs": ['ID', 'ID_Dot', 'TargetValue', 'ActualValue', 'DeleteRequest'],
            "Periods": ['ID'],
            "Classes": ['SiSo'],
            "FinalReviews": ['ID_Dot', 'DaGui_PH']
        }
        
        if sheet_name in numeric_cols and not df.empty:
            for col in numeric_cols[sheet_name]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Fix tên cột cũ Users
        if sheet_name == "Users":
            if 'ClassID' in df.columns and 'TenLop' not in df.columns:
                df = df.rename(columns={'ClassID': 'TenLop'})
            if 'TenLop' not in df.columns: df['TenLop'] = ""
            
        return df
    except Exception as e:
        # st.warning(f"Đang tải lại... {e}")
        return pd.DataFrame()

def batch_add_records(sheet_name, rows_data):
    """
    [QUAN TRỌNG] Fix lỗi 429: Thêm nhiều dòng cùng lúc bằng 1 lệnh API duy nhất.
    """
    ws = get_worksheet(sheet_name)
    if ws and rows_data:
        try:
            ws.append_rows(rows_data, value_input_option='USER_ENTERED')
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"Lỗi Batch Import: {e}. Vui lòng thử lại sau 30 giây.")
            return False
    return False

def update_cell_value(sheet_name, match_col, match_val, update_col, update_val, match_col_2=None, match_val_2=None):
    """Cập nhật 1 ô dữ liệu"""
    ws = get_worksheet(sheet_name)
    if not ws: return
    try:
        # Tìm dòng cần sửa
        # Logic: Đọc toàn bộ dữ liệu, tìm index trong Python (đỡ tốn quota find), rồi update
        data = ws.get_all_records()
        
        # Mapping cột thực tế trong sheet
        header = ws.row_values(1)
        try:
            col_idx = header.index(update_col) + 1
        except ValueError:
            return # Không tìm thấy cột update

        row_idx = -1
        # Xử lý mapping tên cột Users cũ
        real_match_col = "ClassID" if sheet_name == "Users" and match_col == "TenLop" and "ClassID" in header else match_col

        for i, row in enumerate(data):
            val1 = str(row.get(real_match_col, ''))
            is_match = False
            
            if match_col_2:
                val2 = str(row.get(match_col_2, ''))
                if val1 == str(match_val) and val2 == str(match_val_2):
                    is_match = True
            else:
                if val1 == str(match_val):
                    is_match = True
            
            if is_match:
                row_idx = i + 2 # Header là 1, index bắt đầu 0 -> +2
                break
        
        if row_idx != -1:
            ws.update_cell(row_idx, col_idx, update_val)
            st.cache_data.clear()
    except Exception as e:
        st.error(f"Lỗi cập nhật: {e}")

def delete_record(sheet_name, match_col, match_val):
    ws = get_worksheet(sheet_name)
    if not ws: return
    try:
        cell = ws.find(str(match_val), in_column=ws.find(match_col).col)
        if cell:
            ws.delete_rows(cell.row)
            st.cache_data.clear()
    except: pass

def get_next_id(sheet_name):
    df = load_data(sheet_name)
    if df.empty or 'ID' not in df.columns: return 1
    return int(df['ID'].max()) + 1

def cascading_email_update(old_email, new_email):
    """
    [TÍNH NĂNG MỚI] Cập nhật Email đồng bộ trên tất cả các bảng.
    Quy trình: Users -> Relationships -> OKRs -> FinalReviews
    """
    try:
        # 1. Update Users
        update_cell_value("Users", "Email", old_email, "Email", new_email)
        
        # Các bảng khác có thể có nhiều dòng, cần dùng batch update hoặc findall
        # Tuy nhiên để an toàn và đơn giản, ta dùng logic tìm và thay thế từng bảng
        # (Lưu ý: Nếu dữ liệu quá lớn > 2000 dòng/bảng, cần tối ưu hơn nữa)
        
        tables_to_update = [
            ("Relationships", ["Email_HocSinh", "Email_PhuHuynh"]),
            ("OKRs", ["Email_HocSinh"]),
            ("FinalReviews", ["Email_HocSinh"])
        ]
        
        for table, cols in tables_to_update:
            ws = get_worksheet(table)
            if not ws: continue
            
            # Lấy tất cả cells
            # Cách tối ưu: dùng findAll của gspread
            for col_name in cols:
                try:
                    # Tìm cột index
                    header = ws.row_values(1)
                    if col_name in header:
                        col_idx = header.index(col_name) + 1
                        # Tìm các ô chứa old_email trong cột đó
                        cells = ws.findall(old_email, in_column=col_idx)
                        # Batch update các cells đó
                        if cells:
                            for cell in cells:
                                cell.value = new_email
                            ws.update_cells(cells)
                except Exception as ex:
                    print(f"Skip table {table}: {ex}")

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi cập nhật đồng bộ: {e}")
        return False

# ==============================================================================
# CÁC HÀM HỖ TRỢ KHÁC
# ==============================================================================
def calculate_percent(actual, target):
    try:
        return round((float(actual) / float(target) * 100), 1) if float(target) != 0 else 0
    except: return 0

def get_rank(percent):
    if percent >= 80: return "Tốt", "green"
    elif percent >= 65: return "Khá", "blue"
    elif percent >= 50: return "Đạt", "orange"
    return "Chưa đạt", "red"

def create_docx(student_name, class_name, period_name, okr_df, review_gv, review_ph):
    doc = Document()
    doc.add_heading('BÁO CÁO KẾT QUẢ OKR', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f'Họ tên: {student_name} | Lớp: {class_name}')
    doc.add_paragraph(f'Đợt: {period_name} | Ngày: {time.strftime("%d/%m/%Y")}')
    
    doc.add_heading('1. Chi tiết Mục tiêu', level=1)
    if not okr_df.empty:
        table = doc.add_table(rows=1, cols=5)
        table.style = 'Table Grid'
        hdr = table.rows[0].cells
        for i, t in enumerate(['Mục Tiêu', 'Kết Quả (KR)', 'Target', 'Actual', '%']):
            hdr[i].text = t
        
        total = 0
        for _, row in okr_df.iterrows():
            cells = table.add_row().cells
            cells[0].text = str(row['MucTieu'])
            cells[1].text = str(row['KetQuaThenChot'])
            cells[2].text = f"{row['TargetValue']} {row['Unit']}"
            cells[3].text = f"{row['ActualValue']} {row['Unit']}"
            pct = calculate_percent(row['ActualValue'], row['TargetValue'])
            cells[4].text = f"{pct}%"
            total += pct
        
        avg = round(total / len(okr_df), 1)
        rank, _ = get_rank(avg)
        doc.add_paragraph(f'\nTrung bình: {avg}% - Xếp loại: {rank}')
    
    doc.add_heading('2. Nhận xét', level=1)
    doc.add_paragraph(f"GVCN: {review_gv if review_gv else '---'}")
    doc.add_paragraph(f"Phụ huynh: {review_ph if review_ph else '---'}")
    
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

def get_periods_map(role):
    df = load_data("Periods")
    if df.empty or 'TrangThai' not in df.columns: return {}
    if role != 'Admin': df = df[df['TrangThai'] == 'Mo']
    return dict(zip(df['TenDot'], df['ID']))

def change_password_ui(email):
    with st.expander("🔐 Đổi mật khẩu"):
        with st.form("change_pass"):
            p1 = st.text_input("Mật khẩu mới", type="password")
            p2 = st.text_input("Xác nhận", type="password")
            if st.form_submit_button("Lưu"):
                if p1 == p2 and p1:
                    update_cell_value("Users", "Email", email, "Password", p1)
                    st.success("Thành công!")
                else: st.error("Mật khẩu không khớp.")

# ==============================================================================
# DASHBOARD LOGIC
# ==============================================================================

def login_page():
    st.markdown("<h2 style='text-align: center;'>🔐 Đăng Nhập</h2>", unsafe_allow_html=True)
    with st.form("login"):
        email = st.text_input("Email")
        pwd = st.text_input("Mật khẩu", type="password")
        if st.form_submit_button("Đăng nhập"):
            df = load_data("Users")
            if df.empty:
                st.error("Lỗi kết nối CSDL.")
                return
            df['Password'] = df['Password'].astype(str)
            user = df[(df['Email'] == email) & (df['Password'] == str(pwd))]
            if not user.empty:
                u = user.iloc[0]
                st.session_state['user'] = {
                    'email': u['Email'], 'name': u['HoTen'], 
                    'role': u['VaiTro'], 'ten_lop': u.get('TenLop', '')
                }
                st.rerun()
            else: st.error("Sai thông tin.")

# --- ADMIN ---
def admin_dashboard(period_id):
    st.header("🛠️ Admin Dashboard")
    change_password_ui(st.session_state['user']['email'])
    
    tab1, tab2, tab3 = st.tabs(["Thống kê Lớp", "Quản lý User", "Quản lý Đợt"])
    
    with tab1:
        st.subheader(f"📊 Thống kê - Đợt ID: {period_id}")
        classes = load_data("Classes")
        
        if not classes.empty:
            # Prepare Data for Statistics
            reviews = load_data("FinalReviews")
            okrs = load_data("OKRs")
            users = load_data("Users")
            
            stats = []
            for _, cl in classes.iterrows():
                ten_lop = cl.get('TenLop', '')
                siso = int(cl.get('SiSo', 0))
                
                # Get Students in Class
                if not users.empty:
                    hs_list = users[users['TenLop'] == ten_lop]['Email'].tolist()
                else:
                    hs_list = []
                
                # Count OKRs
                okr_count = 0
                approved_count = 0
                
                if hs_list:
                    # Count Total OKRs created by students in this class for this period
                    if not okrs.empty:
                        okr_count = okrs[
                            (okrs['ID_Dot'] == period_id) & 
                            (okrs['Email_HocSinh'].isin(hs_list))
                        ].shape[0]
                    
                    # Count Students Approved (Final Review exists)
                    if not reviews.empty:
                        approved_count = reviews[
                            (reviews['ID_Dot'] == period_id) & 
                            (reviews['Email_HocSinh'].isin(hs_list)) & 
                            (reviews['NhanXet_GV'] != "")
                        ].shape[0]
                
                stats.append({
                    "Lớp": ten_lop,
                    "GVCN": cl.get('EmailGVCN', ''),
                    "Sĩ số": siso,
                    "Tổng OKR": okr_count,
                    "HS Đã Duyệt": f"{approved_count}/{len(hs_list) if hs_list else 0}"
                })
            
            st.dataframe(pd.DataFrame(stats))
            
            # Chart
            if stats:
                df_chart = pd.DataFrame(stats)
                if not df_chart.empty:
                    st.bar_chart(df_chart.set_index("Lớp")[["Tổng OKR"]])

        # Tạo lớp
        st.divider()
        with st.form("create_class"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Tên Lớp")
            gv = c2.text_input("Email GVCN")
            ss = c3.number_input("Sĩ số", 30)
            if st.form_submit_button("Tạo Lớp"):
                try:
                    add_record("Classes", [name, gv, ss])
                    # Auto create GV account
                    all_u = load_data("Users")
                    if all_u.empty or gv not in all_u['Email'].values:
                        add_record("Users", [gv, "123", f"GV {name}", "GiaoVien", ""])
                    st.success("Xong!")
                    st.rerun()
                except Exception as e: st.error(str(e))

    with tab2: # Manage Users
        search = st.text_input("Tìm Email:")
        if search:
            u = load_data("Users")
            if not u.empty:
                res = u[u['Email'] == search]
                st.write(res)
                if not res.empty and st.button("Reset Pass 123"):
                    update_cell_value("Users", "Email", search, "Password", "123")
                    st.success("Đã reset.")

    with tab3: # Periods
        periods = load_data("Periods")
        for _, row in periods.iterrows():
            c1, c2 = st.columns([4, 1])
            is_open = row.get('TrangThai') == 'Mo'
            toggle = c1.toggle(f"{row['TenDot']}", value=is_open, key=f"p_{row['ID']}")
            if toggle != is_open:
                update_cell_value("Periods", "ID", row['ID'], "TrangThai", "Mo" if toggle else "Khoa")
                st.rerun()
            if c2.button("🗑️", key=f"del_p_{row['ID']}"):
                delete_record("Periods", "ID", row['ID'])
                st.rerun()
        
        with st.form("add_p"):
            pn = st.text_input("Tên đợt")
            if st.form_submit_button("Thêm"):
                nid = get_next_id("Periods")
                add_record("Periods", [nid, pn, "Mo"])
                st.rerun()

# --- TEACHER ---
def teacher_dashboard(period_id):
    user_email = st.session_state['user']['email']
    st.header(f"🍎 Giáo Viên: {st.session_state['user']['name']}")
    change_password_ui(user_email)
    
    classes = load_data("Classes")
    if classes.empty: return
    my_class = classes[classes['EmailGVCN'] == user_email]
    if my_class.empty:
        st.warning("Bạn chưa được phân công lớp.")
        return
    class_name = my_class.iloc[0]['TenLop']
    st.info(f"Lớp: {class_name}")

    tab1, tab2 = st.tabs(["Danh sách & Duyệt", "Quản lý HS (Import/Sửa)"])

    # Load Data Once
    users = load_data("Users")
    all_okrs = load_data("OKRs")
    all_reviews = load_data("FinalReviews")
    
    students = users[users['TenLop'] == class_name] if not users.empty and 'TenLop' in users.columns else pd.DataFrame()

    with tab1:
        st.subheader("📋 Tiến độ lớp")
        if students.empty:
            st.write("Chưa có học sinh.")
        else:
            # Metrics
            submitted_count = 0
            for _, hs in students.iterrows():
                if not all_okrs.empty:
                    has_okr = not all_okrs[(all_okrs['Email_HocSinh'] == hs['Email']) & (all_okrs['ID_Dot'] == period_id)].empty
                    if has_okr: submitted_count += 1
            
            m1, m2 = st.columns(2)
            m1.metric("Tổng số HS", len(students))
            m2.metric("Đã nộp OKR", f"{submitted_count}/{len(students)}")
            st.progress(submitted_count/len(students) if len(students) > 0 else 0)

            # Table Header
            c = st.columns([0.5, 2, 1.5, 1.5, 1])
            c[0].markdown("**STT**")
            c[1].markdown("**Họ Tên**")
            c[2].markdown("**Trạng thái L1**")
            c[3].markdown("**Trạng thái L2**")
            
            # Loop students (Reset index 1..N)
            for idx, (_, hs) in enumerate(students.iterrows(), 1):
                hs_email = hs['Email']
                
                # Filter Data
                hs_okrs = all_okrs[(all_okrs['Email_HocSinh'] == hs_email) & (all_okrs['ID_Dot'] == period_id)] if not all_okrs.empty else pd.DataFrame()
                
                # Logic Status L1
                if hs_okrs.empty:
                    s1, b1 = "Chưa tạo", "badge-red"
                else:
                    if not hs_okrs[hs_okrs['TrangThai'] == 'ChoDuyet'].empty:
                        s1, b1 = "Chờ duyệt", "badge-yellow"
                    else:
                        s1, b1 = "Đã duyệt", "badge-green"
                
                # Logic Status L2
                has_rev = False
                if not all_reviews.empty:
                    rev = all_reviews[(all_reviews['Email_HocSinh'] == hs_email) & (all_reviews['ID_Dot'] == period_id)]
                    if not rev.empty and rev.iloc[0]['NhanXet_GV']: has_rev = True
                s2, b2 = ("Đã xong", "badge-green") if has_rev else ("Chưa xong", "badge-grey")
                
                # Check delete request
                has_del = False
                if not hs_okrs.empty and not hs_okrs[hs_okrs['DeleteRequest'] == 1].empty:
                    has_del = True

                with st.container():
                    cols = st.columns([0.5, 2, 1.5, 1.5, 1])
                    cols[0].write(f"{idx}")
                    name_display = hs['HoTen'] + (" ⚠️" if has_del else "")
                    cols[1].write(name_display)
                    cols[2].markdown(f'<span class="status-badge {b1}">{s1}</span>', unsafe_allow_html=True)
                    cols[3].markdown(f'<span class="status-badge {b2}">{s2}</span>', unsafe_allow_html=True)
                    
                    if cols[4].button("Chi tiết", key=f"v_{hs_email}"):
                        st.session_state['selected_hs'] = hs.to_dict()
                        st.rerun()

            st.divider()
            
            # --- DETAIL VIEW ---
            if 'selected_hs' in st.session_state:
                curr = st.session_state['selected_hs']
                st.markdown(f"### 📝 Đang xem: {curr['HoTen']}")
                
                # --- [TÍNH NĂNG MỚI] SỬA EMAIL ---
                with st.expander("🛠️ Chỉnh sửa thông tin học sinh (Cẩn thận)"):
                    with st.form("edit_hs_email"):
                        new_e = st.text_input("Email học sinh", value=curr['Email'])
                        new_n = st.text_input("Họ tên", value=curr['HoTen'])
                        if st.form_submit_button("Lưu & Cập nhật Đồng bộ"):
                            if new_e != curr['Email']:
                                # Check duplicate
                                if new_e in users['Email'].values:
                                    st.error("Email mới đã tồn tại!")
                                else:
                                    if cascading_email_update(curr['Email'], new_e):
                                        update_cell_value("Users", "Email", new_e, "HoTen", new_n)
                                        st.success("Đã cập nhật Email và đồng bộ dữ liệu!")
                                        st.session_state['selected_hs']['Email'] = new_e # Update session
                                        time.sleep(1)
                                        st.rerun()
                            elif new_n != curr['HoTen']:
                                update_cell_value("Users", "Email", curr['Email'], "HoTen", new_n)
                                st.success("Đã cập nhật tên.")
                                st.rerun()

                # OKR LIST
                hs_okrs = all_okrs[(all_okrs['Email_HocSinh'] == curr['Email']) & (all_okrs['ID_Dot'] == period_id)] if not all_okrs.empty else pd.DataFrame()
                
                if hs_okrs.empty:
                    st.warning("Chưa có OKR.")
                else:
                    for i, row in hs_okrs.iterrows():
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([4, 2, 2])
                            if row['DeleteRequest'] == 1:
                                st.error("⚠️ Yêu cầu xóa")
                            
                            c1.markdown(f"**O:** {row['MucTieu']}")
                            c1.text(f"KR: {row['KetQuaThenChot']}")
                            c2.metric("Target", f"{row['TargetValue']} {row['Unit']}")
                            c2.metric("Actual", f"{row['ActualValue']} {row['Unit']}")
                            
                            with c3:
                                if row['TrangThai'] == 'ChoDuyet':
                                    if st.button("✅ Duyệt", key=f"a_{row['ID']}"):
                                        update_cell_value("OKRs", "ID", row['ID'], "TrangThai", "DaDuyetMucTieu")
                                        st.rerun()
                                if row['DeleteRequest'] == 1:
                                    if st.button("🗑️ Đồng ý xóa", key=f"d_{row['ID']}"):
                                        delete_record("OKRs", "ID", row['ID'])
                                        st.rerun()

                    # Final Review
                    st.write("---")
                    gv_cmt, ph_cmt = "", ""
                    if not all_reviews.empty:
                        r_row = all_reviews[(all_reviews['Email_HocSinh'] == curr['Email']) & (all_reviews['ID_Dot'] == period_id)]
                        if not r_row.empty:
                            gv_cmt = r_row.iloc[0]['NhanXet_GV']
                            ph_cmt = r_row.iloc[0]['NhanXet_PH']
                    
                    if ph_cmt: st.info(f"Phụ huynh: {ph_cmt}")
                    
                    with st.form("final_rev"):
                        txt = st.text_area("Nhận xét GV", value=gv_cmt)
                        if st.form_submit_button("Lưu đánh giá"):
                            upsert_final_review(curr['Email'], period_id, "NhanXet_GV", txt)
                            st.success("Đã lưu!")

    with tab2:
        st.subheader("Quản lý Học sinh")
        
        # --- [FIX LỖI 429] BATCH IMPORT ---
        with st.expander("📥 Import Excel (Batch Upload - Chống lỗi 429)"):
            upl = st.file_uploader("Chọn file .xlsx", type=['xlsx'])
            if upl:
                try:
                    df_up = pd.read_excel(upl)
                    
                    # 1. Get existing emails to avoid duplicates
                    existing_emails = set(users['Email'].tolist()) if not users.empty else set()
                    
                    new_users = []
                    new_rels = []
                    
                    count = 0
                    for _, r in df_up.iterrows():
                        e = str(r['Email']).strip()
                        n = str(r['HoTen']).strip()
                        
                        if e and e not in existing_emails:
                            # Users structure: Email, Password, HoTen, VaiTro, TenLop
                            new_users.append([e, "123", n, "HocSinh", class_name])
                            existing_emails.add(e)
                            count += 1
                            
                            if 'EmailPH' in r and pd.notna(r['EmailPH']):
                                ph = str(r['EmailPH']).strip()
                                new_rels.append([e, ph])
                                # Add Parent account if not exist? logic skipped for simplicity, focus on batch
                    
                    if new_users:
                        batch_add_records("Users", new_users)
                    if new_rels:
                        batch_add_records("Relationships", new_rels)
                        
                    st.success(f"Đã thêm {count} học sinh bằng lệnh Batch!")
                    
                except Exception as e:
                    st.error(f"Lỗi: {e}")

# --- STUDENT ---
def student_dashboard(period_id):
    user = st.session_state['user']
    st.header(f"🎒 {user['name']}")
    change_password_ui(user['email'])
    
    with st.expander("➕ Thêm OKR"):
        with st.form("add_okr"):
            mt = st.text_input("Mục tiêu")
            kr = st.text_input("Kết quả then chốt")
            c1, c2 = st.columns(2)
            tar = c1.number_input("Target", 0.1)
            unit = c2.text_input("Đơn vị", "Điểm")
            if st.form_submit_button("Lưu"):
                nid = get_next_id("OKRs")
                # ID, Email, ID_Dot, MT, KR, Progress, Status, GVCmt, PHCmt, Proof, Target, Actual, Unit, DelReq
                add_record("OKRs", [nid, user['email'], period_id, mt, kr, 0, 'ChoDuyet', '', '', '', tar, 0, unit, 0])
                st.rerun()

    st.divider()
    all_okrs = load_data("OKRs")
    my_okrs = all_okrs[(all_okrs['Email_HocSinh'] == user['email']) & (all_okrs['ID_Dot'] == period_id)] if not all_okrs.empty else pd.DataFrame()
    
    if my_okrs.empty:
        st.info("Chưa có dữ liệu.")
    else:
        for _, row in my_okrs.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 2, 2])
                c1.markdown(f"**{row['MucTieu']}** - {row['KetQuaThenChot']}")
                status = row['TrangThai']
                if row['DeleteRequest'] == 1: status += " (Chờ xóa)"
                c1.caption(status)
                
                c2.metric("Tiến độ", f"{row['ActualValue']}/{row['TargetValue']}")
                
                # Logic Update
                with c3:
                    with st.popover("Báo cáo"):
                        with st.form(f"u_{row['ID']}"):
                            val = st.number_input("Đạt:", value=float(row['ActualValue']))
                            if st.form_submit_button("Lưu"):
                                update_cell_value("OKRs", "ID", row['ID'], "ActualValue", val)
                                st.rerun()
                    
                    # Logic Delete
                    if row['TrangThai'] == 'ChoDuyet':
                        if st.button("🗑️ Xóa ngay", key=f"d_{row['ID']}"):
                            delete_record("OKRs", "ID", row['ID'])
                            st.rerun()
                    elif row['DeleteRequest'] == 0:
                        if st.button("❌ Xin xóa", key=f"r_{row['ID']}"):
                            update_cell_value("OKRs", "ID", row['ID'], "DeleteRequest", 1)
                            st.rerun()

    # Reviews & Chart
    st.divider()
    reviews = load_data("FinalReviews")
    if not reviews.empty:
        rev = reviews[(reviews['Email_HocSinh'] == user['email']) & (reviews['ID_Dot'] == period_id)]
        if not rev.empty:
            st.info(f"Giáo viên: {rev.iloc[0]['NhanXet_GV']}")
            st.success(f"Gia đình: {rev.iloc[0]['NhanXet_PH']}")

# --- PARENT ---
def parent_dashboard(period_id):
    user = st.session_state['user']
    st.header("👨‍👩‍👧‍👦 Phụ Huynh")
    
    rels = load_data("Relationships")
    if rels.empty: return
    
    child = rels[rels['Email_PhuHuynh'] == user['email']]
    if child.empty:
        st.warning("Chưa liên kết con.")
        return
        
    child_email = child.iloc[0]['Email_HocSinh']
    
    # View Child OKR
    okrs = load_data("OKRs")
    child_okrs = okrs[(okrs['Email_HocSinh'] == child_email) & (okrs['ID_Dot'] == period_id)] if not okrs.empty else pd.DataFrame()
    
    if not child_okrs.empty:
        st.dataframe(child_okrs[['MucTieu', 'KetQuaThenChot', 'TargetValue', 'ActualValue', 'TrangThai']])
        
        # Add Comment
        reviews = load_data("FinalReviews")
        curr_cmt = ""
        if not reviews.empty:
            r = reviews[(reviews['Email_HocSinh'] == child_email) & (reviews['ID_Dot'] == period_id)]
            if not r.empty: curr_cmt = r.iloc[0]['NhanXet_PH']
            
        with st.form("ph_cmt"):
            txt = st.text_area("Ý kiến gia đình", value=curr_cmt)
            if st.form_submit_button("Gửi"):
                upsert_final_review(child_email, period_id, "NhanXet_PH", txt)
                upsert_final_review(child_email, period_id, "DaGui_PH", 1)
                st.success("Đã gửi!")

# ==============================================================================
# MAIN APP
# ==============================================================================
def main():
    if 'user' not in st.session_state:
        login_page()
    else:
        role = st.session_state['user']['role']
        with st.sidebar:
            st.write(f"Xin chào, **{st.session_state['user']['name']}**")
            if st.button("Đăng xuất"):
                del st.session_state['user']
                st.rerun()
            
            st.divider()
            # Period Selector
            periods = load_data("Periods")
            p_map = {}
            if not periods.empty:
                if role != 'Admin':
                    periods = periods[periods['TrangThai'] == 'Mo']
                if 'TenDot' in periods.columns:
                    p_map = dict(zip(periods['TenDot'], periods['ID']))
            
            p_id = None
            if p_map:
                p_name = st.selectbox("Chọn Đợt", list(p_map.keys()))
                p_id = p_map[p_name]
            else:
                st.warning("Chưa có đợt hoạt động.")

        if p_id:
            if role == 'Admin': admin_dashboard(p_id)
            elif role == 'GiaoVien': teacher_dashboard(p_id)
            elif role == 'HocSinh': student_dashboard(p_id)
            elif role == 'PhuHuynh': parent_dashboard(p_id)
        elif role == 'Admin':
            admin_dashboard(0) # Allow admin to access to create periods

if __name__ == "__main__":
    main()
