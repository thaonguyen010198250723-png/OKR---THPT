import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from fpdf import FPDF
import io
from datetime import datetime
import unicodedata

# ==============================================================================
# CẤU HÌNH TRANG & GIAO DIỆN (THEME)
# ==============================================================================
st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường học",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS cho màu Cam chủ đạo
st.markdown("""
<style>
    .stApp {
        background-color: #fcfcfc;
    }
    .stButton>button {
        background-color: #FF8C00;
        color: white;
        border-radius: 5px;
        border: none;
    }
    .stButton>button:hover {
        background-color: #e07b00;
        color: white;
    }
    h1, h2, h3 {
        color: #E65100;
    }
    .stProgress > div > div > div > div {
        background-color: #FF8C00;
    }
    .sidebar-content {
        background-color: #fff3e0;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# XỬ LÝ DATABASE (SQLITE)
# ==============================================================================
DB_FILE = "school_okr.db"

def init_db():
    """Khởi tạo cấu trúc bảng và dữ liệu mẫu"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # 1. Bảng Users (Thêm ClassID để map học sinh vào lớp)
        c.execute('''CREATE TABLE IF NOT EXISTS Users (
            Email TEXT PRIMARY KEY,
            Password TEXT,
            HoTen TEXT,
            VaiTro TEXT, -- Admin, GiaoVien, HocSinh, PhuHuynh
            ClassID TEXT -- Dùng cho HocSinh để biết thuộc lớp nào
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
            TrangThai TEXT -- 'Mo', 'Khoa'
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
            TrangThai TEXT, -- 'ChoDuyet', 'DaDuyet', 'TuChoi'
            NhanXet_GV TEXT,
            NhanXet_PH TEXT,
            MinhChung TEXT
        )''')

        # SEED DATA (Dữ liệu mẫu)
        # Kiểm tra xem đã có Admin chưa, nếu chưa thì insert toàn bộ
        c.execute("SELECT * FROM Users WHERE Email='admin@school.com'")
        if not c.fetchone():
            # Users
            users = [
                ('admin@school.com', '123', 'Quản Trị Viên', 'Admin', None),
                ('gv12a1@school.com', '123', 'Cô Lan (GVCN 12A1)', 'GiaoVien', None),
                ('gv10a5@school.com', '123', 'Thầy Hùng (GVCN 10A5)', 'GiaoVien', None),
                ('hs1@school.com', '123', 'Nguyễn Văn An', 'HocSinh', '12A1'),
                ('hs2@school.com', '123', 'Trần Thị Bích', 'HocSinh', '12A1'),
                ('ph1@school.com', '123', 'Bố em An', 'PhuHuynh', None),
                ('ph2@school.com', '123', 'Mẹ em Bích', 'PhuHuynh', None)
            ]
            c.executemany("INSERT INTO Users VALUES (?,?,?,?,?)", users)

            # Classes
            classes = [
                ('12A1', 'Lớp 12A1', 'gv12a1@school.com', 40),
                ('10A5', 'Lớp 10A5', 'gv10a5@school.com', 35)
            ]
            c.executemany("INSERT INTO Classes VALUES (?,?,?,?)", classes)

            # Periods
            c.execute("INSERT INTO Periods (TenDot, TrangThai) VALUES (?,?)", ('Học kỳ 1 Năm 2025-2026', 'Mo'))
            
            # Relationships
            rels = [
                ('hs1@school.com', 'ph1@school.com'),
                ('hs2@school.com', 'ph2@school.com')
            ]
            c.executemany("INSERT INTO Relationships VALUES (?,?)", rels)

            # OKRs mẫu cho hs1
            # Lấy ID đợt vừa tạo
            c.execute("SELECT ID FROM Periods LIMIT 1")
            period_id = c.fetchone()[0]
            okrs = [
                ('hs1@school.com', period_id, 'Đạt Học sinh Giỏi', 'Điểm TB các môn > 8.5', 90, 'ChoDuyet', '', '', ''),
                ('hs1@school.com', period_id, 'Cải thiện tiếng Anh', 'IELTS 6.5', 60, 'ChoDuyet', '', '', '')
            ]
            c.executemany("INSERT INTO OKRs (Email_HocSinh, ID_Dot, MucTieu, KetQuaThenChot, TienDo, TrangThai, NhanXet_GV, NhanXet_PH, MinhChung) VALUES (?,?,?,?,?,?,?,?,?)", okrs)
            
            conn.commit()
            print("Đã khởi tạo dữ liệu mẫu thành công!")

        conn.close()
    except Exception as e:
        st.error(f"Lỗi khởi tạo DB: {e}")

# Chạy khởi tạo DB ngay khi load
init_db()

def get_connection():
    return sqlite3.connect(DB_FILE)

# ==============================================================================
# TIỆN ÍCH (HELPER FUNCTIONS)
# ==============================================================================

def remove_accents(input_str):
    """Hàm loại bỏ dấu tiếng Việt để xuất PDF không bị lỗi font"""
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def create_pdf(student_name, okr_data):
    """Tạo file PDF báo cáo"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"BAO CAO OKR - {remove_accents(student_name)}", ln=1, align='C')
    pdf.ln(10)
    
    # Content
    pdf.set_font("Arial", size=12)
    for index, row in okr_data.iterrows():
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, txt=f"Muc Tieu {index + 1}: {remove_accents(row['MucTieu'])}", ln=1)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, txt=f"KR: {remove_accents(row['KetQuaThenChot'])}", ln=1)
        pdf.cell(0, 10, txt=f"Tien Do: {row['TienDo']}%", ln=1)
        pdf.cell(0, 10, txt=f"Nhan Xet GV: {remove_accents(row['NhanXet_GV'])}", ln=1)
        pdf.ln(5)
        
    return pdf.output(dest='S').encode('latin-1', 'ignore')

def ai_analyze_okr(text):
    """Giả lập AI phân tích"""
    text = text.lower()
    if "giỏi" in text or "xuất sắc" in text or "10" in text:
        return "🔥 Mục tiêu đầy tham vọng! Cần kế hoạch cụ thể."
    elif len(text) < 10:
        return "⚠️ Mục tiêu quá ngắn, hãy bổ sung chi tiết (S.M.A.R.T)."
    elif "cải thiện" in text or "nâng cao" in text:
        return "👍 Mục tiêu hướng tới sự phát triển tốt."
    else:
        return "📝 Mục tiêu ổn, hãy theo dõi sát sao."

# ==============================================================================
# CÁC TRANG CHỨC NĂNG (VIEWS)
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
                st.session_state['user'] = {
                    'email': user[0],
                    'name': user[2],
                    'role': user[3],
                    'class_id': user[4]
                }
                st.success(f"Xin chào {user[2]}!")
                st.rerun()
            else:
                st.error("Email hoặc mật khẩu không đúng.")

def admin_dashboard():
    st.header("🛠️ Dashboard Quản Trị Viên")
    conn = get_connection()
    
    # 1. Metrics
    col1, col2, col3 = st.columns(3)
    
    try:
        n_gv = pd.read_sql("SELECT COUNT(*) FROM Users WHERE VaiTro='GiaoVien'", conn).iloc[0,0]
        n_hs = pd.read_sql("SELECT COUNT(*) FROM Users WHERE VaiTro='HocSinh'", conn).iloc[0,0]
        n_okr = pd.read_sql("SELECT COUNT(*) FROM OKRs", conn).iloc[0,0]
        
        col1.metric("Tổng Giáo Viên", n_gv)
        col2.metric("Tổng Học Sinh", n_hs)
        col3.metric("Tổng OKRs", n_okr)
    except Exception as e:
        st.error(f"Lỗi tải thống kê: {e}")

    tab1, tab2, tab3 = st.tabs(["Quản lý Đợt", "Quản lý Lớp", "Thống kê Hiệu suất"])

    with tab1:
        st.subheader("Quản lý Đợt Nhập Liệu (Periods)")
        df_periods = pd.read_sql("SELECT * FROM Periods", conn)
        
        # Toggle Status
        for i, row in df_periods.iterrows():
            is_open = row['TrangThai'] == 'Mo'
            toggle = st.toggle(f"{row['TenDot']}", value=is_open, key=f"p_{row['ID']}")
            new_status = 'Mo' if toggle else 'Khoa'
            if new_status != row['TrangThai']:
                conn.execute("UPDATE Periods SET TrangThai=? WHERE ID=?", (new_status, row['ID']))
                conn.commit()
                st.rerun()
        
        with st.expander("Tạo đợt mới"):
            new_period_name = st.text_input("Tên đợt (VD: HK2 2026)")
            if st.button("Thêm đợt"):
                if new_period_name:
                    conn.execute("INSERT INTO Periods (TenDot, TrangThai) VALUES (?, 'Mo')", (new_period_name,))
                    conn.commit()
                    st.success("Đã thêm đợt mới!")
                    st.rerun()

    with tab2:
        st.subheader("Quản lý Lớp & Gán GVCN")
        df_classes = pd.read_sql("SELECT * FROM Classes", conn)
        st.dataframe(df_classes)
        
        with st.form("add_class"):
            c_id = st.text_input("Mã Lớp (VD: 11B2)")
            c_name = st.text_input("Tên Lớp")
            c_gv = st.text_input("Email GVCN")
            c_siso = st.number_input("Sĩ số", min_value=1)
            if st.form_submit_button("Tạo Lớp"):
                try:
                    conn.execute("INSERT INTO Classes VALUES (?,?,?,?)", (c_id, c_name, c_gv, c_siso))
                    conn.commit()
                    st.success("Tạo lớp thành công")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    with tab3:
        st.subheader("Thống kê hoàn thành OKR")
        # Logic: Số HS đã có ít nhất 1 OKR trong đợt mở / Sĩ số lớp
        active_period = pd.read_sql("SELECT ID FROM Periods WHERE TrangThai='Mo' LIMIT 1", conn)
        if not active_period.empty:
            p_id = active_period.iloc[0,0]
            
            # Get list of classes and calculate stats
            classes = pd.read_sql("SELECT * FROM Classes", conn)
            stats_data = []
            
            for _, cl in classes.iterrows():
                # Count unique students in this class who have submitted OKR for current period
                query = f"""
                    SELECT COUNT(DISTINCT OKRs.Email_HocSinh) 
                    FROM OKRs 
                    JOIN Users ON OKRs.Email_HocSinh = Users.Email
                    WHERE Users.ClassID = '{cl['ID']}' AND OKRs.ID_Dot = {p_id}
                """
                submitted_count = pd.read_sql(query, conn).iloc[0,0]
                percent = round((submitted_count / cl['SiSo']) * 100, 1) if cl['SiSo'] > 0 else 0
                stats_data.append({
                    "Lớp": cl['ID'],
                    "GVCN": cl['EmailGVCN'],
                    "Sĩ Số": cl['SiSo'],
                    "Đã Nộp": submitted_count,
                    "Hoàn Thành (%)": f"{percent}%"
                })
            
            st.table(pd.DataFrame(stats_data))
        else:
            st.info("Chưa có đợt nhập liệu nào đang mở.")

    conn.close()

def teacher_dashboard():
    user_email = st.session_state['user']['email']
    st.header(f"🍎 Khu vực Giáo Viên: {st.session_state['user']['name']}")
    
    conn = get_connection()
    
    # Identify Class
    my_class = pd.read_sql("SELECT * FROM Classes WHERE EmailGVCN=?", conn, params=(user_email,))
    
    if my_class.empty:
        st.warning("Bạn chưa được phân công chủ nhiệm lớp nào.")
        return

    class_id = my_class.iloc[0]['ID']
    st.info(f"Đang quản lý lớp: {class_id} - Sĩ số: {my_class.iloc[0]['SiSo']}")
    
    tab1, tab2, tab3 = st.tabs(["Học sinh & Phụ huynh", "Duyệt OKR", "Phân tích Lớp"])
    
    with tab1:
        st.subheader("Danh sách Học sinh")
        df_hs = pd.read_sql("SELECT Email, HoTen, ClassID FROM Users WHERE ClassID=?", conn, params=(class_id,))
        
        # Show data editor to map Parents
        st.dataframe(df_hs)
        
        with st.expander("Thêm Học sinh vào lớp"):
            with st.form("add_student"):
                s_email = st.text_input("Email HS")
                s_name = st.text_input("Họ tên HS")
                s_pass = "123" # Default
                s_parent = st.text_input("Email Phụ huynh (để liên kết)")
                
                if st.form_submit_button("Thêm"):
                    try:
                        # Add User
                        conn.execute("INSERT OR IGNORE INTO Users (Email, Password, HoTen, VaiTro, ClassID) VALUES (?,?,?,?,?)",
                                     (s_email, s_pass, s_name, 'HocSinh', class_id))
                        # Add Parent User if not exist
                        if s_parent:
                            conn.execute("INSERT OR IGNORE INTO Users (Email, Password, HoTen, VaiTro) VALUES (?,?,'Phụ Huynh','PhuHuynh')",
                                         (s_parent, s_pass))
                            # Add Relationship
                            conn.execute("INSERT OR REPLACE INTO Relationships VALUES (?,?)", (s_email, s_parent))
                        
                        conn.commit()
                        st.success("Đã thêm thành công!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")

    with tab2:
        st.subheader("Phê duyệt OKR")
        # Get OKRs of students in this class
        query_okr = f"""
            SELECT OKRs.ID, Users.HoTen, OKRs.MucTieu, OKRs.KetQuaThenChot, OKRs.TienDo, OKRs.TrangThai, OKRs.NhanXet_GV, OKRs.Email_HocSinh
            FROM OKRs 
            JOIN Users ON OKRs.Email_HocSinh = Users.Email
            WHERE Users.ClassID = '{class_id}'
        """
        df_okrs = pd.read_sql(query_okr, conn)
        
        if df_okrs.empty:
            st.info("Chưa có OKR nào được nộp.")
        else:
            for i, row in df_okrs.iterrows():
                with st.container(border=True):
                    cols = st.columns([3, 1, 2])
                    cols[0].markdown(f"**HS: {row['HoTen']}**")
                    cols[0].text(f"Mục tiêu: {row['MucTieu']}")
                    cols[0].text(f"KR: {row['KetQuaThenChot']}")
                    cols[1].metric("Tiến độ", f"{row['TienDo']}%")
                    cols[1].caption(f"Trạng thái: {row['TrangThai']}")
                    
                    # Actions
                    with cols[2]:
                        with st.form(f"approve_{row['ID']}"):
                            comment = st.text_area("Nhận xét", value=row['NhanXet_GV'] if row['NhanXet_GV'] else "")
                            c1, c2 = st.columns(2)
                            approved = c1.form_submit_button("✅ Duyệt")
                            
                            if approved:
                                conn.execute("UPDATE OKRs SET TrangThai='DaDuyet', NhanXet_GV=? WHERE ID=?", (comment, row['ID']))
                                conn.commit()
                                st.success("Đã duyệt!")
                                st.rerun()
                                
                        # Export PDF button outside form
                        if st.button("📄 Xuất PDF", key=f"pdf_{row['ID']}"):
                            # Get all OKRs for this student to print full report
                            student_okrs = df_okrs[df_okrs['Email_HocSinh'] == row['Email_HocSinh']]
                            pdf_bytes = create_pdf(row['HoTen'], student_okrs)
                            st.download_button(label="Tải xuống", 
                                               data=pdf_bytes, 
                                               file_name=f"OKR_{row['HoTen']}.pdf", 
                                               mime='application/pdf')

    with tab3:
        st.subheader("Trợ lý ảo & Phân tích")
        
        # Simple Chart
        status_counts = df_okrs['TrangThai'].value_counts()
        st.write("Tỷ lệ trạng thái OKR:")
        st.bar_chart(status_counts)
        
        # AI Assistant Simulation
        st.divider()
        st.markdown("#### 🤖 Trợ lý AI Phân tích Mục tiêu")
        sample_okr = st.selectbox("Chọn OKR để phân tích", df_okrs['MucTieu'].unique())
        if sample_okr:
            analysis = ai_analyze_okr(sample_okr)
            st.info(f"AI nhận định: {analysis}")

    conn.close()

def student_dashboard():
    user_email = st.session_state['user']['email']
    st.header(f"🎒 Góc Học Tập: {st.session_state['user']['name']}")
    
    conn = get_connection()
    
    # Check Active Period
    active_period = pd.read_sql("SELECT * FROM Periods WHERE TrangThai='Mo'", conn)
    
    if active_period.empty:
        st.warning("Hiện chưa có đợt nhập liệu nào mở.")
    else:
        period_id = active_period.iloc[0]['ID']
        period_name = active_period.iloc[0]['TenDot']
        st.success(f"Đang mở: {period_name}")
        
        # CRUD OKR
        st.subheader("Mục tiêu của tôi")
        
        # Load existing OKRs
        my_okrs = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=? AND ID_Dot=?", conn, params=(user_email, period_id))
        
        # Edit existing using Data Editor
        edited_df = st.data_editor(
            my_okrs[['ID', 'MucTieu', 'KetQuaThenChot', 'TienDo']],
            column_config={
                "TienDo": st.column_config.ProgressColumn("Tiến độ", min_value=0, max_value=100, format="%d%%"),
            },
            num_rows="dynamic",
            key="okr_editor"
        )
        
        # Save changes logic is complex with data_editor in pure SQL, so let's use a Form for Adding New and separate update
        
        with st.expander("➕ Thêm Mục tiêu Mới", expanded=True):
            with st.form("add_okr"):
                mt = st.text_input("Mục tiêu (Objective)")
                kr = st.text_input("Kết quả then chốt (Key Result)")
                td = st.slider("Tiến độ hiện tại (%)", 0, 100, 0)
                file = st.file_uploader("Minh chứng (Ảnh/PDF)")
                
                if st.form_submit_button("Lưu OKR"):
                    file_name = file.name if file else ""
                    try:
                        conn.execute("""
                            INSERT INTO OKRs (Email_HocSinh, ID_Dot, MucTieu, KetQuaThenChot, TienDo, TrangThai, MinhChung)
                            VALUES (?, ?, ?, ?, ?, 'ChoDuyet', ?)
                        """, (user_email, period_id, mt, kr, td, file_name))
                        conn.commit()
                        st.success("Đã lưu mục tiêu!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")

        # Update Progress functionality
        st.divider()
        st.markdown("### 📊 Cập nhật tiến độ & Xếp loại")
        
        if not my_okrs.empty:
            avg_progress = my_okrs['TienDo'].mean()
            
            # Ranking Logic
            rank = "Chưa đạt"
            color = "red"
            if avg_progress >= 80: rank, color = "Tốt", "green"
            elif avg_progress >= 65: rank, color = "Khá", "blue"
            elif avg_progress >= 50: rank, color = "Đạt", "orange"
            
            st.metric("Điểm trung bình tiến độ", f"{avg_progress:.1f}%")
            st.markdown(f"Xếp loại hiện tại: <span style='color:{color}; font-weight:bold; font-size:20px'>{rank}</span>", unsafe_allow_html=True)
            
            # Allow updating progress for existing items via selectbox
            okr_to_update = st.selectbox("Chọn OKR để cập nhật tiến độ", my_okrs['MucTieu'])
            if okr_to_update:
                new_val = st.slider("Cập nhật %", 0, 100, key="update_slider")
                if st.button("Cập nhật"):
                    conn.execute("UPDATE OKRs SET TienDo=? WHERE Email_HocSinh=? AND MucTieu=?", (new_val, user_email, okr_to_update))
                    conn.commit()
                    st.success("Đã cập nhật!")
                    st.rerun()

    conn.close()

def parent_dashboard():
    user_email = st.session_state['user']['email']
    st.header("👨‍👩‍👧‍👦 Cổng thông tin Phụ Huynh")
    
    conn = get_connection()
    
    # Find Child
    child = pd.read_sql("SELECT Email_HocSinh FROM Relationships WHERE Email_PhuHuynh=?", conn, params=(user_email,))
    
    if child.empty:
        st.warning("Không tìm thấy thông tin học sinh liên kết.")
    else:
        child_email = child.iloc[0]['Email_HocSinh']
        
        # Get Child Info
        child_info = pd.read_sql("SELECT HoTen, ClassID FROM Users WHERE Email=?", conn, params=(child_email,))
        st.info(f"Phụ huynh của em: **{child_info.iloc[0]['HoTen']}** - Lớp: {child_info.iloc[0]['ClassID']}")
        
        # Show OKRs
        st.subheader("Tiến độ học tập của con")
        df_okrs = pd.read_sql("SELECT * FROM OKRs WHERE Email_HocSinh=?", conn, params=(child_email,))
        
        if df_okrs.empty:
            st.text("Học sinh chưa cập nhật mục tiêu.")
        else:
            for i, row in df_okrs.iterrows():
                with st.container(border=True):
                    st.markdown(f"**Mục tiêu:** {row['MucTieu']}")
                    st.progress(row['TienDo'])
                    st.caption(f"KR: {row['KetQuaThenChot']} | Trạng thái: {row['TrangThai']}")
                    
                    if row['NhanXet_GV']:
                        st.info(f"GVCN Nhận xét: {row['NhanXet_GV']}")
                    
                    # Parent Comment
                    with st.form(f"parent_cmt_{row['ID']}"):
                        cmt = st.text_input("Ý kiến gia đình", value=row['NhanXet_PH'] if row['NhanXet_PH'] else "")
                        if st.form_submit_button("Gửi ý kiến"):
                            conn.execute("UPDATE OKRs SET NhanXet_PH=? WHERE ID=?", (cmt, row['ID']))
                            conn.commit()
                            st.success("Đã gửi ý kiến!")
                            st.rerun()

    conn.close()

# ==============================================================================
# MAIN APP FLOW
# ==============================================================================
def main():
    if 'user' not in st.session_state:
        login_page()
    else:
        # Sidebar Info
        with st.sidebar:
            st.markdown(f"### 👤 {st.session_state['user']['name']}")
            st.caption(f"Vai trò: {st.session_state['user']['role']}")
            if st.button("Đăng xuất"):
                del st.session_state['user']
                st.rerun()
            st.divider()
            st.markdown("Developed with Streamlit & Python")

        # Routing
        role = st.session_state['user']['role']
        if role == 'Admin':
            admin_dashboard()
        elif role == 'GiaoVien':
            teacher_dashboard()
        elif role == 'HocSinh':
            student_dashboard()
        elif role == 'PhuHuynh':
            parent_dashboard()

if __name__ == "__main__":
    main()
