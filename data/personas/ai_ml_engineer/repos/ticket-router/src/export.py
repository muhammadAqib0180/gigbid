import torch

torch.onnx.export(model, dummy_input, "model.onnx", opset_version=17)
session = onnxruntime.InferenceSession("model.onnx")
