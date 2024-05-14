import sys
import threading
import multiprocessing
import multiprocessing.managers
import logging
import time

from Config import Config
from modules import URL
from modules import CustomLogging

class HostSemaphoreMgr(multiprocessing.managers.Namespace):
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.HostSemaphore')
  
  def __init__(self, config):
    self.curRequest = dict()
    self.locker = dict()
    self.lock = multiprocessing.Lock()
    
    self.config = config
    CustomLogging.setLogConfig(self.mainLogger, self.config)
    
    self.releaserKillFlag = False
    self.releaser = threading.Thread(target=self.deadlockCheck, daemon=True)
    self.releaser.start()
  
  def acquire(self, id, sURL):
    if not sURL:
      return False
    
    try:
      tmp = self.locker[id]
    except KeyError:
      pass
    else:
      self.logger.error("Double lock acquire: {}".format(id))
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
      self.locker[id] = sHost
      return True
    finally:
      self.lock.release()

    if curHost <= 0:
      return False
    
    self.curRequest[sHost] -= 1
    self.locker[id] = sHost
    return True

  def release(self, id):
    try:
      sHost = self.locker[id]
    except KeyError:
      self.logger.debug("No key matched: {}".format(id))
      return False
    
    del(self.locker[id])
    
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
  
  def reviveReleaser(self):
    if not self.releaser.is_alive():
      self.releaser = threading.Thread(target=self.deadlockCheck, daemon=True)
      self.releaser.start()
  
  def deadlockCheck(self):
    sys.stderr = CustomLogging.StreamToLogger(self.logger, logging.CRITICAL)
    while True:
      cnt = 0
      while cnt < self.config.RecoveryDeadlockPeriod: 
        if self.releaserKillFlag:
          sys.exit(0)
        cnt += 1
        time.sleep(1)
      
      self.lock.acquire(block=True)
      urls = list(self.curRequest.keys())
      for key in self.locker.keys():
        try:
          urls.remove(self.locker[key])
        except (ValueError, KeyError):
          pass
          
      for url in urls:
        self.logger.info("Release unused url: ", url)
        try:
          del(self.curRequest[url])
        except KeyError:
          pass
      self.lock.release()
  
  def showURL(self, sURL):
    try:
      semaphore = self.curRequest[sURL]
    except KeyError:
      return None

    return (semaphore, [id for id, url in self.locker.items() if url == sURL])
  
  def showID(self, ID):
    try:
      return self.locker[ID]
    except KeyError:
      return None
    
  def showAll(self):
    sURL = list(self.curRequest.keys())
    for id, url in self.locker.items():
      try:
        sURL.remove(url)
      except ValueError:
        pass
    
    return [(id,url) for id, url in self.locker.items()], sURL
    
  
  def changeConfig(self, config):
    self.config = config

if __name__=="__main__":
  pass
