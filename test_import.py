import sys
import os
sys.path.append(os.getcwd())
try:
    from tabs.prize_impact import render_prize_impact
    print("Import successful")
except ModuleNotFoundError as e:
    print(f"Import failed: {e}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Contents of tabs/: {os.listdir('tabs')}")
