import sys, os
import time
import multiprocessing
import multiprocessing.managers
import atexit

import crawler
from Config import Config, ConfigMgr


CONFIGPATH = "./config/linkbot.conf"

class MyManager(multiprocessing.managers.BaseManager):
  pass

MyManager.register("ConfigMgr", ConfigMgr)
MyManager.register("PipeMgr", crawler.PipeMgr)

def initConfig(manager):
  configMgr = manager.ConfigMgr(CONFIGPATH)
  return configMgr

def initDuplicationDB(manager, configMgr):
  mainConn, DBConn = multiprocessing.Pipe()
  maxProcess = configMgr.getConfig().MaxProcess
  duplicationDBPipes = manager.PipeMgr(maxProcess)
  # duplicationDB = multiprocessing.Process(name="DuplicationDB", target=)


if __name__=="__main__":
  # Linkbot Initialize
  # Shared Memory Manager Initialize
  manager = MyManager()
  manager.start()
  mainConnections = dict()
  
  # Settings Initialize
  configMgr = initConfig(manager)
  LogFilePath = configMgr.getConfig().LogFilePath
  sys.stderr = open(LogFilePath, "at")
  
  # Judge DB Initialize
  
  # Duplication DB Initialize
  initDuplicationDB()
  
  # Writer Initialize
  
  # Process Manager Initialize
  
  # Start URL Put
  
  # Process Start
  cnt = 0
  while cnt < 10:
    time.sleep(1)
    cnt +=1
  print("main process ended")