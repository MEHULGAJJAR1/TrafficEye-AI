# Required custom model

Place a **trusted, custom-trained Ultralytics YOLO26 axis-aligned detection checkpoint** here as `traffic-custom.pt`, or configure another local `.pt` filename in Settings.

Required class semantics (any order): **Bike, Car, Jeep, Van, Helmet, No-Helmet, Seatbelt, No-Seatbelt**. Exact normalized aliases are in `config/class_aliases.yaml`. Inspect your model's names and label definitions; a schema match alone is not proof of training quality. Do not rename generic classes to bypass validation.

No custom-trained weights were supplied with this project. They are not invented, embedded, or silently downloaded. Stock COCO YOLO26 weights contain neither the complete vehicle taxonomy nor the safety labels and are intentionally rejected. The synthetic demo works without PyTorch inference and is always labelled as scripted data.

Checkpoint loading can execute Python code. Only use checkpoints from trusted sources. Do not accept model uploads from unknown users. Ultralytics licensing (AGPL-3.0 or an appropriate enterprise licence) must be reviewed for your deployment. See `docs/MODEL_GUIDE.md`.
