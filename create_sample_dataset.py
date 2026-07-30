import numpy as np
import pandas as pd

# Generate realistic 100-row industrial telemetry dataset for 4 CNC machines
np.random.seed(42)

timestamps = pd.date_range("2026-07-29 08:00", periods=100, freq="15min").astype(str)
machines = ["CNC-MACHINE-01", "CNC-MACHINE-02", "CNC-MACHINE-03", "CNC-MACHINE-04"]

data = []
for i in range(100):
    m_id = machines[i % 4]
    
    # Introduce Machine 03 as the "Problem Child" with higher temperature, vibration & downtime
    if m_id == "CNC-MACHINE-03":
        temp = np.random.normal(94.5, 4.5)  # Elevated temp
        vib = np.random.normal(0.85, 0.12)  # High vibration
        press = np.random.normal(135.0, 15.0)
        rpm = np.random.normal(3200, 150)
        downtime = np.random.choice([0, 15, 30, 45], p=[0.4, 0.3, 0.2, 0.1])
        status = "FAULT" if downtime > 20 else "OPERATIONAL"
    else:
        temp = np.random.normal(75.0, 2.5)   # Normal temp
        vib = np.random.normal(0.35, 0.04)  # Normal vibration
        press = np.random.normal(110.0, 5.0)
        rpm = np.random.normal(2800, 50)
        downtime = np.random.choice([0, 5], p=[0.9, 0.1])
        status = "OPERATIONAL"

    data.append({
        "timestamp": timestamps[i],
        "machine_id": m_id,
        "temperature": round(temp, 2),
        "vibration": round(vib, 3),
        "pressure": round(press, 2),
        "rpm": round(rpm, 0),
        "status": status,
        "downtime_minutes": downtime,
    })

df = pd.DataFrame(data)
df.to_csv("sample_manufacturing_telemetry.csv", index=False)
print("Successfully generated 'sample_manufacturing_telemetry.csv' with 100 rows for instant testing!")
