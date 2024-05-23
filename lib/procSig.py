import os
import sys
import signal
import subprocess
import psutil

def killByPID(pid):
  try:
    p = psutil.Process(pid)
  except psutil.NoSuchProcess:
    pass
  
def killFamilyByPID(pid):
  try:
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
      child.kill()
    parent.kill()
  except psutil.NoSuchProcess:
    pass