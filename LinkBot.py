import sys, os
import time
import subprocess
import multiprocessing
import multiprocessing.managers
import atexit
import pickle
import signal

import lib
from Config import ConfigMgr
from JudgementTreeMgr import JudgementTreeMgr
from DuplicationDBMgr import DuplicationDBMgr
from HostSemephoreMgr import HostSemaphoreMgr
from KeywordMgr import KeywordMgr

CONFIGPATH = "./config/linkbot.conf"
ORACLEDB_CONFIGPATH = "./config/oracdb.conf"
DUPLICATIONDB_CONFIGPATH = "./config/redisdb.conf"

class MyManager(multiprocessing.managers.BaseManager):
  pass

MyManager.register("ConfigMgr", ConfigMgr)
MyManager.register("JudgementTreeMgr", JudgementTreeMgr)
MyManager.register("DuplicationDBMgr", DuplicationDBMgr)
MyManager.register("HostSemaphoreMgr", HostSemaphoreMgr)
MyManager.register("CrawlerPIDMgr", lib.CrawlerPIDMgr)
MyManager.register("KeywordMgr", KeywordMgr)

def initConfig(manager):
  configMgr = manager.ConfigMgr(CONFIGPATH)
  return configMgr

def initJudgementTree(manager, configMgr):
  # judgementTreeMgr = manager.JudgementTreeMgr(ORACLEDB_CONFIGPATH, configMgr)
  # return judgementTreeMgr
  return None

def initDuplicationDB(manager, config):
  duplicationDBMgr = manager.DuplicationDBMgr(DUPLICATIONDB_CONFIGPATH, config)
  return duplicationDBMgr

def initHostSemephore(manager, config):
  hostSemaphoreMgr = manager.HostSemaphoreMgr(config)
  return hostSemaphoreMgr

def initKeyword(manager, configMgr):
  # keywordMgr = manager.KeywordMgr(configMgr)
  # return keywordMgr
  return None

def writerProcess(id, chiefConn, configMgr, q):
  config = configMgr.getConfig()
  
  cnt = 0
  tStart = time.time()
  while True:
    if chiefConn.poll(0.01):
      data = chiefConn.recv()
      try:
        data = data.split()
        match data[0]:
          case "config":
            match data[1]:
              case "update":
                config = configMgr.getConfig()
              case _:
                pass
          case _:
            pass
      except Exception as e:
        print(str(e), file=sys.__stdout__)
    
    with open(config.URLLogFilePath, "at") as fd:
      while not q.empty():
        fd.write(q.get()+'\n')
        cnt += 1
      if cnt >= 1000:
        tEnd = time.time()
        fd.write("Elapsed time: {}\n".format(tEnd-tStart))
        fd.write("1000!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n\n\n\n")
        cnt = 0
    time.sleep(1)

def runMode1(config):
  return

def runMode2(config):
  return

def runMode3(config):
  startURL = []
  try:
    with open(config.URLFilePath, "rt") as f:
      while True:
        sBufIn = f.readline()
        if not sBufIn:
          break
        
        try:
          url, dummy = sBufIn.split()
        except ValueError:
          startURL.append(sBufIn)
  except (FileNotFoundError, OSError, TypeError):
    pass
  return startURL

# ----------------- Emergency Handler ---------------- #

def sigIntHanlder(signal, frame):
  print("KeyboardInterrupt", file=sys.stderr)
  sys.exit(0)

def emergencyProcessKill(crawlerPIDMgr):
  time.sleep(5)
  pidDict = crawlerPIDMgr.getPidDict()
  for key, pid in pidDict.items():
    if sys.platform == 'win32':
      p = subprocess.Popen(["taskkill", "/pid", str(pid), "/t", "/f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elif sys.platform == 'linux':
      p = subprocess.Popen(["pkill", "-9", "-P", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
      continue
    output, err = p.communicate()
    print("Linkbot killed children")
    # print(output.decode("cp949"))
    # print(err.decode('cp949'))
  
  if sys.platform == 'win32':
    p = subprocess.Popen(["taskkill", "/t", "/f", "/im", "chromedriver.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  elif sys.platform == 'linux':
    p = subprocess.Popen(["killall", "-9", "chromedriver"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p = subprocess.Popen(["killall", "-9", "chrome"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  output, err = p.communicate()
  # p = subprocess.Popen(["taskkill", "/t", "/f", "/im", "chrome.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  # output, err = p.communicate()
  
def emergencyQBackup(q, BackupFilePath):
  backupList = []
  while not q.empty():
    backupList.append(q.get())
  
  if backupList:
    try:
      with open(BackupFilePath, "wb") as fd:
        pickle.dump(backupList, fd)
    except (FileNotFoundError, TypeError, OSError):
      pass
  
  try:
    os.remove(config.PIDFilePath)
  except FileNotFoundError:
    pass

def emergencyQWrite(q, URLLogFilePath):
  try:
    with open(config.URLLogFilePath, "at") as fd:
      while not q.empty():
        fd.write(q.get() + '\n')
  except (FileNotFoundError, TypeError, OSError):
    pass

# --------------- Emergency Handler End ---------------- #

if __name__=="__main__":
  # Linkbot Initiate
  print("Linkbot Start")
  # Shared Memory Manager Initiate
  manager = MyManager()
  manager.start()
  managers = []
  
  # managers
  # 0: configuration manager
  # 1: selenium process emergency killer
  # 2: judgement tree maintain & update manager
  # 3: duplication url check lru manager
  # 4: url semaphore manager
  # 5: keyword update manager
  
  # Settings Initiate
  managers.append(initConfig(manager)) # [0]: config
  config = managers[0].getConfig()
  sys.stderr = open(config.LogFilePath, "at")
  
  # Process Killer Initiate
  managers.append(manager.CrawlerPIDMgr())
  atexit.register(emergencyProcessKill, managers[1])
  
  # Judge DB Initiate
  managers.append(initJudgementTree(manager, managers[0])) # [2]: Tree
  
  # Duplication DB Initiate
  managers.append(initDuplicationDB(manager, config)) # [3]: Duplicate
  
  # Semephore Initiate
  managers.append(initHostSemephore(manager, config))
  
  # Keyword Initiate
  managers.append(initKeyword(manager, managers[0]))
  
  # Writer Initialize
  writerQ = multiprocessing.Queue()
  toWriterConn, writerConn = multiprocessing.Pipe()
  writer = multiprocessing.Process(name="writer",
                                   target=writerProcess,
                                   args=("writer", writerConn, managers[0], writerQ),
                                   daemon=True)
  writer.start()
  
  # Process Manager Initiate
  urlQ = multiprocessing.Queue()
  processMgr = lib.ProcessMgr(config.MaxProcess)
  
  atexit.register(emergencyQBackup, urlQ, config.BackupFilePath)
  atexit.register(emergencyQWrite, writerQ, config.URLLogFilePath)
  
  signal.signal(signal.SIGINT, sigIntHanlder)
  
  # Start URL Put
  if os.path.isfile(config.BackupFilePath):
    try:
      fd = open(config.BackupFilePath, "rb")
    except (FileNotFoundError, TypeError, OSError):
      sys.exit(1)
    
    startURL = pickle.load(fd)
    fd.close()
    os.remove(config.BackupFilePath)
    
    for url, depth in startURL:
      if url[-1] == '/':
        url = url[:-1]
      urlQ.put((url, depth))
  else:
    match config.RunMode:
      case 0:
        startURL = config.StartURL
      case 1:
        pass # FROM DB
      case 3:
        startURL = runMode3(config)
      case _:
        print("[Linkbot Init] Wrong Mode: {}".format(config.RunMode), file=sys.stderr)
        sys.exit(1)
    
    if startURL:
      for url in startURL:
        sharp = url.find('#')
        if sharp > -1:
          url = url[:url.find('#')]
        if url[-1] == '/':
          url = url[:-1]
        urlQ.put((url, 0))
    managers[3].clear()
  
  # Process Start
  
  cnt = 0
  while cnt < 5:
    deadlist = []
    for id in processMgr.children.keys():
      if not processMgr.isProcessAlive(id):
        deadlist.append(id)
    for id in deadlist:
      processMgr.delProcess(id)
      processMgr.setUnusedNum(id)
      
      pid = managers[1].getPid(id)
      if pid < 0:
        continue
      
      if sys.platform == 'win32':
        p = subprocess.Popen(["taskkill", "/pid", str(pid), "/t", "/f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      elif sys.platform == 'linux':
        p = subprocess.Popen(["pkill", "-9", "-P", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      else:
        continue
      output, err = p.communicate()
    
    if not writer.is_alive():
      toWriterConn, writerConn = multiprocessing.Pipe()
      writer = multiprocessing.Process(name="writer",
                                  target=writerProcess,
                                  args=("writer", writerConn, managers[0], writerQ),
                                  daemon=True)
      writer.start()
      print("[Linkbot] Revived writer process", file=sys.stderr)
      sys.stderr = config.applyLog(sys.stderr)
    
    managers[0].reviveUpdater()
    managers[2].reviveUpdater()
    managers[3].reviveRecoverer()
    managers[5].reviveUpdater()
    
    managers[1].setPid("treeMgr", managers[2].getUpdaterPID())
    managers[1].setPid("keywordMgr", managers[5].getUpdaterPID())
      
    if managers[0].getUpdateFlag():
      for id, conn in processMgr.pipes.items():
        conn.send("config update")
      toWriterConn.send("config update")
      
      managers[0].setUpdateFlag(False)
      config = managers[0].getConfig()
      
      managers[2].changeConfig()
      managers[3].changeConfig(config)
      managers[4].changeConfig(config)
      managers[5].changeConfig()
      processMgr.setMaxProcess(config.MaxProcess)
    
    if managers[5].getUpdateFlag():
      for id, conn in processMgr.pipes.items():
        conn.send("keyword update")
    
    if len(processMgr.children) < config.MaxProcess and not urlQ.empty():
      processMgr.addProcess(lib.process, (managers, urlQ, writerQ))
      
    if not len(processMgr.children):
      cnt += 1
    else:
      cnt = 0
    time.sleep(1)
  
  print("Linkbot Terminated")
  os.remove(config.PIDFilePath)
