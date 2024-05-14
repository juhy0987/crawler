import sys, atexit
import time
import threading
import multiprocessing.managers
import logging

import redis
import redis.exceptions

from modules import CustomLogging

class DuplicationDB(object):
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.DuplicationDB')
  
  def __init__(self):
    self.HostIP = ""
    self.Port = 0
    self.DuplicationCheckDB = 0
    self.Timeout = 0.1
    
    self.MaxDBCache = 64
    
    self.DBRecoveryPeriod = 5
    
    self.db = dict()
    self.lru = []
    
    self.redisDB = None
    self.isRedisWork = False # False: use only local db
    
    self.config = None
  
  def load(self, sFilePath):
    duplicateDBFD = open(sFilePath, "rt")
    self.logger.info("File Path: {}".format(sFilePath))
    
    while True:
      sBufIn = duplicateDBFD.readline()
      if not sBufIn:
        duplicateDBFD.close()
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
                          db=self.DuplicationCheckDB)
    try:
      if self.redisDB.ping():
        self.isRedisWork = True
      else:
        self.isRedisWork = False
        self.logger.error("Redis DB Connection Failed")
    except redis.exceptions.ConnectionError:
      self.logger.error("Redis DB Connection Failed")
      self.isRedisWork = False
    
    self.logger.info("Load Process Completed")

  def lookup(self, sURL):
    insertedTime = None
    try:
      insertedTime = self.db[sURL]
    except KeyError:
      try:
        insertedTime = self.redisDB.hget(sURL, "insertedTime")
      except redis.exceptions.ConnectionError:
        self.isRedisWork = False
      
      if self.isRedisWork and insertedTime:
        self.insert(sURL, insertedTime)
    else:
      try:
        self.lru.remove(sURL)
      except ValueError:
        pass
      self.lru.insert(0, sURL)
    
    return insertedTime
  
  def insert(self, sURL, insertTime):
    while self.isRedisWork and len(self.lru) >= self.MaxDBCache:
      self.updateRedis()
      
    self.lru.insert(0, sURL)
    self.db[sURL] = insertTime
  
  def updateRedis(self):
    url = self.lru.pop()
    insertedTime = 0.0
    try:
      insertedTime = self.db[url]
      del(self.db[url])
    except KeyError:
      return None
    
    try:
      self.redisDB.hset(url, "insertedTime", insertedTime)
    except redis.exceptions.ConnectionError:
      self.logger.error("Redis DB Connection Failed")
      self.isRedisWork = False

      self.lru.append((url, insertedTime))
      self.db[url] = insertedTime
      
      return 1
    return None
  
  def delete(self, sURL):
    if not sURL:
      return -1
    
    try:
      del(self.db[sURL])
    except KeyError:
      pass
    
    try:
      self.lru.remove(sURL)
    except ValueError:
      pass
    
    try:
      self.redisDB.delete(sURL)
    except redis.exceptions.ConnectionError:
      self.logger.error("Redis DB Connection Failed")
      self.isRedisWork = False
      
    return 0
  
  def clear(self):
    if self.redisDB.flushdb():
      self.logger.info("DB cleared")
    else:
      self.logger.error("DB clear error")

class DuplicationDBMgr(multiprocessing.managers.Namespace):
  def __init__(self, sFilePath, config):
    super().__init__()
    self.db = DuplicationDB()
    self.sFilePath = sFilePath
    
    self.db.config = config
    CustomLogging.setLogConfig(self.db.mainLogger, self.db.config)
    try:
      self.db.load(sFilePath)
    except (FileNotFoundError,TypeError,OSError):
      self.db.logger.error("There's no DB Config File [{}]".format(sFilePath))
      sys.exit(1)
    
    self.lock = multiprocessing.RLock()
    
    self.recoveryKillFlag = False
    self.recoverer = threading.Thread(target=self.recovery, daemon=True)
    self.recoverer.start()
    
    atexit.register(self.storeDBbeforeExit)
    
  def mutualCheck(self, sURL):
    if self.lock.acquire(block=True, timeout=3.0):
      insertedTime = self.db.lookup(sURL)
      if not insertedTime:
        self.db.insert(sURL, time.time())
        
      self.lock.release()
      return insertedTime
  def lookup(self, sURL):
    if self.lock.acquire(block=True, timeout=3.0):
      insertedTime = self.db.lookup(sURL)
      self.lock.release()
      return insertedTime

  def reviveRecoverer(self):
    if not self.recoverer.is_alive():
      self.recoverer = threading.Thread(target=self.recovery, daemon=True)
      self.recoverer.start()
  
  def recovery(self):
    sys.stderr = CustomLogging.StreamToLogger(self.db.logger, logging.CRITICAL)
    while True:
      cnt = 0
      while cnt < self.db.DBRecoveryPeriod: 
        if self.recoveryKillFlag:
          sys.exit(0)
        cnt += 1
        time.sleep(1)
      
      try:
        if not self.db.isRedisWork and self.lock.acquire(block=True, timeout=10):
          self.db.load(self.sFilePath)
        
          while self.db.lru:
            self.db.updateRedis()
      except (FileNotFoundError,TypeError,OSError):
        self.db.logger.error("There's no DB Config File [{}]".format(self.sFilePath))
      finally:
        try:
          self.lock.release()
        except:
          pass
  
  def delete(self, sURL):
    if self.lock.acquire(block=True):
      try:
        return self.db.delete(sURL)
      finally:
        self.lock.release()
  
  def storeDBbeforeExit(self):
    self.recoveryKillFlag = True
    cnt = 0
    while cnt < 10 and self.db.lru:
      tmp = self.db.updateRedis()
      if tmp:
        time.sleep(0.1)
        cnt += 1
  
  def clear(self):
    self.db.clear()
  
  def changeConfig(self, config):
    if config:
      self.db.config = config
      CustomLogging.setLogConfig(self.db.mainLogger, self.db.config)
  
  def changePath(self, sFilePath):
    self.sFilePath = sFilePath

if __name__=="__main__":
  dbMgr = DuplicationDBMgr("./config/redisdb.conf")
  dbMgr.mutualCheck("www.naver.com")
  dbMgr.clear()
  