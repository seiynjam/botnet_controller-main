# Botnet Controller Dashboard — File Structure

วางไฟล์ตามโครงสร้างนี้แล้วรัน `python main.py`

```
project/
│
├── main.py                        ← entry point (แก้แล้ว)
├── config.py                      ← BOTS list (ของเดิม)
├── models.py                      ← Bus class (ของเดิม)
├── workers.py                     ← AttackWorker (ของเดิม)
│
└── widgets/
    ├── __init__.py                ← package init (ใหม่)
    ├── network_topology.py        ← zoomable topology (ใหม่)
    ├── modern_gauge.py            ← smooth arc gauge (ใหม่)
    └── network_chart.py           ← scrolling TX/RX chart (ใหม่)
```

## Dependencies

```
pip install PySide6 psutil paramiko pillow
```

## Widget Controls

| Widget | การใช้งาน |
|--------|----------|
| Topology | Scroll = Zoom in/out |
| Topology | Drag = Pan |
| Topology | Double-click = Reset zoom |
