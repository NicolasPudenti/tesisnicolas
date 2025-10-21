# tesisnicolas
tesis nicolas pudenti pasini
Sales Performance Sentiment Analysis

Este repositorio provee un pipeline completo para analizar el sentimiento de las respuestas de e-mail de un equipo de ventas y estimar cuántas reuniones debería haber agendado cada representante.

Estructura de Archivos

├── sales_performance.py      # Módulo principal con funciones de entrenamiento e inferencia
├── respuestas_train.csv      # CSV de entrenamiento: columnas [representante, respuesta, label]
├── respuestas_test.xlsx      # Excel de test: columnas [representante, respuesta]
├── predict.py                # Script CLI para inferencia en nuevos textos
├── app.py                    # API FastAPI para servicio de inferencia HTTP (opcional)
└── README.md                 # Documentación de uso


Instalación

Clona o descarga este repositorio y luego instala las dependencias:

pip install transformers accelerate torch torchvision torchaudio pandas matplotlib scikit-learn openpyxl fastapi uvicorn pydantic 

for windows.
pip install pywin32



> **Nota**: Asegúrate de usar el mismo intérprete de Python que tu entorno de Jupyter/producción.

Uso

1. Entrenar el modelo base

from sales_performance import train_base_model

train_base_model(
    train_csv='respuestas_train.csv',   # CSV con etiquetas
    output_dir='model_out',             # Carpeta donde se guardará el artefacto
    epochs=3,                           # Opcional: número de épocas
    batch_size=16                       # Opcional: tamaño de batch
)


El modelo entrenado se guardará en: model_out/sentiment_model/

2. Calcular reuniones esperadas por representante

from sales_performance import evaluate_expected_meetings

evaluate_expected_meetings(
    model_dir='model_out/sentiment_model',    # Ruta al modelo entrenado
    test_file='respuestas_test.xlsx',         # Excel o CSV sin etiquetas
    meet_probs={'negativa':0.05,'neutral':0.2,'positiva':0.6},
    report_dir='reports'                      # Carpeta para guardar gráficos
)


* Se detecta automáticamente `.xlsx` o `.csv`.
* Se genera `reports/expected_meetings.png` con un gráfico ordenado y anotado.
* Imprime en consola la tabla de reuniones esperadas (entero redondeado).

3. Inferencia Manual (Opcional)

Para predecir etiquetas y probabilidades en nuevos textos:

python predict.py model_out/sentiment_model "Otra respuesta..."
```
python predict.py model_out/sentiment_model "Otra"

predict.py will also allow to upload file to predict data.

after running select 1 if want to enter text and 
""""""
1. Text input
2. File input (Excel/CSV)
Enter 1 or 2: 1
Enter your texts (type 'done' to finish):
¿Agendamos reunión?
Gracias, no interesa.
done
""""

4. Despliegue como API (Opcional)

Inicia un servidor REST con FastAPI:


uvicorn app:app --host 0.0.0.0 --port 8000
http://127.0.0.1:8000/docs#/


Endpoint `/predict` acepta POST JSON:
click try it out and add text in json formate

```json
{ "texts": ["¿Agendamos reunión?","Gracias, no interesa."] }
```

You can also upload excel file. Press try it out and upload file to predict.

Retorna JSON con etiquetas y confidencias.

📈 Personalización

* Ajusta `meet_probs` según tus probabilidades históricas.
* Cambia `epochs` y `batch_size` acorde a tu dataset.
* Extiende gráficas o funciones para incluir métricas adicionales.


¡Listo! Con este pipeline tú como Manager podras procesar al final de mes las respuestas de tu equipo y obtener insights accionables para comparar expectativas vs. resultados reales.
