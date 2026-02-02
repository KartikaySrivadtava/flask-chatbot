from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from excel_store import save_qa_to_excel
from agent_service import ask_agent
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

USERNAME = os.getenv("APP_USERNAME", "admin")
PASSWORD = os.getenv("APP_PASSWORD", "Syntebot@123")


# -------------------- LOGIN --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        if (
            request.form.get("username") == USERNAME
            and request.form.get("password") == PASSWORD
        ):
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            error = "Invalid username or password"

    return render_template("login.html", error=error)


# -------------------- MAIN PAGE --------------------
@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html")


# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------- CHAT API --------------------
@app.route("/api/chat", methods=["POST"])
def chat_api():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}

    question = data.get("prompt")
    chat_id = data.get("chatId")
    chat_title = data.get("chatTitle")

    if not question:
        return jsonify({"bot_reply": "Please enter a valid question."})

    # 🔥 Agentic RAG Call
    answer = ask_agent(question)

    # Save Q&A (no feedback yet)
    save_qa_to_excel(
        chat_id=chat_id,
        chat_title=chat_title,
        question=question,
        answer=answer
    )

    return jsonify({"bot_reply": answer})


# -------------------- FEEDBACK API --------------------
@app.route("/api/feedback", methods=["POST"])
def feedback_api():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}

    # Feedback relates to an existing answer
    save_qa_to_excel(
        chat_id=data.get("chatId"),
        chat_title=data.get("chatTitle"),
        question=data.get("question"),
        answer=data.get("answer"),
        feedback_rating=data.get("rating"),        # "up" or "down"
        feedback_comment=data.get("comment")       # optional text
    )

    return jsonify({"status": "ok"})


# -------------------- RUN --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
