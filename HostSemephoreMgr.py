import multiprocessing
import multiprocessing.managers

from Config import Config
from modules import URL

class HostSemaphoreMgr(multiprocessing.managers.Namespace):
  def __init__(self, config):
    self.curRequest = dict()
    self.lock = multiprocessing.Lock()
    
    self.config = config
  
  def acquire(self, sURL):
    if not sURL:
      return False
    
    sHost = URL.getHost(sURL)
    for semaphore in self.config.URLSemaphore.keys():
      if semaphore in sHost:
        sHost = semaphore
        break
    
    if not self.lock.acquire(block=True, timeout=3.0):
      return False

    try:
      curHost = self.curRequest[sHost]
    except KeyError:
      try:
        preSet = self.config.URLSemaphore[sHost]
      except KeyError:
        self.curRequest[sHost] = self.config.DefaultSemaphore
      else:
        self.curRequest[sHost] = preSet
      
      self.curRequest[sHost] -= 1
      return True
    finally:
      self.lock.release()

    if curHost <= 0:
      return False
    
    self.curRequest[sHost] -= 1
    return True

  def release(self, sURL):
    if not sURL:
      return False
    
    sHost = URL.getHost(sURL)
    for semaphore in self.config.URLSemaphore.keys():
      if semaphore in sHost:
        sHost = semaphore
        break
    
    try:
      curHost = self.curRequest[sHost]
    except KeyError:
      return False
    
    self.curRequest[sHost] += 1
    try:
      limit = self.config.URLSemaphore[sHost]
    except KeyError:
      limit = self.config.DefaultSemaphore
      
    if self.curRequest[sHost] >= limit:
      self.lock.acquire(block=True)
      try:
        del(self.curRequest[sHost])
      except KeyError:
        pass
      self.lock.release()
    
    return True
  
  def changeConfig(self, config):
    self.config = config

if __name__=="__main__":
  pass
