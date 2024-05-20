import os
import sys
import signal
import subprocess

def killByPID(pid):
  if sys.platform == 'win32':
    p = subprocess.Popen(["taskkill", "/pid", str(pid), "/t", "/f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  elif sys.platform == 'linux':
    p = subprocess.Popen(["kill", "-9", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)