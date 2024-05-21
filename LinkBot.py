import sys, os
import time
import subprocess
import threading
import multiprocessing
import multiprocessing.managers
import atexit
import pickle
import signal
import logging
import psutil

import lib
from Config import ConfigMgr
from JudgementTreeMgr import JudgementTreeMgr
from DuplicationDBMgr import DuplicationDBMgr
from HostSemephoreMgr import HostSemaphoreMgr
from KeywordMgr import KeywordMgr
from lib.process import writerProcess, showInfo
from modules import CustomLogging
from modules import procSig

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

def manageProcess(logger, managers, commands, processMgr, urlQ, writerQ, config):
  toWriterConn, writerConn = multiprocessing.Pipe()
  writer = multiprocessing.Process(name="Writer",
                                   target=writerProcess,
                                   args=("Writer", writerConn, managers[0], writerQ),
                                   daemon=True)
  writer.start()
  managers[1].setPid("Writer", writer.pid)
  
  sigInt = False
  cnt = 0
  resManageCnt = 0
  try:
    while cnt < 5:
      if not commands.empty():
        cmd = commands.get().split()
        
        match cmd[0]:
          case "x":
            sigInt = True
            break
          case _:
            pass
      deadlist = []
      for id in processMgr.children.keys():
        if not processMgr.checkProcess(id):
          deadlist.append(id)
          continue
        
        if processMgr.getLifeCnt(id) > 20:
          pid = processMgr.getProcess(id).pid
          if not processMgr.softKill[id]:
            logger.info("exit signal to child {}".format(id))
            os.kill(pid, signal.SIGINT)
            processMgr.softKill[id] = True
          else:
            logger.info("kill child {}".format(id))
            
            procSig.killByPID(pid)

          processMgr.initCnt(id)
        
        if not processMgr.isProcessAlive(id):
          deadlist.append(id)
      for id in deadlist:
        p = processMgr.getProcess(id)
        p.terminate()
        p.join()
        
        processMgr.delProcess(id)
        # curFDList = lib.getFDList()
        # for fType, fNum in processMgr.usedFD[id]:
        #   for fd, path in curFDList.items():
        #     if (fType, fNum) == path:
        #       try:
        #         os.close(fd)
        #       except OSError:
        #         pass
        processMgr.setUnusedNum(id)
        
        pid = managers[1].getPid(id)
        if pid < 0:
          continue
        
        procSig.killByPID(pid)
      
      try:
        allProcesses = psutil.process_iter(['pid', 'ppid', 'cmdline'])
        for proc in allProcesses:
          try:
            if proc.info['ppid'] == 1 and proc.info['cmdline'] and 'LinkBot.py' in proc.info['cmdline']:
              subprocess.Popen(["kill", "-9", str(proc.info['pid'])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
          except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
      except (KeyError, OSError):
        pass
      
      if not writer.is_alive():
        writer = multiprocessing.Process(name="Writer",
                                    target=writerProcess,
                                    args=("Writer", writerConn, managers[0], writerQ),
                                    daemon=True)
        writer.start()
        managers[1].setPid("Writer", writer.pid)
        logger.info("Revived writer")
      
      if managers[0].reviveUpdater():
        logger.info("Revived configuration updater")
      if managers[2].reviveUpdater():
        logger.info("Revived tree updater")
        managers[1].setPid("treeMgr", managers[2].getUpdaterPID())
      if managers[3].reviveRecoverer():
        logger.info("Revived Duplication exclude DB recoverer")
      if managers[4].reviveReleaser():
        logger.info("Revived Semaphore deadlock releaser")
      if managers[5].reviveUpdater():
        logger.info("Revived keyword updater")
        managers[1].setPid("keywordMgr", managers[5].getUpdaterPID())
      
      if managers[0].getUpdateFlag():
        for id, conn in processMgr.pipes.items():
          conn[0].send("config update")
        toWriterConn.send("config update")
        
        managers[0].setUpdateFlag(False)
        config = managers[0].getConfig()
        CustomLogging.setLogConfig(logger, config)
        
        managers[2].changeConfig()
        managers[3].changeConfig(config)
        managers[4].changeConfig(config)
        managers[5].changeConfig()
        processMgr.setMaxProcess(config.MaxProcess)
      
      if managers[5].getUpdateFlag():
        for id, conn in processMgr.pipes.items():
          conn[0].send("keyword update")
        
        managers[5].setUpdateFlag(False)
      
      if len(processMgr.children) < config.MaxProcess and not urlQ.empty():
        processMgr.addProcess(lib.process, (managers, urlQ, writerQ))
      
      if not resManageCnt:
        try:
          # cpu_usage = 0
          memory_usage = 0
          
          allProcesses = psutil.process_iter(['pid', 'cmdline'])
          for proc in allProcesses:
            try:
              if proc.info['cmdline'] and ('LinkBot.py' in proc.info['cmdline'] or 'chrome' in proc.info['cmdline']):
                p = psutil.Process(proc.info['pid'])
                # cpu_usage += p.cpu_percent(interval=1.0)
                memory_usage += p.memory_info().rss / 1024 / 1024
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
              pass
          
          logger.info(f"Memory Usage: {memory_usage:.2f} MB")
        except (KeyError, OSError):
          pass
      
      if not len(processMgr.children):
        cnt += 1
      else:
        cnt = 0
      resManageCnt = (resManageCnt + 1) % 10
      time.sleep(3)
  except KeyboardInterrupt:
    sigInt = True
    pass
  except Exception as e:
    raise e
    pass
  
  if not sigInt:
    os.kill(os.getppid(), signal.SIGINT)
  
  print("end manageProcess")
  
  time.sleep(10)
  os.kill(os.getppid(), signal.SIGINT)
  sys.exit(0)

def getStartURL(managers, urlQ, config):
  if os.path.isfile(config.BackupFilePath):
    try:
      with open(config.BackupFilePath, "rb") as fd:
        startURL = pickle.load(fd)
      os.remove(config.BackupFilePath)
    except (FileNotFoundError, TypeError, OSError):
      sys.exit(1)

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
        logger.error("Wrong Mode: {}".format(config.RunMode))
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

def console(commands, managers, processMgr, urlQ, args):
  p = multiprocessing.Process(name="management", target=manageProcess, args=args)
  p.start()
  
  flag = True
  while True:
    try:
      if flag:
        cmd = input("Linkbot >>> ")
        if not cmd:
          continue
        
        cmd = cmd.split()
        match cmd[0].lower():
          case letter if letter in ("exit", "x"):
            break
          
          case letter if letter in ("queue", "q"):
            print("queue size: {}".format(urlQ.qsize()))
            
          case letter if letter in ("config", "c"):
            match cmd[1].lower():
              case letter if letter in ("update", "u"):
                managers[0].update()
              case letter if letter in ("get", "g"):
                result = managers[0].get(cmd[2])
                if result is None:
                  print("No configuration option named [{}]".format(cmd[2]))
                else:
                  print("{}: {}".format(cmd[2], result))
              case _:
                showInfo()
                
          case letter if letter in ("tree", "t"):
            match cmd[1].lower():
              case letter if letter in ("update", "u"):
                try:
                  if not managers[2].update(cmd[2]):
                    print("Update Successful")
                  else:
                    print("Update Failed")
                except IndexError:
                  managers[2].updateAll()
              case letter if letter in ("lookup", "l"):
                result = managers[2].lookupDetail(cmd[2])
                if not result:
                  print("No matched")
                else:
                  print("Matched DBs:", result)
              case _:
                showInfo()
                
          case letter if letter in ("duplicate", "d"):
            if managers[3].lookup(cmd[1]):
              print('Passed')
            else:
              print('Not Passed')
              
          case letter if letter in ("lock", "l"):
            match cmd[1].lower():
              case letter if letter in ("url", "u"):
                result = managers[4].showURL(cmd[2])
                if not result:
                  print("No work for URL: [{}]".format(cmd[2]))
                else:
                  print("Currently using process:", result[1])
                  print("Left semaphore: {}".format(result[0]))
              case letter if letter in ("id", "i"):
                print("ID: {} - {}".format(cmd[2], managers[4].showID(int(cmd[2]))))
              case letter if letter in ("all", "a"):
                locker, left = managers[4].showAll()
                locker.sort()
                print("######### Locker #########")
                for id, url in locker:
                  print("ID: {} - {}".format(id, url))
                
                if left:
                  print("\n##### useless semaphore #####")
                  for url in left:
                    print(url)
              case _:
                showInfo()
              
          case letter if letter in ("keyword", "k"):
            match cmd[1].lower():
              case letter if letter in ("update", "u"):
                managers[5].update()
              case letter if letter in ("get", "g"):
                result = managers[5].get(cmd[2])
                if not result:
                  print("No matched keyword: {}".format(cmd[2]))
                  continue
                for key, weight in result:
                  print("Category type: {}, Weight: {}".format(key, weight))
              case _:
                showInfo()
                
          case letter if letter in ("process", "p"):
            match cmd[1].lower():
              case letter if letter in ("check", "c"):
                status = processMgr.showProcess(int(cmd[2]))
                if status is None:
                  print("ID: {} - Not allocated".format(cmd[2]))
                elif status:
                  print("ID: {} - alive({})".format(cmd[2], status[1]))
                else:
                  print("ID: {} - dead".format(cmd[2]))
              case letter if letter in ("show", "s"):
                try:
                  if not processMgr.showProcesses(cmd[2].lower()):
                    showInfo()
                except IndexError:
                  processMgr.showProcesses('all')
              case letter if letter in ("kill", "k"):
                match cmd[2].lower():
                  case "error":
                    pass
                  case "soft":
                    p = processMgr.getProcess(int(cmd[3]))
                    if p:
                      os.kill(p.pid, signal.SIGINT)
                    else:
                      print("No process :", cmd[3])
                  case "hard":
                    p = processMgr.getProcess(int(cmd[3]))
                    if p:
                      if sys.platform == 'win32':
                        p = subprocess.Popen(["taskkill", "/pid", str(p.pid), "/t", "/f"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                      elif sys.platform == 'linux':
                        p = subprocess.Popen(["pkill", "-9", "-P", str(p.pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                      else:
                        print("Not predefined OS")
                    else:
                      print("No process :", cmd[3])
                  case _:
                    showInfo()
              case letter if letter in ("number", "n"):
                print("Number of processes: {}".format(processMgr.getProcessNum()))
          
          case letter if letter in ("insert", "i"):
            urlQ.put(cmd[1])
          
          case letter if letter in ("help", "h"):
            showInfo()
            
          case _:
            showInfo()
      else:
        time.sleep(5)
      
      
      if not p.is_alive():
        print("\n\n<<< Management Process Dead >>> revive the Management Process\n\n")
        p = multiprocessing.Process(name="management", target=manageProcess, args=args)
        p.start()
    except KeyboardInterrupt:
      break
    except (EOFError, OSError):
      print("Background mode")
      flag = False
    except (IndexError, ValueError):
      showInfo()
  
  commands.put("x")
  for id, child in processMgr.children.items():
    try:
      os.kill(child.pid, signal.SIGINT)
    except ProcessLookupError:
      pass
  
  print("end console")

def initConfig(manager):
  configMgr = manager.ConfigMgr(CONFIGPATH, os.getpid())
  return configMgr

def initJudgementTree(manager, configMgr):
  judgementTreeMgr = manager.JudgementTreeMgr(ORACLEDB_CONFIGPATH, configMgr)
  return judgementTreeMgr
  # return None

def initDuplicationDB(manager, config):
  duplicationDBMgr = manager.DuplicationDBMgr(DUPLICATIONDB_CONFIGPATH, config)
  return duplicationDBMgr

def initHostSemephore(manager, config):
  hostSemaphoreMgr = manager.HostSemaphoreMgr(config)
  return hostSemaphoreMgr

def initKeyword(manager, configMgr):
  keywordMgr = manager.KeywordMgr(configMgr)
  return keywordMgr
  # return None

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

def emergencyProcessKill(managers):
  print("@@@@")
  managers[0].killUpdater()
  managers[2].killUpdater()
  managers[3].killRecoverer()
  managers[4].killReleaser()
  managers[5].killUpdater()
  print("!!!!")
  time.sleep(5)
  pidDict = managers[1].getPidDict()
  for key, pid in pidDict.items():
    procSig.killByPID(pid)
    
    # print(output.decode("cp949"))
    # print(err.decode('cp949'))
  
  if sys.platform == 'win32':
    p = subprocess.Popen(["taskkill", "/t", "/f", "/im", "chromedriver.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  elif sys.platform == 'linux':
    p = subprocess.Popen(["killall", "-9", "chromedriver"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p = subprocess.Popen(["killall", "-9", "chrome"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  output, err = p.communicate()

  print("Linkbot killed children")
  
  # p = subprocess.Popen(["taskkill", "/t", "/f", "/im", "chrome.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  # output, err = p.communicate()
  
def emergencyQBackup(q, BackupFilePath):
  print("^^^^^^")
  backupList = []
  while not q.empty():
    backupList.append(q.get())
  
  if backupList:
    dir = '/'.join(BackupFilePath.split('/')[:-1])
    if dir and not os.path.exists(dir):
      os.makedirs(dir)
    
    try:
      with open(BackupFilePath, "wb") as fd:
        pickle.dump(backupList, fd)
    except (FileNotFoundError, TypeError, OSError):
      pass
  print("&&&&&")

def emergencyQWrite(q, URLLogFilePath):
  print("#####")
  dir = '/'.join(URLLogFilePath.split('/')[:-1])
  if dir and not os.path.exists(dir):
    os.makedirs(dir)
  
  try:
    with open(URLLogFilePath, "at") as fd:
      while not q.empty():
        fd.write(q.get() + '\n')
  except (FileNotFoundError, TypeError, OSError):
    pass

  print("$$$$$$")

# --------------- Emergency Handler End ---------------- #

if __name__=="__main__":
  # Linkbot Initiate
  print("Linkbot Start")
  logger = logging.getLogger('Linkbot')
  sys.stderr = CustomLogging.StreamToLogger(logger, logging.CRITICAL)
  
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
  CustomLogging.setLogConfig(logger, config)
  atexit.register(os.remove, config.PIDFilePath)
  
  # Process Killer Initiate
  managers.append(manager.CrawlerPIDMgr())
  atexit.register(emergencyProcessKill, managers)
  managers[1].setPid("manager", managers[0].getManagerPID())
  
  # Judge DB Initiate
  managers.append(initJudgementTree(manager, managers[0])) # [2]: Tree
  managers[1].setPid("treeMgr", managers[2].getUpdaterPID())
  
  # Duplication DB Initiate
  managers.append(initDuplicationDB(manager, config)) # [3]: Duplicate
  
  # Semephore Initiate
  managers.append(initHostSemephore(manager, config))
  
  # Keyword Initiate
  managers.append(initKeyword(manager, managers[0]))
  managers[1].setPid("keywordMgr", managers[5].getUpdaterPID())
  
  # Data Queue Initiate
  writerQ = multiprocessing.Queue()
  urlQ = multiprocessing.Queue()
  commands = multiprocessing.Queue()
  
  atexit.register(emergencyQBackup, urlQ, config.BackupFilePath)
  atexit.register(emergencyQWrite, writerQ, config.URLLogFilePath)
  
  # Process Start
  processMgr = lib.ProcessMgr(config.MaxProcess)
  getStartURL(managers, urlQ, config)
  console(commands, managers, processMgr, urlQ, (logger, managers, commands, processMgr, urlQ, writerQ, config))
  print("Linkbot Terminated")