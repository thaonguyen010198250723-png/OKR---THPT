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
    page_title="Hệ thống Quản lý OKR Trường học (V5)",
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
    .student-row {
        padding: 10px;
        border-bottom: 1px solid #eee;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
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

        # 5. Bảng OKRs
        c.execute('''CREATE TABLE IF NOT EXISTS OKRs (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Email_HocSinh TEXT,
            ID_Dot INTEGER,
            MucTieu TEXT,
            KetQuaThenChot TEXT,
            TienDo INTEGER,
            TrangThai TEXT, 
            NhanXet_GV TEXT,
            NhanXet_PH TEXT,
            MinhChung TEXT
        )''')

        # === MIGRATION: Thêm cột mới ===
        try: c.execute("ALTER TABLE OKRs ADD COLUMN TargetValue REAL DEFAULT 0")
        except: pass
        try: c.execute("ALTER TABLE OKRs ADD COLUMN ActualValue REAL DEFAULT 0")
        except: pass
        try: c.execute("ALTER TABLE OKRs ADD COLUMN Unit TEXT DEFAULT ''")
        except: pass
        try: c.execute("ALTER TABLE OKRs ADD COLUMN DeleteRequest INTEGER DEFAULT 0")
        except: pass

        # 6. Bảng FinalReviews
        c.execute('''CREATE TABLE IF NOT EXISTS FinalReviews (
            Email_HocSinh TEXT,
            ID_Dot INTEGER,
            NhanXet_GV TEXT,
            NhanXet_PH TEXT,
            DaGui_PH INTEGER DEFAULT 0,
            PRIMARY KEY (Email_HocSinh, ID_Dot)
        )''')

        # SEED DATA
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
                    conn = get_connection()
                    conn.execute("UPDATE Users SET Password=? WHERE Email=?", (new_pass, email))
                    conn.commit()
                    conn.close()
                    st.success("Đổi mật khẩu thành công!")
                else:
                    st.error("Mật khẩu không khớp.")

def get_periods_map(role):
    """
    Lấy danh sách đợt.
    - Admin: Lấy tất cả.
    - GV, HS, PH: Chỉ lấy đợt 'Mo'.
    """
    conn = get_connection()
    if role == 'Admin':
        df = pd.read_sql("SELECT ID, TenDot, TrangThai FROM Periods", conn)
    else:
        df = pd.read_sql("SELECT ID, TenDot, TrangThai FROM Periods WHERE TrangThai='Mo'", conn)
    conn.close()
    if df.empty: return {}
    return dict(zip(df['TenDot'], df['ID']))

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
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM Users WHERE Email=? AND Password=?", (email, password))
            user = c.fetchone()
            conn.close()
            if user:
                st.session_state['user'] = {'email': user[0], 'name': user[2], 'role': user[3], 'class_id': user[4]}
                st.rerun()
            else:
                st.error("Sai Email hoặc mật khẩu.")

# --- 1. ADMIN DASHBOARD ---
def admin_dashboard(period_id):
    st.header("🛠️ Dashboard Quản Trị Viên")
    conn = get_connection()
    change_password_ui(st.session_state['user']['email'])

    tab1, tab2, tab3 = st.tabs(["Quản lý Lớp & Thống kê", "Quản lý User", "Quản lý Đợt"])

    # TAB 1: DANH SÁCH LỚP & THỐNG KÊ THEO ĐỢT
    with tab1:
        st.subheader(f"📊 Thống kê Lớp học - Đợt ID: {period_id}")
        
        # Lấy danh sách lớp
        classes = pd.read_sql("SELECT * FROM Classes", conn)
        
        if classes.empty:
            st.info("Chưa có lớp học nào.")
        else:
            stats_data = []
            for _, cl in classes.iterrows():
                siso = cl['SiSo']
                q_approved = f"""
                    SELECT COUNT(DISTINCT FinalReviews.Email_HocSinh)
                    FROM FinalReviews 
                    JOIN Users ON FinalReviews.Email_HocSinh = Users.Email
                    WHERE Users.ClassID = '{cl['ID']}' AND FinalReviews.ID_Dot = {period_id} 
                    AND FinalReviews.NhanXet_GV IS NOT NULL AND FinalReviews.NhanXet_GV != ''
                """
                approved_count = pd.read_sql(q_approved, conn).iloc[0,0]
                pct_approved = round((approved_count / siso * 100), 1) if siso > 0 else 0
                
                stats_data.append({
                    "ID Lớp": cl['ID'],
                    "Tên Lớp": cl['TenLop'],
                    "GVCN": cl['EmailGVCN'],
                    "Sĩ Số": siso,
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
                        gen_id = f"{c_name}_{int(time.time())}"
                        try:
                            conn.execute("INSERT INTO Classes (ID, TenLop, EmailGVCN, SiSo) VALUES (?,?,?,?)", 
                                         (gen_id, c_name, c_gv, c_siso))
                            cursor = conn.cursor()
                            cursor.execute("SELECT 1 FROM Users WHERE Email=?", (c_gv,))
                            if not cursor.fetchone():
                                conn.execute("INSERT INTO Users (Email, Password, HoTen, VaiTro) VALUES (?, ?, ?, 'GiaoVien')",
                                             (c_gv, '123', f"GV ({c_name})"))
                            conn.commit()
                            st.success(f"Đã tạo lớp {c_name}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi: {e}")

        with col_b:
            st.write("###### Danh sách kích hoạt")
            for _, cl in classes.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"**{cl['TenLop']}** - GV: {cl['EmailGVCN']}")
                    if c2.button("🚀 Cấp TK", key=f"grant_{cl['ID']}"):
                        conn.execute("UPDATE Users SET Password='123' WHERE Email=?", (cl['EmailGVCN'],))
                        conn.commit()
                        st.toast(f"Đã kích hoạt tài khoản cho GV: {cl['EmailGVCN']} (Pass: 123)")

    with tab2:
        st.subheader("Quản lý User")
        search = st.text_input("Tìm Email:")
        if search:
            u = pd.read_sql("SELECT * FROM Users WHERE Email=?", conn, params=(search,))
            st.write(u)
            if not u.empty and st.button("Reset Pass"):
                conn.execute("UPDATE Users SET Password='123' WHERE Email=?", (search,))
                conn.commit()
                st.success("Đã reset về 123")

    with tab3:
        st.subheader("Quản lý Đợt")
        periods = pd.read_sql("SELECT * FROM Periods", conn)
        for i, row in periods.iterrows():
            c_tog, c_del = st.columns([4, 1])
            with c_tog:
                is_open = row['TrangThai'] == 'Mo'
                toggle = st.toggle(f"{row['TenDot']} (ID: {row['ID']})", value=is_open, key=f"p_{row['ID']}")
                new_st = 'Mo' if toggle else 'Khoa'
                if new_st != row['TrangThai']:
                    conn.execute("UPDATE Periods SET TrangThai=? WHERE ID=?", (new_st, row['ID']))
                    conn.commit()
                    st.rerun()
            with c_del:
                if st.button("🗑️", key=f"del_p_{row['ID']}"):
                    conn.execute("DELETE FROM Periods WHERE ID=?", (row['ID'],))
                    conn.commit()
                    st.warning(f"Đã xóa đợt: {row['TenDot']}")
                    st.rerun()
        
        with st.form("new_period"):
            p_name = st.text_input("Tên đợt mới")
            if st.form_submit_button("Thêm"):
                conn.execute("INSERT INTO Periods (TenDot, TrangThai) VALUES (?, 'Mo')", (p_name,))
                conn.commit()
                st.rerun()
    
    conn.close()

# --- 2. TEACHER DASHBOARD ---
def teacher_dashboard(period_id):
    user_email = st.session_state['user']['email']
    st.header(f"🍎 Giáo Viên: {st.session_state['user']['name']}")
    change_password_ui(user_email)
    conn = get_connection()
    
    my_class = pd.read_sql("SELECT * FROM Classes WHERE EmailGVCN=?", conn, params=(user_email,))
    if my_class.empty:
        st.warning("Bạn chưa được phân công lớp.")
        conn.close()
        return

    class_id = my_class.iloc[0]['ID']
    st.info(f"Lớp: {my_class.iloc[0]['TenLop']} (ID: {class_id}) - Đợt làm việc ID: {period_id}")

    tab1, tab2 = st.tabs(["Danh sách Học sinh (List View)", "Import Excel"])

    with tab1:
        st.subheader("📋 Trạng thái OKR Học sinh")
        
        # Danh sách HS
        students = pd.read_sql("SELECT Email, HoTen FROM Users WHERE ClassID=?", conn, params=(class_id,))
        
        if students.empty:
            st.write("Lớp chưa có học sinh.")
        else:
            # Header
            cols = st.columns([0.5, 2, 1.5, 1.5, 1])
            cols[0].markdown("**STT**")
            cols[1].markdown("**Họ Tên**")
            cols[2].markdown("**Duyệt Lần 1 (Mục Tiêu)**")
            cols[3].markdown("**Duyệt Lần 2 (Tổng Kết)**")
            cols[4].markdown("**Hành động**")
            
            for idx, hs in students.iterrows():
                # Logic xác định trạng thái Lần 1 (Mục tiêu)
                okrs = pd.read_sql("SELECT TrangThai, DeleteRequest FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(hs['Email'], period_id))
                
                l1_status = ""
                l1_badge = ""
                
                if okrs.empty:
                    l1_status = "Chưa tạo"
                    l1_badge = "badge-red"
                else:
                    pending_count = okrs[okrs['TrangThai'] == 'ChoDuyet'].shape[0]
                    if pending_count > 0:
                        l1_status = "Chờ duyệt"
                        l1_badge = "badge-yellow"
                    else:
                        l1_status = "Đã duyệt"
                        l1_badge = "badge-green"

                # Logic xác định trạng thái Lần 2 (Tổng kết)
                fr = pd.read_sql("SELECT * FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=? AND NhanXet_GV IS NOT NULL AND NhanXet_GV != ''", 
                                         conn, params=(hs['Email'], period_id))
                has_final_review = not fr.empty
                
                l2_status = "Đã xong" if has_final_review else "Chưa xong"
                l2_badge = "badge-green" if has_final_review else "badge-grey"
                
                # Check yêu cầu xóa
                has_del_req = not okrs[okrs['DeleteRequest'] == 1].empty
                
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
                        st.session_state['selected_hs'] = hs
                        st.rerun()

            st.divider()
            
            # --- PHẦN CHI TIẾT HỌC SINH ---
            if 'selected_hs' in st.session_state:
                hs_curr = st.session_state['selected_hs']
                st.markdown(f"### 📝 Chi tiết: {hs_curr['HoTen']}")
                
                df_okr = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(hs_curr['Email'], period_id))
                
                if df_okr.empty:
                    st.warning("Học sinh này chưa nhập OKR nào.")
                else:
                    for i, row in df_okr.iterrows():
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([4, 2, 2])
                            
                            bg_color = ""
                            if row['DeleteRequest'] == 1:
                                st.error(f"⚠️ Học sinh yêu cầu xóa mục tiêu: {row['MucTieu']} - {row['KetQuaThenChot']}")
                            
                            c1.markdown(f"**O:** {row['MucTieu']}")
                            c1.text(f"KR: {row['KetQuaThenChot']}")
                            
                            c2.metric("Mục tiêu/Đạt", f"{row['TargetValue']} / {row['ActualValue']} {row['Unit']}")
                            pct = calculate_percent(row['ActualValue'], row['TargetValue'])
                            c2.progress(min(pct/100, 1.0))
                            
                            with c3:
                                st.write(f"TT: {row['TrangThai']}")
                                
                                # Xử lý duyệt Lần 1
                                if row['TrangThai'] == 'ChoDuyet':
                                    if st.button("✅ Duyệt Mục Tiêu", key=f"app_{row['ID']}"):
                                        conn.execute("UPDATE OKRs SET TrangThai='DaDuyetMucTieu' WHERE ID=?", (row['ID'],))
                                        conn.commit()
                                        st.rerun()
                                
                                # Xử lý Yêu cầu xóa
                                if row['DeleteRequest'] == 1:
                                    if st.button("🗑️ Chấp thuận xóa", key=f"del_{row['ID']}"):
                                        conn.execute("DELETE FROM OKRs WHERE ID=?", (row['ID'],))
                                        conn.commit()
                                        st.rerun()

                    # Duyệt Tổng Kết (Lần 2) & Xem ý kiến gia đình
                    st.write("---")
                    
                    fr = pd.read_sql("SELECT * FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(hs_curr['Email'], period_id))
                    old_cmt_gv = fr.iloc[0]['NhanXet_GV'] if not fr.empty else ""
                    cmt_ph = fr.iloc[0]['NhanXet_PH'] if not fr.empty else None
                    
                    # Hiển thị Ý kiến gia đình
                    if cmt_ph:
                        st.info(f"🏠 **Ý kiến gia đình:** {cmt_ph}")
                    else:
                        st.caption("🏠 Gia đình chưa gửi ý kiến.")

                    # Form GV nhập nhận xét
                    st.write("**Đánh giá cuối kỳ (Final Review):**")
                    with st.form("teacher_review"):
                        cmt = st.text_area("Nhận xét giáo viên:", value=old_cmt_gv)
                        if st.form_submit_button("Lưu & Hoàn tất Duyệt Lần 2"):
                            conn.execute("INSERT OR REPLACE INTO FinalReviews (Email_HocSinh, ID_Dot, NhanXet_GV) VALUES (?,?,?)",
                                         (hs_curr['Email'], period_id, cmt))
                            # Giữ lại NhanXet_PH nếu có (logic REPLACE của SQLite có thể xóa cột khác nếu không khai báo đủ)
                            # Nên dùng UPDATE hoặc INSERT OR IGNORE + UPDATE
                            # Safe Update Logic:
                            cursor = conn.cursor()
                            cursor.execute("SELECT 1 FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", (hs_curr['Email'], period_id))
                            if cursor.fetchone():
                                conn.execute("UPDATE FinalReviews SET NhanXet_GV=? WHERE Email_HocSinh=? AND ID_Dot=?", (cmt, hs_curr['Email'], period_id))
                            else:
                                conn.execute("INSERT INTO FinalReviews (Email_HocSinh, ID_Dot, NhanXet_GV) VALUES (?,?,?)", (hs_curr['Email'], period_id, cmt))
                                
                            conn.commit()
                            st.success("Đã lưu nhận xét!")

    with tab2:
        st.subheader("Import Excel")
        st.caption("Cột bắt buộc: Email, HoTen, EmailPH")
        upl = st.file_uploader("Upload Excel", type=['xlsx'])
        if upl:
            try:
                df = pd.read_excel(upl)
                count = 0
                for _, r in df.iterrows():
                    # Thêm HS
                    conn.execute("INSERT OR IGNORE INTO Users (Email, Password, HoTen, VaiTro, ClassID) VALUES (?,?,?,?,?)",
                                 (r['Email'], '123', r['HoTen'], 'HocSinh', class_id))
                    # Thêm PH
                    if pd.notna(r['EmailPH']):
                        conn.execute("INSERT OR IGNORE INTO Users (Email, Password, HoTen, VaiTro) VALUES (?,?,'Phụ Huynh','PhuHuynh')",
                                     (str(r['EmailPH']), '123'))
                        conn.execute("INSERT OR REPLACE INTO Relationships VALUES (?,?)", (r['Email'], str(r['EmailPH'])))
                    count += 1
                conn.commit()
                st.success(f"Đã import {count} dòng.")
            except Exception as e:
                st.error(str(e))
                
    conn.close()

# --- 3. STUDENT DASHBOARD ---
def student_dashboard(period_id):
    user_email = st.session_state['user']['email']
    st.header(f"🎒 Góc Học Tập: {st.session_state['user']['name']}")
    change_password_ui(user_email)
    conn = get_connection()
    
    # 1. NHẬP LIỆU
    with st.expander("➕ Thêm Mục tiêu & Kết quả (OKR)", expanded=True):
        with st.form("student_add"):
            st.caption("Bạn có thể nhập nhiều KR cho cùng 1 Mục tiêu bằng cách gõ lại tên Mục tiêu đó.")
            mt = st.text_input("Mục tiêu (Objective) - VD: Học sinh giỏi", placeholder="Nhập tên mục tiêu lớn...")
            kr = st.text_input("Kết quả then chốt (KR) - VD: Toán > 8.0")
            c1, c2 = st.columns(2)
            target = c1.number_input("Con số mục tiêu (Target)", min_value=0.1)
            unit = c2.text_input("Đơn vị (VD: Điểm, Bài...)", value="Điểm")
            
            if st.form_submit_button("Lưu OKR"):
                if mt and kr:
                    conn.execute("""
                        INSERT INTO OKRs (Email_HocSinh, ID_Dot, MucTieu, KetQuaThenChot, TargetValue, Unit, ActualValue, TrangThai, DeleteRequest)
                        VALUES (?,?,?,?,?,?,0,'ChoDuyet',0)
                    """, (user_email, period_id, mt, kr, target, unit))
                    conn.commit()
                    st.success("Đã thêm!")
                    st.rerun()

    # 2. HIỂN THỊ (GROUP BY OBJECTIVE)
    st.divider()
    st.subheader("📋 OKR của tôi")
    
    df_okrs = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(user_email, period_id))
    
    if df_okrs.empty:
        st.info("Chưa có dữ liệu.")
    else:
        # Group by Objective
        unique_objs = df_okrs['MucTieu'].unique()
        
        total_pct = 0
        count_kr = 0
        
        for obj in unique_objs:
            st.markdown(f"#### 🎯 O: {obj}")
            
            # Get KRs for this Objective
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
                    
                    # Update Result Popover
                    with c3:
                        with st.popover("Báo cáo KQ"):
                            with st.form(f"upd_{row['ID']}"):
                                new_val = st.number_input("Đạt được:", value=float(row['ActualValue']))
                                if st.form_submit_button("Lưu"):
                                    conn.execute("UPDATE OKRs SET ActualValue=? WHERE ID=?", (new_val, row['ID']))
                                    conn.commit()
                                    st.rerun()
                    
                    # Delete Request
                    with c4:
                        if row['TrangThai'] == 'ChoDuyet':
                            if st.button("🗑️", key=f"del_{row['ID']}"):
                                conn.execute("DELETE FROM OKRs WHERE ID=?", (row['ID'],))
                                conn.commit()
                                st.rerun()
                        else:
                            if row['DeleteRequest'] == 0:
                                if st.button("Xin xóa", key=f"req_{row['ID']}"):
                                    conn.execute("UPDATE OKRs SET DeleteRequest=1 WHERE ID=?", (row['ID'],))
                                    conn.commit()
                                    st.rerun()
                            else:
                                st.caption("Đang chờ xóa")

        # 3. TỔNG KẾT
        st.divider()
        final_score = round(total_pct / count_kr, 1) if count_kr > 0 else 0
        rank, color = get_rank(final_score)
        st.markdown(f"### 🏁 Tổng kết: <span style='color:{color}'>{final_score}% - {rank}</span>", unsafe_allow_html=True)
        
        # Xem Nhận xét (GV & PH)
        fr = pd.read_sql("SELECT * FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(user_email, period_id))
        
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

    conn.close()

# --- 4. PARENT DASHBOARD ---
def parent_dashboard(period_id):
    user_email = st.session_state['user']['email']
    st.header("👨‍👩‍👧‍👦 Phụ Huynh")
    change_password_ui(user_email)
    conn = get_connection()
    
    child = pd.read_sql("SELECT Email_HocSinh FROM Relationships WHERE Email_PhuHuynh=?", conn, params=(user_email,))
    if child.empty:
        st.warning("Chưa liên kết học sinh.")
        conn.close()
        return
        
    child_email = child.iloc[0]['Email_HocSinh']
    child_info = pd.read_sql("SELECT HoTen, ClassID FROM Users WHERE Email=?", conn, params=(child_email,))
    st.info(f"Con: {child_info.iloc[0]['HoTen']} - Lớp: {child_info.iloc[0]['ClassID']}")
    
    # Hiển thị OKR
    df_okr = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(child_email, period_id))
    
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
        
        # Nhận xét
        st.divider()
        col1, col2 = st.columns(2)
        fr = pd.read_sql("SELECT * FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(child_email, period_id))
        
        with col1:
            st.write("**Giáo viên:**")
            if not fr.empty and fr.iloc[0]['NhanXet_GV']:
                st.info(fr.iloc[0]['NhanXet_GV'])
            else:
                st.text("Chưa có nhận xét.")
                
        with col2:
            st.write("**Gia đình:**")
            cmt_ph = fr.iloc[0]['NhanXet_PH'] if not fr.empty else ""
            sent = fr.iloc[0]['DaGui_PH'] if not fr.empty and pd.notna(fr.iloc[0]['DaGui_PH']) else 0
            
            if sent == 1:
                st.success(f"Đã gửi: {cmt_ph}")
            else:
                with st.form("ph_cmt"):
                    txt = st.text_area("Ý kiến:", value=cmt_ph)
                    if st.form_submit_button("Gửi"):
                        # Insert/Update logic safe
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1 FROM FinalReviews WHERE Email_HocSinh=? AND ID_Dot=?", (child_email, period_id))
                        if cursor.fetchone():
                            conn.execute("UPDATE FinalReviews SET NhanXet_PH=?, DaGui_PH=1 WHERE Email_HocSinh=? AND ID_Dot=?", (txt, child_email, period_id))
                        else:
                            conn.execute("INSERT INTO FinalReviews (Email_HocSinh, ID_Dot, NhanXet_PH, DaGui_PH) VALUES (?,?,?,1)", 
                                         (child_email, period_id, txt))
                        conn.commit()
                        st.rerun()
    conn.close()

# ==============================================================================
# MAIN ROUTING
# ==============================================================================
def main():
    if 'user' not in st.session_state:
        login_page()
    else:
        role = st.session_state['user']['role']
        
        # SIDEBAR GLOBAL SETTINGS
        with st.sidebar:
            st.markdown(f"### 👤 {st.session_state['user']['name']}")
            st.caption(f"Vai trò: {role}")
            
            st.divider()
            st.write("📅 **Chọn Đợt (Học kỳ):**")
            
            # Lọc đợt theo vai trò
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

        # ROUTING
        if selected_period_id:
            if role == 'Admin': admin_dashboard(selected_period_id)
            elif role == 'GiaoVien': teacher_dashboard(selected_period_id)
            elif role == 'HocSinh': student_dashboard(selected_period_id)
            elif role == 'PhuHuynh': parent_dashboard(selected_period_id)
        else:
            if role == 'Admin':
                admin_dashboard(0) # Cho vào để tạo đợt
            else:
                st.info("Hiện không có đợt nhập liệu nào đang mở.")

if __name__ == "__main__":
    main()
