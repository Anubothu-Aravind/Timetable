import streamlit as st
import pandas as pd
import random
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client
from dotenv import load_dotenv
import re
import hashlib
import datetime

load_dotenv()
st.set_page_config(page_title="Student Timetable Processor", page_icon="📅")

# Access the variables
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # Convert to integer
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPER_ADMIN_EMAIL = "2200080137@kluniversity.in"  # Only this admin can demote other admins

time_slot_mapping = {
    1: "7:10 AM - 8:00 AM",
    2: "8:00 AM - 8:50 AM",
    3: "9:20 AM - 10:10 AM",
    4: "10:10 AM - 11:00 AM",
    5: "11:10 AM - 12:00 PM",
    6: "12:00 PM - 12:50 PM",
    7: "1:00 PM - 1:50 PM",
    8: "1:50 PM - 2:40 PM",
    9: "2:50 PM - 3:40 PM",
    10: "3:50 PM - 4:40 PM",
    11: "4:40 PM - 5:30 PM"
}

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Streamlit session state for authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.is_admin = False
    st.session_state.user_email = None
    st.session_state.current_page = "login"

# Hash the password
def hash_password(password):
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

# Create users table if not exists
def init_users_table():
    try:
        # Check if super admin exists
        response = supabase.table("users").select("*").eq("email", SUPER_ADMIN_EMAIL).execute()
        if not response.data:
            # Create super admin if doesn't exist
            super_admin = {
                "email": SUPER_ADMIN_EMAIL,
                "password": hash_password("admin123"),  # Default password
                "is_admin": True,
                "super_admin": True,
                "created_at": datetime.datetime.now().isoformat()
            }
            supabase.table("users").insert(super_admin).execute()
            st.success(f"Super admin account created: {SUPER_ADMIN_EMAIL}")
    except Exception as e:
        st.error(f"Error initializing users table: {str(e)}")

# User authentication functions
def signup_user(email, password, confirm_password):
    """Register a new user."""
    if not email.endswith("@kluniversity.in"):
        return False, "Only @kluniversity.in emails are allowed"
    
    if password != confirm_password:
        return False, "Passwords do not match"
    
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    
    try:
        # Check if user already exists
        response = supabase.table("users").select("*").eq("email", email).execute()
        if response.data:
            return False, "User already exists"
        
        # Hash the password
        hashed_password = hash_password(password)
        
        # Create new user
        new_user = {
            "email": email,
            "password": hashed_password,
            "is_admin": False,
            "super_admin": False,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        supabase.table("users").insert(new_user).execute()
        return True, "Account created successfully! Please login."
    except Exception as e:
        return False, f"Error creating account: {str(e)}"

def login_user(email, password):
    """Login a user."""
    try:
        # Get user from database
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            return False, "Invalid email or password"
        
        user = response.data[0]
        hashed_password = hash_password(password)
        
        if user["password"] == hashed_password:
            # Successful login
            st.session_state.authenticated = True
            st.session_state.user_email = email
            st.session_state.is_admin = user.get("is_admin", False)
            st.session_state.is_super_admin = user.get("super_admin", False)
            return True, "Login successful!"
        else:
            return False, "Invalid email or password"
    except Exception as e:
        return False, f"Login error: {str(e)}"

def get_all_users():
    """Get all users from database."""
    try:
        response = supabase.table("users").select("*").execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching users: {str(e)}")
        return []

def update_user_admin_status(email, make_admin):
    """Update user's admin status."""
    try:
        supabase.table("users").update({"is_admin": make_admin}).eq("email", email).execute()
        return True, f"User {email} {'promoted to' if make_admin else 'demoted from'} admin"
    except Exception as e:
        return False, f"Error updating user: {str(e)}"

def process_timetable_data(df, student_id, student_name):
    """Process the timetable data to extract busy slots"""
    time_slots = df.iloc[:, 1:12]  # Get only columns 1-11
    days = df.iloc[:, 0]  # Get days column

    busy_slots = []
    for day_idx, day in enumerate(days):
        for slot_idx in range(11):  # Process only slots 1-11
            cell_value = time_slots.iloc[day_idx, slot_idx]
            if cell_value != '-' and pd.notna(cell_value):
                busy_slots.append({
                    'id': student_id,
                    'student_name': student_name,
                    'day': day,
                    'time_slot': slot_idx + 1,
                    'class_details': str(cell_value).strip()
                })

    return pd.DataFrame(busy_slots)

def delete_existing_data(student_id):
    """Delete existing data for a student ID in the Supabase database"""
    try:
        response = supabase.table("timetable").delete().eq("id", student_id).execute()
        return True, "Existing data deleted successfully"
    except Exception as e:
        return False, f"Error deleting existing data: {str(e)}"

def upload_to_supabase(df):
    """Upload processed timetable data to Supabase"""
    try:
        student_id = df['id'].iloc[0]
        delete_success, delete_message = delete_existing_data(student_id)

        if not delete_success:
            return False, delete_message

        # Convert DataFrame to records
        df = df.where(pd.notna(df), None)
        records = df.to_dict(orient="records")

        # Upload new data to Supabase
        response = supabase.table("timetable").insert(records).execute()
        return True, "Timetable data updated successfully!"
    except Exception as e:
        return False, f"Error uploading data: {str(e)}"

def check_availability(student_id):
    """Check student's timetable availability from Supabase"""
    try:
        response = supabase.table("timetable").select("*").eq("id", student_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error checking availability: {str(e)}")
        return None

def get_all_timetable_data():
    """Get all timetable data from Supabase"""
    try:
        response = supabase.table("timetable").select("*").execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching data: {str(e)}")
        return None

def get_batch_year(student_id):
    """Determine batch year from student ID"""
    try:
        if student_id.startswith("22000"):
            return "Y22"
        elif student_id.startswith("23000"):
            return "Y23"
        elif student_id.startswith("21000"):
            return "Y21"
        elif student_id.startswith("24000"):
            return "Y24"
        else:
            return "Unknown"
    except:
        return "Unknown"

def parse_class_details(class_details):
    """Parse class details to extract course code, component, section, and room"""
    try:
        # Example format: "21CC3047-S - S-2 -RoomNo-L303 - 21CC3047"
        pattern = r"([A-Z0-9]+)-([A-Z]) - ([A-Z]-\d+) -RoomNo-([A-Z0-9]+)(.*)"
        match = re.match(pattern, class_details)
        
        if match:
            course_code = match.group(1)
            component = match.group(2)
            section = match.group(3)
            room = match.group(4)
            return {
                "course_code": course_code,
                "component": component,
                "section": section,
                "room": room
            }
        else:
            # If pattern doesn't match, return the raw string
            return {
                "course_code": "Unknown",
                "component": "Unknown",
                "section": "Unknown",
                "room": "Unknown",
                "raw": class_details
            }
    except:
        return {
            "course_code": "Unknown",
            "component": "Unknown",
            "section": "Unknown",
            "room": "Unknown",
            "raw": class_details
        }

def get_available_students(day, time_slot, all_data=None):
    """Get list of students available at a specific day and time slot"""
    if all_data is None:
        all_data = get_all_timetable_data()
        
    if not all_data:
        return []
    
    # Convert to DataFrame
    df = pd.DataFrame(all_data)
    
    # Get all unique student IDs
    all_students = df[['id', 'student_name']].drop_duplicates()
    
    # Get busy students for this day and time slot
    busy_students = df[(df['day'] == day) & (df['time_slot'] == time_slot)]['id'].unique()
    
    # Get available students (those not in busy_students)
    available_students = all_students[~all_students['id'].isin(busy_students)]
    
    return available_students.to_dict('records')

# Initialize the database
init_users_table()

# App Navigation
def show_login_page():
    st.title("🔐 Login to Timetable System")
    
    # Create tabs for login and signup
    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])
    
    with login_tab:
        email = st.text_input("Email address", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login", key="login_btn"):
            if not email or not password:
                st.error("Please enter email and password")
            else:
                success, message = login_user(email, password)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
    
    with signup_tab:
        new_email = st.text_input("Email address (@kluniversity.in)", key="signup_email")
        new_password = st.text_input("Create password", type="password", key="signup_password")
        confirm_password = st.text_input("Confirm password", type="password", key="signup_confirm")
        
        if st.button("Sign Up", key="signup_btn"):
            if not new_email or not new_password or not confirm_password:
                st.error("Please fill all fields")
            else:
                success, message = signup_user(new_email, new_password, confirm_password)
                if success:
                    st.success(message)
                    # Switch to login tab
                    st.session_state.current_page = "login"
                    st.rerun()
                else:
                    st.error(message)

def show_admin_dashboard():
    st.title("👑 Admin Dashboard")
    
    admin_tabs = st.tabs(["User Management", "System Stats", "My Profile"])
    
    with admin_tabs[0]:
        st.header("User Management")
        
        # Get all users
        users = get_all_users()
        
        if users:
            # Create a DataFrame for better display
            users_df = pd.DataFrame(users)
            
            # Remove password column for security
            if "password" in users_df.columns:
                users_df = users_df.drop(columns=["password"])
            
            # Convert boolean columns to more readable format
            users_df["Admin Status"] = users_df["is_admin"].apply(lambda x: "Admin" if x else "Regular User")
            users_df["Super Admin"] = users_df["super_admin"].apply(lambda x: "Yes" if x else "No")
            
            # Format created_at date
            if "created_at" in users_df.columns:
                users_df["Joined On"] = pd.to_datetime(users_df["created_at"]).dt.strftime("%Y-%m-%d")
            
            # Display users
            st.write(f"### Registered Users ({len(users_df)})")
            
            # Clean up display columns
            display_df = users_df[["email", "Admin Status", "Super Admin", "Joined On"]].copy()
            display_df = display_df.rename(columns={"email": "Email"})
            
            st.dataframe(display_df)
            
            # Admin management section
            st.write("### Manage Admin Access")
            
            # Only super admin can demote other admins
            if st.session_state.is_super_admin:
                st.write("As Super Admin, you can promote or demote any user.")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Promote regular users to admin
                    regular_users = [user["email"] for user in users if not user.get("is_admin", False)]
                    if regular_users:
                        user_to_promote = st.selectbox("Select user to promote to admin", regular_users)
                        if st.button("Promote to Admin"):
                            success, message = update_user_admin_status(user_to_promote, True)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                    else:
                        st.info("No regular users available to promote")
                
                with col2:
                    # Demote admins (except super admin)
                    admins = [user["email"] for user in users if user.get("is_admin", False) and not user.get("super_admin", False)]
                    if admins:
                        admin_to_demote = st.selectbox("Select admin to demote", admins)
                        if st.button("Demote to Regular User"):
                            success, message = update_user_admin_status(admin_to_demote, False)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                    else:
                        st.info("No admins available to demote")
            else:
                # Regular admins can only promote users
                regular_users = [user["email"] for user in users if not user.get("is_admin", False)]
                if regular_users:
                    user_to_promote = st.selectbox("Select user to promote to admin", regular_users)
                    if st.button("Promote to Admin"):
                        success, message = update_user_admin_status(user_to_promote, True)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                else:
                    st.info("No regular users available to promote")
        else:
            st.error("Could not fetch user data")
    
    with admin_tabs[1]:
        st.header("System Statistics")
        
        # Get all users
        users = get_all_users()
        
        # Get all timetable data
        timetable_data = get_all_timetable_data()
        
        if users and timetable_data:
            # Calculate stats
            total_users = len(users)
            admin_count = sum(1 for user in users if user.get("is_admin", False))
            
            # Timetable stats
            timetable_df = pd.DataFrame(timetable_data)
            total_students = len(timetable_df["id"].unique())
            total_classes = len(timetable_df)
            
            # Create metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Users", total_users)
            col2.metric("Admin Users", admin_count)
            col3.metric("Students with Timetables", total_students)
            col4.metric("Total Classes Recorded", total_classes)
            
            # Batch distribution
            if "id" in timetable_df.columns:
                timetable_df["batch"] = timetable_df["id"].apply(get_batch_year)
                batch_counts = timetable_df[["id", "batch"]].drop_duplicates()["batch"].value_counts()
                
                st.write("### Student Distribution by Batch")
                st.bar_chart(batch_counts)
        else:
            st.warning("Not enough data to show statistics")
    
    with admin_tabs[2]:
        st.header("My Profile")
        
        st.write(f"**Email:** {st.session_state.user_email}")
        st.write(f"**Role:** {'Super Admin' if st.session_state.is_super_admin else 'Admin'}")

def main():
    # Navigation sidebar
    with st.sidebar:
        if st.session_state.authenticated:
            st.write(f"✅ Logged in as: {st.session_state.user_email}")
            st.write(f"Role: {'Super Admin' if st.session_state.get('is_super_admin', False) else 'Admin' if st.session_state.is_admin else 'User'}")
            
            # Admin dashboard link (only for admins)
            if st.session_state.is_admin:
                if st.button("📊 Admin Dashboard"):
                    st.session_state.current_page = "admin_dashboard"
                    st.rerun()
            
            # Timetable system link
            if st.button("📅 Timetable System"):
                st.session_state.current_page = "timetable_system"
                st.rerun()
            
            # Logout button
            if st.button("🚪 Logout"):
                st.session_state.authenticated = False
                st.session_state.is_admin = False
                st.session_state.is_super_admin = False
                st.session_state.user_email = None
                st.session_state.current_page = "login"
                st.rerun()

    # Show the appropriate page based on session state
    if not st.session_state.authenticated:
        show_login_page()
    else:
        if st.session_state.current_page == "admin_dashboard" and st.session_state.is_admin:
            show_admin_dashboard()
        else:
            # Timetable system
            if st.session_state.is_admin:
                # Admin can see both Upload and Check Schedule tabs
                tab1, tab2,tab3 = st.tabs(["Upload Timetable", "Check Schedule","Student Data Analysis"])

                with tab1:
                    st.header("Upload Student Timetable")
                    student_id = st.text_input("Enter Student ID", key="upload_student_id")
                    student_name = st.text_input("Enter Student Name", key="upload_student_name")

                    # File upload
                    uploaded_file = st.file_uploader("Upload Timetable File", type=['csv', 'xlsx', 'xls'], key="timetable_file")

                    if uploaded_file is not None:
                        try:
                            # Read file based on type
                            if uploaded_file.name.endswith('.csv'):
                                df = pd.read_csv(uploaded_file)
                            else:
                                df = pd.read_excel(uploaded_file)

                            # Show raw data preview
                            st.write("### Raw Data Preview")
                            st.dataframe(df, key="raw_data_preview")

                            if st.button("Process and Upload", key="process_upload_btn") and student_id and student_name:
                                # Process the data
                                processed_df = process_timetable_data(df, student_id, student_name)

                                # Show processed data preview
                                st.write("### Processed Data Preview")
                                st.dataframe(processed_df, key="processed_data_preview")

                                # Upload to Supabase
                                success, message = upload_to_supabase(processed_df)
                                if success:
                                    st.success(message)
                                else:
                                    st.error(message)
                        except Exception as e:
                            st.error(f"Error processing file: {str(e)}")

                with tab2:
                    st.header("Check Student Schedule")
                    search_id = st.text_input("Enter Student ID to Check Schedule", key="search_student_id")

                    # Sub-tab - Check Schedule by Time Range
                    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["Check Schedule by Time Range", "Full Day Schedule", "Data Analysis"])

                    with sub_tab1:
                        st.header("Check Schedule by Time Range")
                        weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
                        # Get day input (from the weekday_order list)
                        day_input = st.selectbox("Select Day", options=weekday_order, key="day_select_tab1")

                        # Get time input
                        start_time = st.time_input("Start Time", value=None, key="start_time_tab1")
                        end_time = st.time_input("End Time", value=None, key="end_time_tab1")

                        if st.button("Check Availability", key="check_avail_btn_tab1"):
                            if search_id and day_input and start_time and end_time:
                                results = check_availability(search_id)
                                if results:
                                    schedule_df = pd.DataFrame(results)

                                    # Get student name
                                    student_name = schedule_df['student_name'].iloc[0]

                                    # Convert time slot mapping to a dataframe for easy filtering
                                    time_slot_df = pd.DataFrame(list(time_slot_mapping.items()),
                                                                columns=['time_slot', 'time_range'])
                                    time_slot_df[['start_time', 'end_time']] = time_slot_df['time_range'].str.split(" - ",
                                                                                                                    expand=True)

                                    # Convert time strings to actual datetime.time objects
                                    time_slot_df['start_time'] = pd.to_datetime(time_slot_df['start_time'],
                                                                                format="%I:%M %p").dt.time
                                    time_slot_df['end_time'] = pd.to_datetime(time_slot_df['end_time'],
                                                                            format="%I:%M %p").dt.time

                                    # Check for overlapping slots
                                    valid_slots = \
                                        time_slot_df[
                                            (time_slot_df['start_time'] < end_time) & (time_slot_df['end_time'] > start_time)][
                                            'time_slot'].tolist()

                                    # Filter schedule based on valid slots and selected day
                                    filtered_schedule = schedule_df[
                                        schedule_df['time_slot'].isin(valid_slots) & (schedule_df['day'] == day_input)]

                                    st.write(
                                        f"### Schedule for {student_name} on {day_input} from {start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')}:")

                                    if filtered_schedule.empty:
                                        st.info(
                                            f"No classes scheduled on {day_input} from {start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')} for Student ID: {search_id}. It's **Leisure Time**!")

                                    else:
                                        for _, row in filtered_schedule.iterrows():
                                            time_range = time_slot_mapping.get(row['time_slot'], "Unknown Time")
                                            st.write(f"⏳ **{time_range}:** {row['class_details']}")

                            else:
                                st.error("Please enter a Student ID, select a Day, and both Start and End times.")

                    with sub_tab2:
                        if st.button("View Full Schedule", key="view_full_schedule_btn"):
                            if search_id:
                                results = check_availability(search_id)
                                if results:
                                    schedule_df = pd.DataFrame(results)

                                    # Get the student's name
                                    student_name = schedule_df['student_name'].iloc[0]

                                    # Define weekday order
                                    weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

                                    # Convert 'day' column to categorical and sort by day and time slot
                                    schedule_df['day'] = pd.Categorical(schedule_df['day'], categories=weekday_order,
                                                                        ordered=True)
                                    schedule_df = schedule_df.sort_values(['day', 'time_slot'])

                                    st.write(f"### Full Schedule for {student_name} (ID: {search_id})")

                                    # Display the schedule day-wise
                                    for day in weekday_order:
                                        day_schedule = schedule_df[schedule_df['day'] == day]
                                        if day_schedule.empty:
                                            st.info(f"📌 {student_name} has no class on {day}")
                                        else:
                                            st.subheader(day)
                                            for _, row in day_schedule.iterrows():
                                                time_range = time_slot_mapping.get(row['time_slot'], "Unknown Time")
                                                st.write(f"⏳ **{time_range}:** {row['class_details']}")
                                else:
                                    st.info("No schedule found for this student.")
                            else:
                                st.error("Please enter a Student ID.")
                    
                    # Data Analysis Tab content omitted for brevity, but would remain the same as original
                with tab3:
                        st.header("Student Data Analysis")
                        
                        analysis_options = ["Batch-wise Analysis", "Student Availability by Time Slot", "Course Analysis"]
                        analysis_choice = st.radio("Select Analysis Type", analysis_options, key="analysis_type_radio")
                        
                        if analysis_choice == "Batch-wise Analysis":
                            st.subheader("Batch-wise Student Distribution")
                            
                            # Fetch all data
                            all_data = get_all_timetable_data()
                            
                            if all_data:
                                df = pd.DataFrame(all_data)
                                
                                # Get unique students with their IDs
                                students_df = df[['id', 'student_name']].drop_duplicates()
                                
                                # Add batch year column
                                students_df['batch'] = students_df['id'].apply(get_batch_year)
                                
                                # Display student distribution by batch
                                batch_counts = students_df['batch'].value_counts().reset_index()
                                batch_counts.columns = ['Batch', 'Number of Students']
                                
                                st.write("### Student Distribution by Batch")
                                st.dataframe(batch_counts, key="batch_counts_df")
                                
                                # Create a pie chart of the distribution
                                st.write("### Batch Distribution")
                                st.bar_chart(batch_counts.set_index('Batch'))
                                
                                # Allow downloading the student data by batch
                                st.write("### Download Student Data by Batch")
                                
                                # Select batch to download
                                selected_batch = st.selectbox("Select Batch to Download", 
                                                            students_df['batch'].unique().tolist(),
                                                            key="batch_download_select")
                                
                                # Filter students by selected batch
                                batch_students = students_df[students_df['batch'] == selected_batch]
                                
                                # Convert to CSV
                                csv = batch_students.to_csv(index=False).encode('utf-8')
                                
                                st.download_button(
                                    label=f"Download {selected_batch} Students Data",
                                    data=csv,
                                    file_name=f"{selected_batch}_students.csv",
                                    mime="text/csv",
                                    key="download_batch_btn"
                                )
                            else:
                                st.info("No data available for analysis.")
                        
                        elif analysis_choice == "Student Availability by Time Slot":
                            st.subheader("Student Availability by Time Slot")
                            
                            # Select day and time slot
                            weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
                            selected_day = st.selectbox("Select Day", options=weekday_order, key="availability_day_select")
                            
                            # Allow for custom time slot range selection
                            col1, col2 = st.columns(2)
                            with col1:
                                start_slot = st.selectbox("Start Time Slot", 
                                                    options=list(range(1, 12)),
                                                    format_func=lambda x: time_slot_mapping.get(x, f"Slot {x}"),
                                                    key="availability_start_slot_select")
                            with col2:
                                end_slot = st.selectbox("End Time Slot", 
                                                    options=list(range(start_slot, 12)),
                                                    format_func=lambda x: time_slot_mapping.get(x, f"Slot {x}"),
                                                    key="availability_end_slot_select")
                            
                            if st.button("Find Available Students", key="find_available_btn"):
                                # Get all data
                                all_data = get_all_timetable_data()
                                
                                if all_data:
                                    # Create time slot range
                                    time_slot_range = list(range(start_slot, end_slot + 1))
                                    
                                    # Get available students and their class details if any
                                    available_students = []
                                    students_with_partial_classes = []
                                    
                                    # Group all students
                                    student_ids = set([record['id'] for record in all_data])
                                    
                                    for student_id in student_ids:
                                        # Get student records
                                        student_records = [r for r in all_data if r['id'] == student_id]
                                        
                                        if not student_records:
                                            continue
                                        
                                        student_name = student_records[0]['student_name']
                                        
                                        # Check if student has classes in the selected day and time slot range
                                        classes_in_range = []
                                        for record in student_records:
                                            if record['day'] == selected_day and record['time_slot'] in time_slot_range:
                                                # Parse class_details to extract course code, section, and room
                                                class_details = record.get('class_details', '')
                                                
                                                # Improved parsing for format: "22ASS3309A-P - S-11 -RoomNo-R204A"
                                                parts = class_details.split('-')
                                                
                                                # Extract course code (everything before first hyphen)
                                                course_code = parts[0].strip() if parts else "Unknown"
                                                
                                                # Extract section number (part that contains S-xx)
                                                section = "S-01"  # Default
                                                for i in range(len(parts) - 1):
                                                    if parts[i].strip() == "S" and i + 1 < len(parts) and parts[i + 1].strip().isdigit():
                                                        section = f"S-{parts[i + 1].strip()}"
                                                        break
                                                    # Check for "S-11" format (without spaces)
                                                    elif parts[i].strip().startswith("S") and len(parts[i].strip()) > 1:
                                                        section = parts[i].strip()
                                                        break
                                                
                                                # Extract room (part that follows "RoomNo")
                                                room = "Unknown"
                                                for i, part in enumerate(parts):
                                                    if part.strip() == "RoomNo" and i + 1 < len(parts):
                                                        room = parts[i+1].strip()
                                                        break
                                                
                                                classes_in_range.append({
                                                    'time_slot': record['time_slot'],
                                                    'course_code': course_code,
                                                    'section': section,
                                                    'room': room,
                                                    'class_details': class_details  # Keep original string
                                                })
                                        
                                        # If no classes in range, student is fully available
                                        if not classes_in_range:
                                            available_students.append({
                                                'id': student_id,
                                                'student_name': student_name,
                                                'status': 'Fully Available',
                                                'classes': None
                                            })
                                        else:
                                            # Consolidate continuous time slots with same course and room
                                            consolidated_classes = []
                                            current_class = None
                                            
                                            # Sort classes by time slot
                                            sorted_classes = sorted(classes_in_range, key=lambda x: x['time_slot'])
                                            
                                            for class_info in sorted_classes:
                                                if current_class is None:
                                                    current_class = class_info.copy()
                                                    current_class['end_slot'] = class_info['time_slot']
                                                elif (current_class['course_code'] == class_info['course_code'] and 
                                                    current_class['room'] == class_info['room'] and
                                                    current_class['end_slot'] + 1 == class_info['time_slot']):
                                                    # Extend the current class if continuous
                                                    current_class['end_slot'] = class_info['time_slot']
                                                else:
                                                    # Add the completed class and start a new one
                                                    consolidated_classes.append(current_class)
                                                    current_class = class_info.copy()
                                                    current_class['end_slot'] = class_info['time_slot']
                                            
                                            # Add the last class if any
                                            if current_class:
                                                consolidated_classes.append(current_class)
                                            
                                            # Format the classes for display
                                            classes_info = []
                                            for cls in consolidated_classes:
                                                if cls['time_slot'] == cls['end_slot']:
                                                    time_info = f"{time_slot_mapping.get(cls['time_slot'])}"
                                                else:
                                                    time_info = f"{time_slot_mapping.get(cls['time_slot'])} - {time_slot_mapping.get(cls['end_slot'])}"
                                                
                                                # Use original class_details if parsing was challenging
                                                if cls['course_code'] == "Unknown" or cls['room'] == "Unknown":
                                                    classes_info.append(f"{cls['class_details']} (Time: {time_info})")
                                                else:
                                                    classes_info.append(f"{cls['course_code']} (Sec: {cls['section']}, Room: {cls['room']}, Time: {time_info})")
                                            
                                            students_with_partial_classes.append({
                                                'id': student_id,
                                                'student_name': student_name,
                                                'status': 'Partially Available',
                                                'classes': ", ".join(classes_info)
                                            })
                                    
                                    # Combine fully available and partially available
                                    all_students_info = available_students + students_with_partial_classes
                                    
                                    if all_students_info:
                                        # Create dataframe and add batch information
                                        result_df = pd.DataFrame(all_students_info)
                                        result_df['batch'] = result_df['id'].apply(get_batch_year)
                                        
                                        # Display available students
                                        st.write(f"### Students Availability on {selected_day} during {time_slot_mapping.get(start_slot)} to {time_slot_mapping.get(end_slot)}")
                                        
                                        # Display fully available students
                                        fully_available_df = result_df[result_df['status'] == 'Fully Available']
                                        if not fully_available_df.empty:
                                            st.write("#### Fully Available Students")
                                            st.dataframe(fully_available_df[['id', 'student_name', 'batch']], key="fully_available_students_df")
                                        
                                        # Display partially available students (with classes)
                                        partially_available_df = result_df[result_df['status'] == 'Partially Available']
                                        if not partially_available_df.empty:
                                            st.write("#### Students With Classes")
                                            st.dataframe(partially_available_df[['id', 'student_name', 'batch', 'classes']], key="partially_available_students_df")
                                        
                                        # Summary stats
                                        availability_summary = result_df['status'].value_counts().reset_index()
                                        availability_summary.columns = ['Availability Status', 'Count']
                                        
                                        batch_summary = result_df['batch'].value_counts().reset_index()
                                        batch_summary.columns = ['Batch', 'Total Students']
                                        
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.write("### Availability Summary")
                                            st.dataframe(availability_summary, key="availability_summary_df")
                                        
                                        with col2:
                                            st.write("### Students by Batch")
                                            st.dataframe(batch_summary, key="batch_summary_df")
                                        
                                        # Download option
                                        csv = result_df.to_csv(index=False).encode('utf-8')
                                        
                                        st.download_button(
                                            label=f"Download Students Availability List",
                                            data=csv,
                                            file_name=f"students_availability_{selected_day}_slot{start_slot}to{end_slot}.csv",
                                            mime="text/csv",
                                            key="download_available_btn"
                                        )
                                    else:
                                        st.info(f"No students available on {selected_day} during {time_slot_mapping.get(start_slot)} to {time_slot_mapping.get(end_slot)}")
                                else:
                                    st.info("No data available for analysis.")
                        
                        elif analysis_choice == "Course Analysis":
                            st.subheader("Course Details Analysis")
                            
                            # Fetch all data
                            all_data = get_all_timetable_data()
                            
                            if all_data:
                                df = pd.DataFrame(all_data)
                                
                                # Parse class details
                                parsed_details = []
                                for _, row in df.iterrows():
                                    details = parse_class_details(row['class_details'])
                                    details.update({
                                        'id': row['id'],
                                        'student_name': row['student_name'],
                                        'day': row['day'],
                                        'time_slot': row['time_slot']
                                    })
                                    parsed_details.append(details)
                                
                                parsed_df = pd.DataFrame(parsed_details)
                                
                                # Add batch year
                                parsed_df['batch'] = parsed_df['id'].apply(get_batch_year)
                                
                                # Course distribution
                                course_counts = parsed_df['course_code'].value_counts().reset_index()
                                course_counts.columns = ['Course Code', 'Number of Occurrences']
                                
                                st.write("### Course Distribution")
                                st.dataframe(course_counts, key="course_counts_df")
                                
                                # Room utilization
                                room_counts = parsed_df['room'].value_counts().reset_index()
                                room_counts.columns = ['Room', 'Number of Occurrences']
                                
                                st.write("### Room Utilization")
                                st.dataframe(room_counts, key="room_counts_df")
                                
                                # Download detailed course data
                                st.write("### Download Detailed Course Data")
                                
                                csv = parsed_df.to_csv(index=False).encode('utf-8')
                                
                                st.download_button(
                                    label="Download Complete Course Analysis",
                                    data=csv,
                                    file_name="course_analysis.csv",
                                    mime="text/csv",
                                    key="download_course_analysis_btn"
                                )
                            else:
                                st.info("No data available for analysis.")
            else:
                    st.header("Upload Student Timetable")
                    student_id = st.text_input("Enter Student ID", key="upload_student_id")
                    student_name = st.text_input("Enter Student Name", key="upload_student_name")

                    # File upload
                    uploaded_file = st.file_uploader("Upload Timetable File", type=['csv', 'xlsx', 'xls'], key="timetable_file")

                    if uploaded_file is not None:
                        try:
                            # Read file based on type
                            if uploaded_file.name.endswith('.csv'):
                                df = pd.read_csv(uploaded_file)
                            else:
                                df = pd.read_excel(uploaded_file)

                            # Show raw data preview
                            st.write("### Raw Data Preview")
                            st.dataframe(df, key="raw_data_preview")

                            if st.button("Process and Upload", key="process_upload_btn") and student_id and student_name:
                                # Process the data
                                processed_df = process_timetable_data(df, student_id, student_name)

                                # Show processed data preview
                                st.write("### Processed Data Preview")
                                st.dataframe(processed_df, key="processed_data_preview")

                                # Upload to Supabase
                                success, message = upload_to_supabase(processed_df)
                                if success:
                                    st.success(message)
                                else:
                                    st.error(message)
                        except Exception as e:
                            st.error(f"Error processing file: {str(e)}")

    # Add instructions
    st.markdown("---")
    st.markdown("""
    ### Instructions:
    1. In the **Upload** tab:
       - Enter the student's ID and name
       - Upload your timetable file (CSV or Excel)
       - Review the data preview
       - Click "Process and Upload" to save the schedule
    2. In the **Check Schedule** tab:
       - Enter a student ID to view their complete schedule
       - The schedule will show all classes organized by day and time slot

    ### File Format Requirements:
    - First column should contain days (Mon, Tue, etc.)
    - Columns 1-11 should contain the time slots
    - Use '-' or leave empty for free slots
    """)

    st.markdown("---")
    st.markdown("""
        <p style='text-align:center; font-size:14px; color:gray;'>
            Made with ❤️ from <b>Intelligentsia Club</b><br>
            Department of AI & DS<br><br>
            Developed by <b>Aravind</b> (2200080137)<br>
            Contact: <a href='https://t.me/iarvn1' target='_blank'>@iarvn1</a> on Telegram
        </p>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()