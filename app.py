import os
import re
import pandas as pd
import torch
import matplotlib.pyplot as plt
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from transformers import BertTokenizerFast, BertForSequenceClassification
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
import platform


app = FastAPI(title="Sales Performance Sentiment Analysis")

# Serve reports folder
app.mount("/reports", StaticFiles(directory="reports"), name="reports")

# -------------------- Model Setup --------------------
MODEL_DIR = "model_out/sentiment_model"
tokenizer = BertTokenizerFast.from_pretrained(MODEL_DIR)
model = BertForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()

# -------------------- Mappings --------------------
id2label = {0: "negativa", 1: "neutral", 2: "positiva"}
meet_probs = {"negativa": 0.05, "neutral": 0.2, "positiva": 0.6}
sentiment_map = {"negativa": 0, "neutral": 50, "positiva": 100}

# -------------------- Helpers --------------------
def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^a-záéíóúñü¡!?,.\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()

def predict_sentiment(texts):
    texts_clean = [clean_text(t) for t in texts]
    enc = tokenizer(texts_clean, padding=True, truncation=True, max_length=128, return_tensors="pt")
    with torch.no_grad():
        logits = model(**enc).logits
    probs = torch.softmax(logits, dim=-1).cpu().numpy()
    preds = [id2label[p.argmax()] for p in probs]
    confs = [round(float(p.max()), 3) for p in probs]
    return preds, confs


output_files = [
    os.path.join("reports", "predicted_meetings.xlsx"),
    os.path.join("reports", "expected_meetings.xlsx"),
    os.path.join("reports", "expected_meetings_chart.png"),
    os.path.join("reports", "sentiment_percentage_chart.png")
]

def handle_open_files():
    """
    Handles output files before overwriting:
    - On Windows: attempts to save & close Excel files automatically
    - On other OS: prints message to close files manually
    """
    current_os = platform.system()

    for f in output_files:
        if os.path.exists(f):
            if current_os == "Windows":
                try:
                    import win32com.client
                    excel = win32com.client.Dispatch("Excel.Application")
                    for wb in excel.Workbooks:
                        if f.lower() in wb.FullName.lower():
                            print(f"Saving and closing open file: {f}")
                            wb.Save()
                            wb.Close()
                    excel.Quit()
                except Exception:
                    print(f"Could not auto-close {f}. Please close it manually.")
            else:
                print(f"File is open or locked: {f}. Please close it before running the script.")

def autofit_excel_columns(file_path):
    wb = load_workbook(file_path)
    ws = wb.active
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[col_letter].width = max_length + 2
    wb.save(file_path)


# -------------------- API Models --------------------
class TextsInput(BaseModel):
    texts: list[str]

# -------------------- Endpoints --------------------
@app.post("/predict_texts")
async def predict_texts_endpoint(data: TextsInput):
    label, confs = predict_sentiment(data.texts)
    result = []
    for t, l, c in zip(data.texts, label, confs):
        result.append({
            "text": t,
            "label": l,
            "confidence": c,
            "expected_meeting": meet_probs[l],
            "sentiment_percentage": sentiment_map[l]
        })
    return result

@app.post("/predict_file")

async def predict_file(file: UploadFile = File(...)):
    handle_open_files()
    os.makedirs("reports", exist_ok=True)
    
    # ---- Load file ----
    ext = os.path.splitext(file.filename)[1].lower()

    if ext in [".xls", ".xlsx"]:
        df = pd.read_excel(file.file, engine="openpyxl")
    else:
        try:
            df = pd.read_csv(file.file, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file.file, encoding='latin-1')

    if "respuesta" not in df.columns or "representante" not in df.columns:
        return {"error": "File must contain 'respuesta' and 'representante' columns."}

    # ---- Predict ----
    # Clean the text and predict sentiment
    df["cleaned"] = df["respuesta"].astype(str).apply(clean_text)
    preds, confs = predict_sentiment(df["respuesta"].tolist())

    # Add predictions, confidence, and mapped values
    df["label"] = preds  
    df["confidence"] = confs
    df["expected_meeting"] = df["label"].map(meet_probs)
    df["sentiment_percentage"] = df["label"].map(sentiment_map)


    df.reset_index(drop=True, inplace=True)

    # ---- Save full prediction file ----
    prediction_file = os.path.join("reports", "predicted_meetings.xlsx")
    df.to_excel(prediction_file, index=False)
    autofit_excel_columns(prediction_file)

    # ---- Summary ----
    summary = df.groupby("representante").agg(
        expected_meetings=("expected_meeting", "sum"),
        total_messages=("respuesta", "count"),
        avg_percentage=("sentiment_percentage", "mean")
    ).reset_index()

    summary["expected_meetings"] = summary["expected_meetings"].round(2)
    summary["avg_percentage"] = summary["avg_percentage"].round(2)
    summary_sorted_percentage = summary.sort_values("avg_percentage", ascending=False)

    # Save expected meetings summary
    summary_file = os.path.join("reports", "expected_meetings.xlsx")
    
    summary_sorted_percentage.to_excel(summary_file, index=False)
    autofit_excel_columns(summary_file)

    # ---- Graph 1: Expected meetings ----
    summary_sorted_meetings = summary.sort_values("expected_meetings", ascending=False)

    plt.figure(figsize=(10, 6))
    ax = summary_sorted_meetings.set_index("representante")["expected_meetings"].plot(kind="bar", color="skyblue")
    ax.set_title("Reuniones Esperadas por Representante")
    ax.set_ylabel("Reuniones Esperadas")
    ax.set_xlabel("Representante")
    plt.grid(axis="y", linestyle="--", alpha=0.7)
    for p in ax.patches:
        ax.annotate(f"{p.get_height():.2f}", (p.get_x() + p.get_width()/2, p.get_height()), ha="center", va="bottom", fontsize=9)
    plt.xticks(rotation=45)
    plt.tight_layout()
    meetings_chart = os.path.join("reports", "expected_meetings_chart.png")
    plt.savefig(meetings_chart)
    plt.close()

    # ---- Graph 2: Sentiment percentage ----
    summary_sorted_percentage = summary.sort_values("avg_percentage", ascending=False)

    plt.figure(figsize=(10, 6))
    ax2 = summary_sorted_percentage.set_index("representante")["avg_percentage"].plot(kind="bar", color="orange")
    ax2.set_title("Average Sentiment Percentage by Representative")
    ax2.set_ylabel("Sentiment Percentage (%)")
    ax2.set_xlabel("Representative")
    ax2.set_ylim(0, 110)
    plt.grid(axis="y", linestyle="--", alpha=0.7)
    for p in ax2.patches:
        ax2.annotate(f"{int(p.get_height())}%", (p.get_x() + p.get_width()/2, p.get_height()), ha="center", va="bottom", fontsize=9)
    plt.xticks(rotation=45)
    plt.tight_layout()
    sentiment_chart = os.path.join("reports", "sentiment_percentage_chart.png")
    plt.savefig(sentiment_chart)
    plt.close()


    return {
        "summary": summary.to_dict(orient="records"),
        "prediction_file": prediction_file,
        "summary_file": summary_file,
        "meetings_chart": meetings_chart,
        "sentiment_chart": sentiment_chart
    }
