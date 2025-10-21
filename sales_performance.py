import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import torch
from torch.utils.data import Dataset
from transformers import BertTokenizerFast, BertForSequenceClassification, Trainer, TrainingArguments

def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'http\S+', '', text)
    # text = re.sub(r'[^a-záéíóúñü\s]', '', text)
    text = re.sub(r"[^a-záéíóúñü¡!?,.\s]", "", text)
    return re.sub(r'\s+', ' ', text).strip()

class EmailDataset(Dataset):
    def __init__(self, texts, labels, tokenizer):
        texts = texts.tolist() if hasattr(texts, 'tolist') else list(texts)
        labels = labels.tolist() if hasattr(labels, 'tolist') else list(labels)
        self.encodings = tokenizer(
            texts, padding=True, truncation=True, max_length=128, return_tensors='pt'
        )
        label2id = {'negativa':0, 'neutral':1, 'positiva':2}
        self.labels = torch.tensor([label2id[l] for l in labels])

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item['labels'] = self.labels[idx]
        return item

def train_base_model(train_csv: str, output_dir: str,
                     epochs: int = 3, batch_size: int = 16):
    df = pd.read_csv(train_csv)
    df['cleaned'] = df['respuesta'].astype(str).apply(clean_text)
    train_df, val_df = pd.DataFrame(), pd.DataFrame()
    from sklearn.model_selection import train_test_split
    train_df, val_df = train_test_split(
        df, test_size=0.2, stratify=df['label'], random_state=42
    )

    tokenizer = BertTokenizerFast.from_pretrained('dccuchile/bert-base-spanish-wwm-cased')
    train_ds = EmailDataset(train_df['cleaned'], train_df['label'], tokenizer)
    val_ds   = EmailDataset(val_df['cleaned'],   val_df['label'],   tokenizer)

    model = BertForSequenceClassification.from_pretrained(
        'dccuchile/bert-base-spanish-wwm-cased', num_labels=3
    )

    args = TrainingArguments(
        output_dir=os.path.join(output_dir, 'base'),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        eval_strategy='steps', eval_steps=100,
        save_steps=100, logging_steps=10,
        overwrite_output_dir=True
    )

    from sklearn.metrics import precision_recall_fscore_support, accuracy_score
    import numpy as np
    def compute_metrics(pred):
        labels = pred.label_ids
        preds  = np.argmax(pred.predictions, axis=1)
        p, r, f1, _ = precision_recall_fscore_support(
            labels, preds, average='weighted'
        )
        acc = accuracy_score(labels, preds)
        return {'accuracy': acc, 'precision': p, 'recall': r, 'f1': f1}

    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=val_ds,
        tokenizer=tokenizer, compute_metrics=compute_metrics
    )
    trainer.train()

    save_dir = os.path.join(output_dir, 'sentiment_model')
    os.makedirs(save_dir, exist_ok=True)
    model.save_pretrained(save_dir)
    tokenizer.save_pretrained(save_dir)
    print(f"Modelo base entrenado y guardado en: {save_dir}")

def evaluate_expected_meetings(model_dir: str, test_file: str,
                               meet_probs: dict, report_dir: str):
    ext = os.path.splitext(test_file)[1].lower()
    if ext in ['.xls', '.xlsx']:
        df = pd.read_excel(test_file, engine='openpyxl')
    else:
        try:
            df = pd.read_csv(test_file, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(test_file, encoding='latin-1')

    df['cleaned'] = df['respuesta'].astype(str).apply(clean_text)

    tokenizer = BertTokenizerFast.from_pretrained(model_dir)
    model     = BertForSequenceClassification.from_pretrained(model_dir)
    model.eval()

    texts = df['cleaned'].tolist()
    enc = tokenizer(texts, padding=True, truncation=True,
                    max_length=128, return_tensors='pt')
    with torch.no_grad():
        logits = model(**enc).logits
    probs = torch.softmax(logits, dim=-1).cpu().numpy()
    id2label = {0:'negativa', 1:'neutral', 2:'positiva'}
    df['pred'] = [id2label[p.argmax()] for p in probs]

    df['expected_meeting'] = df['pred'].map(meet_probs)

    # Save full table to Excel
    os.makedirs(report_dir, exist_ok=True)
    full_excel_path = os.path.join(report_dir, 'predicted_meetings.xlsx')
    df.to_excel(full_excel_path, index=False)

    # Aggregate per representative
    summary = df.groupby('representante')['expected_meeting'] \
                .sum().reset_index(name='expected_meetings')
    summary['expected_meetings'] = summary['expected_meetings'].round(2)

    summary_sorted = summary.sort_values('expected_meetings', ascending=False)
    # Save sorted expected meetings summary
    summary_sorted_path = os.path.join(report_dir, 'expected_meetings.xlsx')
    summary_sorted.to_excel(summary_sorted_path, index=False)
    print(f"Resumen guardado en: {summary_sorted_path}")

    plt.figure(figsize=(10, 6))
    ax = summary_sorted.set_index('representante')['expected_meetings'].plot(kind='bar')
    ax.set_title('Reuniones Esperadas por Representante')
    ax.set_ylabel('Reuniones Esperadas')
    ax.set_xlabel('Representante')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    for p in ax.patches:
        ax.annotate(f"{p.get_height():.1f}",
                    (p.get_x() + p.get_width() / 2, p.get_height()),
                    ha='center', va='bottom', fontsize=9)
    plt.xticks(rotation=45)
    plt.tight_layout()
    graph_path = os.path.join(report_dir, 'expected_meetings.png')
    plt.savefig(graph_path)
    plt.close()

    print(summary)
    print(f"Gráfico guardado en: {graph_path}")
    print(f"Tabla completa guardada en: {full_excel_path}")


if __name__ == "__main__":
  
    train_base_model(
        train_csv='respuestas_train.csv', 
        output_dir='model_out',            
        epochs=3,                          
        batch_size=16                       
    )


    evaluate_expected_meetings(
        model_dir='model_out/sentiment_model',  
        test_file='respuestas_test.xlsx',       
        meet_probs={'negativa': 0.05, 'neutral': 0.2, 'positiva': 0.6},  
        report_dir='reports'                     
    )
