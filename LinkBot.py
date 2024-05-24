import sys, os
import time
import subprocess
import multiprocessing
import multiprocessing.managers
import atexit
import pickle
import signal
import logging
import psutil
import queue
import random

import modules
from lib import CustomLogging, procSig

CONFIGPATH = "./config/linkbot.conf"
ORACLEDB_CONFIGPATH = "./config/oracdb.conf"
DUPLICATIONDB_CONFIGPATH = "./config/redisdb.conf"

class MyManager(multiprocessing.managers.BaseManager):
  pass

MyManager.register("ConfigMgr", modules.ConfigMgr.ConfigMgr)
MyManager.register("CrawlerPIDMgr", modules.process.CrawlerPIDMgr)
MyManager.register("JudgementTreeMgr", modules.JudgementTreeMgr.JudgementTreeMgr)
MyManager.register("DuplicationDBMgr", modules.DuplicationDBMgr.DuplicationDBMgr)
MyManager.register("HostSemaphoreMgr", modules.HostSemaphoreMgr.HostSemaphoreMgr)
MyManager.register("KeywordMgr", modules.KeywordMgr.KeywordMgr)
MyManager.register("Queue", queue.Queue)

def manageProcess(logger, managers, commands, processMgr, urlQ, writerQ, config):
  toWriterConn, writerConn = multiprocessing.Pipe()
  writer = multiprocessing.Process(name="Writer",
                                   target=modules.process.writerProcess,
                                   args=("Writer", writerConn, managers[0], writerQ),
                                   daemon=True)
  writer.start()
  managers[1].setPid("Writer", writer.pid)
  
  cnt = 0
  resManageCnt = 0
  recentMemoryUsed = []
  try:
    while cnt < 5:
      if commands.qsize(): # exit signal check
        cmd = commands.get().split()
        
        match cmd[0]:
          case "x":
            break
          case _:
            pass
          
      # Resource Check
      try:
        # cpu_usage = 0
        memory_usage = 0
        
        allProcesses = psutil.process_iter(['pid', 'name', 'cmdline'])
        for proc in allProcesses:
          try:
            if proc.info['cmdline'] and ('LinkBot.py' in proc.info['cmdline'] or 'chrome' in proc.info['name']):
              p = psutil.Process(proc.info['pid'])
              # cpu_usage += p.cpu_percent(interval=1.0)
              memory_usage += p.memory_info().rss
          except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        
        if len(recentMemoryUsed) > 10:
          recentMemoryUsed.remove(recentMemoryUsed[0])
        recentMemoryUsed.append(memory_usage)
        
        if not resManageCnt:
          avg = 0
          for tmp in recentMemoryUsed:
            avg += tmp
          avg = avg / len(recentMemoryUsed) / psutil.virtual_memory().total
          
          logger.info(f"Memory Usage: {avg * 100:.2f} %")
          logger.info(f"URL Queue Size: {urlQ.qsize()}")
          logger.info(f"Current Running Children #: {len(processMgr.children)}")
          if avg > 0.8 or psutil.virtual_memory().free / psutil.virtual_memory().total < 0.02:
            if processMgr.maxProcess > config.MaxProcess // 2:
              processMgr.killProcess(random.choice(list(processMgr.children.keys())))
              processMgr.maxProcess -= 1
              logger.info(f"Decrease the Process #")
            else:
              break
          elif processMgr.maxProcess < config.MaxProcess and avg < 0.8 and psutil.virtual_memory().free / psutil.virtual_memory().total > 0.05:
            processMgr.maxProcess += 1
            logger.info(f"Increase the Process #")
            
      except (KeyError, OSError):
        pass
          
      # Dead Process Check
      deadlist = [] # check dead children + check heart beat from children
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
        
        pid = managers[1].getPid(id)
        if pid < 0:
          continue
        
        procSig.killFamilyByPID(pid)
      
      try: # kill all children with no parent
        allProcesses = psutil.process_iter(['pid', 'ppid', 'cmdline'])
        for proc in allProcesses:
          try:
            if proc.info['ppid'] == 1 and proc.info['cmdline'] and ('LinkBot.py' in proc.info['cmdline'] or 'chrome' in proc.info['cmdline']):
              subprocess.Popen(["kill", "-9", str(proc.info['pid'])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
          except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
      except (KeyError, OSError):
        pass
      
      # Revive Essential Managers
      if not psutil.pid_exists(managers[1].getPid("Writer")):
        writer = multiprocessing.Process(name="Writer",
                                    target=modules.process.writerProcess,
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
      
      # Check Update Flags
      if managers[0].getUpdateFlag():
        for id in processMgr.children.keys():
          conn = processMgr.getPipe(id)
          if conn:
            conn.send("config update")
        toWriterConn.send("config update")
        
        managers[0].setUpdateFlag(False)
        config = managers[0].getConfig()
        CustomLogging.setLogConfig(logger, config)
        
        managers[2].changeConfig()
        managers[3].changeConfig(config)
        managers[4].changeConfig(config)
        managers[5].changeConfig(config)
        processMgr.setMaxProcess(config.MaxProcess)
      
      if managers[5].getUpdateFlag():
        for id in processMgr.children.keys():
          conn = processMgr.getPipe(id)
          if conn:
            conn.send("keyword update")
        
        managers[5].setUpdateFlag(False)
      
      # Add process
      if urlQ.qsize():
        processMgr.addProcess(modules.process.process, (managers, urlQ, writerQ))
        
      # Rest
      if not len(processMgr.children):
        cnt += 1
      else:
        cnt = 0
      resManageCnt = (resManageCnt + 1) % 10
      time.sleep(3)
  except KeyboardInterrupt:
    pass
  except Exception as e:
    raise e
  finally:
    for id in processMgr.children.keys():
      processMgr.killProcess(id)
    crawlerKill(managers)
  
  print("end manageProcess")
  
  # Receive exit signal from main process
  try:
    while True:
      if commands.qsize():
        cmd = commands.get().split()
        
        match cmd[0]:
          case "f":
            break
          case _:
            pass
      time.sleep(1)
  except:
    pass
          
  time.sleep(3)
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
          url = url[:sharp]
        urlQ.put((url, 0))
    managers[3].clear()

def console(commands, managers, processMgr, urlQ, args):
  p = multiprocessing.Process(name="management", target=manageProcess, args=args)
  p.start()
  
  flag = False
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
                modules.process.showInfo()
                
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
                modules.process.showInfo()
                
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
                modules.process.showInfo()
              
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
                modules.process.showInfo()
                
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
                    modules.process.showInfo()
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
                    modules.process.showInfo()
              case letter if letter in ("number", "n"):
                print("Number of processes: {}".format(processMgr.getProcessNum()))
          
          case letter if letter in ("insert", "i"):
            urlQ.put(cmd[1])
          
          case letter if letter in ("help", "h"):
            modules.process.showInfo()
            
          case _:
            modules.process.showInfo()
      else:
        time.sleep(5)
      
      
      if not p.is_alive():
        if not urlQ.qsize():
          print("URL Q is empty.. restart after the period")
          time.sleep(managers[0].getConfig().LinkbotReworkPeriod)
          getStartURL(managers, urlQ, managers[0].getConfig())
        
        print("\n\n<<< Management Process Dead >>> revive the Management Process\n\n")
        p = multiprocessing.Process(name="management", target=manageProcess, args=args)
        p.start()
    except KeyboardInterrupt:
      break
    except (EOFError, OSError):
      print("Background mode")
      flag = False
    except (IndexError, ValueError):
      modules.process.showInfo()
  
  commands.put("x")
  
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

def initKeyword(manager, config):
  keywordMgr = manager.KeywordMgr(config)
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

def crawlerKill(managers):
  pidDict = managers[1].getPidDict()
  if pidDict:
    for key, pid in pidDict.items():
      procSig.killFamilyByPID(pid)
  
  # 혹시 몰라서.. (kill all chrome & chromedriver process)
  if sys.platform == 'win32':
    subprocess.Popen(["taskkill", "/t", "/f", "/im", "chromedriver.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  elif sys.platform == 'linux':
    subprocess.Popen(["killall", "-9", "chromedriver"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["killall", "-9", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ----------------- Emergency Handler ---------------- #

def exitProcessKill(managers):
  managers[0].killUpdater()
  managers[2].killUpdater()
  managers[3].killRecoverer()
  managers[4].killReleaser()
  managers[5].killUpdater()
  
  crawlerKill(managers)
  
  # p = subprocess.Popen(["taskkill", "/t", "/f", "/im", "chrome.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  # output, err = p.communicate()
  
def exitQBackup(q, BackupFilePath):
  backupList = []
  while q.qsize():
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

def exitQWrite(q, URLLogFilePath):
  dir = '/'.join(URLLogFilePath.split('/')[:-1])
  if dir and not os.path.exists(dir):
    os.makedirs(dir)
  
  try:
    with open(URLLogFilePath, "at") as fd:
      while q.qsize():
        fd.write(q.get() + '\n')
  except (FileNotFoundError, TypeError, OSError):
    pass

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
  atexit.register(exitProcessKill, managers)
  # managers[1].setPid("manager", managers[0].getManagerPID())
  
  # Judge DB Initiate
  managers.append(initJudgementTree(manager, managers[0])) # [2]: Tree
  # managers[1].setPid("treeMgr", managers[2].getUpdaterPID())
  
  # Duplication DB Initiate
  managers.append(initDuplicationDB(manager, config)) # [3]: Duplicate
  
  # Semephore Initiate
  managers.append(initHostSemephore(manager, config))
  
  # Keyword Initiate
  managers.append(initKeyword(manager, config))
  # managers[1].setPid("keywordMgr", managers[5].getUpdaterPID())
  
  # Data Queue Initiate
  writerQ = manager.Queue()
  urlQ = manager.Queue()
  commands = manager.Queue()
  
  atexit.register(exitQBackup, urlQ, config.BackupFilePath)
  atexit.register(exitQWrite, writerQ, config.URLLogFilePath)
  
  # Process Start
  processMgr = modules.ProcessMgr.ProcessMgr(config.MaxProcess)
  getStartURL(managers, urlQ, config)
  console(commands, managers, processMgr, urlQ, (logger, managers, commands, processMgr, urlQ, writerQ, config))
  
  print("Linkbot Terminated")
  
  exitQWrite(writerQ, config.URLLogFilePath)
  exitQBackup(urlQ, config.BackupFilePath)
  exitProcessKill(managers)
  
  commands.put("f")