FROM python:3.13-slim

WORKDIR /code

# System deps kept minimal for Milestone 0. Revisit if a later milestone
# needs something extra (e.g. wkhtmltopdf / weasyprint system libs for
# Milestone 14's PDF generation).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
