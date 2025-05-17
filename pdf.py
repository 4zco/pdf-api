from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pdf2image import convert_from_path
import pytesseract
import json
import os
import re
import time
import subprocess

# === SETTINGS ===
WATCH_FOLDER = '/home/kali/Desktop/API/Watch'
JSON_OUTPUT_PATH = os.path.join(WATCH_FOLDER, 'db.json')

# === Extract text from PDF (OCR only) and save to .txt ===
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        print("🧠 Using OCR to extract text...")
        images = convert_from_path(pdf_path)
        for img in images:
            text += pytesseract.image_to_string(img) + "\n"

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        txt_path = os.path.join(WATCH_FOLDER, base_name + "_ocr.txt")
        with open(txt_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(text)
        print(f"📝 OCR text saved to: {txt_path}")

    except Exception as e:
        print(f"❌ OCR failed: {e}")

    return text

# === Extract invoice fields using robust regex ===
def extract_invoice_fields(text):
    fields = {}

    date_match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", text)
    fields["Invoice Date"] = date_match.group(0) if date_match else None

    times = re.findall(r"\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)\b", text, flags=re.IGNORECASE)
    fields["Invoice Time"] = times[-1] if times else None

    # FIXED: Multi-line invoice number support
    match = re.search(r"Invoice\s*No\.?\s*\n\s*([0-9]+)\s*[-]?\s*([0-9]+)", text, re.IGNORECASE)
    if match:
        inv_no = f"{match.group(1)}-{match.group(2)}"
    else:
        inv_no = None
    fields["Invoice Number"] = inv_no

    # Sold To Block
    sold_match = re.search(r"Sold to[^\n]*\n(?P<block>(?:(?!^Delivery).*\n)*)", text, flags=re.MULTILINE)
    sold_block = sold_match.group("block") if sold_match else ""
    sold_lines = [ln.strip() for ln in sold_block.splitlines() if ln.strip()]
    cleaned_lines = []
    for ln in sold_lines:
        if '//' in ln:
            ln = ln.split('//')[0].strip()
        ln = re.sub(r"\s{2,}", " ", ln)
        if ln:
            cleaned_lines.append(ln)
    if cleaned_lines:
        min_indent = min(len(ln) - len(ln.lstrip()) for ln in cleaned_lines)
        if min_indent > 0:
            cleaned_lines = [ln[min_indent:] for ln in cleaned_lines]
    fields["Sold To"] = "\n".join(cleaned_lines).strip() if cleaned_lines else None

    # Customer Number
    match = re.search(r"(?P<cust>\d+)\s*\(\d{3}\)\s*\d{3}-\d{4}", text)
    fields["Customer Number"] = match.group("cust") if match else None

    # Vehicle / Order
    match = re.search(r"(?:(?:P\/U|DELIVERY)\s*)?(?P<order>[^(\n]+?)\s+(?P<custno>\d+)\s+\(\d{3}\)\s*\d{3}-\d{4}", text)
    fields["Vehicle"] = match.group("order").strip() if match else None

    # Clerk
    match = re.search(r"Clerk.*\n\s*(?:\d+\s+)?(?P<name>[A-Za-z ]+?)(?=\s+(?:Net\b|COD\b|C\.O\.D\b|EXEMPT\b))", text, flags=re.IGNORECASE)
    fields["Clerk"] = match.group("name").strip() if match else None

    # Final Total
    amounts = re.findall(r"\d+\.\d{2}", text)
    fields["Final Total"] = amounts[-1] if amounts else None

    return fields

# === Check for Duplicates by Invoice Number ===
def is_duplicate(existing_data, invoice_number):
    return any(inv.get("Invoice Number") == invoice_number for inv in existing_data.get("invoices", []))

# === Process a Single PDF File ===
def process_pdf(pdf_path):
    print(f"📄 Processing: {os.path.basename(pdf_path)}")
    try:
        print("🖨️ Sending to printer...")
        subprocess.run(['lpr', pdf_path], check=True)
        print("✅ Sent to printer.")
    except Exception as e:
        print(f"⚠️ Failed to print: {e} — continuing anyway.")

    time.sleep(1)
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print("⚠️ No text found in file, skipping.")
        return

    data = extract_invoice_fields(text)
    if not data.get("Invoice Number"):
        print("⚠️ Missing invoice number, skipping.")
        return

    if os.path.exists(JSON_OUTPUT_PATH):
        with open(JSON_OUTPUT_PATH, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    else:
        existing_data = {"invoices": []}

    if is_duplicate(existing_data, data["Invoice Number"]):
        print(f"⚠️ Duplicate invoice #{data['Invoice Number']}, skipping.")
        return

    existing_data["invoices"].append(data)
    with open(JSON_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=4)

    print(f"✅ Invoice #{data['Invoice Number']} added.")

# === Watchdog Event Handler ===
class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.lower().endswith('.pdf'):
            print(f"🕒 Detected new PDF: {event.src_path}")
            time.sleep(2)
            process_pdf(event.src_path)

# === Start Watcher ===
if __name__ == "__main__":
    print(f"🔍 Watching for new PDFs in: {WATCH_FOLDER}")
    event_handler = PDFHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
