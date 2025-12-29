from flask import Flask, request, render_template, send_file, session, redirect
import os, random, smtplib, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import psycopg2
import bcrypt
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name="dt6yls8rh",
    api_key="935787172616493",
    api_secret="OJFhbpCo4ou1XiY918mPlAuj6mM"
)


app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- DATABASE CONNECTION ----------------
def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="secure_cloud",
        user="postgres",
        password="password"
    )

# ---------------- EMAIL OTP FUNCTION ----------------
def send_email_otp(receiver_email, otp):
    sender_email = "klutzykiru29@gmail.com"
    sender_password = "ezir xyua vfwn csxb"  # App password from Google

    subject = "Your Secure File Download OTP"
    body = f"Your OTP for file access is: {otp}\nThis OTP expires in 5 minutes."

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.sendmail(sender_email, receiver_email, msg.as_string())
    server.quit()

# ---------------- Landing Page ----------------
@app.route("/")
def start():
    return redirect("/select-role")

@app.route("/select-role")
def select_role():
    return render_template("select_role.html")

# ---------------- Register Page ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        pwd = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            conn.close()
            return render_template("register.html", msg="⚠ User already exists")

        hashed_pwd = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt())
        cur.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, hashed_pwd.decode('utf-8')))
        conn.commit()
        cur.close()
        conn.close()

        return redirect("/uploader-login")

    return render_template("register.html")

# ---------------- LOGIN (UPLOADER) ----------------
@app.route("/uploader-login", methods=["GET", "POST"])
def uploader_login():
    if request.method == "POST":
        email = request.form["email"]
        pwd = request.form["password"].encode('utf-8')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and bcrypt.checkpw(pwd, user[0].encode('utf-8')):
            session["user"] = email
            session["role"] = "uploader"
            return redirect("/upload")

        return render_template("login.html", msg="❌ Incorrect Email or Password")

    return render_template("login.html")

# ---------------- LOGIN (RECEIVER) ----------------
@app.route("/verify-login", methods=["GET", "POST"])
def verify_login():
    if request.method == "POST":
        email = request.form["email"]
        pwd = request.form["password"].encode('utf-8')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and bcrypt.checkpw(pwd, user[0].encode('utf-8')):
            session["user"] = email
            session["role"] = "receiver"
            return redirect("/enter-otp")

        return render_template("login.html", msg="❌ Incorrect Email or Password")

    return render_template("login.html")

# ---------------- FILE UPLOAD (Uploader Only) ----------------
import requests

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if session.get("role") != "uploader":
        return redirect("/uploader-login")

    if request.method == "POST":
        file = request.files["file"]
        receiver_email = request.form["receiver_email"]

        if not file or file.filename == "":
            return render_template("upload.html", msg="⚠ Please select a file")

        filename = file.filename
        local_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(local_path)

        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            local_path,
            resource_type="auto",
            folder="secure_file_sharing"
        )

        cloud_url = upload_result["secure_url"]
        cloud_url = cloud_url.replace("/upload/", "/upload/fl_attachment/")

        # Remove local file (optional but professional)
        os.remove(local_path)

        otp = random.randint(100000, 999999)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO file_otp (receiver_email, otp, filename, cloud_url, created_time)
            VALUES (%s, %s, %s, %s, NOW())
        """, (receiver_email, str(otp), filename, cloud_url))
        conn.commit()
        cur.close()
        conn.close()

        send_email_otp(receiver_email, otp)

        return render_template(
            "upload_success.html",
            cloud_url=cloud_url
        )

    return render_template("upload.html")



# ---------------- OTP Verification ----------------
@app.route("/enter-otp", methods=["GET", "POST"])
def enter_otp():

    if session.get("role") != "receiver":
        return redirect("/verify-login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT otp, filename, cloud_url, created_time
    FROM file_otp
    WHERE receiver_email=%s
    ORDER BY created_time DESC
    LIMIT 1
    """, (session["user"],))

    record = cur.fetchone()
    cur.close()
    conn.close()

    if not record:
        return render_template("otp.html",
            msg="⚠ No file shared with you yet.")

    db_otp, filename, cloud_url, created_time = record

    if request.method == "POST":
        user_otp = request.form["otp"]

        # Expiry check (5 mins)
        if (time.time() - created_time.timestamp()) > 300:
            return render_template("otp.html",
                msg="⏳ OTP expired.")

        if user_otp == db_otp:
            session["file"] = filename
            session["cloud_url"] = cloud_url
            return redirect("/download")

        return render_template("otp.html", msg="❌ Wrong OTP")

    return render_template("otp.html")



# ---------------- DOWNLOAD PAGE ----------------
@app.route("/download")
def download():
    if "cloud_url" not in session:
        return redirect("/verify-login")
    return render_template("download.html")

@app.route("/download-file")
def download_file():
    cloud_url = session.get("cloud_url")
    return redirect(cloud_url)


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/select-role")

from flask import send_from_directory

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    app.run(debug=True)
