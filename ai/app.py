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



# Initialize Flask App
app = Flask(__name__)
app.config["SECRET_KEY"] = "xxxxxxxxxx"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"



migrate = Migrate(app, db) 

OPENAI_API_KEY = "xxxxxxxxxxxxxxx"
openai.api_key = OPENAI_API_KEY


# Cohere API Key
COHERE_API_KEY = "xxxxxxxxx"
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


   


# Load User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_inner_voices(user_input):
    try:
        response = co.generate(
            model="command",
            prompt=user_input,
            max_tokens=300
        )
        return response.generations[0].text.strip()
    except Exception as e:
        return f"Error: {e}"



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









# Run App
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
