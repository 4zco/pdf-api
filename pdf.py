from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pdf2image import convert_from_path
import pytesseract
import PyPDF2
import json
import os
import re
import time
import subprocess

# === SETTINGS ===
WATCH_FOLDER = '/home/kali/Desktop/API/'
JSON_OUTPUT_PATH = os.path.join(WATCH_FOLDER, 'db.json')


# === Extract text from PDF (with OCR fallback) and save to .txt ===
def extract_text_from_pdf(pdf_path):
    text = ""

    # Try PyPDF2 first
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except:
        pass

    # Use OCR if no extractable text
    if not text.strip():
        print("🔍 No extractable text found — using OCR...")
        try:
            images = convert_from_path(pdf_path)
            for img in images:
                text += pytesseract.image_to_string(img) + "\n"

            # ✅ Save OCR result as .txt
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            txt_path = os.path.join(WATCH_FOLDER, base_name + "_ocr.txt")
            with open(txt_path, "w", encoding="utf-8") as txt_file:
                txt_file.write(text)
            print(f"📝 OCR text saved to: {txt_path}")

        except Exception as e:
            print(f"❌ OCR failed: {e}")

    return text


# === Extract invoice fields using regex (tolerant to line breaks) ===
def extract_invoice_fields(text):
    # Extract invoice number
    invoice_number = re.search(
        r'Invoice\s*Number\s*\n\s*(\d{4,})',
        text, re.IGNORECASE
    )

    # Match the line with all 3 fields together
    multi_field_match = re.search(
        r'Billed\s*To\s+Date\s*Issued\s+Due\s*Date\s*\n\s*(.+?)\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})',
        text, re.IGNORECASE
    )

    billed_to = multi_field_match.group(1).strip() if multi_field_match else None
    date_issued = multi_field_match.group(2).strip() if multi_field_match else None
    # due_date = multi_field_match.group(3).strip() if you want to extract this later

    return {
        "invoice_number": invoice_number.group(1) if invoice_number else None,
        "date_issued": date_issued,
        "billed_to": billed_to
    }


# === Check for Duplicates by Invoice Number ===
def is_duplicate(existing_data, invoice_number):
    return any(inv.get("invoice_number") == invoice_number for inv in existing_data.get("invoices", []))


# === Process a Single PDF File ===
def process_pdf(pdf_path):
    print(f"📄 Processing: {os.path.basename(pdf_path)}")

    # Step 1: Attempt to send to printer
    try:
        print("🖨️ Sending to printer...")
        subprocess.run(['lpr', pdf_path], check=True)
        print("✅ Sent to printer.")
    except Exception as e:
        print(f"⚠️ Failed to print: {e} — continuing anyway.")

    # Step 2: Wait a moment before continuing
    time.sleep(3)

    # Step 3: Extract text
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print("⚠️ No text found in file, skipping.")
        return

    # Step 4: Extract invoice fields
    data = extract_invoice_fields(text)
    if not data["invoice_number"]:
        print("⚠️ Missing invoice number, skipping.")
        return

    # Step 5: Load or initialize db.json
    if os.path.exists(JSON_OUTPUT_PATH):
        with open(JSON_OUTPUT_PATH, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    else:
        existing_data = {"invoices": []}

    # Step 6: Avoid duplicates
    if is_duplicate(existing_data, data["invoice_number"]):
        print(f"⚠️ Duplicate invoice #{data['invoice_number']}, skipping.")
        return

    # Step 7: Append and save
    existing_data["invoices"].append(data)
    with open(JSON_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=4)

    print(f"✅ Invoice #{data['invoice_number']} added.")


# === Watchdog Event Handler ===
class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.lower().endswith('.pdf'):
            print(f"🕒 Detected new PDF: {event.src_path}")
            time.sleep(5)  # Wait for file to finish saving
            process_pdf(event.src_path)


# === Start Watcher ===
if __name__ == "__main__":
    print(f"👀 Watching for new PDFs in: {WATCH_FOLDER}")
    event_handler = PDFHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
