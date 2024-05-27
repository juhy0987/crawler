import sys
import time
import queue
import pickle
import logging
import atexit
import threading
import multiprocessing
import multiprocessing.managers

import redis
import redis.exceptions

from lib import CustomLogging

# from . import ConfigMgr

class URLQMgr(multiprocessing.managers.Namespace):
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.URLQ')
  
  def __init__(self, sFilePath, configMgr):
    super().__init__()
    self.HostIP = ""
    self.Port = 0
    self.URLQDB = 0
    self.Timeout = 0.1
    
    self.QInsertAmount = 10000
    self.QMax = 1000
    
    self.QInsertPeriod = 5
    
    self.q = queue.Queue()
    
    self.redisDB = None
    self.isRedisWork = False # False: use only local db
    
    self.configMgr = configMgr
    self.config = configMgr.getConfig()
    CustomLogging.setLogConfig(self.mainLogger, self.config)
    self.online = True
    
    self.load(sFilePath)
    self.update()
    self.online = False
    
    self.updaterKillFlag = False
    self.updater = threading.Thread(target=self.autoUpdate, daemon=True)
    self.updater.start()
  
  def load(self, sFilePath):
    urlQDBFD = open(sFilePath, "rt")
    self.logger.info("File Path: {}".format(sFilePath))
    
    while True:
      sBufIn = urlQDBFD.readline()
      if not sBufIn:
        urlQDBFD.close()
        break
      elif sBufIn[0] == '#' or sBufIn[0] == '\n':
        continue
      
      try:
        option, value = sBufIn.split()
      except ValueError:
        self.logger.warning("Wrong formated string: {}".format(sBufIn))
        continue
      
      try:
        curValue = self.__dict__[option]
      except KeyError:
        self.logger.warning("There's no option [{}]".format(option))
        continue
      else:
        pass
      
      if type(curValue) == int:
        value = int(value)
      
      if curValue != value:
        self.__dict__[option] = value
        self.logger.info("{}: {} > {}".format(option, curValue, value))
    
    self.redisDB = redis.Redis(host=self.HostIP,
                          port=self.Port,
                          db=self.URLQDB)
    try:
      if self.redisDB.ping():
        self.isRedisWork = True
      else:
        self.isRedisWork = False
        self.online = False
        self.logger.error("Redis DB Connection Failed")
    except redis.exceptions.ConnectionError:
      self.logger.error("Redis DB Connection Failed")
      self.isRedisWork = False
      self.online = False
    
    self.logger.info("Load Process Completed")
  
  def reviveUpdater(self):
    if not self.updater.is_alive():
      self.updater = threading.Thread(target=self.autoUpdate, daemon=True)
      self.updater.start()
  
  def killUpdater(self):
    self.updaterKillFlag = True
  
  def autoUpdate(self):
    while True:
      cnt = 0
      while cnt < self.QInsertPeriod:
        if self.updaterKillFlag:
          sys.exit(0)
          
        cnt += 1
        time.sleep(1)
      
      if self.q.qsize() <= self.QMax:
        self.update()
          
  def put(self, obj):
    if self.q.qsize() > self.QMax:
      self.online = True
    elif not self.isRedisWork:
      try:
        if not self.redisDB.dbsize():
          self.online = False
      except redis.exceptions.ConnectionError:
        self.logger.error("Redis DB Connection Failed")
        self.isRedisWork = False
        self.online = False
    
    if self.online:
      try:
        self.redisDB.rpush("URLQ", pickle.dumps(obj))
        return
      except redis.exceptions.ConnectionError:
        self.logger.error("Redis DB Connection Failed")
        self.isRedisWork = False
        self.online = False
        
    self.q.put(obj)

  def update(self):
    if not self.online or not self.isRedisWork:
      return False
    try:
      if not self.redisDB.dbsize():
        return True

      cnt = -1
      for i in range(self.QInsertAmount):
        data = self.redisDB.lpop('URLQ')
                
        if not data:
          self.online = False
          break
        
        self.q.put(pickle.loads(data))
        cnt = i
      if cnt > -1:
        self.logger.info(f"Update {cnt+1} URLs from DB")
    except redis.exceptions.ConnectionError:
      self.logger.error("Redis DB Connection Failed")
      self.isRedisWork = False
      self.online = False
      return False
    
    return True
    
  def exitQBackup(self):
    if not self.updaterKillFlag:
      return
    
    backup = []
    while self.q.qsize():
      backup.append(self.q.get())
    
    while backup:
      try:
        self.redisDB.lpush("URLQ", pickle.dumps(backup.pop()))
      except redis.exceptions.ConnectionError:
        break
  
  def empty(self):
    return self.q.empty() and not self.redisDB.dbsize()
  
  def qsize(self):
    return self.q.qsize()
  
  def forcePut(self, obj):
    return self.q.put(obj)
  
  def get(self):
    try:
      return self.q.get(timeout=1.0)
    except queue.Empty:
      return ("", self.config.MaxDepth+1)
  
  def changeConfig(self, config):
    self.config = config
    