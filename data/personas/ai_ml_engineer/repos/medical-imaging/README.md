# medical-imaging

Medical image classification prototype (synthetic portfolio repository).

## Stack

- PyTorch
- computer vision
- transfer learning

## Setup

```bash
make install
make test
```

## Architecture

The service fine-tuned an ImageNet backbone with heavy augmentation and site-wise validation. See `src/` for the pipeline entry points.
