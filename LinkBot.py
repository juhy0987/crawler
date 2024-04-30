import sys, os
import time
import subprocess
import multiprocessing
import multiprocessing.managers
import atexit
import pickle

import lib
from Config import Config, ConfigMgr
from DuplicationDBMgr import DuplicationDB, DuplicationDBMgr

CONFIGPATH = "./config/linkbot.conf"
DUPLICATIONDB_CONFIGPATH = "./config/redisdb.conf"

class MyManager(multiprocessing.managers.BaseManager):
  pass

MyManager.register("ConfigMgr", ConfigMgr)
MyManager.register("DuplicationDBMgr", DuplicationDBMgr)
MyManager.register("PipeMgr", lib.PipeMgr)
MyManager.register("CrawlerPIDMgr", lib.CrawlerPIDMgr)

def initConfig(manager):
  configMgr = manager.ConfigMgr(CONFIGPATH)
  return configMgr

def initJudgementTree(manager, config):
  # judgementTreeMgr
  return None

def initDuplicationDB(manager, config):
  duplicationDBMgr = manager.DuplicationDBMgr(DUPLICATIONDB_CONFIGPATH, config)
  return duplicationDBMgr

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
          case "C":
            match data[1]:
              case "U":
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
        fd.write("stop!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n\n\n\n")
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

def emergencyProcessKill(crawlerPIDMgr):
  time.sleep(5)
  pidDict = crawlerPIDMgr.getPid()
  for key, pid in pidDict.items():
    p = subprocess.Popen(["taskkill", "/pid", str(pid), "/t", "/f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, err = p.communicate()
    # print(output.decode("cp949"))
    # print(err.decode('cp949'))
    
  # p = subprocess.Popen(["taskkill", "/t", "/f", "/im", "chrome.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  # output, err = p.communicate()
  
  # p = subprocess.Popen(["taskkill", "/t", "/f", "/im", "chromemanager.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  # output, err = p.communicate()

def emergencyQBackup(q, BackupFilePath):
  backupList = []
  while not q.empty():
    backupList.append(q.get())
  
  if backupList:
    try:
      fd = open(BackupFilePath, "wb")
    except (FileNotFoundError, TypeError, OSError):
      sys.exit(1)
    
    pickle.dump(backupList, fd)
    fd.close()
  try:
    os.remove(config.PIDFilePath)
  except FileNotFoundError:
    pass

def emergencyQWrite(q, URLLogFilePath):
  try:
    fd = open(config.URLLogFilePath, "at")
  except (FileNotFoundError, TypeError, OSError):
    sys.exit(1)
  
  while not q.empty():
    fd.write(q.get() + '\n')

# --------------- Emergency Handler End ---------------- #

if __name__=="__main__":
  # Linkbot Initialize
  print("Linkbot Start")
  # Shared Memory Manager Initialize
  manager = MyManager()
  manager.start()
  managers = []
  
  # Settings Initialize
  managers.append(initConfig(manager)) # [0]: config
  config = managers[0].getConfig()
  sys.stderr = open(config.LogFilePath, "at")
  # Judge DB Initialize
  managers.append(initJudgementTree(manager, config)) # [1]: Tree
  
  # Duplication DB Initialize
  managers.append(initDuplicationDB(manager, config)) # [2]: Duplicate
  
  # Process Killer Initalize
  managers.append(manager.CrawlerPIDMgr())
  atexit.register(emergencyProcessKill, managers[3])
  
  # Writer Initialize
  writerQ = multiprocessing.Queue()
  toWriterConn, writerConn = multiprocessing.Pipe()
  writer = multiprocessing.Process(name="writer",
                                   target=writerProcess,
                                   args=("writer", writerConn, managers[0], writerQ),
                                   daemon=True)
  writer.start()
  
  # Process Manager Initialize
  urlQ = multiprocessing.Queue()
  processMgr = lib.ProcessMgr(config.MaxProcess)
  
  atexit.register(emergencyQBackup, urlQ, config.BackupFilePath)
  atexit.register(emergencyQWrite, writerQ, config.URLLogFilePath)
  
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
    managers[2].clear()
  
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
    
    if not writer.is_alive():
      toWriterConn, writerConn = multiprocessing.Pipe()
      writer = multiprocessing.Process(name="writer",
                                  target=writerProcess,
                                  args=("writer", writerConn, managers[0], writerQ),
                                  daemon=True)
      writer.start()
      print("[Linkbot] Revived writer process", file=sys.stderr)
      config.applyLog(sys.stderr)
    
    managers[0].reviveUpdater()
    # managers[1].reviveUpdater()
    managers[2].reviveRecoverer()
      
    if managers[0].getUpdateFlag():
      for id, conn in processMgr.pipes.items():
        conn.send("C U")
      toWriterConn.send("C U")
      
      managers[0].setUpdateFlag(False)
      config = managers[0].getConfig()
      
      managers[2].changeConfig(config)
      processMgr.setMaxProcess(config.MaxProcess)
    
    if len(processMgr.children) < config.MaxProcess and not urlQ.empty():
      processMgr.addProcess(lib.process, (managers, urlQ, writerQ))
      
    if not len(processMgr.children):
      cnt += 1
    else:
      cnt = 0
    time.sleep(1)
  
  print("Linkbot Finished")
  os.remove(config.PIDFilePath)
