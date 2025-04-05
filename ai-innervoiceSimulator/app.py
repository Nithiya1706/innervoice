import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import cohere
from datetime import datetime
from flask_mail import Mail, Message
import secrets
from flask_migrate import Migrate
import openai
from pydub import AudioSegment


personas = {
    "Optimist": "Respond with an encouraging, hopeful tone.",
    "Realist": "Respond with a practical, grounded perspective.",
    "Worrier": "Respond with concern, cautious, and highlighting risks.",
    "Rebel": "Respond boldly, favoring taking risks and breaking norms.",
    "Lover": "Respond emotionally, with romantic or heart-centered reasoning."
}

# Initialize Flask App
app = Flask(__name__)
app.config["SECRET_KEY"] = "8865a0b002adb68c3d2ddc65a7efaeb1"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"



migrate = Migrate(app, db) 

OPENAI_API_KEY = "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"
openai.api_key = OPENAI_API_KEY


# Cohere API Key
COHERE_API_KEY = "V02NuIFoompn9ml1c3mQysf81vtowL2j0WgYTJPc"
co = cohere.Client(COHERE_API_KEY)

# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)  # Add email field
    password = db.Column(db.String(200), nullable=False)


# Interaction Model
class Interaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user_input = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)





@app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    """Handles audio file and transcribes it using Whisper API."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    audio_file = request.files["audio"]
    temp_audio_path = "temp_audio.webm"
    temp_wav_path = "temp_audio.wav"

    audio_file.save(temp_audio_path)

    # Convert to WAV format (Whisper supports WAV)
    AudioSegment.from_file(temp_audio_path).export(temp_wav_path, format="wav")

    try:
        with open(temp_wav_path, "rb") as audio:
            response = openai.Audio.transcribe("whisper-1", audio)
            transcription = response["text"]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.remove(temp_audio_path)
        os.remove(temp_wav_path)

    return jsonify({"transcription": transcription})


# Load User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# AI Response Generator
def generate_inner_voices(user_input):
    prompt = f"""You are simulating an inner voice debate in the user's mind about a decision.

Respond in the voice of 5 personas discussing this thought:
1. Optimist - always hopeful and positive
2. Realist - practical, logical thinker
3. Worrier - anxious and cautious
4. Rebel - impulsive and bold
5. Lover - guided by emotions and heart

Question: "{user_input}"

Respond like this:
Optimist: ...
Realist: ...
Worrier: ...
Rebel: ...
Lover: ...
"""

    try:
        response = co.generate(
            model="command",
            prompt=prompt,
            max_tokens=300,
            temperature=0.8
        )
        return response.generations[0].text.strip()
    except Exception as e:
        return f"Error: {e}"


# Register Route
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]  # Get email
        password = request.form["password"]

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        user = User(username=username, email=email, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# Login Route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user:
            if bcrypt.check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for("home"))  # Redirect after successful login
            else:
                flash("Incorrect password. Please try again.", "danger")
        else:
            flash("Username not found. Please register first.", "danger")

    return render_template("login.html")


# Logout Route
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# Home Route
@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    ai_response = ""
    if request.method == "POST":
        user_input = request.form["decision"]
        ai_response = generate_inner_voices(user_input)
        
        # Save interaction to database
        interaction = Interaction(user_id=current_user.id, user_input=user_input, ai_response=ai_response)
        db.session.add(interaction)
        db.session.commit()

    return render_template("index.html", ai_response=ai_response)

@app.route("/history")
@login_required
def history():
    interactions = Interaction.query.filter_by(user_id=current_user.id).order_by(Interaction.timestamp.desc()).all()
    return render_template("history.html", interactions=interactions)

# Delete a specific interaction
@app.route("/delete_interaction/<int:interaction_id>", methods=["POST"])
@login_required
def delete_interaction(interaction_id):
    interaction = Interaction.query.get(interaction_id)
    if interaction and interaction.user_id == current_user.id:
        db.session.delete(interaction)
        db.session.commit()
        return jsonify({"success": True, "message": "Interaction deleted successfully."})
    return jsonify({"success": False, "message": "Interaction not found."})

# Delete all interactions
@app.route("/delete_all_interactions", methods=["POST"])
@login_required
def delete_all_interactions():
    Interaction.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "All interactions deleted successfully."})

# About Page
@app.route("/about")
def about():
    return render_template("about.html")

# Contact Page


# Terms & Conditions Page
@app.route("/terms")
def terms():
    return render_template("terms.html")


    # Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Use your email provider's SMTP server
app.config['MAIL_PORT'] = 587  # Common SMTP port
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False 
app.config['MAIL_USERNAME'] = 'blessysan017@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'nysn bvmb eskj lhyi'  # Use an app password if using Gmail

mail = Mail(app)


# Contact Page Route
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        message = request.form["message"]

        if name and email and message:
            try:
                msg = Message("New Contact Form Submission", sender=email, recipients=["blessysan017@gmail.com"])
                msg.body = f"Name: {name}\nEmail: {email}\nMessage: {message}"
                mail.send(msg)
                flash("Your message has been sent!", "success")
            except Exception as e:
                flash("Error sending email. Please try again later.", "danger")

        return redirect(url_for("contact"))

    return render_template("contact.html")



# Run App
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
