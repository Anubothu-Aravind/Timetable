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

load_dotenv()
st.set_page_config(page_title="Student Timetable Processor", page_icon="📅")
# Access the variables
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))  # Convert to integer
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Constants
# ADMIN_EMAIL = "2200080137@kluniversity.in"  # Replace with your admin email
# SMTP_SERVER = "smtp.gmail.com"
# SMTP_PORT = 465
# EMAIL_SENDER = "aanubothu@gmail.com"
# EMAIL_PASSWORD = "rhdjcndngwrxango"

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
# SUPABASE_URL = "https://nzvehfhhgoymyebernzn.supabase.co"
# SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im56dmVoZmhoZ295bXllYmVybnpuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzk0Mjg2ODMsImV4cCI6MjA1NTAwNDY4M30.5i79rVe_BTC2lTVtWOdkxVOtd6EZb5ufQHhQqymMRwM"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Streamlit session state for authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.is_admin = False
    st.session_state.user_email = None
    st.session_state.otp = None


def send_otp(email):
    """Generates an OTP and sends it to the provided email."""

    otp = str(random.randint(100000, 999999))
    st.session_state.otp = otp  # Store OTP in session

    subject = "🔐 Your OTP for Login"
    body = f"""
    <html>
    <body>
        <p>Hello,</p>
        <p>Your OTP for login is: <strong>{otp}</strong></p>
        <p><b>Do not share this OTP with anyone.</b></p>
        <p>Best Regards,<br>Timetable System</p>
    </body>
    </html>
    """

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        # Use SMTP_SSL instead of starttls
        with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, email, msg.as_string())  # Send email to recipient

        # st.success("OTP sent successfully! Check your inbox.")
        return True

    except smtplib.SMTPAuthenticationError:
        st.error("Authentication failed. Check your email credentials.")
    except smtplib.SMTPException as e:
        st.error(f"Failed to send OTP: {e}")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")

    return False


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


if not st.session_state.get("authenticated", False):
    # Login System
    st.title("🔐 Login to Timetable System")
    email_input = st.text_input("Enter your email address")

    if st.button("Send OTP"):
        if not email_input:
            st.error("Please enter an email address!")
        elif not email_input.endswith("@kluniversity.in") and email_input != ADMIN_EMAIL:
            st.error("Only @kluniversity.in emails are allowed (or Admin email)")
        else:
            if send_otp(email_input):
                st.success("OTP sent to your email. Please check your inbox!")

    # OTP Verification
    otp_input = st.text_input("Enter the OTP sent to your email")
    if st.button("Verify OTP"):
        if otp_input == st.session_state.otp:
            st.session_state.authenticated = True
            st.session_state.user_email = email_input
            st.session_state.is_admin = email_input == ADMIN_EMAIL
            st.success("Login successful! Redirecting...")
            st.rerun()
        else:
            st.error("Invalid OTP. Please try again.")

# After Authentication
if st.session_state.authenticated:
    st.sidebar.write(f"✅ Logged in as: {st.session_state.user_email}")

    tab1, tab2 = st.tabs(["Upload Timetable", "Check Schedule"])

    with tab1:
        st.header("Upload Student Timetable")
        student_id = st.text_input("Enter Student ID")
        student_name = st.text_input("Enter Student Name")

        # File upload
        uploaded_file = st.file_uploader("Upload Timetable File", type=['csv', 'xlsx', 'xls'])

        if uploaded_file is not None:
            try:
                # Read file based on type
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)

                # Show raw data preview
                st.write("### Raw Data Preview")
                st.dataframe(df)

                if st.button("Process and Upload") and student_id and student_name:
                    # Process the data
                    processed_df = process_timetable_data(df, student_id, student_name)

                    # Show processed data preview
                    st.write("### Processed Data Preview")
                    st.dataframe(processed_df)

                    # Upload to Supabase
                    success, message = upload_to_supabase(processed_df)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")

    if st.session_state.is_admin:
        with tab2:
            st.header("Check Student Schedule")
            search_id = st.text_input("Enter Student ID to Check Schedule")

            # Sub-tab - Check Schedule by Time Range
            sub_tab1, sub_tab2 = st.tabs(["Check Schedule by Time Range", "Full Day Schedule"])

            with sub_tab1:
                st.header("Check Schedule by Time Range")
                weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
                # Get day input (from the weekday_order list)
                day_input = st.selectbox("Select Day", options=weekday_order)

                # Get time input
                start_time = st.time_input("Start Time", value=None)
                end_time = st.time_input("End Time", value=None)

                if st.button("Check Availability"):
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
                if st.button("View Full Schedule"):
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
