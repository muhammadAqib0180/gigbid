#!/bin/sh
# runs on an NVIDIA Jetson next to the camera
python3 infer.py --engine model.trt --camera /dev/video0 --fps 30
