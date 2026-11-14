---
id: case-defect-detection
type: case_study
project: defect-detection
client_industry: manufacturing
date: 2023-04
skills: [PyTorch, YOLO, OpenCV, computer vision]
synthetic: true
---

# Visual defect detection on a production line

**Client:** a manufacturing company (anonymised, synthetic)  
**Year:** 2023

## The problem

The client's manual inspection missed hairline scratches on aluminium panels.

## What I did

I labelled 6,000 images, trained a YOLO detector and tuned it for the line's lighting. The work used PyTorch, YOLO, OpenCV and computer vision. The model is exported to a framework-neutral graph for fast inference. Inference runs on a small device right next to the camera.

## Results

- Detected 96% of scratches at 30 frames per second.
- False rejects stayed under 1.5%.

## What I would do differently

I would agree the evaluation metric with the client in week one; most of the rework came from changing what "good" meant halfway through.
