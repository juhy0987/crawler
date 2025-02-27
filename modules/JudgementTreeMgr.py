import sys
import time
import pickle
import subprocess
import multiprocessing
import multiprocessing.managers
import logging

from lib import URL
from lib import CustomLogging
from lib.URLTree import URLTree
from lib.RegexURLTree import RegexTree
from lib.query import oracQry

from . import ConfigMgr

class JudgementTree(object):
  mainLogger = logging.getLogger('Linkbot')
  logger = logging.getLogger('Linkbot.JudgementTree')
  
  def __init__(self):
    self.queryDict = dict()
    self.treeDict = dict()

    self.config = None
  
  def init(self):
    self.queryDict = oracQry.treeDict
    self.treeDict.clear()

  def lookupAll(self, sURL):
    for key in self.treeDict.keys():
      if not self.treeDict[key].lookupURL(sURL):
        return 0
    return -1
  
  def lookup(self, sURL, treeKeys):
    if not treeKeys:
      return -1
    
    for key in treeKeys:
      try:
        curTree = self.treeDict[key]
      except KeyError:
        continue
      
      if not curTree.lookupURL(sURL):
        return 0
    return -1
  
  def lookupDetail(self, sURL):
    result = []
    for key in self.treeDict.keys():
      if not self.treeDict[key].lookupURL(sURL):
        result.append(key)
    return result
  
  def updateAll(self):
    cnt = 0
    for key in self.queryDict.keys():
      if not self.update(key):
        self.logger.info("Tree [{}] Updated".format(key))
        cnt += 1
    
    self.logger.info("Update Completed, Success: {}, Failed: {}".format(cnt, len(self.queryDict)-cnt))
  
  def update(self, key):
    oracMgr = subprocess.Popen(["python", "./lib/oracMgr.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
      data, errMsg = oracMgr.communicate(self.queryDict[key][0].encode())
    except KeyError:
      oracMgr.terminate()
      return -1
    # print(errMsg.decode(), file=sys.stderr)
    conts = pickle.loads(data)
    
    # print(len(conts))
    
    if not len(conts):
      return -1
    
    match self.queryDict[key][1]:
      case 0:
        tmpTree = URLTree()
      case 1:
        tmpTree = RegexTree()
      case _:
        self.logger.error("Wrong Tree Type: {}".format(self.queryList[id][1]))
        return -1
  
    if tmpTree.load(conts) < 0:
      return -1

    self.treeDict[key] = tmpTree
    return 0


class JudgementTreeMgr(multiprocessing.managers.Namespace):
  def __init__(self, sFilePath, configMgr):
    super().__init__()
    self.judgementTree = JudgementTree()
    self.sFilePath = sFilePath
    self.configMgr = configMgr
    self.judgementTree.config = configMgr.getConfig()
    CustomLogging.setLogConfig(self.judgementTree.mainLogger, self.judgementTree.config)
    
    self.judgementTree.init()
    self.judgementTree.updateAll()
    
    self.updaterKillFlag = False
    self.conn, cConn = multiprocessing.Pipe()
    self.updater = multiprocessing.Process(target=self.update, args=(cConn,), daemon=True)
    self.updater.start()
  
  def lookupAll(self, sURL):
    if self.judgementTree.lookupAll(sURL) < 0:
      return -1
    return 0
  
  def lookup(self, sURL, treeKeys):
    return self.judgementTree.lookup(sURL, treeKeys)
  
  def lookupDetail(self, sURL):
    return self.judgementTree.lookupDetail(sURL)
  
  def reviveUpdater(self):
    if not self.updater.is_alive():
      try:
        self.conn.close()
      except:
        pass
      self.conn, cConn = multiprocessing.Pipe()
      self.updater = multiprocessing.Process(target=self.autoUpdate, args=(cConn,), daemon=True)
      self.updater.start()
  
  def killUpdater(self):
    self.updaterKillFlag = True
    try:
      self.conn.send("kill")
    except:
      pass
  
  def autoUpdate(self, conn):
    sys.stderr = CustomLogging.StreamToLogger(self.judgementTree.logger, logging.CRITICAL)
    while True:
      cnt = 0
      while cnt < self.judgementTree.config.DBUpdatePeriod:
        if self.updaterKillFlag:
          sys.exit(0)
          
        try:
          if conn.poll(0):
            data = conn.recv().split()
            match data[0]:
              case "config":
                match data[1]:
                  case "update":
                    self.judgementTree.config = self.configMgr.getConfig()
                    
                    # apply changed configuration
                    CustomLogging.setLogConfig(self.judgementTree.mainLogger, self.judgementTree.config)
                    self.judgementTree.logger.info("Configuration change applied")
                  case _:
                    pass
              case "kill":
                self.updaterKillFlag = True
              case  _:
                pass
        except BrokenPipeError:
          sys.exit(0)
        cnt += 1
        time.sleep(1)
      
      self.judgementTree.updateAll()
  
  def updateAll(self):
    return self.judgementTree.updateAll()
  
  def update(self, key):
    return self.judgementTree.update(key)
    
  def getUpdaterPID(self):
    if self.updater.is_alive():
      return self.updater.pid
    return -1
  
  def changeConfig(self):
    try:
      self.conn.send("config update")
    except:
      pass

if __name__=="__main__":
  import os
  try:
    os.remove("linkbot.pid")
  except:
    pass
  
  config = Config()
  config.load("./config/linkbot.conf")
  treeMgr = JudgementTreeMgr("./config/oracdb.conf", configMgr)
  
  while True:
    url = input("url >> ").split('\n')[0]
    if treeMgr.lookup(url) == 0:
      print("detected")
    else:
      print("Not detected")
