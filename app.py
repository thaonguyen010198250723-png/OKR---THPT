import streamlit as st
import pandas as pd
import sqlite3
import unicodedata
from fpdf import FPDF
import time

# ==============================================================================
# CẤU HÌNH TRANG & GIAO DIỆN (THEME)
# ==============================================================================
st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường học (V2)",
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
    .status-box { padding: 10px; border-radius: 5px; margin-bottom: 10px; font-weight: bold; }
    .status-green { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .status-red { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .big-score { font-size: 24px; font-weight: bold; color: #E65100; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# XỬ LÝ DATABASE (SQLITE) & MIGRATION
# ==============================================================================
DB_FILE = "school_okr.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_and_migrate_db():
    """Khởi tạo và tự động cập nhật cấu trúc bảng mới"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # 1. Bảng Users
        c.execute('''CREATE TABLE IF NOT EXISTS Users (
            Email TEXT PRIMARY KEY,
            Password TEXT,
            HoTen TEXT,
            VaiTro TEXT,
            ClassID TEXT
        )''')

        # 2. Bảng Classes
        c.execute('''CREATE TABLE IF NOT EXISTS Classes (
            ID TEXT PRIMARY KEY,
            TenLop TEXT,
            EmailGVCN TEXT,
            SiSo INTEGER
        )''')

        # 3. Bảng Periods
        c.execute('''CREATE TABLE IF NOT EXISTS Periods (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            TenDot TEXT,
            TrangThai TEXT
        )''')

        # 4. Bảng Relationships
        c.execute('''CREATE TABLE IF NOT EXISTS Relationships (
            Email_HocSinh TEXT,
            Email_PhuHuynh TEXT,
            PRIMARY KEY (Email_HocSinh, Email_PhuHuynh)
        )''')

        # 5. Bảng OKRs (Cũ) - Sẽ alter thêm cột nếu thiếu
        c.execute('''CREATE TABLE IF NOT EXISTS OKRs (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Email_HocSinh TEXT,
            ID_Dot INTEGER,
            MucTieu TEXT,
            KetQuaThenChot TEXT,
            TienDo INTEGER, -- Vẫn giữ để tương thích, nhưng logic mới sẽ dùng Actual/Target
            TrangThai TEXT, 
            NhanXet_GV TEXT, -- Giữ lại cho dữ liệu cũ, logic mới dùng bảng FinalReviews
            NhanXet_PH TEXT, -- Giữ lại cho dữ liệu cũ
            MinhChung TEXT
        )''')

        # === MIGRATION: Thêm cột mới cho tính năng V2 ===
        # Các cột: TargetValue (Mục tiêu số), ActualValue (Thực đạt), Unit (Đơn vị), DeleteRequest (Yêu cầu xóa)
        try:
            c.execute("ALTER TABLE OKRs ADD COLUMN TargetValue REAL DEFAULT 0")
        except: pass
        try:
            c.execute("ALTER TABLE OKRs ADD COLUMN ActualValue REAL DEFAULT 0")
        except: pass
        try:
            c.execute("ALTER TABLE OKRs ADD COLUMN Unit TEXT DEFAULT ''")
        except: pass
        try:
            c.execute("ALTER TABLE OKRs ADD COLUMN DeleteRequest INTEGER DEFAULT 0") -- 0: Không, 1: Có
        except: pass

        # 6. Bảng FinalReviews (MỚI): Lưu nhận xét cuối kỳ duy nhất
        c.execute('''CREATE TABLE IF NOT EXISTS FinalReviews (
            Email_HocSinh TEXT,
            ID_Dot INTEGER,
            NhanXet_GV TEXT,
            NhanXet_PH TEXT,
            DaGui_PH INTEGER DEFAULT 0, -- 0: Chưa gửi, 1: Đã gửi (Hiện xanh)
            PRIMARY KEY (Email_HocSinh, ID_Dot)
        )''')

        # SEED DATA (Nếu chưa có Admin)
        c.execute("SELECT * FROM Users WHERE Email='admin@school.com'")
        if not c.fetchone():
            users = [
                ('admin@school.com', '123', 'Quản Trị Viên', 'Admin', None),
                ('gv1@school.com', '123', 'Cô Lan', 'GiaoVien', None),
                ('hs1@school.com', '123', 'Em An', 'HocSinh', '12A1')
            ]
            for u in users:
                c.execute("INSERT OR IGNORE INTO Users VALUES (?,?,?,?,?)", u)
            conn.commit()

        conn.close()
    except Exception as e:
        st.error(f"Lỗi khởi tạo DB: {e}")

init_and_migrate_db()

# ==============================================================================
# TIỆN ÍCH (HELPER FUNCTIONS)
# ==============================================================================

def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', str(input_str))
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def calculate_percent(actual, target):
    """Tính % hoàn thành"""
    try:
        acc = float(actual)
        tar = float(target)
        if tar == 0: return 0
        return round((acc / tar) * 100, 1)
    except:
        return 0

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
                    conn = get_connection()
                    conn.execute("UPDATE Users SET Password=? WHERE Email=?", (new_pass, email))
                    conn.commit()
                    conn.close()
                    st.success("Đổi mật khẩu thành công!")
                else:
                    st.error("Mật khẩu không khớp hoặc để trống.")

# ==============================================================================
# LOGIC DASHBOARD CÁC VAI TRÒ
# ==============================================================================

def login_page():
    st.markdown("<h2 style='text-align: center;'>🔐 Đăng Nhập Hệ Thống OKR</h2>", unsafe_allow_html=True)
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Mật khẩu", type="password")
        submitted = st.form_submit_button("Đăng nhập")
        if submitted:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM Users WHERE Email=? AND Password=?", (email, password))
            user = c.fetchone()
            conn.close()
            if user:
                st.session_state['user'] = {'email': user[0], 'name': user[2], 'role': user[3], 'class_id': user[4]}
                st.success(f"Xin chào {user[2]}!")
                st.rerun()
            else:
                st.error("Email hoặc mật khẩu không đúng.")

# --- 1. ADMIN DASHBOARD ---
def admin_dashboard():
    st.header("🛠️ Dashboard Quản Trị Viên")
    conn = get_connection()
    change_password_ui(st.session_state['user']['email'])
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    n_gv = pd.read_sql("SELECT COUNT(*) FROM Users WHERE VaiTro='GiaoVien'", conn).iloc[0,0]
    n_hs = pd.read_sql("SELECT COUNT(*) FROM Users WHERE VaiTro='HocSinh'", conn).iloc[0,0]
    
    # Thống kê duyệt (OKR + Final Review)
    n_okr_approved = pd.read_sql("SELECT COUNT(*) FROM OKRs WHERE TrangThai IN ('DaDuyetMucTieu', 'HoanThanh')", conn).iloc[0,0]
    n_final_review = pd.read_sql("SELECT COUNT(*) FROM FinalReviews WHERE NhanXet_GV IS NOT NULL AND NhanXet_GV != ''", conn).iloc[0,0]
    
    col1.metric("Giáo Viên", n_gv)
    col2.metric("Học Sinh", n_hs)
    col3.metric("OKR Đã Duyệt", n_okr_approved)
    col4.metric("Đã Nhận Xét CK", n_final_review)

    tab1, tab2, tab3 = st.tabs(["Quản lý Lớp", "Quản lý User & Pass", "Quản lý Đợt"])

    # Tab 1: Quản lý Lớp (Logic Mới)
    with tab1:
        st.subheader("Danh sách Lớp học")
        df_classes = pd.read_sql("SELECT * FROM Classes", conn)
        
        # Display with Delete option
        for i, row in df_classes.iterrows():
            c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 1, 1])
            c1.write(f"**{row['ID']}**") # ID ẩn trong DB nhưng hiển thị cho rõ
            c2.write(row['TenLop'])
            c3.write(row['EmailGVCN'])
            c4.write(f"SS: {row['SiSo']}")
            if c5.button("🗑️ Xóa", key=f"del_class_{row['ID']}"):
                conn.execute("DELETE FROM Classes WHERE ID=?", (row['ID'],))
                conn.commit()
                st.warning(f"Đã xóa lớp {row['TenLop']}")
                st.rerun()
        
        st.divider()
        st.markdown("### Thêm Lớp Mới")
        with st.form("add_class_new"):
            # Bỏ nhập ID, tự sinh ID bằng tên lớp hoặc Timestamp
            c_name = st.text_input("Tên Lớp (VD: 12A1)")
            c_gv = st.text_input("Email GVCN")
            c_siso = st.number_input("Sĩ số", min_value=1)
            
            if st.form_submit_button("Tạo Lớp"):
                if c_name and c_gv:
                    # Tạo ID tự động dựa trên thời gian để tránh trùng
                    gen_id = f"{c_name}_{int(time.time())}"
                    try:
                        conn.execute("INSERT INTO Classes (ID, TenLop, EmailGVCN, SiSo) VALUES (?,?,?,?)", 
                                     (gen_id, c_name, c_gv, c_siso))
                        
                        # Tự động tạo TK GV nếu chưa có
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1 FROM Users WHERE Email=?", (c_gv,))
                        if not cursor.fetchone():
                            default_name = f"GV ({c_gv.split('@')[0]})"
                            conn.execute("INSERT INTO Users (Email, Password, HoTen, VaiTro) VALUES (?, ?, ?, 'GiaoVien')",
                                         (c_gv, '123', default_name))
                            st.info(f"Đã tạo tài khoản mới cho GV: {c_gv} (Pass: 123)")
                        
                        conn.commit()
                        st.success("Tạo lớp thành công")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
                else:
                    st.error("Vui lòng nhập Tên lớp và Email GV.")

    # Tab 2: Quản lý User & Reset Pass
    with tab2:
        st.subheader("Tra cứu & Reset Mật khẩu")
        search_email = st.text_input("Nhập Email cần tìm/reset:")
        if search_email:
            u_info = pd.read_sql("SELECT * FROM Users WHERE Email=?", conn, params=(search_email,))
            if not u_info.empty:
                st.write(u_info)
                new_p = st.text_input("Mật khẩu mới cho user này:", key="new_p_admin")
                if st.button("Cập nhật mật khẩu"):
                    conn.execute("UPDATE Users SET Password=? WHERE Email=?", (new_p, search_email))
                    conn.commit()
                    st.success("Đã reset mật khẩu.")
                
                if st.button("Xóa tài khoản này", type="primary"):
                     conn.execute("DELETE FROM Users WHERE Email=?", (search_email,))
                     conn.commit()
                     st.warning("Đã xóa user.")
                     st.rerun()
            else:
                st.warning("Không tìm thấy User.")

    # Tab 3: Quản lý Đợt
    with tab3:
        st.subheader("Quản lý Đợt OKR")
        df_periods = pd.read_sql("SELECT * FROM Periods", conn)
        for i, row in df_periods.iterrows():
            is_open = row['TrangThai'] == 'Mo'
            toggle = st.toggle(f"{row['TenDot']}", value=is_open, key=f"p_{row['ID']}")
            new_status = 'Mo' if toggle else 'Khoa'
            if new_status != row['TrangThai']:
                conn.execute("UPDATE Periods SET TrangThai=? WHERE ID=?", (new_status, row['ID']))
                conn.commit()
                st.rerun()
        
        with st.expander("Tạo đợt mới"):
            new_period_name = st.text_input("Tên đợt (VD: HK1 2026)")
            if st.button("Thêm đợt"):
                if new_period_name:
                    conn.execute("INSERT INTO Periods (TenDot, TrangThai) VALUES (?, 'Mo')", (new_period_name,))
                    conn.commit()
                    st.rerun()

    conn.close()

# --- 2. TEACHER DASHBOARD ---
def teacher_dashboard():
    user_email = st.session_state['user']['email']
    st.header(f"🍎 Giáo Viên: {st.session_state['user']['name']}")
    change_password_ui(user_email)
    conn = get_connection()
    
    # Get Class
    my_class = pd.read_sql("SELECT * FROM Classes WHERE EmailGVCN=?", conn, params=(user_email,))
    if my_class.empty:
        st.warning("Bạn chưa được phân công lớp.")
        return
    class_id = my_class.iloc[0]['ID']
    class_name = my_class.iloc[0]['TenLop']
    st.info(f"Lớp: {class_name} | Sĩ số: {my_class.iloc[0]['SiSo']}")
    
    tab1, tab2 = st.tabs(["Học Sinh & Nhập Excel", "Duyệt OKR & Tổng Kết"])
    
    # Tab 1: QL Học sinh
    with tab1:
        st.markdown("### Import danh sách HS từ Excel")
        st.caption("File Excel cần có các cột: 'Email', 'HoTen', 'EmailPH'")
        uploaded_file = st.file_uploader("Chọn file Excel", type=['xlsx'])
        if uploaded_file:
            try:
                df_upload = pd.read_excel(uploaded_file)
                # Check columns
                if set(['Email', 'HoTen', 'EmailPH']).issubset(df_upload.columns):
                    count_ok = 0
                    for _, row in df_upload.iterrows():
                        # Add HS
                        conn.execute("INSERT OR IGNORE INTO Users (Email, Password, HoTen, VaiTro, ClassID) VALUES (?,?,?,?,?)",
                                     (row['Email'], "123", row['HoTen'], "HocSinh", class_id))
                        # Add PH
                        if pd.notna(row['EmailPH']):
                            conn.execute("INSERT OR IGNORE INTO Users (Email, Password, HoTen, VaiTro) VALUES (?,?,'Phụ Huynh','PhuHuynh')",
                                         (str(row['EmailPH']), "123"))
                            conn.execute("INSERT OR REPLACE INTO Relationships VALUES (?,?)", (row['Email'], str(row['EmailPH'])))
                        count_ok += 1
                    conn.commit()
                    st.success(f"Đã nhập {count_ok} học sinh thành công!")
                else:
                    st.error("File Excel thiếu cột bắt buộc: Email, HoTen, EmailPH")
            except Exception as e:
                st.error(f"Lỗi đọc file: {e}")

        st.subheader("Danh sách lớp")
        df_hs = pd.read_sql("SELECT Email, HoTen FROM Users WHERE ClassID=?", conn, params=(class_id,))
        st.dataframe(df_hs)

    # Tab 2: Duyệt OKR
    with tab2:
        # Lấy đợt đang mở
        active_period = pd.read_sql("SELECT * FROM Periods WHERE TrangThai='Mo'", conn)
        if active_period.empty:
            st.warning("Không có đợt nào đang mở.")
        else:
            p_id = active_period.iloc[0]['ID']
            st.markdown(f"**Đợt: {active_period.iloc[0]['TenDot']}**")
            
            # 1. Danh sách tổng quan (Xanh/Đỏ)
            st.markdown("### 📋 Danh sách trạng thái")
            col_list = st.columns(5) # Grid view
            df_hs_list = pd.read_sql("SELECT Email, HoTen FROM Users WHERE ClassID=?", conn, params=(class_id,))
            
            selected_hs = None
            
            # Hiển thị grid status
            cols_status = st.columns(4)
            for idx, hs in df_hs_list.iterrows():
                # Check if created OKR
                has_okr = pd.read_sql("SELECT COUNT(*) FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(hs['Email'], p_id)).iloc[0,0] > 0
                color = "green" if has_okr else "red"
                btn_label = f"{'🟢' if has_okr else '🔴'} {hs['HoTen']}"
                
                if cols_status[idx % 4].button(btn_label, key=f"btn_hs_{idx}"):
                    st.session_state['selected_hs_email'] = hs['Email']
                    st.session_state['selected_hs_name'] = hs['HoTen']
                    st.rerun()

            st.divider()
            
            # 2. Chi tiết HS được chọn
            if 'selected_hs_email' in st.session_state:
                curr_email = st.session_state['selected_hs_email']
                curr_name = st.session_state['selected_hs_name']
                
                st.markdown(f"### 📝 Chi tiết: {curr_name}")
                
                # Load OKRs
                df_okr = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(curr_email, p_id))
                
                if df_okr.empty:
                    st.info("Học sinh chưa tạo OKR nào.")
                else:
                    # DUYỆT LẦN 1: MỤC TIÊU
                    st.markdown("#### Phần 1: Các mục tiêu & Kết quả")
                    
                    for i, row in df_okr.iterrows():
                        with st.container(border=True):
                            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                            c1.markdown(f"**MT:** {row['MucTieu']}")
                            c1.text(f"KR: {row['KetQuaThenChot']}")
                            c2.text(f"Target: {row['TargetValue']} {row['Unit']}")
                            c2.text(f"Đạt: {row['ActualValue']}")
                            
                            # Tính %
                            pct = calculate_percent(row['ActualValue'], row['TargetValue'])
                            c3.metric("Hoàn thành", f"{pct}%")
                            
                            # Logic Duyệt & Xóa
                            with c4:
                                st.caption(f"Trạng thái: {row['TrangThai']}")
                                
                                # Xử lý yêu cầu xóa
                                if row['DeleteRequest'] == 1:
                                    st.error("⚠️ HS Yêu cầu xóa")
                                    if st.button("Chấp thuận xóa", key=f"del_okr_{row['ID']}"):
                                        conn.execute("DELETE FROM OKRs WHERE ID=?", (row['ID'],))
                                        conn.commit()
                                        st.rerun()
                                
                                # Duyệt Mục Tiêu (Lần 1)
                                if row['TrangThai'] == 'ChoDuyet':
                                    if st.button("✅ Duyệt Mục Tiêu", key=f"app_goal_{row['ID']}"):
                                        conn.execute("UPDATE OKRs SET TrangThai='DaDuyetMucTieu' WHERE ID=?", (row['ID'],))
                                        conn.commit()
                                        st.rerun()

                    # DUYỆT LẦN 2: NHẬN XÉT CUỐI KỲ (FINAL REVIEW)
                    st.divider()
                    st.markdown("#### Phần 2: Đánh giá & Nhận xét cuối kỳ")
                    
                    # Lấy dữ liệu Final Review
                    fr = pd.read_sql("SELECT * FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(curr_email, p_id))
                    existing_cmt = fr.iloc[0]['NhanXet_GV'] if not fr.empty else ""
                    
                    # Form Nhận xét
                    with st.form("final_review_form"):
                        new_cmt = st.text_area("Nhận xét của Giáo viên (Tổng kết):", value=existing_cmt)
                        if st.form_submit_button("Lưu & Gửi Nhận xét"):
                            conn.execute("INSERT OR REPLACE INTO FinalReviews (Email_HocSinh, ID_Dot, NhanXet_GV) VALUES (?,?,?)", 
                                         (curr_email, p_id, new_cmt))
                            
                            # Cập nhật trạng thái OKR thành Hoàn Thành (Option)
                            conn.execute("UPDATE OKRs SET TrangThai='HoanThanh' WHERE Email_HocSinh=? AND ID_Dot=?", (curr_email, p_id))
                            conn.commit()
                            st.success("Đã lưu nhận xét cuối kỳ!")

    conn.close()

# --- 3. STUDENT DASHBOARD ---
def student_dashboard():
    user_email = st.session_state['user']['email']
    st.header(f"🎒 Góc Học Tập: {st.session_state['user']['name']}")
    change_password_ui(user_email)
    conn = get_connection()
    
    active_period = pd.read_sql("SELECT * FROM Periods WHERE TrangThai='Mo'", conn)
    
    if active_period.empty:
        st.warning("Chưa có đợt nhập liệu.")
    else:
        p_id = active_period.iloc[0]['ID']
        st.success(f"Đang mở: {active_period.iloc[0]['TenDot']}")
        
        # 1. FORM NHẬP OKR (Logic Mới: Objective -> KR -> Target -> Unit)
        with st.expander("➕ Thêm Mục tiêu Mới", expanded=False):
            with st.form("add_okr_v2"):
                st.markdown("Các kết quả then chốt (KR) sẽ được nhóm theo Tên mục tiêu.")
                mt = st.text_input("Tên Mục tiêu (Objective)", placeholder="Ví dụ: Đạt Học sinh Giỏi")
                kr = st.text_input("Kết quả then chốt (KR)", placeholder="Ví dụ: Điểm Toán > 8.0")
                col_a, col_b = st.columns(2)
                target = col_a.number_input("Mục tiêu số (Target)", min_value=0.0, step=0.1)
                unit = col_b.text_input("Đơn vị tính", placeholder="Điểm, %, Cuốn sách...")
                
                if st.form_submit_button("Lưu Mục tiêu"):
                    if mt and kr and target > 0:
                        conn.execute("""
                            INSERT INTO OKRs (Email_HocSinh, ID_Dot, MucTieu, KetQuaThenChot, TargetValue, Unit, ActualValue, TrangThai, DeleteRequest) 
                            VALUES (?, ?, ?, ?, ?, ?, 0, 'ChoDuyet', 0)
                        """, (user_email, p_id, mt, kr, target, unit))
                        conn.commit()
                        st.success("Đã thêm KR!")
                        st.rerun()
                    else:
                        st.error("Vui lòng nhập đầy đủ thông tin và Target > 0")

        # 2. DANH SÁCH & BÁO CÁO KẾT QUẢ
        st.divider()
        st.subheader("📋 Danh sách OKR của tôi")
        
        my_okrs = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(user_email, p_id))
        
        if my_okrs.empty:
            st.info("Bạn chưa có mục tiêu nào.")
        else:
            total_percent = 0
            count = 0
            
            # Nhóm theo Mục tiêu
            objectives = my_okrs['MucTieu'].unique()
            
            for obj in objectives:
                st.markdown(f"##### 🎯 {obj}")
                subset = my_okrs[my_okrs['MucTieu'] == obj]
                
                for _, row in subset.iterrows():
                    with st.container(border=True):
                        cols = st.columns([4, 2, 2, 2])
                        cols[0].write(f"- {row['KetQuaThenChot']}")
                        cols[0].caption(f"Mục tiêu: {row['TargetValue']} {row['Unit']}")
                        
                        # Logic Báo cáo kết quả
                        pct = calculate_percent(row['ActualValue'], row['TargetValue'])
                        cols[1].metric("Đạt", f"{row['ActualValue']} {row['Unit']}")
                        cols[2].metric("% Hoàn thành", f"{pct}%")
                        
                        total_percent += pct
                        count += 1
                        
                        # Action: Cập nhật kết quả hoặc Xóa
                        with cols[3]:
                            # Nút Cập nhật kết quả (Popover)
                            with st.popover("📝 Báo cáo"):
                                with st.form(f"update_res_{row['ID']}"):
                                    new_act = st.number_input("Kết quả đạt được:", value=float(row['ActualValue']))
                                    if st.form_submit_button("Lưu kết quả"):
                                        conn.execute("UPDATE OKRs SET ActualValue=? WHERE ID=?", (new_act, row['ID']))
                                        conn.commit()
                                        st.rerun()
                            
                            # Nút Xóa
                            if row['DeleteRequest'] == 1:
                                st.caption("⏳ Đang chờ xóa")
                            else:
                                if st.button("🗑️ Xóa", key=f"req_del_{row['ID']}"):
                                    # Nếu chưa duyệt -> Xóa luôn. Nếu đã duyệt -> Gửi yêu cầu
                                    if row['TrangThai'] == 'ChoDuyet':
                                        conn.execute("DELETE FROM OKRs WHERE ID=?", (row['ID'],))
                                        st.success("Đã xóa")
                                    else:
                                        conn.execute("UPDATE OKRs SET DeleteRequest=1 WHERE ID=?", (row['ID'],))
                                        st.warning("Đã gửi yêu cầu xóa cho GV")
                                    conn.commit()
                                    st.rerun()

            # 3. TỔNG KẾT & XẾP LOẠI
            st.divider()
            avg_score = round(total_percent / count, 1) if count > 0 else 0
            rank, color = get_rank(avg_score)
            
            c1, c2 = st.columns(2)
            c1.markdown(f"### Điểm Trung Bình: <span class='big-score'>{avg_score}%</span>", unsafe_allow_html=True)
            c2.markdown(f"### Xếp loại: <span style='color:{color}; font-size:24px; font-weight:bold'>{rank}</span>", unsafe_allow_html=True)

    conn.close()

# --- 4. PARENT DASHBOARD ---
def parent_dashboard():
    user_email = st.session_state['user']['email']
    st.header("👨‍👩‍👧‍👦 Phụ Huynh")
    change_password_ui(user_email)
    conn = get_connection()
    
    # Tìm con
    child = pd.read_sql("SELECT Email_HocSinh FROM Relationships WHERE Email_PhuHuynh=?", conn, params=(user_email,))
    
    if child.empty:
        st.warning("Chưa liên kết với học sinh.")
        return

    child_email = child.iloc[0]['Email_HocSinh']
    child_info = pd.read_sql("SELECT HoTen, ClassID FROM Users WHERE Email=?", conn, params=(child_email,))
    st.info(f"Con: **{child_info.iloc[0]['HoTen']}** - Lớp: {child_info.iloc[0]['ClassID']}")
    
    # Chọn Kỳ
    df_periods = pd.read_sql("SELECT * FROM Periods", conn)
    p_choice = st.selectbox("Chọn Đợt/Học Kỳ:", df_periods['TenDot'])
    p_id = df_periods[df_periods['TenDot'] == p_choice].iloc[0]['ID']
    
    # Hiển thị OKR & Kết quả
    st.subheader("Kết quả học tập của con")
    df_okr = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(child_email, p_id))
    
    if df_okr.empty:
        st.text("Chưa có dữ liệu cho kỳ này.")
    else:
        total = 0
        cnt = 0
        for _, row in df_okr.iterrows():
            pct = calculate_percent(row['ActualValue'], row['TargetValue'])
            total += pct
            cnt += 1
            st.markdown(f"- **{row['MucTieu']}** ({row['KetQuaThenChot']}): Đạt {row['ActualValue']}/{row['TargetValue']} {row['Unit']} -> **{pct}%**")
        
        avg = round(total/cnt, 1) if cnt > 0 else 0
        rank, color = get_rank(avg)
        st.markdown(f"#### 📊 Tổng kết: {avg}% - Xếp loại: <span style='color:{color}'>{rank}</span>", unsafe_allow_html=True)
        
        st.divider()
        
        # Phần Nhận xét (GV & PH) - Lấy từ bảng FinalReviews
        fr = pd.read_sql("SELECT * FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(child_email, p_id))
        
        col_gv, col_ph = st.columns(2)
        
        # Xem nhận xét GV
        with col_gv:
            st.markdown("### 👩‍🏫 Giáo viên nhận xét")
            gv_cmt = fr.iloc[0]['NhanXet_GV'] if not fr.empty and fr.iloc[0]['NhanXet_GV'] else "Chưa có nhận xét."
            st.info(gv_cmt)
            
        # PH nhận xét
        with col_ph:
            st.markdown("### 🏠 Ý kiến gia đình")
            ph_cmt_db = fr.iloc[0]['NhanXet_PH'] if not fr.empty else ""
            da_gui = fr.iloc[0]['DaGui_PH'] if not fr.empty and pd.notna(fr.iloc[0]['DaGui_PH']) else 0
            
            # Nếu đã gửi -> Hiện màu xanh
            if da_gui == 1:
                st.success(f"Đã gửi: {ph_cmt_db}")
                if st.button("Sửa ý kiến"):
                    conn.execute("UPDATE FinalReviews SET DaGui_PH=0 WHERE Email_HocSinh=? AND ID_Dot=?", (child_email, p_id))
                    conn.commit()
                    st.rerun()
            else:
                with st.form("ph_review"):
                    txt_ph = st.text_area("Nhập ý kiến:", value=ph_cmt_db)
                    if st.form_submit_button("Gửi ý kiến"):
                        conn.execute("INSERT OR REPLACE INTO FinalReviews (Email_HocSinh, ID_Dot, NhanXet_PH, DaGui_PH) VALUES (?,?,?, 1)", 
                                     (child_email, p_id, txt_ph))
                        # Giữ nguyên NhanXet_GV nếu đã có (SQL replace sẽ xóa cột kia nếu ko cẩn thận, nên dùng Update)
                        # Fix logic an toàn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1 FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", (child_email, p_id))
                        if cursor.fetchone():
                            conn.execute("UPDATE FinalReviews SET NhanXet_PH=?, DaGui_PH=1 WHERE Email_HocSinh=? AND ID_Dot=?", (txt_ph, child_email, p_id))
                        else:
                             conn.execute("INSERT INTO FinalReviews (Email_HocSinh, ID_Dot, NhanXet_PH, DaGui_PH) VALUES (?,?,?,1)", (child_email, p_id, txt_ph))
                        
                        conn.commit()
                        st.rerun()

    conn.close()

# ==============================================================================
# MAIN FLOW
# ==============================================================================
def main():
    if 'user' not in st.session_state:
        login_page()
    else:
        with st.sidebar:
            st.markdown(f"### 👤 {st.session_state['user']['name']}")
            st.caption(f"Vai trò: {st.session_state['user']['role']}")
            if st.button("Đăng xuất"):
                del st.session_state['user']
                if 'selected_hs_email' in st.session_state: del st.session_state['selected_hs_email']
                st.rerun()
            st.divider()
        
        role = st.session_state['user']['role']
        if role == 'Admin': admin_dashboard()
        elif role == 'GiaoVien': teacher_dashboard()
        elif role == 'HocSinh': student_dashboard()
        elif role == 'PhuHuynh': parent_dashboard()

if __name__ == "__main__":
    main()
