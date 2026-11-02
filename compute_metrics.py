import os
import sys

# Ensure workspace root is in python path
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from pipeline.compute_metrics import print_report

if __name__ == "__main__":
    print_report()

