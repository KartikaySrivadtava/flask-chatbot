import pandas as pd
from pathlib import Path
from datetime import datetime

CHAT_DIR = Path("chats")
CHAT_DIR.mkdir(exist_ok=True)

FILE_PATH = CHAT_DIR / "chat_history.xlsx"

def save_qa_to_excel(
    chat_id,
    chat_title,
    question,
    answer,
    feedback_rating=None,
    feedback_comment=None
):
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "chat_id": chat_id,
        "chat_title": chat_title,
        "question": question,
        "answer": answer,
        "feedback_rating": feedback_rating,
        "feedback_comment": feedback_comment,
        "feedback_time": (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if feedback_rating or feedback_comment
            else None
        ),
    }

    new_df = pd.DataFrame([row])

    if FILE_PATH.exists():
        existing_df = pd.read_excel(FILE_PATH)
        final_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        final_df = new_df

    final_df.to_excel(FILE_PATH, index=False)
