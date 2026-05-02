import serial
import csv
import os
from datetime import datetime

# CHANGE THIS
PORT = "COM13"



BAUD = 115200

SAVE_ROOT = "imu_dataset"

os.makedirs(SAVE_ROOT, exist_ok=True)

ser = serial.Serial(PORT, BAUD)

print("Connected to Nano.")

while True:

    label = input("\nEnter digit label (0-9) or q to quit: ")

    if label.lower() == "q":
        break

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"session_{timestamp}_label_{label}.csv"

    filepath = os.path.join(SAVE_ROOT, filename)

    input("Press ENTER and write the digit in air...")

    print("Recording started.")
    print("Press CTRL+C to stop recording.")

    try:

        with open(filepath, "w", newline="") as f:

            writer = csv.writer(f)

            writer.writerow([
                "timestamp_ms",
                "ax",
                "ay",
                "az",
                "gx",
                "gy",
                "gz",
                "mx",
                "my",
                "mz",
                "label"
            ])

            while True:

                line = ser.readline().decode(errors="ignore").strip()

                parts = line.split(",")

                if len(parts) != 10:
                    continue

                writer.writerow(parts + [label])

    except KeyboardInterrupt:
        print(f"\nSaved: {filepath}")