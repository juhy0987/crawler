import sys, atexit
import time
import threading
import multiprocessing.managers

import redis
import redis.exceptions

class DuplicationDB(object):
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
    print("[Duplication Load] File Path: {}".format(sFilePath), file=sys.stderr)
    
    while True:
      sBufIn = duplicateDBFD.readline()
      if not sBufIn:
        break
      elif sBufIn[0] == '#' or sBufIn[0] == '\n':
        continue
      
      try:
        option, value = sBufIn.split()
      except ValueError:
        print("[Dupliction Load] Wrong formated string: {}".format(sBufIn), file=sys.stderr)
        continue
      
      try:
        curValue = self.__dict__[option]
      except KeyError:
        print("[Duplication Load] There's no option [{}]".format(option), file=sys.stderr)
        continue
      else:
        pass
      
      if type(curValue) == int:
        value = int(value)
      
      if curValue != value:
        self.__dict__[option] = value
        print("[Duplication changed] {}: {} > {}".format(option, curValue, value), file=sys.stderr)
    
    self.redisDB = redis.Redis(host=self.HostIP,
                          port=self.Port,
                          db=self.DuplicationCheckDB)
    try:
      if self.redisDB.ping():
        self.isRedisWork = True
      else:
        self.isRedisWork = False
        print("[Duplication Load] Redis DB Connection Failed", file=sys.stderr)
    except redis.exceptions.ConnectionError:
      print("[Duplication Load] Redis DB Connection Failed", file=sys.stderr)
      self.isRedisWork = False
    
    print("[Duplication Load] Load Process Completed", file=sys.stderr)
    sys.stderr = self.config.applyLog(sys.stderr)

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
    
    return insertedTime
  
  def insert(self, sURL, insertTime):
    if self.isRedisWork and len(self.lru) >= self.MaxDBCache:
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
      if not url:
        print("[Duplication Insert] Wrong DB URL: {}".format(url), file=sys.stderr)
    
    try:
      self.redisDB.hset(url, "insertedTime", insertedTime)
    except redis.exceptions.ConnectionError:
      print("[Duplication Insert] DB not connected[{}:{}]".format(self.hostIP, self.port), file=sys.stderr)
      self.isRedisWork = False

      self.lru.append((url, insertedTime))
      self.db[url] = insertedTime
      
      return 1
    return None
  def clear(self):
    if self.redisDB.flushdb():
      print("[Duplication Clear] DB cleared", file=sys.stderr)
    else:
      print("[Duplication Clear] DB clear malfunctioned", file=sys.stderr)
    sys.stderr = self.config.applyLog(sys.stderr)

class DuplicationDBMgr(multiprocessing.managers.Namespace):
  def __init__(self, sFilePath, config):
    super().__init__()
    self.db = DuplicationDB()
    self.sFilePath = sFilePath
    
    self.db.config = config
    try:
      self.db.load(sFilePath)
    except (FileNotFoundError,TypeError,OSError) as e:
      print("[Duplication Init] There's no DB Config File [{}]".format(sFilePath), file=sys.stderr)
      print(str(e))
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

  def recovery(self):
    while True:
      time.sleep(self.db.DBRecoveryPeriod)
      if self.recoveryKillFlag:
        break
      
      if not self.db.isRedisWork and self.lock.acquire(block=True, timeout=10):
        try:
          self.db.load(self.sFilePath)
        except (FileNotFoundError,TypeError,OSError):
          print("[Duplication Recovery] There's no DB Config File [{}]".format(self.sFilePath), file=sys.stderr)
        except Exception as e:
          print(str(e), file=sys.stderr)
        
        while self.db.lru:
          self.db.updateRedis()
        self.lock.release()
        
      sys.stderr = self.db.config.applyLog(sys.stderr)
  
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
  
  def changePath(self, sFilePath):
    self.sFilePath = sFilePath

if __name__=="__main__":
  dbMgr = DuplicationDBMgr("./config/redisdb.conf")
  dbMgr.mutualCheck("www.naver.com")
  dbMgr.clear()
  