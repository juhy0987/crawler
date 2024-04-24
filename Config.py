import multiprocessing.managers
import sys, atexit
import time
import threading
import multiprocessing
import copy

class Config(object):
  def __init__ (self):
    self.LogFilePath = ""
    self.PIDFilePath = ""
    self.URLSignFilePath = ""
    self.KeywordPath = ""
    self.MsgLogFilePath = ""
    self.MsgLogTmpFilePath = ""
    self.AvailRate = 0
    
    # Linkbot Work Settings
    self.ConfigLoadPeriod = 30 * 60 # seconds
    self.qEmptyTimeoutLimit = 10
    
    # Start & End Settings
    self.MaxLogCount = 0
    self.StartTime = time.time()
    self.EndTime = 0.0
    
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

    self.URLDelay = dict()

    # RunMode 1
    self.DaysAgo = 0         # Filter urls by time
    self.GetURLCount = 0       # Max num of URL from DB(0: ALL)
    
    # Google Keyword Search(RunMode 2)
    self.GoogleKeyGID = 0
    self.GooglePref = ""
    
    # RunMode 3
    self.URLFilePath = ""
    self.URLFileURLCnt = 0
    
    # Keyword Check Option for StartURL
    # 0(False): Not Check
    # 1(True): Check
    self.CheckZeroDepth = False
    
    # Start URLs(RunMode 0)
    self.StartURL = []

  def load(self, sFilePath):
    configFD = open(sFilePath, "rt")
    print("[Config Load] File Path: {}".format(sFilePath), file=sys.stderr)
    
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
          if option == "URLDelay":
            try:
              self.__dict__[option][value] = int(dummy)  
            except ValueError:
              pass
            else:
              continue

        print("[Wrong Config Format] error string: {}".format(sBufIn), file=sys.stderr)
        continue
      
      if option in ["StartTime", "EndTime"]:
        continue
      
      try:
        curValue = self.__dict__[option]
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
          continue
        
        if curValue != value:
          self.__dict__[option] = value
          print("[Config changed] {}: {} > {}".format(option, curValue, value), file=sys.stderr)
      except KeyError:
        print("[Wrong Config Format] There's no option [{}]".format(option), file=sys.stderr)
        continue
    
    print("[Config Load] Load Process Completed", file=sys.stderr)

  def dump(self, sConfigDumpPath):
    fd = open(sConfigDumpPath, "wt")
    self.EndTime = time.time()
    
    for k, v in self.__dict__.items():
      fd.write("{} {}\n".format(k, v))
    fd.close()

class ConfigMgr(multiprocessing.managers.Namespace):
  def __init__(self, sFilePath):
    super().__init__()
    self.config = Config()
    self.sFilePath = sFilePath
    try:
      self.config.load(sFilePath)
    except FileNotFoundError|TypeError|OSError:
      print("[Config Init] There's no Config File [{}]".format(sFilePath), file=sys.stderr)
      sys.exit(1)
    
    sys.stderr = open(self.config.LogFilePath, "at")
    self.lock = multiprocessing.RLock()
    
    self.updaterKillFlag = False
    self.updater = threading.Thread(target=self.update, daemon=True)
    self.updater.start()
    
    atexit.register(self.dump, "./tmp.txt")
  
  def getConfig(self):
    if self.lock.acquire(block=False, timeout=3.0):
      tmp = copy.deepcopy(self.config)
      self.lock.release()
      return tmp
  
  def update(self):
    while True:
      time.sleep(self.config.ConfigLoadPeriod)
      if self.updaterKillFlag:
        break
      try:
        self.lock.acquire(block=True)
        self.config.load(self.sFilePath)
        self.lock.release()
      except FileNotFoundError|TypeError|OSError:
        print("[Config Update] There's no Config File [{}]".format(self.sFilePath), file=sys.stderr)
      except Exception as e:
        print(str(e), file=sys.stderr)
  
  def dump(self, sConfigDumpPath):
    self.updaterKillFlag = True
    self.config.dump(sConfigDumpPath)
    
  def changePath(self, sFilePath):
    self.sFilePath = sFilePath

if __name__=="__main__":
  configMgr = ConfigMgr("./config/linkbot.conf")
  # atexit.register(configMgr.dump, "./tmp.txt")
  cnt = 0
  while cnt < 10:
    time.sleep(1)
    cnt +=1
  print("main process ended")
  
  