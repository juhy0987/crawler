import sys, atexit, os
import time
import threading
import multiprocessing
import multiprocessing.managers
import copy
import logging

from lib import CustomLogging

class Config(object):
  mainLogger = logging.getLogger("Linkbot")
  logger = logging.getLogger("Linkbot.Config")
  
  def __init__ (self):
    self.pid = -1
    
    self.LogFilePath = ""
    self.PIDFilePath = ""
    self.URLSignFilePath = ""
    self.KeywordPath = ""
    self.URLLogFilePath = ""
    self.BackupFilePath = ""
    
    self.LogLevel = 0
    
    # Linkbot Work Settings
    self.ConfigLoadPeriod = 30 * 60 # seconds
    self.KeywordLoadPeriod = 30 * 60 # seconds
    self.DBUpdatePeriod = 30 * 60 # seconds
    self.RecoveryDeadlockPeriod = 20 # seconds
    self.qEmptyTimeoutLimit = 10.0 # seconds
    self.PageLoadTimeoutLimit = 1.5 # seconds
    self.LinkbotReworkPeriod = 10.0 # seconds
    
    # RunMode
    # 0: default mode(Start URL From Config)
    # 1: use black URL from database
    # 3: use url from file
    self.RunMode = 0
    
    # Start Options
    self.KeyGID = 0          # Keyword DB Column
    self.KeyWeightLimit = 0  # Critition for black judgement 
    self.URLKeyGID = 1       # URL DB Column
    self.MaxDepth = 1        # Traverse depth
    self.MaxProcess = 1      # Max num of child process
    self.MaxThread = 1       # Max num of threads in child process

    self.DefaultSemaphore = 10
    self.URLSemaphore = dict()

    # RunMode 1
    self.DaysAgo = 0         # Filter urls by time
    self.GetURLCount = 0       # Max num of URL from DB(0: ALL)
    
    # Keyword Search(RunMode 2)
    self.GoogleKeyGID = 0
    self.GooglePref = ""
    self.NaverPref =""
    
    # RunMode 3
    self.URLFilePath = ""
    self.URLFileURLCnt = 0
    
    # Keyword Check Option for StartURL
    # 0(False): Not Check
    # 1(True): Check
    self.CheckZeroDepth = False
    
    # Robot Check Option if URL can be crawled
    # 0(False): Not Check
    # 1(True): Check
    self.CheckRobot = False
    
    # Start URLs(RunMode 0)
    self.StartURL = []
    
    self.pidFlag = False
    self.updateToken = False
    
    self.changeList = []
    
    self.mainLogger.setLevel(logging.NOTSET)
    streamHandler = logging.StreamHandler()
    self.formatter = logging.Formatter('[%(name)s:%(funcName)s-%(processName)s][%(levelname)s] %(asctime)s - %(message)s')
    streamHandler.setFormatter(self.formatter)
    self.mainLogger.addHandler(streamHandler)

  def load(self, sFilePath):
    configFD = open(sFilePath, "rt", encoding='utf-8')
    self.logger.info("File Path: {}".format(sFilePath))
    self.changeList.clear()
    
    while True:
      sBufIn = configFD.readline()
      if not sBufIn:
        break
      elif sBufIn[0] == '#' or sBufIn[0] == '\n':
        continue
      
      try:
        option, value = sBufIn.split()
      except ValueError:
        try:
          option, value, dummy = sBufIn.split()
        except ValueError:
          pass
        else:
          if option == "URLSemaphore":
            try:
              self.__dict__[option][value] = int(dummy)  
            except ValueError:
              pass
            else:
              continue

        self.logger.warning("Wrong formated string: {}".format(sBufIn))
        continue
      
      if option in ["StartTime", "EndTime"]:
        continue
      
      try:
        curValue = self.__dict__[option]
      except KeyError:
        self.logger.warning("[Config Load] There's no option [{}]".format(option))
        continue
      else:
        pass
      
      if type(curValue) == int:
        value = int(value)
      elif type(curValue) == float:  
        value = float(value)
      elif type(curValue) == bool:
        if value == "0" or value == "False":
          value = False
        else:
          value = True
      elif type(curValue) == list:
        if not value in curValue:
          curValue.append(value)
          if not option in self.changeList:
            self.changeList.append(option)
        continue
      
      if curValue != value:
        if option == "LogFilePath":

          for handler in self.mainLogger.handlers:
            handler.close()
            self.mainLogger.removeHandler(handler)
          
          if value == "":
            streamHandler = logging.StreamHandler()
            self.mainLogger.addHandler(streamHandler)
          else:
            dir = '/'.join(value.split('/')[:-1])
            if dir and not os.path.exists(dir):
              os.makedirs(dir)

            fileHandler = logging.FileHandler(value)
            fileHandler.setFormatter(self.formatter)
            self.mainLogger.addHandler(fileHandler)
            
        elif option == "PIDFilePath":
          if self.pidFlag:
            continue
          
          if os.path.isfile(value):
            self.logger.error("Process is already working")
            sys.exit(1)

          dir = '/'.join(value.split('/')[:-1])
          if dir and not os.path.exists(dir):
            os.makedirs(dir)
            
          try:
            with open(value, "w") as fd:
              fd.write(str(self.pid)+'\n')
          except (FileNotFoundError,TypeError,OSError):
            self.logger.error("PID Path is wrong: {}".format(value))
            sys.exit(1)
          
          self.pidFlag = True
          
        elif option == "LogLevel":
          if not CustomLogging.setLoggerLevel(self.mainLogger, value):
            continue

        self.__dict__[option] = value
        self.changeList.append(option)
        self.logger.info("{}: {} > {}".format(option, curValue, value))
    
    self.logger.info("Load Process Completed")

  def dump(self, sConfigDumpPath):
    fd = open(sConfigDumpPath, "wt")
    self.EndTime = time.time()
    
    for k, v in self.__dict__.items():
      fd.write("{} {}\n".format(k, v))
    fd.close()
    try:
      os.remove(self.PIDFilePath)
    except FileNotFoundError:
      pass
  
  def getChildLogger(self, suffix):
    return self.mainLogger.getChild(suffix)
  
  

class ConfigMgr(multiprocessing.managers.Namespace):
  def __init__(self, sFilePath, pid):
    super().__init__()
    self.config = Config()
    self.sFilePath = sFilePath
    
    self.config.pid = pid
    try:
      self.config.load(sFilePath)
    except (FileNotFoundError,TypeError,OSError):
      self.config.logger.error("There's no Config File [{}]".format(sFilePath))
      sys.exit(1)
    
    sys.stderr = open(self.config.LogFilePath, "at")
    self.lock = multiprocessing.RLock()
    
    self.updaterKillFlag = False
    self.updateFlag = False
    self.updater = threading.Thread(target=self.autoUpdate, daemon=True)
    self.updater.start()
  
  def getConfig(self):
    if self.lock.acquire(block=True, timeout=3.0):
      tmp = copy.deepcopy(self.config)
      self.lock.release()
      return tmp
  
  def reviveUpdater(self):
    if not self.updater.is_alive():
      self.updater = threading.Thread(target=self.recovery, daemon=True)
      self.updater.start()
      return True
    return False
  
  def killUpdater(self):
    self.updaterKillFlag = True
  
  def autoUpdate(self):
    sys.stderr = CustomLogging.StreamToLogger(self.config.logger, logging.CRITICAL)
    while True:
      cnt = 0
      while cnt < self.config.ConfigLoadPeriod:
        if self.updaterKillFlag:
          sys.exit(0)
        
        cnt += 1
        time.sleep(1)
      
      if self.lock.acquire(block=True, timeout=10):
        try:
          self.config.load(self.sFilePath)
        except (FileNotFoundError,TypeError,OSError):
          self.config.logger.error("There's no Config File [{}]".format(self.sFilePath), file=sys.stderr)
        except Exception as e:
          raise e
        finally:
          self.lock.release()
        
        self.updateFlag = True
  
  def update(self):
    if self.lock.acquire(block=True, timeout=10):
      try:
        self.config.load(self.sFilePath)
      except (FileNotFoundError,TypeError,OSError):
        print("There's no Config File [{}]".format(self.sFilePath))
      except Exception as e:
        raise e
      finally:
        self.lock.release()
      
      self.updateFlag = True
  
  def get(self, option):
    try:
      return self.config.__dict__[option]
    except KeyError:
      return None
    
  def dump(self, sConfigDumpPath):
    self.updaterKillFlag = True
    self.config.dump(sConfigDumpPath)
    
  def changePath(self, sFilePath):
    self.sFilePath = sFilePath
  
  def getUpdateFlag(self):
    return self.updateFlag

  def setUpdateFlag(self, value):
    self.updateFlag = value
    
  def getManagerPID(self):
    return os.getpid()

if __name__=="__main__":
  configMgr = ConfigMgr("./config/linkbot.conf")
  # atexit.register(configMgr.dump, "./tmp.txt")
  cnt = 0
  while cnt < 10:
    time.sleep(1)
    cnt +=1
  print("main process ended")
  
  