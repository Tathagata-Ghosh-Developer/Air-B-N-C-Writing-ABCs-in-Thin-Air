import argparse
import time
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as T
from PIL import Image

# ==========================================
# 1. TRAINED MODEL ARCHITECTURE
# ==========================================
class GhostModule(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size=3, ratio=2, stride=1, dw_kernel=3):
        super().__init__()
        init_ch = math.ceil(out_ch / ratio)
        new_ch  = init_ch * (ratio - 1)
        self.primary = nn.Sequential(
            nn.Conv2d(in_ch, init_ch, kernel_size, stride, kernel_size // 2, bias=False),
            nn.BatchNorm2d(init_ch),
            nn.ReLU(inplace=True),
        )
        self.cheap = nn.Sequential(
            nn.Conv2d(init_ch, new_ch, dw_kernel, 1, dw_kernel // 2, groups=init_ch, bias=False),
            nn.BatchNorm2d(new_ch),
            nn.ReLU(inplace=True),
        )
        self.out_ch = out_ch
    def forward(self, x):
        x1 = self.primary(x)
        x2 = self.cheap(x1)
        out = torch.cat([x1, x2], dim=1)
        return out[:, :self.out_ch]

class ECA(nn.Module):
    def __init__(self, channels, gamma=2, b=1):
        super().__init__()
        t = int(abs((math.log2(channels) + b) / gamma))
        k = t if t % 2 else t + 1
        self.k = max(k, 3)
        self.conv = nn.Conv1d(1, 1, kernel_size=self.k, padding=self.k // 2, bias=False)
        self.sig  = nn.Sigmoid()
    def forward(self, x):
        b, c, _, _ = x.shape
        y = F.adaptive_avg_pool2d(x, 1).view(b, 1, c)
        y = self.sig(self.conv(y)).view(b, c, 1, 1)
        return x * y

class GhostBlock(nn.Module):
    def __init__(self, in_ch, out_ch, stride=1, use_eca=True):
        super().__init__()
        self.expand = GhostModule(in_ch, out_ch, kernel_size=3, stride=stride)
        self.eca    = ECA(out_ch) if use_eca else nn.Identity()
        self.proj   = GhostModule(out_ch, out_ch, kernel_size=3, stride=1)
        if stride == 1 and in_ch == out_ch:
            self.shortcut = nn.Identity()
        else:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 1, stride, 0, bias=False),
                nn.BatchNorm2d(out_ch),
            )
        self.relu = nn.ReLU(inplace=True)
    def forward(self, x):
        s = self.shortcut(x)
        x = self.expand(x)
        x = self.eca(x)
        x = self.proj(x)
        return self.relu(x + s)

class TrajectoryGhostNet(nn.Module):
    def __init__(self, n_classes=10, width=1.0, dropout=0.2, use_eca=True):
        super().__init__()
        ch = lambda c: max(8, int(round(c * width)))
        self.stem = nn.Sequential(
            nn.Conv2d(1, ch(16), 3, 2, 1, bias=False),
            nn.BatchNorm2d(ch(16)),
            nn.ReLU(inplace=True),
        )
        self.stage1 = GhostBlock(ch(16), ch(24), stride=2, use_eca=use_eca)
        self.stage2 = GhostBlock(ch(24), ch(40), stride=2, use_eca=use_eca)
        self.stage3 = GhostBlock(ch(40), ch(64), stride=2, use_eca=use_eca)
        self.gap    = nn.AdaptiveAvgPool2d(1)
        self.dropout = nn.Dropout(dropout)
        self.fc      = nn.Linear(ch(64), n_classes)
    def forward(self, x):
        x = self.stem(x)
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.gap(x).flatten(1)
        x = self.dropout(x)
        return self.fc(x)

# ==========================================
# 2. INFERENCE PIPELINE
# ==========================================
def run_pytorch_inference(image_path, weights_path, csv_path = None, img_size=96, n_classes=10, width=1.0, dropout=0.2, use_eca=True):
    print("[*] Initializing TrajectoryGhostNet Architecture...")
    # Instantiate the Trained Model
    model = TrajectoryGhostNet(n_classes=n_classes, width=width, dropout=dropout, use_eca=use_eca)

    print(f"[*] Loading Model Parameters (Weights) from {weights_path}...")
    # Load the parameters (state_dict) into the model architecture
    model.load_state_dict(torch.load(weights_path, map_location='cpu'))

    # Set to evaluation mode
    model.eval()

    print(f"[*] Loading and Preprocessing Image: {image_path}...")
    img = Image.open(image_path).convert('L')

    # Exactly match the validation/test dataloader transform pipeline
    transform = T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor()
    ])

    # Apply transforms and add batch dimension -> Shape: (1, 1, 96, 96)
    input_tensor = transform(img).unsqueeze(0)

    print("[*] Running PyTorch Inference...")
    start_time = time.time()

    # Disable gradients for inference speed
    with torch.no_grad():
        logits = model(input_tensor)
        probabilities = F.softmax(logits, dim=1)

    predicted_class = int(logits.argmax(1)[0])
    confidence = probabilities[0][predicted_class].item() * 100
    inference_time = (time.time() - start_time) * 1000

    print("\n" + "="*40)
    print(" PYTORCH INFERENCE RESULTS")
    print("="*40)
    print(f" Predicted Label : Class {predicted_class}")
    print(f" Confidence      : {confidence:.2f} %")
    print(f" Inference Time  : {inference_time:.2f} ms")
    print("="*40 + "\n")

    # ==========================================
    # SAVE RESULTS TO SAME TEXT FILE
    # ==========================================

    with open("serial_log.txt", "a") as f:

        f.write("\n")
        f.write("="*40 + "\n")
        f.write(" RPI PYTORCH INFERENCE\n")
        f.write("="*40 + "\n")
        f.write(f"CSV File         : {csv_path}\n")
        f.write(f"Image            : {image_path}\n")
        f.write(f"Predicted Label  : {predicted_class}\n")
        f.write(f"Confidence       : {confidence:.2f} %\n")
        f.write(f"Inference Time   : {inference_time:.2f} ms\n")
        
        f.write("="*40 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Raspberry Pi PyTorch Trajectory Inference")
    parser.add_argument("--image", type=str, required=True, help="Path to input image")
    parser.add_argument("--weights", type=str, default="artifacts/final_fp32.pt", help="Path to the trained model parameters (.pt)")

    # These must match your BEST Optuna parameters if they differ from the defaults!
    parser.add_argument("--size", type=int, default=96, help="Image size")
    parser.add_argument("--width", type=float, default=1.0, help="Model width multiplier")
    parser.add_argument("--dropout", type=float, default=0.2, help="Dropout rate")
    parser.add_argument("--csv", type=str, required=False, help="Path to CSV file")
    args = parser.parse_args()

    run_pytorch_inference(args.image, args.weights, csv_path=args.csv, img_size=args.size, width=args.width, dropout=args.dropout)
 
# python3 rpi_pytorch_inference.py   --image "/home/rpi4/dataset/session_20260502_110516_label_0/trajectory.png"   --weights "baseline_fp32_2.pt"   --csv "/home/rpi4/dataset/session_20260502_110516_label_0/imu_data.csv"
