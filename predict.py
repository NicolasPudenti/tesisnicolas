import os
import re
import sys
import pandas as pd
import torch
from transformers import BertTokenizerFast, BertForSequenceClassification
import matplotlib.pyplot as plt
import platform
import tkinter as tk
from tkinter import filedialog
from openpyxl import load_workbook

# ---- Config ----
DEFAULT_MODEL_DIR = "model_out/sentiment_model"
id2label = {0: "negativa", 1: "neutral", 2: "positiva"}
meet_probs = {"negativa": 0.05, "neutral": 0.2, "positiva": 0.6}

# ---- Load model/tokenizer once ----
print("Loading model...")
tokenizer = BertTokenizerFast.from_pretrained(DEFAULT_MODEL_DIR)
model = BertForSequenceClassification.from_pretrained(DEFAULT_MODEL_DIR)
model.eval()
print("Model loaded.")


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
        col_letter = col[0].column_letter  # get column letter (A, B, C...)
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        adjusted_width = max_length + 2  # add padding
        ws.column_dimensions[col_letter].width = adjusted_width

    wb.save(file_path)

# ---- Functions ----
def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^a-záéíóúñü¡!?,.\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()

def predict_sentiment_batch(texts, batch_size=512):
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        texts_clean = [clean_text(t) for t in batch]
        enc = tokenizer(texts_clean, padding=True, truncation=True, max_length=128, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        for text, p in zip(batch, probs):
            label = id2label[p.argmax()]
            conf = float(p.max())
            expected_meeting = meet_probs[label]
            results.append((text, label, conf, expected_meeting))
    return results


def process_file():
    handle_open_files()
    # Open file dialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Select Excel or CSV file",
        filetypes=[("Excel files", "*.xlsx *.xls"), ("CSV files", "*.csv")]
    )
    if not file_path:
        print("No file selected.")
        return

    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.xls', '.xlsx']:
        df = pd.read_excel(file_path, engine="openpyxl")
    else:
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='latin1')

    if "respuesta" not in df.columns or "representante" not in df.columns:
        print("File must contain 'respuesta' and 'representante' columns.")
        return
    # Clean the text and predict sentiment
    df["cleaned"] = df["respuesta"].astype(str).apply(clean_text)
    results = predict_sentiment_batch(df["respuesta"].tolist())
    df["label"] = [r[1] for r in results]              
    df["confidence"] = [round(r[2], 3) for r in results]  
    df["expected_meeting"] = [r[3] for r in results]     

    # Map label to sentiment percentage
    sentiment_map = {"negativa": 0, "neutral": 50, "positiva": 100}
    df["sentiment_percentage"] = df["label"].map(sentiment_map)

    # Reset index
    df.reset_index(drop=True, inplace=True)

    # --- Save full prediction file ---
    os.makedirs("reports", exist_ok=True)
    report_file = os.path.join("reports", "predicted_meetings.xlsx")
    df.to_excel(report_file, index=False)
    autofit_excel_columns(report_file)
    print(f"\nFull prediction report saved to {report_file}\n")

    # ---- Summary tables ----
    summary = df.groupby('representante').agg(
        expected_meetings=('expected_meeting', 'sum'),
        total_messages=('respuesta', 'count'),
        avg_percentage=('sentiment_percentage', 'mean')
    ).reset_index()
    summary['avg_percentage'] = summary['avg_percentage'].round().astype(int)

    summary_sorted = summary.sort_values('avg_percentage', ascending=False)

    # Save summary
    summary_file = os.path.join("reports", "expected_meetings.xlsx")
    summary_sorted.to_excel(summary_file, index=False)
    autofit_excel_columns(summary_file)
    print(f"Expected meetings summary saved to {summary_file}\n")
    print("Summary:")
    print(summary_sorted)
    summary_sorted = summary.sort_values('expected_meetings', ascending=False)
    # ---- Graph: Expected meetings ----
    plt.figure(figsize=(10, 6))
    ax = summary_sorted.set_index('representante')['expected_meetings'].plot(kind='bar', color='skyblue')
    ax.set_title('Reuniones Esperadas por Representante')
    ax.set_ylabel('Reuniones Esperadas')
    ax.set_xlabel('Representante')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    for p in ax.patches:
        ax.annotate(f"{p.get_height():.2f}",
                    (p.get_x() + p.get_width() / 2, p.get_height()),
                    ha='center', va='bottom', fontsize=9)
    plt.xticks(rotation=45)
    plt.tight_layout()
    meetings_chart = os.path.join("reports", "expected_meetings_chart.png")
    plt.savefig(meetings_chart)
    plt.close()

    # ---- Graph: Sentiment percentage ----
    plt.figure(figsize=(10, 6))
    summary_sorted = summary.sort_values('avg_percentage', ascending=False)
    ax2 = summary_sorted.set_index('representante')['avg_percentage'].plot(kind='bar', color='orange')
    
    ax2.set_title('Average Sentiment Percentage by Representative')
    ax2.set_ylabel('Sentiment Percentage (%)')
    ax2.set_xlabel('Representative')
    ax2.set_ylim(0, 110)  #  Set y-axis from 0 to 110
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    for p in ax2.patches:
        ax2.annotate(f"{int(p.get_height())}%",
                    (p.get_x() + p.get_width() / 2, p.get_height()),
                    ha='center', va='bottom', fontsize=9)

    plt.xticks(rotation=45)
    plt.tight_layout()
    sentiment_chart = os.path.join("reports", "sentiment_percentage_chart.png")
    plt.savefig(sentiment_chart)
    plt.close()

    print(f"Charts saved:\n- {meetings_chart}\n- {sentiment_chart}")

# ---- Main ----
def main():
    if len(sys.argv) > 2:
        texts = sys.argv[2:]
        results = predict_sentiment_batch(texts)
        print("\nPredictions:")
        for text, label, conf, expected_meeting in results:
            print(f'"{text}" → {label} (conf={conf:.2f}, expected_meeting={expected_meeting})')
        return

    print("Choose input type:")
    print("1. Text input")
    print("2. File input (Excel/CSV)")
    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        print("Enter your texts (type 'done' to finish):")
        texts = []
        while True:
            t = input()
            if t.lower() == "done":
                break
            if t.strip():
                texts.append(t)
        if not texts:
            print("No texts entered.")
            return
        results = predict_sentiment_batch(texts)
        print("\nPredictions:")
        for text, label, conf, expected_meeting in results:
            print(f'"{text}" → {label} (conf={conf:.2f}, expected_meeting={expected_meeting})')

    elif choice == "2":
        process_file()
    else:
        print("Invalid choice.")

if __name__ == "__main__":
    main()