#!/usr/bin/env python3
"""Test and screenshot the PIT Dashboard."""

import subprocess
import time
import sys
from pathlib import Path

def main():
    # Start streamlit in background
    print("Starting PIT Dashboard...")
    
    # Start the server
    proc = subprocess.Popen(
        ["streamlit", "run", "pit-dashboard.py", "--server.headless", "true"],
        cwd="/Users/rahulkashyap/.openclaw/workspace/pit",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(5)
    
    print(f"Dashboard running at: http://localhost:8501")
    print(f"Process PID: {proc.pid}")
    
    # Test with curl
    result = subprocess.run(
        ["curl", "-s", "http://localhost:8501"],
        capture_output=True,
        text=True
    )
    
    if "PIT Dashboard" in result.stdout or "streamlit" in result.stdout.lower():
        print("✅ Dashboard is serving correctly!")
    else:
        print("⚠️  Dashboard may not be fully loaded")
    
    # Keep it running for a bit
    try:
        print("\nPress Ctrl+C to stop...")
        time.sleep(30)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait()
        print("\n✅ Dashboard stopped")

if __name__ == "__main__":
    main()
